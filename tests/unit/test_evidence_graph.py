"""BE-010 unit tests: validation, compatibility, provenance, idempotency.

No database required: a small fake session implements just enough query
behavior (equality filters, OR groups, IN lists, pagination) to exercise
the real service and repository code paths.
"""

import uuid

import pytest

from backend.db.models import (
    GRAPH_NODE_TYPES,
    GRAPH_RELATIONSHIP_STATUSES,
    GRAPH_RELATIONSHIP_TYPES,
    Activity,
    Claim,
    DuplicateMatch,
    Evidence,
    GraphNode,
    GraphRelationship,
    Project,
)
from backend.repositories import evidence_graph as graph_repo
from backend.schemas import evidence_graph as graph_schemas
from backend.services import evidence_graph as graph_service


# ---------------------------------------------------------------------------
# Fake session
# ---------------------------------------------------------------------------


def _new_id() -> str:
    return str(uuid.uuid4())


class FakeQuery:
    def __init__(self, db, entities):
        self.db = db
        self.entities = entities
        self.filters: dict = {}
        self.or_groups: list[list[tuple[str, object]]] = []
        self._offset = 0
        self._limit: int | None = None

    def _capture(self, criterion) -> None:
        clauses = getattr(criterion, "clauses", None)
        if clauses is not None:  # or_(...) / and_(...) group
            group = []
            for clause in clauses:
                left = getattr(clause, "left", None)
                right = getattr(clause, "right", None)
                if getattr(left, "key", None) is not None:
                    group.append((left.key, getattr(right, "value", right)))
            if group:
                self.or_groups.append(group)
            return
        left = getattr(criterion, "left", None)
        right = getattr(criterion, "right", None)
        if getattr(left, "key", None) is not None:
            self.filters[left.key] = getattr(right, "value", right)

    def filter(self, *criteria):
        for criterion in criteria:
            self._capture(criterion)
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def offset(self, value):
        self._offset = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def count(self):
        return len(self._resolve_all())

    def all(self):
        rows = self._resolve_all()
        end = None if self._limit is None else self._offset + self._limit
        return rows[self._offset : end]

    def one_or_none(self):
        rows = self._resolve_all()
        return rows[0] if rows else None

    # -- resolution ----------------------------------------------------
    def _resolve_all(self):
        first = self.entities[0]
        if hasattr(first, "class_"):
            return self._resolve_attribute_select(first)
        if first is GraphNode:
            return self._resolve_nodes()
        if first is GraphRelationship:
            return self._resolve_relationships()
        return []

    def _resolve_attribute_select(self, attr):
        model = attr.class_
        if len(self.entities) > 1:
            # Project-map select: (id, project_id) with an IN filter.
            ids = self.filters.get("id", [])
            if isinstance(ids, str):
                ids = [ids]
            return [
                (entity_id, self.db.projects.get((model.__name__, str(entity_id))))
                for entity_id in ids
            ]
        ident = self.filters.get("id")
        if ident is not None and (model.__name__, str(ident)) in self.db.existing:
            return [object()]
        return []

    def _resolve_nodes(self):
        nodes = list(self.db.nodes.values())
        id_filter = self.filters.get("id")
        if isinstance(id_filter, (list, tuple, set)):
            wanted = {str(value) for value in id_filter}
            return [node for node in nodes if node.id in wanted]
        node_type = self.filters.get("node_type")
        entity_id = self.filters.get("entity_id")
        if node_type is not None and entity_id is not None:
            node = self.db.nodes.get((node_type, str(entity_id)))
            return [node] if node is not None else []
        return nodes

    def _resolve_relationships(self):
        rows = list(self.db.relationships)
        for key, value in self.filters.items():
            rows = [row for row in rows if str(getattr(row, key)) == str(value)]
        for group in self.or_groups:
            rows = [
                row
                for row in rows
                if any(str(getattr(row, key)) == str(value) for key, value in group)
            ]
        return rows


class FakeDB:
    """Minimal stand-in for a SQLAlchemy session."""

    def __init__(self):
        self.existing: set[tuple[str, str]] = set()  # (ModelName, entity_id)
        self.projects: dict[tuple[str, str], str | None] = {}
        self.nodes: dict[tuple[str, str], GraphNode] = {}
        self.relationships: list[GraphRelationship] = []
        self.commits = 0

    def add_entity(self, model, entity_id, project_id="unset"):
        self.existing.add((model.__name__, str(entity_id)))
        if project_id != "unset":
            self.projects[(model.__name__, str(entity_id))] = project_id

    def query(self, *entities):
        return FakeQuery(self, entities)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = _new_id()
        if isinstance(obj, GraphNode):
            self.nodes[(obj.node_type, str(obj.entity_id))] = obj
        elif isinstance(obj, GraphRelationship):
            self.relationships.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


