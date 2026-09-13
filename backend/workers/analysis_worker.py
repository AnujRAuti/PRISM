import logging
import sys
from typing import Any

from backend.core.config import settings
from backend.db.models import AnalysisJob, AnalysisResult, Evidence
from backend.db.session import get_session
from backend.services.analysis_jobs import utc_now
from backend.services.analysis_queue import AnalysisQueue, QueueMessage
from backend.services.fingerprinting import process_evidence
from backend.services.duplicate_intelligence import analyze_duplicates
from backend.services.storage import StorageService


logger = logging.getLogger(__name__)


def process_message(message: QueueMessage, queue: AnalysisQueue) -> str:
    db = get_session()
    job = None
    try:
        job: Any = db.query(AnalysisJob).filter(AnalysisJob.id == message.job_id).one_or_none()
        if job is None:
            queue.acknowledge(message)
            return "missing"
        if job.status == "completed":
            queue.acknowledge(message)
            return "already_completed"
        if job.status == "failed":
            queue.acknowledge(message)
            return "already_failed"
        evidence = db.query(Evidence).filter(Evidence.id == job.evidence_id).one_or_none()
        if evidence is None:
            _fail(db, job, "Evidence not found")
            queue.acknowledge(message)
            return "failed"

        job.status = "running"
        job.started_at = utc_now()
        job.attempt_count += 1
        job.error = None
        db.commit()

        fingerprint = process_evidence(job.evidence_id, db)
        duplicate_analysis = analyze_duplicates(
            job.evidence_id,
            db,
            StorageService(),
            job.id,
        )
        result: Any = db.query(AnalysisResult).filter(AnalysisResult.job_id == job.id).one_or_none()
        result_payload = {
            "sha256": fingerprint.sha256,
            "phash": fingerprint.phash,
            "exif_status": fingerprint.exif_status,
            "phash_status": "success" if fingerprint.phash else "failed",
            "duplicate_analysis": {
                "exact_matches": duplicate_analysis.exact_matches,
                "perceptual_matches": duplicate_analysis.perceptual_matches,
                "semantic_matches": duplicate_analysis.semantic_matches,
                "embedding_status": duplicate_analysis.embedding_status,
                "embedding_error": duplicate_analysis.embedding_error,
            },
        }
        if result is None:
            db.add(AnalysisResult(job_id=job.id, result=result_payload))
        else:
            result.result = result_payload
        job.status = "completed"
        job.completed_at = utc_now()
        db.commit()
        queue.acknowledge(message)
        logger.info("analysis job completed job_id=%s", job.id)
        return "completed"
    except Exception as error:
        db.rollback()
        if job is not None:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job.id).one()
            if job.attempt_count >= settings.analysis_max_attempts:
                _fail(db, job, "Analysis processing failed")
                queue.acknowledge(message)
                logger.exception("analysis job failed job_id=%s", job.id)
                return "failed"
            job.status = "queued"
            job.error = "Analysis processing will be retried"
            db.commit()
            queue.retry(message)
            logger.warning("analysis job retried job_id=%s", job.id)
            return "retry"
        queue.acknowledge(message)
        logger.exception("analysis queue message failed")
        return "failed"
    finally:
        db.close()


def _fail(db, job: Any, message: str) -> None:
    job.status = "failed"
    job.error = message
    job.completed_at = utc_now()
    db.commit()


def run_worker() -> None:
    queue = AnalysisQueue()
    logger.info("analysis worker started")
    while True:
        message = queue.dequeue(timeout=5)
        if message is not None:
            process_message(message, queue)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        run_worker()
    except KeyboardInterrupt:
        sys.exit(0)