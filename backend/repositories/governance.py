"""BE-021 governance repository: persistence and deterministic queries only.

Dependency traversal policy, staleness semantics, and reprocessing rules
live in ``backend.services.governance``. Marking helpers here are plain
bulk UPDATEs restricted to explicitly enumerated ids — never open-ended.
"""

from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.db.models import (
    AnalysisJob,
    Evidence,
    ExplanationRun,
    ExternalAssertion,
    FusionRun,
    GraphRelationship,
    IntegrityAssessment,
    IntelligenceInvalidation,
    ReprocessingRequest,
    ReviewCase,
)


# ---------------------------------------------------------------------------
# Target lookup / locking (§29: invalidation operations must serialize)
# ---------------------------------------------------------------------------

def get_target_row(db: Session, target_type: str, target_id: str):
    """Fetch the governed target row (or None) by dispute-target vocabulary."""
    model = {
        "EVIDENCE": Evidence,
        "EVIDENCE_CLAIM_RELATIONSHIP": GraphRelationship,
        "CLAIM": None,  # imported lazily below to keep this mapping explicit
        "EXTERNAL_ASSERTION": ExternalAssertion,
        "FUSION_ASSESSMENT": IntegrityAssessment,
        "REVIEW_CASE": ReviewCase,
    }.get(target_type)
    if model is None:
        from backend.db.models import Claim

        if target_type == "CLAIM":
            return db.query(Claim).filter(Claim.id == target_id).one_or_none()
        return None
    return db.query(model).filter(model.id == target_id).one_or_none()


def lock_target_row(db: Session, target_type: str, target_id: str):
    """SELECT ... FOR UPDATE the governed target row (§29)."""
    model = {
        "EVIDENCE": Evidence,
        "EVIDENCE_CLAIM_RELATIONSHIP": GraphRelationship,
        "EXTERNAL_ASSERTION": ExternalAssertion,
        "FUSION_ASSESSMENT": IntegrityAssessment,
        "REVIEW_CASE": ReviewCase,
    }.get(target_type)
    if model is None:
        from backend.db.models import Claim

        if target_type == "CLAIM":
            return db.query(Claim).filter(Claim.id == target_id).with_for_update().one_or_none()
        return None
    return db.query(model).filter(model.id == target_id).with_for_update().one_or_none()


# ---------------------------------------------------------------------------
# Dependency discovery queries (deterministic; ids returned, no payload)
# ---------------------------------------------------------------------------