def make_db() -> FakeDB:
    return FakeDB()


# ---------------------------------------------------------------------------
# Vocab / matrix / provenance (pure)
# ---------------------------------------------------------------------------


def test_schema_enums_match_service_vocabularies():
    assert {item.value for item in graph_schemas.NodeType} == set(GRAPH_NODE_TYPES)
    assert {item.value for item in graph_schemas.RelationshipType} == set(
        GRAPH_RELATIONSHIP_TYPES
    )
    assert {item.value for item in graph_schemas.RelationshipStatus} == set(
        GRAPH_RELATIONSHIP_STATUSES
    )
    assert {item.value for item in graph_schemas.NodeType} == graph_service.NODE_TYPES
    assert {item.value for item in graph_schemas.RelationshipType} == (
        graph_service.RELATIONSHIP_TYPES
    )


def test_response_schema_has_no_truth_or_score_fields():
    fields = set(graph_schemas.RelationshipResponse.model_fields)
    assert not (
        fields
        & {
            "truth_score",
            "fraud_probability",
            "authenticity_score",
            "compliance_score",
            "risk_score",
            "trust_score",
        }
    )


def test_dedupe_key_is_deterministic():
    key = graph_service.build_dedupe_key("s", "t", "SUPPORTS", "run-1")
    assert graph_service.build_dedupe_key("s", "t", "SUPPORTS", "run-1") == key
    assert graph_service.build_dedupe_key("s", "t", "SUPPORTS", "run-2") != key
    assert graph_service.build_dedupe_key("s", "t", "SUPPORTS", None) != key
    assert graph_service.build_dedupe_key("t", "s", "SUPPORTS", "run-1") != key


def test_provenance_validation():
    with pytest.raises(ValueError):
        graph_service.validate_provenance(None)
    with pytest.raises(ValueError):
        graph_service.validate_provenance({"method": "m"})
    with pytest.raises(ValueError):
        graph_service.validate_provenance({"source": "s", "method": "  "})
    with pytest.raises(ValueError):
        graph_service.validate_provenance(
            {"source": "s", "method": "m", "analysis_run_id": "nope"}
        )
    assert (
        graph_service.validate_provenance({"source": "s", "method": "m"})["method"] == "m"
    )


# ---------------------------------------------------------------------------
# Node identity
# ---------------------------------------------------------------------------


def test_node_identity_is_deterministic():
    db = make_db()
    evidence_id = _new_id()
    db.add_entity(Evidence, evidence_id)
    first = graph_service.resolve_node(db, "EVIDENCE", evidence_id)
    second = graph_service.resolve_node(db, "EVIDENCE", evidence_id)
    assert first is not None and second is not None
    assert first.id == second.id
    assert len(db.nodes) == 1


def test_resolve_node_rejects_bad_type_bad_uuid_and_missing_entity():
    db = make_db()
    with pytest.raises(ValueError):
        graph_service.resolve_node(db, "SPACESHIP", _new_id())
    with pytest.raises(ValueError):
        graph_service.resolve_node(db, "EVIDENCE", "not-a-uuid")
    with pytest.raises(LookupError):
        graph_service.resolve_node(db, "EVIDENCE", _new_id())


def test_read_path_never_creates_nodes():
    db = make_db()
    evidence_id = _new_id()
    db.add_entity(Evidence, evidence_id)
    assert graph_service.resolve_node(db, "EVIDENCE", evidence_id, create=False) is None
    assert len(db.nodes) == 0
    rows, total = graph_service.list_for_entity(db, "EVIDENCE", evidence_id)
    assert (rows, total) == ([], 0)
    assert len(db.nodes) == 0


# ---------------------------------------------------------------------------
# Relationship creation / compatibility / idempotency
# ---------------------------------------------------------------------------


def _evidence_claim_db() -> tuple[FakeDB, str, str]:
    db = make_db()
    evidence_id, claim_id = _new_id(), _new_id()
    db.add_entity(Evidence, evidence_id, project_id="proj-1")
    db.add_entity(Claim, claim_id, project_id="proj-1")
    return db, evidence_id, claim_id


def _supports_edge(db, evidence_id, claim_id, run=None):
    provenance: dict = {"source": "human_review", "method": "manual_link"}
    if run is not None:
        provenance["analysis_run_id"] = run
    return graph_service.create_relationship(
        db,
        source_type="EVIDENCE",
        source_id=evidence_id,
        target_type="CLAIM",
        target_id=claim_id,
        relationship_type="SUPPORTS",
        provenance=provenance,
        explanation="reviewer linked evidence to claim",
    )


