import logging
import random
import signal
import sys
import time
from typing import Any

import redis

from backend.core.config import settings
from backend.core.logging import setup_logging
from backend.db.models import AnalysisJob, AnalysisResult, Evidence
from backend.db.session import get_engine, get_session
from backend.services.analysis_jobs import utc_now
from backend.services.analysis_queue import AnalysisQueue, QueueMessage
from backend.services import audit_ledger as audit_service
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

#: BE-037 I1 / WS-C: the failures treated as a Redis outage.
#:
#: Hierarchy measured on the pinned redis-py 4.6.0, not assumed:
#: ``TimeoutError`` and ``ConnectionError`` are *siblings* under ``RedisError``,
#: so a read timeout is only waited out if it is listed here explicitly -- the
#: earlier comment claiming ``ConnectionError`` covered it was wrong, and a
#: stalled socket would escape the outage handler exactly like the pre-I1 crash.
#: ``BusyLoadingError`` (Redis reloading its dataset after a restart) really is a
#: ``ConnectionError`` subclass, so it is covered by that entry.
#: ``ResponseError`` (e.g. ``WRONGTYPE``) and ``DataError`` stay outside the
#: tuple: they are programming faults and must propagate.
#: ``AuthenticationError`` is the trap -- it subclasses ``ConnectionError``, so
#: the tuple would otherwise wait out bad credentials forever even though no
#: amount of retrying can fix them; ``_is_configuration_fault`` excludes it.
TRANSIENT_REDIS_ERRORS = (
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
)


def _audit_lifecycle(db: Any, job: Any, event_type: str, action: str, **payload: Any) -> None:
    """Record a worker-owned lifecycle transition in the job transaction."""
    evidence = db.query(Evidence).filter(Evidence.id == job.evidence_id).one_or_none()
    audit_service.append_event(
        db,
        event_type=event_type,
        action=action,
        resource_type="analysis_jobs",
        resource_id=job.id,
        project_id=evidence.project_id if evidence is not None else None,
        payload={
            "evidence_id": str(job.evidence_id),
            "job_type": str(getattr(job, "job_type", "fingerprint")),
            "attempt": int(job.attempt_count),
            **payload,
        },
        source="analysis_worker",
    )


def _is_configuration_fault(error: BaseException) -> bool:
    """True for a Redis error the tuple catches but retrying cannot cure."""
    return isinstance(error, redis.exceptions.AuthenticationError)


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


def _backoff_delay(consecutive_failures: int) -> float:
    """Bounded exponential backoff with equal jitter, in seconds.

    ``min(cap, base * 2 ** (failures - 1))`` halves, plus jitter in the other
    half: the wait is capped (so a long outage settles at a steady poll rate
    instead of growing without limit) and de-synchronised (so several workers
    that lost Redis at the same moment do not all retry in lockstep).
    """
    cap = min(
        settings.analysis_retry_backoff_max_seconds,
        settings.analysis_retry_backoff_base_seconds * (2 ** (consecutive_failures - 1)),
    )
    half = cap / 2
    return half + random.uniform(0, half)


def _interruptible_sleep(seconds: float) -> bool:
    """Sleep in short slices; True if a shutdown was requested meanwhile.

    A single ``time.sleep(delay)`` could not be interrupted: CPython retries the
    remaining time after a signal handler returns (PEP 475), so a SIGTERM during
    a backoff wait would keep the worker blocked until the wait expired.
    """
    deadline = time.monotonic() + seconds
    poll = settings.analysis_shutdown_poll_seconds
    while True:
        if _shutdown_requested:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(remaining, poll))


def _await_redis_retry(consecutive_failures: int) -> bool:
    """Wait out one backoff period. True when the worker must stop now."""
    delay = _backoff_delay(consecutive_failures)
    logger.warning(
        "redis unavailable; backing off %.1fs (consecutive failures %d)",
        delay,
        consecutive_failures,
    )
    return _interruptible_sleep(delay)


def _recover(queue: AnalysisQueue) -> None:
    """One idempotent recovery pass over the processing list.

    Run at startup and again after a Redis outage, so payloads a worker could
    not acknowledge while Redis was down are reclassified once it is reachable:
    terminal jobs are discarded, genuinely abandoned ones requeued. The
    recovery itself skips fresh ``running`` jobs, so it never steals live work.
    """
    session = get_session()
    try:
        recovered = queue.recover_abandoned(session)
    finally:
        session.close()
    if recovered:
        logger.info("analysis worker recovered %d abandoned job(s)", recovered)


