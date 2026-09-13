from datetime import datetime, timezone

import redis
from sqlalchemy.orm import Session

from backend.db.models import AnalysisJob, AnalysisResult, Evidence
from backend.services.analysis_queue import AnalysisQueue


def create_analysis_job(
    evidence_id: str,
    db: Session,
    queue: AnalysisQueue | None = None,
) -> AnalysisJob:
    if db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none() is None:
        raise LookupError("Evidence not found")
    job = AnalysisJob(evidence_id=evidence_id, status="queued", attempt_count=0)
    db.add(job)
    db.commit()
    db.refresh(job)
    queue = queue or AnalysisQueue()
    try:
        queue.enqueue(job.id)
    except redis.RedisError as error:
        job.status = "failed"
        job.error = "Unable to enqueue analysis job"
        db.commit()
        raise RuntimeError("Unable to enqueue analysis job") from error
    return job


def get_analysis_job(job_id: str, db: Session) -> AnalysisJob | None:
    return db.query(AnalysisJob).filter(AnalysisJob.id == job_id).one_or_none()


def get_analysis_result(job_id: str, db: Session) -> AnalysisResult | None:
    return db.query(AnalysisResult).filter(AnalysisResult.job_id == job_id).one_or_none()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)