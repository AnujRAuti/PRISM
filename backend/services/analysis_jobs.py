from datetime import datetime, timezone

import redis
from sqlalchemy.orm import Session

from backend.db.models import AnalysisJob, AnalysisResult, Evidence
from backend.services.analysis_queue import AnalysisQueue
from backend.services import audit_ledger as audit_service


JOB_TYPES = ("fingerprint", "vision")


def create_analysis_job(
    evidence_id: str,
    db: Session,
    queue: AnalysisQueue | None = None,
    job_type: str = "fingerprint",
) -> AnalysisJob:
    if job_type not in JOB_TYPES:
        raise ValueError(f"Invalid job_type: {job_type!r}")
    if db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none() is None:
        raise LookupError("Evidence not found")
    job = AnalysisJob(evidence_id=evidence_id, status="queued", attempt_count=0, job_type=job_type)
    db.add(job)
    # The queued state and its audit record share one transaction.  A job is
    # therefore never visible without its lifecycle beginning in the ledger.
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one()
    audit_service.append_event(
        db,
        event_type="ANALYSIS_QUEUED",
        action="queue",
        resource_type="analysis_jobs",
        resource_id=job.id,
        project_id=evidence.project_id,
        payload={"evidence_id": str(evidence.id), "job_type": job_type, "attempt": 0},
        source="analysis_jobs",
    )
    db.commit()
    db.refresh(job)
    queue = queue or AnalysisQueue()
    try:
        queue.enqueue(job.id)
    except redis.RedisError as error:
        job.status = "failed"
        job.error = "Unable to enqueue analysis job"
        audit_service.append_event(
            db,
            event_type="ANALYSIS_FAILED",
            action="enqueue_failed",
            resource_type="analysis_jobs",
            resource_id=job.id,
            project_id=evidence.project_id,
            payload={"evidence_id": str(evidence.id), "job_type": job_type, "attempt": 0},
            source="analysis_jobs",
        )
        db.commit()
        raise RuntimeError("Unable to enqueue analysis job") from error
    return job


def get_analysis_job(job_id: str, db: Session) -> AnalysisJob | None:
    return db.query(AnalysisJob).filter(AnalysisJob.id == job_id).one_or_none()


def get_analysis_result(job_id: str, db: Session) -> AnalysisResult | None:
    return db.query(AnalysisResult).filter(AnalysisResult.job_id == job_id).one_or_none()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