def analysis_job_ids_for_evidence(db: Session, evidence_id: str) -> list[str]:
    rows = (
        db.query(AnalysisJob.id)
        .filter(AnalysisJob.evidence_id == evidence_id)
        .order_by(AnalysisJob.created_at.asc(), AnalysisJob.id.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


def fusion_run_ids_for_target(
    db: Session, target_type: str, target_id: str
) -> list[str]:
    rows = (
        db.query(FusionRun.id)
        .filter(FusionRun.target_type == target_type, FusionRun.target_id == target_id)
        .order_by(FusionRun.created_at.asc(), FusionRun.id.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


def explanation_run_ids_for_fusion_runs(db: Session, fusion_run_ids: list[str]) -> list[str]:
    if not fusion_run_ids:
        return []
    rows = (
        db.query(ExplanationRun.id)
        .filter(ExplanationRun.fusion_run_id.in_(fusion_run_ids))
        .order_by(ExplanationRun.created_at.asc(), ExplanationRun.id.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


def assessment_ids_for_fusion_runs(db: Session, fusion_run_ids: list[str]) -> list[str]:
    if not fusion_run_ids:
        return []
    rows = (
        db.query(IntegrityAssessment.id)
        .filter(IntegrityAssessment.fusion_run_id.in_(fusion_run_ids))
        .order_by(IntegrityAssessment.created_at.asc(), IntegrityAssessment.id.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


def relationship_ids_for_node_entity(
    db: Session, node_type: str, entity_ids: list[str]
) -> list[str]:
    """Graph edges (BE-010) whose source or target node is one of the entities."""
    if not entity_ids:
        return []
    from backend.db.models import GraphNode

    node_rows = (
        db.query(GraphNode.id)
        .filter(
            GraphNode.node_type == node_type,
            GraphNode.entity_id.in_(entity_ids),
        )
        .all()
    )
    node_ids = [str(row[0]) for row in node_rows]
    if not node_ids:
        return []
    rows = (
        db.query(GraphRelationship.id)
        .filter(
            GraphRelationship.relationship_status == "ACTIVE",
            (
                GraphRelationship.source_node_id.in_(node_ids)
                | GraphRelationship.target_node_id.in_(node_ids)
            ),
        )
        .order_by(GraphRelationship.created_at.asc(), GraphRelationship.id.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


def review_case_ids_for_intelligence(
    db: Session,
    *,
    evidence_id: str | None = None,
    claim_id: str | None = None,
    fusion_run_ids: list[str] | None = None,
) -> list[str]:
    """Cases referencing the governed intelligence (notification-only links)."""
    from backend.db.models import ReviewCase as RC

    query = db.query(RC.id).filter(RC.status != "RESOLVED")
    clauses = []
    if evidence_id is not None:
        clauses.append(RC.evidence_id == evidence_id)
    if claim_id is not None:
        clauses.append(RC.claim_id == claim_id)
    if fusion_run_ids:
        clauses.append(RC.fusion_run_id.in_(fusion_run_ids))
    if not clauses:
        return []
    from sqlalchemy import or_

    rows = (
        query.filter(or_(*clauses))
        .order_by(RC.created_at.asc(), RC.id.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


# ---------------------------------------------------------------------------
# Bulk staleness marking (bounded by explicitly enumerated ids)
# ---------------------------------------------------------------------------

def mark_analysis_jobs(db: Session, job_ids: list[str], staleness: str) -> int:
    if not job_ids:
        return 0
    return (
        db.query(AnalysisJob)
        .filter(AnalysisJob.id.in_(job_ids))
        .filter(AnalysisJob.staleness != staleness)
        .update({AnalysisJob.staleness: staleness}, synchronize_session=False)
    )


def mark_fusion_runs(db: Session, run_ids: list[str], staleness: str) -> int:
    if not run_ids:
        return 0
    return (
        db.query(FusionRun)
        .filter(FusionRun.id.in_(run_ids))
        .filter(FusionRun.staleness != staleness)
        .update({FusionRun.staleness: staleness}, synchronize_session=False)
    )


def mark_explanation_runs(db: Session, run_ids: list[str], staleness: str) -> int:
    if not run_ids:
        return 0
    return (
        db.query(ExplanationRun)
        .filter(ExplanationRun.id.in_(run_ids))
        .filter(ExplanationRun.staleness != staleness)
        .update({ExplanationRun.staleness: staleness}, synchronize_session=False)
    )


def mark_integrity_assessments(db: Session, assessment_ids: list[str], status: str) -> int:
    if not assessment_ids:
        return 0
    return (
        db.query(IntegrityAssessment)
        .filter(IntegrityAssessment.id.in_(assessment_ids))
        .filter(IntegrityAssessment.assessment_status != status)
        .update({IntegrityAssessment.assessment_status: status}, synchronize_session=False)
    )


def mark_graph_relationships(db: Session, relationship_ids: list[str], status: str) -> int:
    if not relationship_ids:
        return 0
    return (
        db.query(GraphRelationship)
        .filter(GraphRelationship.id.in_(relationship_ids))
        .filter(
            GraphRelationship.relationship_status == "ACTIVE",
            GraphRelationship.relationship_status != status,
        )
        .update({GraphRelationship.relationship_status: status}, synchronize_session=False)
    )


# ---------------------------------------------------------------------------
# Invalidation records
# ---------------------------------------------------------------------------

def insert_invalidation(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    project_id: str | None,
    cause: str,
    dispute_id: str | None,
    correction_id: str | None,
    reason: str,
    invalidated_by: str,
    affected_analysis: int,
    affected_fusion: int,
    affected_explanations: int,
    affected_relationships: int,
    affected_assessments: int,
) -> IntelligenceInvalidation:
    row = IntelligenceInvalidation(
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        cause=cause,
        dispute_id=dispute_id,
        correction_id=correction_id,
        reason=reason,
        invalidated_by=invalidated_by,
        affected_analysis=affected_analysis,
        affected_fusion=affected_fusion,
        affected_explanations=affected_explanations,
        affected_relationships=affected_relationships,
        affected_assessments=affected_assessments,
    )
    db.add(row)
    db.flush()
    return row


def get_invalidation(db: Session, invalidation_id: str) -> IntelligenceInvalidation | None:
    return (
        db.query(IntelligenceInvalidation)
        .filter(IntelligenceInvalidation.id == invalidation_id)
        .one_or_none()
    )


# ---------------------------------------------------------------------------
# Reprocessing requests
# ---------------------------------------------------------------------------

def insert_reprocessing(
    db: Session,
    *,
    evidence_id: str,
    project_id: str | None,
    invalidation_id: str | None,
    requested_by: str,
    reason: str,
) -> ReprocessingRequest:
    row = ReprocessingRequest(
        evidence_id=evidence_id,
        project_id=project_id,
        invalidation_id=invalidation_id,
        requested_by=requested_by,
        reason=reason,
        status="PENDING",
    )
    db.add(row)
    db.flush()
    return row


def get_reprocessing(db: Session, reprocessing_id: str) -> ReprocessingRequest | None:
    return (
        db.query(ReprocessingRequest)
        .filter(ReprocessingRequest.id == reprocessing_id)
        .one_or_none()
    )


def lock_reprocessing(db: Session, reprocessing_id: str) -> ReprocessingRequest | None:
    return (
        db.query(ReprocessingRequest)
        .filter(ReprocessingRequest.id == reprocessing_id)
        .with_for_update()
        .one_or_none()
    )


def pending_reprocessing_for_evidence(
    db: Session, evidence_id: str
) -> ReprocessingRequest | None:
    return (
        db.query(ReprocessingRequest)
        .filter(
            ReprocessingRequest.evidence_id == evidence_id,
            ReprocessingRequest.status == "PENDING",
        )
        .order_by(ReprocessingRequest.created_at.asc(), ReprocessingRequest.id.asc())
        .first()
    )


def analysis_result_ids_for_jobs(db: Session, job_ids: list[str]) -> list[str]:
    """Analysis results produced by the given jobs (BE-005 outputs)."""
    if not job_ids:
        return []
    from backend.db.models import AnalysisResult

    rows = (
        db.query(AnalysisResult.id)
        .filter(AnalysisResult.job_id.in_(job_ids))
        .order_by(AnalysisResult.created_at.asc(), AnalysisResult.id.asc())
        .all()
    )
    return [str(row[0]) for row in rows]


def invalidation_for_dispute(db: Session, dispute_id: str) -> IntelligenceInvalidation | None:
    """The invalidation triggered by a dispute resolution, if any (§28)."""
    return (
        db.query(IntelligenceInvalidation)
        .filter(IntelligenceInvalidation.dispute_id == dispute_id)
        .order_by(IntelligenceInvalidation.created_at.desc(), IntelligenceInvalidation.id.desc())
        .first()
    )


def invalidation_for_correction(
    db: Session, correction_id: str
) -> IntelligenceInvalidation | None:
    """The invalidation triggered by a correction application, if any (§28)."""
    return (
        db.query(IntelligenceInvalidation)
        .filter(IntelligenceInvalidation.correction_id == correction_id)
        .order_by(IntelligenceInvalidation.created_at.desc(), IntelligenceInvalidation.id.desc())
        .first()
    )


def pending_reprocessing_for_job(
    db: Session, analysis_job_id: str
) -> ReprocessingRequest | None:
    """PENDING reprocessing request that delegated to this job (worker hook)."""
    return (
        db.query(ReprocessingRequest)
        .filter(
            ReprocessingRequest.analysis_job_id == analysis_job_id,
            ReprocessingRequest.status == "PENDING",
        )
        .order_by(ReprocessingRequest.created_at.asc(), ReprocessingRequest.id.asc())
        .first()
    )


def lock_pending_reprocessing_for_job(
    db: Session, analysis_job_id: str
) -> ReprocessingRequest | None:
    """SELECT ... FOR UPDATE the request delegating to this job.

    Used by the analysis-worker completion hook so a worker finish and any
    concurrent manual completion serialize (§29).

    Deliberately not filtered to PENDING: the completion hook is idempotent
    (§17), so a repeated call after the request is already COMPLETED must find
    the row and return it unchanged rather than raising "not found". The
    caller owns the state machine and rejects any other status.
    """
    return (
        db.query(ReprocessingRequest)
        .filter(ReprocessingRequest.analysis_job_id == analysis_job_id)
        .with_for_update()
        .one_or_none()
    )
