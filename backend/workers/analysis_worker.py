import logging
import signal
import sys
from typing import Any

from backend.core.config import settings
from backend.db.models import AnalysisJob, AnalysisResult, Evidence
from backend.db.session import get_engine, get_session
from backend.services.analysis_jobs import utc_now
from backend.services.analysis_queue import AnalysisQueue, QueueMessage
from backend.services.fingerprinting import process_evidence
from backend.services.duplicate_intelligence import analyze_duplicates
from backend.services.storage import StorageService
from backend.services.temporal_intelligence import analyze_single
from backend.services.vision_intelligence import analyze_vision


logger = logging.getLogger(__name__)

#: Set only by the signal handler; read between queue messages. Checked after a
#: message has been fully processed, so an in-flight job and its database
#: transaction are never interrupted (BE-037A-D3).
_shutdown_requested = False


def _request_shutdown(signum: int, frame: Any) -> None:
    """Signal handler: flip the flag and return immediately.

    Must do no work — the handler can fire while the loop is inside a database
    transaction, and a blocked ``brpoplpush`` resumes after ``EINTR``. Stopping
    happens in ``run_worker``'s loop condition, not here.
    """
    global _shutdown_requested
    _shutdown_requested = True


def install_shutdown_handlers() -> None:
    """Handle SIGTERM so the worker stops cleanly under Docker and systemd.

    As container PID 1 the kernel does not act on default-action signals, so an
    unhandled SIGTERM is ignored until Docker escalates to SIGKILL (exit 137).
    SIGINT is deliberately left alone: it keeps raising ``KeyboardInterrupt``,
    which ``__main__`` already maps to a clean exit.
    """
    signal.signal(signal.SIGTERM, _request_shutdown)


def _complete_reprocessing_hook(db: Any, job: Any) -> None:
    """BE-021 §17: when a job that a reprocessing request delegated to
    finishes, mark that request COMPLETED. Failure-isolated — governance
    bookkeeping must never break the analysis pipeline — and idempotent."""
    try:
        from backend.services import governance as governance_service

        governance_service.complete_reprocessing(
            db, analysis_job_id=str(job.id), completed_by=None
        )
    except Exception:
        logger.exception(
            "reprocessing completion hook failed job_id=%s", job.id
        )


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

        if getattr(job, "job_type", "fingerprint") == "vision":
            _complete_vision_job(db, job)
            queue.acknowledge(message)
            logger.info("vision job completed job_id=%s", job.id)
            return "completed"

        fingerprint = process_evidence(job.evidence_id, db)
        duplicate_analysis = analyze_duplicates(
            job.evidence_id,
            db,
            StorageService(),
            job.id,
        )
        try:
            temporal_analysis = analyze_single(job.evidence_id, db)
        except LookupError:
            raise
        except Exception as error:
            temporal_analysis = {
                "evidence_id": job.evidence_id,
                "captured_at": None,
                "captured_source": None,
                "captured_tz_known": False,
                "uploaded_at": None,
                "capture_upload": "UNKNOWN",
                "claim_id": None,
                "claim_window": "UNKNOWN",
                "relationships": [],
                "time_differences": [],
                "inconsistencies": [],
                "status": "unknown",
                "error": str(error),
            }
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
            "temporal_analysis": temporal_analysis,
        }
        if result is None:
            db.add(AnalysisResult(job_id=job.id, result=result_payload))
        else:
            result.result = result_payload
        job.status = "completed"
        job.completed_at = utc_now()
        db.commit()
        _complete_reprocessing_hook(db, job)
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


def _complete_vision_job(db, job: Any) -> None:
    """Run vision analysis for a vision-typed job (raises on failure).

    Vision failures propagate to the standard retry/failed handling in
    ``process_message``; they are never converted into successful results.
    """
    analysis = analyze_vision(job.evidence_id, db, StorageService(), job.id)
    job.status = "completed"
    job.completed_at = utc_now()
    db.commit()
    _complete_reprocessing_hook(db, job)
    logger.info(
        "vision analysis stored job_id=%s result_id=%s detection_count=%d",
        job.id,
        analysis.result_id,
        analysis.detection_count,
    )


def run_worker() -> None:
    queue = AnalysisQueue()
    logger.info("analysis worker started")
    # Recover at startup: only genuinely abandoned messages (stale/missing
    # started_at, queued-but-unacknowledged) predate this worker, so no live
    # job is stolen. Recovery itself skips fresh ``running`` jobs, so it is
    # also safe to invoke periodically without stealing concurrent work.
    session = get_session()
    try:
        recovered = queue.recover_abandoned(session)
    finally:
        session.close()
    if recovered:
        logger.info("analysis worker recovered %d abandoned job(s)", recovered)
    try:
        while not _shutdown_requested:
            message = queue.dequeue(timeout=5)
            if message is not None:
                process_message(message, queue)
    finally:
        # Reached on a SIGTERM-flagged stop and on Ctrl-C alike. Per-message DB
        # sessions are already closed by process_message; this releases the
        # queue connection and the pooled DB connections.
        logger.info("analysis worker stopping; releasing queue and database resources")
        queue.client.close()
        get_engine().dispose()
        logger.info("analysis worker stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    install_shutdown_handlers()
    try:
        run_worker()
    except KeyboardInterrupt:
        sys.exit(0)