"""BE-010 Evidence Graph service: typed nodes/edges, provenance, lifecycle.

The graph records relationships between existing domain and intelligence
objects. It never determines truth, fraud, authenticity, risk, or
compliance, and it never recalculates analytical similarity — BE-006,
BE-008, and BE-009 remain the sources of their outputs; this layer only
references them with provenance.

Conventions (mirroring existing services):
- ``ValueError``: invalid type, incompatible edge, bad provenance, bad transition.
- ``LookupError``: referenced entity/row does not exist.
- Mutating operations commit; failures raise before any write.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    GRAPH_NODE_TYPES,
    GRAPH_RELATIONSHIP_STATUSES,
    GRAPH_RELATIONSHIP_TYPES,
    Activity,
    AnalysisJob,
    AnalysisResult,
    Claim,
    DuplicateMatch,
    Evidence,
    GraphNode,
    GraphRelationship,
    Project,
    VisionDetection,
)
from backend.repositories import evidence_graph as graph_repo
from backend.services import audit_ledger as audit_service


logger = logging.getLogger(__name__)

NODE_TYPES = frozenset(GRAPH_NODE_TYPES)
RELATIONSHIP_TYPES = frozenset(GRAPH_RELATIONSHIP_TYPES)
STATUSES = frozenset(GRAPH_RELATIONSHIP_STATUSES)
DIRECTIONS = frozenset({"outgoing", "incoming", "both"})

_ENTITY_MODELS = {
    "PROJECT": Project,
    "ACTIVITY": Activity,
    "CLAIM": Claim,
    "EVIDENCE": Evidence,
    "ANALYSIS_RESULT": AnalysisResult,
    "VISION_DETECTION": VisionDetection,
    "DUPLICATE_MATCH": DuplicateMatch,
}

# Deliberate compatibility matrix: (source_type, relationship_type, target_type).
# Anything not listed is rejected — arbitrary edges are never accepted.
COMPATIBILITY: frozenset[tuple[str, str, str]] = frozenset(
    {
        ("EVIDENCE", "SUPPORTS", "CLAIM"),
        ("EVIDENCE", "CONTRADICTS", "CLAIM"),
        ("EVIDENCE", "ASSOCIATED_WITH", "CLAIM"),
        ("EVIDENCE", "RELATES_TO_CLAIM", "CLAIM"),
        ("EVIDENCE", "DUPLICATE_OF", "EVIDENCE"),
        ("EVIDENCE", "TEMPORALLY_RELATED_TO", "EVIDENCE"),
        ("EVIDENCE", "ASSOCIATED_WITH", "EVIDENCE"),
        ("EVIDENCE", "BELONGS_TO", "PROJECT"),
        ("PROJECT", "CONTAINS_ACTIVITY", "ACTIVITY"),
        ("CLAIM", "ASSOCIATED_WITH", "ACTIVITY"),
        ("ACTIVITY", "ASSOCIATED_WITH", "CLAIM"),
        ("EVIDENCE", "HAS_ANALYSIS", "ANALYSIS_RESULT"),
        ("ANALYSIS_RESULT", "HAS_DETECTION", "VISION_DETECTION"),
        ("ANALYSIS_RESULT", "DERIVED_FROM", "EVIDENCE"),
        ("VISION_DETECTION", "DERIVED_FROM", "ANALYSIS_RESULT"),
        ("DUPLICATE_MATCH", "DERIVED_FROM", "EVIDENCE"),
        # BE-021 evidence version lineage (§9): a new evidence version derived
        # from a corrected original. The edge direction is NEW → OLD.
        ("EVIDENCE", "DERIVED_FROM", "EVIDENCE"),
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def build_dedupe_key(
    source_node_id: str, target_node_id: str, relationship_type: str, analysis_run_id: str | None
) -> str:
    """Deterministic idempotency key: same run + edge ⇒ same key."""
    return f"{source_node_id}|{target_node_id}|{relationship_type}|{analysis_run_id or '-'}"


def validate_provenance(provenance: dict | None) -> dict:
    """Provenance must identify source and method; never invented here."""
    if not isinstance(provenance, dict):
        raise ValueError("Provenance must be an object with 'source' and 'method'")
    source = provenance.get("source")
    method = provenance.get("method")
    if not source or not str(source).strip():
        raise ValueError("Provenance 'source' is required")
    if not method or not str(method).strip():
        raise ValueError("Provenance 'method' is required")
    run_id = provenance.get("analysis_run_id")
    if run_id is not None:
        _require_uuid(run_id, "analysis_run_id")
    return provenance


def resolve_node(
    db: Session, node_type: str, entity_id: str, *, create: bool = True
) -> GraphNode | None:
    """Validate and resolve ``(node_type, entity_id)`` to its graph node.

    The underlying entity must exist — nodes never reference missing rows.
    With ``create=False`` (reads) no node is created; returns None instead.
    """
    if node_type not in NODE_TYPES:
        raise ValueError(f"Unknown node type: {node_type!r}")
    entity_id = _require_uuid(entity_id, "entity_id")
    model = _ENTITY_MODELS[node_type]
    exists = db.query(model.id).filter(model.id == entity_id).one_or_none() is not None
    if not exists:
        raise LookupError(f"{node_type} entity not found: {entity_id}")
    if not create:
        return graph_repo.get_node(db, node_type, entity_id)
    node, _ = graph_repo.get_or_create_node(db, node_type, entity_id)
    return node


def create_relationship(
    db: Session,
    *,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relationship_type: str,
    provenance: dict,
    explanation: str | None = None,
) -> tuple[GraphRelationship, bool]:
    """Create an edge; same active edge ⇒ return existing (idempotent).

    Returns ``(relationship, created)``. History is preserved: different
    analysis runs produce distinct rows; only the same run re-assertion
    collapses to the existing ACTIVE row.
    """
    if relationship_type not in RELATIONSHIP_TYPES:
        raise ValueError(f"Unknown relationship type: {relationship_type!r}")
    if (source_type, relationship_type, target_type) not in COMPATIBILITY:
        raise ValueError(
            f"Incompatible relationship: {source_type} -[{relationship_type}]-> {target_type}"
        )
    provenance = validate_provenance(provenance)
    try:
        source_node = resolve_node(db, source_type, source_id)
        target_node = resolve_node(db, target_type, target_id)
    except IntegrityError:
        # Concurrent writer created the node first: roll back and re-read it.
        db.rollback()
        source_node = resolve_node(db, source_type, source_id)
        target_node = resolve_node(db, target_type, target_id)
    assert source_node is not None and target_node is not None
    if source_node.id == target_node.id:
        raise ValueError("Self-loop relationships are not allowed")

    run_id = provenance.get("analysis_run_id")
    run_id = str(UUID(str(run_id))) if run_id is not None else None
    dedupe_key = build_dedupe_key(source_node.id, target_node.id, relationship_type, run_id)
    existing = graph_repo.find_active_by_dedupe(db, dedupe_key)
    if existing is not None:
        return existing, False

    try:
        relationship = graph_repo.insert_relationship(
            db,
            source_node_id=source_node.id,
            target_node_id=target_node.id,
            relationship_type=relationship_type,
            dedupe_key=dedupe_key,
            analysis_run_id=run_id,
            method=str(provenance.get("method")),
            method_version=provenance.get("method_version"),
            provenance={**provenance, "created_at": utc_now().isoformat()},
            explanation=explanation,
        )
        audit_service.append_event(
            db,
            event_type="GRAPH_RELATIONSHIP_CREATED",
            action="create",
            resource_type="graph_relationships",
            resource_id=relationship.id,
            actor_id=None,
            project_id=None,
            payload={"graph_relationship_id": relationship.id,
                     "relationship_type": relationship_type,
                     "source": {"node_type": source_type, "entity_id": source_id},
                     "target": {"node_type": target_type, "entity_id": target_id}},
            source="evidence_graph_service",
        )
        db.commit()
    except IntegrityError:
        # Lost a concurrent insert race on the partial-unique dedupe key:
        # the winner is the canonical row — return it idempotently.
        db.rollback()
        existing = graph_repo.find_active_by_dedupe(db, dedupe_key)
        if existing is not None:
            return existing, False
        raise
    db.refresh(relationship)
    logger.info(
        "graph relationship created type=%s source=%s:%s target=%s:%s",
        relationship_type,
        source_type,
        source_id,
        target_type,
        target_id,
    )
    return relationship, True


def set_relationship_status(
    db: Session, relationship_id: str, new_status: str
) -> GraphRelationship:
    """Transition ACTIVE → SUPERSEDED/INVALIDATED (history-preserving)."""
    relationship_id = _require_uuid(relationship_id, "relationship_id")
    if new_status not in STATUSES:
        raise ValueError(f"Unknown relationship status: {new_status!r}")
    relationship = graph_repo.get_relationship(db, relationship_id)
    if relationship is None:
        raise LookupError(f"Graph relationship not found: {relationship_id}")
    if relationship.relationship_status != "ACTIVE":
        raise ValueError(
            f"Only ACTIVE relationships can transition (current: {relationship.relationship_status})"
        )
    if new_status == "ACTIVE":
        raise ValueError("Relationship is already ACTIVE")
    relationship.relationship_status = new_status
    audit_service.append_event(
        db,
        event_type=(
            "GRAPH_RELATIONSHIP_SUPERSEDED"
            if new_status == "SUPERSEDED"
            else "GRAPH_RELATIONSHIP_INVALIDATED"
        ),
        action="transition",
        resource_type="graph_relationships",
        resource_id=relationship.id,
        actor_id=None,
        project_id=None,
        payload={"graph_relationship_id": relationship.id,
                 "relationship_type": relationship.relationship_type,
                 "from_status": "ACTIVE", "to_status": new_status},
        source="evidence_graph_service",
    )
    db.commit()
    db.refresh(relationship)
    return relationship


def _node_project_map(db: Session, nodes: list[GraphNode]) -> dict[str, str | None]:
    """Bulk-resolve each node's owning project (one query per node type)."""
    by_type: dict[str, list[str]] = {}
    for node in nodes:
        by_type.setdefault(node.node_type, []).append(node.entity_id)
    entity_project: dict[tuple[str, str], str | None] = {}
    for node_type, entity_ids in by_type.items():
        if node_type == "PROJECT":
            for entity_id in entity_ids:
                entity_project[(node_type, entity_id)] = entity_id
        elif node_type in {"ACTIVITY", "CLAIM", "EVIDENCE"}:
            model = _ENTITY_MODELS[node_type]
            rows = (
                db.query(model.id, model.project_id).filter(model.id.in_(entity_ids)).all()
            )
            for row in rows:
                entity_project[(node_type, str(row[0]))] = str(row[1]) if row[1] else None
        elif node_type == "ANALYSIS_RESULT":
            rows = (
                db.query(AnalysisResult.id, Evidence.project_id)
                .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
                .join(Evidence, Evidence.id == AnalysisJob.evidence_id)
                .filter(AnalysisResult.id.in_(entity_ids))
                .all()
            )
            for row in rows:
                entity_project[(node_type, str(row[0]))] = str(row[1]) if row[1] else None
        elif node_type == "VISION_DETECTION":
            rows = (
                db.query(VisionDetection.id, Evidence.project_id)
                .join(AnalysisResult, AnalysisResult.id == VisionDetection.analysis_result_id)
                .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
                .join(Evidence, Evidence.id == AnalysisJob.evidence_id)
                .filter(VisionDetection.id.in_(entity_ids))
                .all()
            )
            for row in rows:
                entity_project[(node_type, str(row[0]))] = str(row[1]) if row[1] else None
        elif node_type == "DUPLICATE_MATCH":
            rows = (
                db.query(DuplicateMatch.id, Evidence.project_id)
                .join(Evidence, Evidence.id == DuplicateMatch.evidence_id)
                .filter(DuplicateMatch.id.in_(entity_ids))
                .all()
            )
            for row in rows:
                entity_project[(node_type, str(row[0]))] = str(row[1]) if row[1] else None
    return {
        node.id: entity_project.get((node.node_type, node.entity_id)) for node in nodes
    }


