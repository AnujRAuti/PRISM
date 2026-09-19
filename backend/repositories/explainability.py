"""BE-012 explainability repository: retrieval and record persistence only.

Explanation content assembly lives in ``backend.services.explainability``.
"""

from sqlalchemy.orm import Session

from backend.db.models import (
    ExplanationRun,
    FusionConfiguration,
    FusionRun,
    FusionSignal,
    GraphNode,
    GraphRelationship,
    IntegrityAssessment,
    ReviewPriority,
)


def get_fusion_bundle(db: Session, run_id: str):
    """Run + signals + ACTIVE assessment + priority for one fusion execution."""
    run = db.query(FusionRun).filter(FusionRun.id == run_id).one_or_none()
    if run is None:
        return None
    signals = (
        db.query(FusionSignal)
        .filter(FusionSignal.fusion_run_id == run_id)
        .order_by(FusionSignal.signal_type, FusionSignal.id)
        .all()
    )
    assessment = (
        db.query(IntegrityAssessment)
        .filter(IntegrityAssessment.fusion_run_id == run_id)
        .one_or_none()
    )
    priority = (
        db.query(ReviewPriority).filter(ReviewPriority.fusion_run_id == run_id).one_or_none()
    )
    config = (
        db.query(FusionConfiguration)
        .filter(FusionConfiguration.version == run.configuration_version)
        .one_or_none()
    )
    return run, signals, assessment, priority, config


def get_explanation(db: Session, fusion_run_id: str) -> ExplanationRun | None:
    return (
        db.query(ExplanationRun)
        .filter(ExplanationRun.fusion_run_id == fusion_run_id)
        .one_or_none()
    )


def insert_explanation(
    db: Session,
    *,
    fusion_run_id: str,
    method: str,
    method_version: str,
    summary: dict,
    status: str = "GENERATED",
    error: str | None = None,
) -> ExplanationRun:
    row = ExplanationRun(
        fusion_run_id=fusion_run_id,
        status=status,
        method=method,
        method_version=method_version,
        summary=summary,
        error=error,
    )
    db.add(row)
    db.flush()
    return row


def bulk_relationships(db: Session, edge_ids: list[str]) -> dict[str, GraphRelationship]:
    """Bounded provenance lookup for referenced graph edges (no full scans)."""
    if not edge_ids:
        return {}
    rows = (
        db.query(GraphRelationship).filter(GraphRelationship.id.in_(sorted(set(edge_ids)))).all()
    )
    return {row.id: row for row in rows}


def bulk_nodes(db: Session, node_ids: list[str]) -> dict[str, GraphNode]:
    if not node_ids:
        return {}
    rows = db.query(GraphNode).filter(GraphNode.id.in_(sorted(set(node_ids)))).all()
    return {row.id: row for row in rows}