def test_supports_edge_creation_and_idempotent_reassertion():
    db, evidence_id, claim_id = _evidence_claim_db()
    first, created = _supports_edge(db, evidence_id, claim_id)
    assert created is True
    assert first.relationship_status == "ACTIVE"
    assert first.provenance["source"] == "human_review"
    second, created_again = _supports_edge(db, evidence_id, claim_id)
    assert created_again is False
    assert second.id == first.id
    assert len(db.relationships) == 1


def test_distinct_runs_preserve_history():
    db, evidence_id, claim_id = _evidence_claim_db()
    first, _ = _supports_edge(db, evidence_id, claim_id, run=_new_id())
    second, created = _supports_edge(db, evidence_id, claim_id, run=_new_id())
    assert created is True
    assert second.id != first.id
    assert len(db.relationships) == 2


def test_incompatible_combination_is_rejected_without_writes():
    db, evidence_id, claim_id = _evidence_claim_db()
    detection_id = _new_id()
    db.add_entity(Project, _new_id())
    with pytest.raises(ValueError):
        graph_service.create_relationship(
            db,
            source_type="PROJECT",
            source_id=_new_id(),
            target_type="VISION_DETECTION",
            target_id=detection_id,
            relationship_type="SUPPORTS",
            provenance={"source": "x", "method": "y"},
        )
    with pytest.raises(ValueError):
        graph_service.create_relationship(
            db,
            source_type="EVIDENCE",
            source_id=evidence_id,
            target_type="CLAIM",
            target_id=claim_id,
            relationship_type="NOPE",
            provenance={"source": "x", "method": "y"},
        )
    assert len(db.relationships) == 0
    assert db.commits == 0


def test_self_loop_is_rejected():
    db = make_db()
    evidence_id = _new_id()
    db.add_entity(Evidence, evidence_id)
    with pytest.raises(ValueError):
        graph_service.create_relationship(
            db,
            source_type="EVIDENCE",
            source_id=evidence_id,
            target_type="EVIDENCE",
            target_id=evidence_id,
            relationship_type="DUPLICATE_OF",
            provenance={"source": "duplicate_intelligence", "method": "duplicate_detection"},
        )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_status_transitions_preserve_history():
    db, evidence_id, claim_id = _evidence_claim_db()
    rel, _ = _supports_edge(db, evidence_id, claim_id)
    assert len(db.relationships) == 1
    updated = graph_service.set_relationship_status(db, rel.id, "SUPERSEDED")
    assert updated.relationship_status == "SUPERSEDED"
    assert len(db.relationships) == 1  # status change, never delete
    with pytest.raises(ValueError):
        graph_service.set_relationship_status(db, rel.id, "ACTIVE")
    with pytest.raises(ValueError):
        graph_service.set_relationship_status(db, rel.id, "INVALIDATED")
    with pytest.raises(ValueError):
        graph_service.set_relationship_status(db, rel.id, "BOGUS")
    with pytest.raises(LookupError):
        graph_service.set_relationship_status(db, _new_id(), "SUPERSEDED")


def test_reassertion_after_supersede_creates_new_history_row():
    db, evidence_id, claim_id = _evidence_claim_db()
    rel, _ = _supports_edge(db, evidence_id, claim_id)
    graph_service.set_relationship_status(db, rel.id, "INVALIDATED")
    _, created = _supports_edge(db, evidence_id, claim_id)
    assert created is True
    assert len(db.relationships) == 2


# ---------------------------------------------------------------------------
# Traversal / direction / filters / project scope
# ---------------------------------------------------------------------------


def _seed_two_claims() -> tuple[FakeDB, str, str, str]:
    db = make_db()
    evidence_id, claim_a, claim_b = _new_id(), _new_id(), _new_id()
    db.add_entity(Evidence, evidence_id, project_id="proj-1")
    db.add_entity(Claim, claim_a, project_id="proj-1")
    db.add_entity(Claim, claim_b, project_id="proj-1")
    _supports_edge(db, evidence_id, claim_a)
    graph_service.create_relationship(
        db,
        source_type="EVIDENCE",
        source_id=evidence_id,
        target_type="CLAIM",
        target_id=claim_b,
        relationship_type="CONTRADICTS",
        provenance={"source": "human_review", "method": "manual_link"},
    )
    return db, evidence_id, claim_a, claim_b


def test_direction_filtering():
    db, evidence_id, claim_a, _ = _seed_two_claims()
    outgoing, total = graph_service.list_for_entity(db, "EVIDENCE", evidence_id, direction="outgoing")
    assert total == 2 and len(outgoing) == 2
    incoming, total = graph_service.list_for_entity(db, "CLAIM", claim_a, direction="incoming")
    assert total == 1
    empty, total = graph_service.list_for_entity(db, "CLAIM", claim_a, direction="outgoing")
    assert (empty, total) == ([], 0)
    both, total = graph_service.list_for_entity(db, "CLAIM", claim_a, direction="both")
    assert total == 1 and len(both) == 1
    with pytest.raises(ValueError):
        graph_service.list_for_entity(db, "EVIDENCE", evidence_id, direction="sideways")


