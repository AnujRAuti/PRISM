import json
from dataclasses import dataclass

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
        self.client = client or redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.queue_name = settings.analysis_queue_name
        self.processing_name = f"{self.queue_name}:processing"

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

        Loss-safety: the head payload is only peeked (LINDEX) until the
        database decision is made, then removed (LREM) after it has been
        safely requeued or discarded. A crash between RPUSH and LREM can at
        most produce a duplicate delivery, which the worker already handles
        idempotently (completed/failed guards); a message is never lost.
        """
        recovered = 0
        while True:
            payload = self.client.lindex(self.processing_name, 0)
            if payload is None:
                break
            try:
                job_id = str(json.loads(payload)["job_id"])
            except (TypeError, ValueError, KeyError):
                self.client.lrem(self.processing_name, 1, payload)
                continue
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).one_or_none()
            if job is None:
                self.client.lrem(self.processing_name, 1, payload)
                continue
            if job.status == "running":
                job.status = "queued"
                job.error = "Recovered from abandoned processing state"
                db.commit()
                pipeline = self.client.pipeline()
                pipeline.rpush(self.queue_name, payload)
                pipeline.lrem(self.processing_name, 1, payload)
                pipeline.execute()
                recovered += 1
            elif job.status in {"completed", "failed"}:
                self.client.lrem(self.processing_name, 1, payload)
                db.commit()
            else:
                pipeline = self.client.pipeline()
                pipeline.rpush(self.queue_name, payload)
                pipeline.lrem(self.processing_name, 1, payload)
                pipeline.execute()
                db.commit()
        return recovered

    def clear(self) -> None:
        self.client.delete(self.queue_name, self.processing_name)