def _complete_reprocessing_hook(db: Any, job: Any) -> None:
    """BE-021 §17: when a job that a reprocessing request delegated to
    finishes, mark that request COMPLETED. Failure-isolated — governance
    bookkeeping must never break the analysis pipeline — and idempotent.

    The linkage is checked before calling the service because most jobs are
    created directly by the evidence pipeline and no reprocessing request
    delegates them; ``complete_reprocessing`` raises ``LookupError`` for those,
    and catching it here logged an ERROR plus traceback after every completed
    job, burying real failures in expected noise (BE-037 G5). An unlinked job is
    therefore a quiet no-op, while a fault in the linkage query or a rejection
    by the state machine stays observable at ERROR with its traceback. Neither
    propagates: the job has already committed, and the acknowledgement that
    follows must not depend on governance bookkeeping.
    """
    from backend.repositories import governance as governance_repo
    from backend.services import governance as governance_service

    try:
        request = governance_repo.lock_pending_reprocessing_for_job(
            db, str(job.id)
        )
    except Exception:
        logger.exception(
            "reprocessing linkage lookup failed job_id=%s", job.id
        )
        return
    if request is None:
        logger.debug(
            "no reprocessing request delegates job_id=%s; governance hook skipped",
            job.id,
        )
        return

    try:
        governance_service.complete_reprocessing(
            db, reprocessing_id=str(request.id), completed_by=None
        )
    except Exception:
        logger.exception(
            "reprocessing completion hook failed job_id=%s reprocessing_id=%s",
            job.id,
            request.id,
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
        _audit_lifecycle(db, job, "ANALYSIS_STARTED", "start")
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
        _audit_lifecycle(db, job, "ANALYSIS_COMPLETED", "complete")
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
    _audit_lifecycle(db, job, "ANALYSIS_FAILED", "fail", reason=message)
    db.commit()


def _complete_vision_job(db, job: Any) -> None:
    """Run vision analysis for a vision-typed job (raises on failure).

    Vision failures propagate to the standard retry/failed handling in
    ``process_message``; they are never converted into successful results.
    """
    analysis = analyze_vision(job.evidence_id, db, StorageService(), job.id)
    job.status = "completed"
    job.completed_at = utc_now()
    _audit_lifecycle(db, job, "ANALYSIS_COMPLETED", "complete")
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
    failures = 0
    # The startup recovery pass runs as the loop's first guarded action rather
    # than before it: an outage that begins while this process is starting must
    # be backed off like any other, not raised out of an unprotected call site.
    # Recovering is safe to repeat: only genuinely abandoned messages (stale or
    # missing started_at, queued-but-unacknowledged) predate this worker, and
    # recovery itself skips fresh ``running`` jobs, so no live job is stolen.
    requeue_needs_recovery = True
    try:
        while not _shutdown_requested:
            try:
                if requeue_needs_recovery:
                    # Redis just came back after an outage: reclassify whatever
                    # was left un-acknowledged while it was down.
                    _recover(queue)
                    requeue_needs_recovery = False
                message = queue.dequeue(timeout=settings.analysis_dequeue_block_seconds)
            except TRANSIENT_REDIS_ERRORS as error:
                if _is_configuration_fault(error):
                    # Wrong credentials: retrying cannot fix it, and looping
                    # quietly would hide a broken deployment.
                    raise
                failures += 1
                requeue_needs_recovery = True
                if _await_redis_retry(failures):
                    break
                continue
            # A dequeue that returned means Redis answered, with or without a
            # payload, so the counter is cleared here rather than after
            # ``process_message``: an idle queue has no message to complete, and
            # resetting only on completion left an idle worker sleeping through
            # every later outage at the previous outage's backoff.
            if failures:
                logger.info("redis reachable again after %d backoff(s)", failures)
                failures = 0
            if message is None:
                continue
            try:
                process_message(message, queue)
            except TRANSIENT_REDIS_ERRORS as error:
                if _is_configuration_fault(error):
                    raise
                # The acknowledgement (or the retry requeue) could not reach
                # Redis. The payload is left in the processing list, which is
                # exactly the state a crashed worker leaves behind: the job is
                # never acknowledged early, and the next recovery pass either
                # discards it (terminal) or requeues it (abandoned).
                failures += 1
                requeue_needs_recovery = True
                if _await_redis_retry(failures):
                    break
                continue
    finally:
        # Reached on a SIGTERM-flagged stop and on Ctrl-C alike. Per-message DB
        # sessions are already closed by process_message; this releases the
        # queue connection and the pooled DB connections.
        logger.info("analysis worker stopping; releasing queue and database resources")
        queue.client.close()
        get_engine().dispose()
        logger.info("analysis worker stopped")


if __name__ == "__main__":
    setup_logging()
    install_shutdown_handlers()
    try:
        run_worker()
    except KeyboardInterrupt:
        sys.exit(0)