def test_type_and_status_filters_and_pagination():
    db, evidence_id, _, _ = _seed_two_claims()
    supports, total = graph_service.list_for_entity(
        db, "EVIDENCE", evidence_id, relationship_type="SUPPORTS"
    )
    assert total == 1 and supports[0].relationship_type == "SUPPORTS"
    page, total = graph_service.list_for_entity(db, "EVIDENCE", evidence_id, limit=1, offset=1)
    assert total == 2 and len(page) == 1
    active, total = graph_service.list_for_entity(
        db, "EVIDENCE", evidence_id, relationship_status="ACTIVE"
    )
    assert total == 2
    graph_service.set_relationship_status(db, supports[0].id, "SUPERSEDED")
    active, _ = graph_service.list_for_entity(
        db, "EVIDENCE", evidence_id, relationship_status="ACTIVE"
    )
    assert len(active) == 1
    with pytest.raises(ValueError):
        graph_service.list_for_entity(db, "EVIDENCE", evidence_id, relationship_type="BOGUS")


def test_project_scope_filtering():
    db = make_db()
    proj_a, proj_b, proj_z = _new_id(), _new_id(), _new_id()
    evidence_a, evidence_b = _new_id(), _new_id()
    db.add_entity(Evidence, evidence_a, project_id=proj_a)
    db.add_entity(Evidence, evidence_b, project_id=proj_b)
    run = _new_id()
    graph_service.create_relationship(
        db,
        source_type="EVIDENCE",
        source_id=evidence_a,
        target_type="EVIDENCE",
        target_id=evidence_b,
        relationship_type="DUPLICATE_OF",
        provenance={
            "source": "duplicate_intelligence",
            "method": "duplicate_detection",
            "analysis_run_id": run,
        },
    )
    # Cross-project edge is representable without changing ownership ...
    rows, total = graph_service.list_for_entity(db, "EVIDENCE", evidence_a)
    assert total == 1
    # ... but strict project-local scope hides it from either side: a
    # single-project query never leaks another project's entities merely
    # because an edge exists. Cross-project signals surface in unscoped
    # traversal (BE-015 authorization will gate that path).
    scoped, _ = graph_service.list_for_entity(db, "EVIDENCE", evidence_a, project_id=proj_a)
    assert scoped == []
    scoped_b, _ = graph_service.list_for_entity(db, "EVIDENCE", evidence_b, project_id=proj_b)
    assert scoped_b == []
    # ... and hidden under an unrelated project scope.
    hidden, _ = graph_service.list_for_entity(db, "EVIDENCE", evidence_a, project_id=proj_z)
    assert hidden == []


def test_project_scope_keeps_fully_local_edges():
    db = make_db()
    proj = _new_id()
    evidence_id, claim_id = _new_id(), _new_id()
    db.add_entity(Evidence, evidence_id, project_id=proj)
    db.add_entity(Claim, claim_id, project_id=proj)
    _supports_edge(db, evidence_id, claim_id)
    scoped, total = graph_service.list_for_entity(
        db, "EVIDENCE", evidence_id, project_id=proj
    )
    assert total == 1 and len(scoped) == 1


# ---------------------------------------------------------------------------
# Analytical recorders (consume outputs, never recalculate)
# ---------------------------------------------------------------------------


def test_record_duplicate_requires_real_match_row():
    db = make_db()
    with pytest.raises(LookupError):
        graph_service.record_duplicate_relationship(db, _new_id())


def test_record_temporal_refuses_unknown_verdicts():
    db = make_db()
    with pytest.raises(ValueError):
        graph_service.record_temporal_relationship(
            db, {"evidence_a": _new_id(), "evidence_b": _new_id(), "relationship": "UNKNOWN"}
        )
    with pytest.raises(ValueError):
        graph_service.record_temporal_relationship(db, "not-a-mapping")  # type: ignore[arg-type]


def test_record_vision_and_has_analysis_validate_ownership():
    db = make_db()
    with pytest.raises(LookupError):
        graph_service.record_vision_relationship(db, _new_id())
    with pytest.raises(LookupError):
        graph_service.record_has_analysis(db, _new_id(), _new_id())


def test_repository_query_orders_and_paginates():
    db, evidence_id, _, _ = _seed_two_claims()
    node = graph_repo.get_node(db, "EVIDENCE", evidence_id)
    assert node is not None
    query = graph_repo.query_for_node(db, node.id, direction="both", relationship_type=None, relationship_status=None)
    assert query.count() == 2
    assert len(query.offset(1).limit(1).all()) == 1
