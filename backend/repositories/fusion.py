"""BE-011 fusion repository: persistence and retrieval only.

Business logic (extraction, normalization, rules, priority) lives in
``backend.services.fusion``.
"""

from sqlalchemy.orm import Session

from backend.db.models import (
    FusionConfiguration,
    FusionRun,
    FusionSignal,
    IntegrityAssessment,
    ReviewPriority,
)


def get_configuration(db: Session, version: str) -> FusionConfiguration | None:
    return (
        db.query(FusionConfiguration)
        .filter(FusionConfiguration.version == version)
        .one_or_none()
    )


def insert_configuration(
    db: Session,
    *,
    version: str,
    name: str,
    method_version: str,
    weights: dict,
    thresholds: dict,
    priority: dict,
    signals: dict,
    enabled: bool = True,
) -> FusionConfiguration:
    config = FusionConfiguration(
        version=version,
        name=name,
        enabled=enabled,
        method_version=method_version,
        weights=weights,
        thresholds=thresholds,
        priority=priority,
        signals=signals,
    )
    db.add(config)
    db.flush()
    return config


def insert_run(
    db: Session,
    *,
    target_type: str,
    target_id: str,
    method: str,
    method_version: str,
    configuration_version: str,
    input_snapshot: dict,
) -> FusionRun:
    run = FusionRun(
        target_type=target_type,
        target_id=target_id,
        status="RUNNING",
        method=method,
        method_version=method_version,
        configuration_version=configuration_version,
        input_snapshot=input_snapshot,
    )
    db.add(run)
    db.flush()
    return run


def get_run(db: Session, run_id: str) -> FusionRun | None:
    return db.query(FusionRun).filter(FusionRun.id == run_id).one_or_none()


def lock_run(db: Session, run_id: str) -> FusionRun | None:
    """Lock the run row so concurrent mutations derived from it serialize.

    Review-case generation is a read-then-insert sequence: check for an
    existing active case, then insert one. Without a lock two callers can both
    observe "no case" and both attempt the insert. The partial unique index then
    correctly rejects the loser, but only by aborting its transaction. Taking
    the row lock up front means the loser blocks and, once it resumes, observes
    the winner's committed row. Same pattern as publication/correction/dispute
    mutations. The lock is held until the caller's transaction ends.
    """
    return (
        db.query(FusionRun).filter(FusionRun.id == run_id).with_for_update().one_or_none()
    )


def insert_signals(db: Session, run_id: str, signals: list[dict]) -> list[FusionSignal]:
    rows = [
        FusionSignal(
            fusion_run_id=run_id,
            signal_type=item["signal_type"],
            state=item["state"],
            source=item["source"],
            source_entity_id=item.get("source_entity_id"),
            source_analysis_run_id=item.get("source_analysis_run_id"),
            raw_value=item.get("raw_value"),
            normalized_value=item.get("normalized_value"),
            weight=item.get("weight", 0.0),
            method=item["method"],
            method_version=item["method_version"],
            details=item.get("details", {}),
        )
        for item in signals
    ]
    db.add_all(rows)
    db.flush()
    return rows


def insert_assessment(
    db: Session,
    *,
    run_id: str,
    target_type: str,
    target_id: str,
    value: str,
    score: float | None,
    signal_summary: dict,
) -> IntegrityAssessment:
    row = IntegrityAssessment(
        fusion_run_id=run_id,
        target_type=target_type,
        target_id=target_id,
        assessment_status="ACTIVE",
        assessment_value=value,
        integrity_score=score,
        signal_summary=signal_summary,
    )
    db.add(row)
    db.flush()
    return row


def insert_priority(
    db: Session,
    *,
    run_id: str,
    target_type: str,
    target_id: str,
    priority: str,
    score: float,
    signal_summary: dict,
) -> ReviewPriority:
    row = ReviewPriority(
        fusion_run_id=run_id,
        target_type=target_type,
        target_id=target_id,
        priority=priority,
        priority_score=score,
        signal_summary=signal_summary,
    )
    db.add(row)
    db.flush()
    return row


def supersede_prior_outputs(db: Session, target_type: str, target_id: str, run_id: str) -> int:
    """Supersede older ACTIVE outputs; history rows are never deleted."""
    assessments = (
        db.query(IntegrityAssessment)
        .filter(
            IntegrityAssessment.target_type == target_type,
            IntegrityAssessment.target_id == target_id,
            IntegrityAssessment.assessment_status == "ACTIVE",
            IntegrityAssessment.fusion_run_id != run_id,
        )
        .all()
    )
    for row in assessments:
        row.assessment_status = "SUPERSEDED"
    return len(assessments)


def latest_outputs(db: Session, target_type: str, target_id: str):
    """Latest COMPLETED run with its ACTIVE assessment + priority, if any."""
    run = (
        db.query(FusionRun)
        .filter(
            FusionRun.target_type == target_type,
            FusionRun.target_id == target_id,
            FusionRun.status == "COMPLETED",
        )
        .order_by(FusionRun.created_at.desc(), FusionRun.id.desc())
        .first()
    )
    if run is None:
        return None, None, None
    assessment = (
        db.query(IntegrityAssessment)
        .filter(
            IntegrityAssessment.fusion_run_id == run.id,
            IntegrityAssessment.assessment_status == "ACTIVE",
        )
        .one_or_none()
    )
    priority = (
        db.query(ReviewPriority).filter(ReviewPriority.fusion_run_id == run.id).one_or_none()
    )
    if assessment is None or priority is None:
        return None, None, None
    return run, assessment, priority


def run_history_query(db: Session, target_type: str, target_id: str, status: str | None):
    query = db.query(FusionRun).filter(
        FusionRun.target_type == target_type, FusionRun.target_id == target_id
    )
    if status is not None:
        query = query.filter(FusionRun.status == status)
    return query.order_by(FusionRun.created_at.desc(), FusionRun.id.desc())


def signals_for_run(db: Session, run_id: str) -> list[FusionSignal]:
    return (
        db.query(FusionSignal)
        .filter(FusionSignal.fusion_run_id == run_id)
        .order_by(FusionSignal.signal_type, FusionSignal.id)
        .all()
    )
