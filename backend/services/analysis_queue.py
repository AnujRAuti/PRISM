import json
from dataclasses import dataclass
from datetime import datetime, timezone

import redis
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import AnalysisJob


@dataclass(frozen=True)
class QueueMessage:
    job_id: str
    payload: str


class AnalysisQueue:
    def __init__(self, client: redis.Redis | None = None) -> None:
        self.client = client or self._bounded_client()
        self.queue_name = settings.analysis_queue_name
        self.processing_name = f"{self.queue_name}:processing"

    @staticmethod
    def _bounded_client() -> redis.Redis:
        """A client whose reads have a deadline.

        Without these bounds redis-py leaves ``socket_timeout`` unset, so a
        server that stops answering without closing the connection blocks the
        call forever — and a worker stuck inside ``brpoplpush`` reaches neither
        the outage handler nor its shutdown check. The timeouts turn that stall
        into ``TimeoutError``, which the worker treats as an outage.

        ``health_check_interval`` is included because it catches a silently dead
        connection *between* commands; it cannot help mid-reply, which is why the
        socket timeout is the load-bearing one.
        """
        socket_timeout = settings.analysis_redis_socket_timeout_seconds
        block = settings.analysis_dequeue_block_seconds
        if socket_timeout <= block:
            raise ValueError(
                "ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS "
                f"({socket_timeout}) must be greater than ANALYSIS_DEQUEUE_BLOCK_SECONDS "
                f"({block}): a healthy idle poll is supposed to time out on the "
                "server side and return no message, and a socket deadline at or "
                "below it reports every idle poll as a Redis outage."
            )
        return redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=socket_timeout,
            socket_connect_timeout=settings.analysis_redis_socket_connect_timeout_seconds,
            health_check_interval=settings.analysis_redis_health_check_interval_seconds,
        )

    def enqueue(self, job_id: str) -> None:
        payload = json.dumps({"job_id": job_id}, separators=(",", ":"))
        self.client.rpush(self.queue_name, payload)

    def dequeue(self, timeout: int = 0) -> QueueMessage | None:
        item = self.client.brpoplpush(self.queue_name, self.processing_name, timeout=timeout)
        if item is None:
            return None
        try:
            job_id = str(json.loads(item)["job_id"])
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError("Invalid analysis queue payload") from error
        return QueueMessage(job_id=job_id, payload=item)

    def acknowledge(self, message: QueueMessage) -> None:
        self.client.lrem(self.processing_name, 1, message.payload)

    def retry(self, message: QueueMessage) -> None:
        pipeline = self.client.pipeline()
        pipeline.lrem(self.processing_name, 1, message.payload)
        pipeline.rpush(self.queue_name, message.payload)
        pipeline.execute()

    def recover_abandoned(self, db: Session) -> int:
        """Requeue processing-list messages left by dead workers.

        Abandonment is established from PostgreSQL job state plus the age of
        ``started_at`` — never from Redis presence alone:

        - ``completed`` / ``failed`` / missing job / corrupt payload:
          discard from the processing list, never requeue.
        - ``queued`` (dequeued but crashed before ``running``) or ``running``
          with a missing/stale ``started_at`` (older than
          ``analysis_abandoned_timeout_seconds``): genuinely abandoned,
          reset to ``queued`` and requeue.
        - ``running`` with a fresh ``started_at``: still actively processed
          by a live worker — left untouched so recovery never steals it.

        Loss-safety: an abandoned payload is RPUSHed to the main queue
        before LREM removes it from processing. A crash between RPUSH and
        LREM can at most produce a duplicate delivery, which the worker
        already handles idempotently (completed/failed guards); a message
        is never lost. Active jobs are never moved, so concurrent recovery
        is safe. Repeated recovery is idempotent.
        """
        recovered = 0
        timeout = settings.analysis_abandoned_timeout_seconds
        payloads = list(self.client.lrange(self.processing_name, 0, -1) or [])
        for payload in payloads:
            try:
                job_id = str(json.loads(payload)["job_id"])
            except (TypeError, ValueError, KeyError):
                self.client.lrem(self.processing_name, 1, payload)
                continue
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).one_or_none()
            if job is None:
                self.client.lrem(self.processing_name, 1, payload)
                continue
            if job.status in {"completed", "failed"}:
                self.client.lrem(self.processing_name, 1, payload)
                db.commit()
                continue
            if job.status == "running" and not _is_abandoned(job, timeout):
                # Live worker: do not touch.
                continue
            if job.status == "running":
                job.status = "queued"
                job.error = "Recovered from abandoned processing state"
            # ``queued`` (or any other non-terminal) payload found in the
            # processing list means the worker died between BRPOPLPUSH and
            # acknowledgement: safe to requeue.
            db.commit()
            pipeline = self.client.pipeline()
            pipeline.rpush(self.queue_name, payload)
            pipeline.lrem(self.processing_name, 1, payload)
            pipeline.execute()
            recovered += 1
        return recovered

    def clear(self) -> None:
        self.client.delete(self.queue_name, self.processing_name)


def _is_abandoned(job: AnalysisJob, timeout_seconds: int) -> bool:
    """True only when a ``running`` job is genuinely abandoned.

    A missing ``started_at`` predates abandonment tracking and is treated
    as abandoned (preserves recovery for legacy rows). Otherwise the job
    is abandoned only when ``started_at`` is older than the timeout, so a
    live worker with a fresh heartbeat-equivalent timestamp is never
    stolen. Timezone-naive values are assumed UTC for comparison.
    """
    started_at = job.started_at
    if started_at is None:
        return True
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - started_at).total_seconds() >= timeout_seconds