def list_for_entity(
    db: Session,
    node_type: str,
    entity_id: str,
    *,
    direction: str = "both",
    relationship_type: str | None = None,
    relationship_status: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[GraphRelationship], int]:
    """One-hop traversal for an entity (reads never create nodes)."""
    if node_type not in NODE_TYPES:
        raise ValueError(f"Unknown node type: {node_type!r}")
    if direction not in DIRECTIONS:
        raise ValueError(f"Invalid direction: {direction!r}")
    if relationship_type is not None and relationship_type not in RELATIONSHIP_TYPES:
        raise ValueError(f"Unknown relationship type: {relationship_type!r}")
    if relationship_status is not None and relationship_status not in STATUSES:
        raise ValueError(f"Unknown relationship status: {relationship_status!r}")
    if limit < 1 or offset < 0:
        raise ValueError("Invalid pagination")
    if project_id is not None:
        project_id = _require_uuid(project_id, "project_id")

    node = resolve_node(db, node_type, entity_id, create=False)
    if node is None:
        return [], 0
    query = graph_repo.query_for_node(
        db,
        node.id,
        direction=direction,
        relationship_type=relationship_type,
        relationship_status=relationship_status,
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    if project_id is None or not rows:
        return rows, total

    involved = db.query(GraphNode).filter(
        GraphNode.id.in_({row.source_node_id for row in rows} | {row.target_node_id for row in rows})
    ).all()
    node_by_id = {item.id: item for item in involved}
    projects = _node_project_map(db, involved)
    # Strict project-local default: an edge is visible under a project scope
    # only when every endpoint with a known project belongs to it. Endpoints
    # whose project cannot be resolved do not exclude the edge. Cross-project
    # edges therefore surface only in unscoped traversal (which BE-015
    # authorization will gate), so one project's query never leaks another
    # project's entities merely because an edge exists.
    scoped = [
        row
        for row in rows
        if all(
            projects.get(endpoint_id) in (None, project_id)
            for endpoint_id in (row.source_node_id, row.target_node_id)
        )
        and node_by_id.get(row.source_node_id) is not None
        and node_by_id.get(row.target_node_id) is not None
    ]
    return scoped, total


# ---------------------------------------------------------------------------
# Analytical recorders: consume BE-006/BE-008/BE-009 outputs (never
# recalculate them). A failed analysis leaves no persisted output row, so
# these raise LookupError/ValueError instead of recording — a failed run
# can never produce a successful graph relationship.
# ---------------------------------------------------------------------------


def record_duplicate_relationship(
    db: Session, duplicate_match_id: str, *, analysis_run_id: str | None = None
) -> tuple[GraphRelationship, bool]:
    """EVIDENCE -[DUPLICATE_OF]-> EVIDENCE from a BE-006 DuplicateMatch row."""
    duplicate_match_id = _require_uuid(duplicate_match_id, "duplicate_match_id")
    match = db.query(DuplicateMatch).filter(DuplicateMatch.id == duplicate_match_id).one_or_none()
    if match is None:
        raise LookupError(f"DuplicateMatch not found: {duplicate_match_id}")
    provenance: dict = {
        "source": "duplicate_intelligence",
        "method": "duplicate_detection",
        "method_version": str((match.signals or {}).get("method_version", "be006")),
        "duplicate_match_id": match.id,
        "match_type": match.match_type,
    }
    if match.phash_distance is not None:
        provenance["phash_distance"] = match.phash_distance
    if match.embedding_similarity is not None:
        provenance["embedding_similarity"] = match.embedding_similarity
    if analysis_run_id is not None:
        provenance["analysis_run_id"] = _require_uuid(analysis_run_id, "analysis_run_id")
    first, second = sorted((match.evidence_id, match.matched_evidence_id))
    return create_relationship(
        db,
        source_type="EVIDENCE",
        source_id=first,
        target_type="EVIDENCE",
        target_id=second,
        relationship_type="DUPLICATE_OF",
        provenance=provenance,
        explanation="Relationship generated by BE-006 duplicate analysis.",
    )


def record_temporal_relationship(
    db: Session, pair: dict, *, analysis_run_id: str | None = None
) -> tuple[GraphRelationship, bool]:
    """EVIDENCE -[TEMPORALLY_RELATED_TO]-> EVIDENCE from a BE-008 pair verdict.

    ``pair`` is the output of ``compare_pair()``; UNKNOWN verdicts are
    refused — no relationship was established, so none is recorded.
    """
    if not isinstance(pair, dict):
        raise ValueError("Temporal pair verdict must be a mapping")
    relationship = pair.get("relationship")
    evidence_a = pair.get("evidence_a")
    evidence_b = pair.get("evidence_b")
    if relationship not in {"CAPTURED_BEFORE", "CAPTURED_AFTER", "SAME_TIME"}:
        raise ValueError("Temporal verdict is UNKNOWN: no relationship to record")
    provenance: dict = {
        "source": "temporal_intelligence",
        "method": "temporal_comparison",
        "method_version": "be008",
        "temporal_relationship": relationship,
    }
    if pair.get("reason"):
        provenance["reason"] = pair["reason"]
    if analysis_run_id is not None:
        provenance["analysis_run_id"] = _require_uuid(analysis_run_id, "analysis_run_id")
    return create_relationship(
        db,
        source_type="EVIDENCE",
        source_id=str(evidence_a),
        target_type="EVIDENCE",
        target_id=str(evidence_b),
        relationship_type="TEMPORALLY_RELATED_TO",
        provenance=provenance,
        explanation=f"BE-008 temporal ordering: {relationship}.",
    )


def record_vision_relationship(
    db: Session, vision_detection_id: str, *, analysis_run_id: str | None = None
) -> tuple[GraphRelationship, bool]:
    """ANALYSIS_RESULT -[HAS_DETECTION]-> VISION_DETECTION for a BE-009 row."""
    vision_detection_id = _require_uuid(vision_detection_id, "vision_detection_id")
    detection = (
        db.query(VisionDetection).filter(VisionDetection.id == vision_detection_id).one_or_none()
    )
    if detection is None:
        raise LookupError(f"VisionDetection not found: {vision_detection_id}")
    result = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.id == detection.analysis_result_id)
        .one_or_none()
    )
    if result is None:
        raise LookupError("Owning AnalysisResult not found for vision detection")
    payload = result.result if isinstance(result.result, dict) else {}
    model = payload.get("model", {}) if isinstance(payload.get("model"), dict) else {}
    provenance: dict = {
        "source": "vision_intelligence",
        "method": "yolo_detection",
        "method_version": str(model.get("name", "unknown")),
        "vision_detection_id": detection.id,
        "class_name": detection.class_name,
    }
    provenance["analysis_run_id"] = (
        _require_uuid(analysis_run_id, "analysis_run_id")
        if analysis_run_id is not None
        else result.job_id
    )
    return create_relationship(
        db,
        source_type="ANALYSIS_RESULT",
        source_id=result.id,
        target_type="VISION_DETECTION",
        target_id=detection.id,
        relationship_type="HAS_DETECTION",
        provenance=provenance,
        explanation="Relationship generated by BE-009 vision analysis.",
    )


def record_has_analysis(
    db: Session, evidence_id: str, analysis_result_id: str
) -> tuple[GraphRelationship, bool]:
    """EVIDENCE -[HAS_ANALYSIS]-> ANALYSIS_RESULT (result must belong to it)."""
    analysis_result_id = _require_uuid(analysis_result_id, "analysis_result_id")
    result = db.query(AnalysisResult).filter(AnalysisResult.id == analysis_result_id).one_or_none()
    if result is None:
        raise LookupError(f"AnalysisResult not found: {analysis_result_id}")
    job = db.query(AnalysisJob).filter(AnalysisJob.id == result.job_id).one_or_none()
    if job is None or str(job.evidence_id) != str(UUID(str(evidence_id))):
        raise ValueError("AnalysisResult does not belong to the given evidence")
    return create_relationship(
        db,
        source_type="EVIDENCE",
        source_id=str(evidence_id),
        target_type="ANALYSIS_RESULT",
        target_id=result.id,
        relationship_type="HAS_ANALYSIS",
        provenance={
            "source": "analysis_pipeline",
            "method": "analysis_completion",
            "method_version": job.job_type,
            "analysis_run_id": job.id,
        },
        explanation="Evidence was processed by the analysis pipeline.",
    )
