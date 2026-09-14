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
        recovered = 0
        while True:
            payload = self.client.lpop(self.processing_name)
            if payload is None:
                break
            try:
                job_id = str(json.loads(payload)["job_id"])
            except (TypeError, ValueError, KeyError):
                continue
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).one_or_none()
            if job is None:
                continue
            if job.status == "running":
                job.status = "queued"
                job.error = "Recovered from abandoned processing state"
                self.client.rpush(self.queue_name, payload)
                recovered += 1
            elif job.status in {"completed", "failed"}:
                pass
            else:
                self.client.rpush(self.queue_name, payload)
            db.commit()
        return recovered

    def clear(self) -> None:
        self.client.delete(self.queue_name, self.processing_name)