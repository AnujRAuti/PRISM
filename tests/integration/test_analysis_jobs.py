import json
from io import BytesIO
from uuid import uuid4

import redis
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import AnalysisJob, AnalysisResult, DuplicateMatch, Evidence, EvidenceMetadata
from backend.db.session import get_session
from backend.services.analysis_queue import AnalysisQueue
from backend.services.storage import StorageService
from backend.workers.analysis_worker import process_message


client = TestClient(app)


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 12), color=(40, 100, 180)).save(output, format="JPEG")
    return output.getvalue()


def create_evidence() -> dict:
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("job.jpg", image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def cleanup(evidence_id: str, storage_key: str, job_id: str | None = None) -> None:
    storage = StorageService()
    if storage.object_exists(storage.quarantine_bucket, storage_key):
        storage.delete_object(storage.quarantine_bucket, storage_key)
    session = get_session()
    if job_id:
        session.query(AnalysisResult).filter_by(job_id=job_id).delete()
        session.query(AnalysisJob).filter_by(id=job_id).delete()
    session.query(DuplicateMatch).filter(
        (DuplicateMatch.evidence_id == evidence_id)
        | (DuplicateMatch.matched_evidence_id == evidence_id)
    ).delete(synchronize_session=False)
    session.query(EvidenceMetadata).filter_by(evidence_id=evidence_id).delete()
    session.query(Evidence).filter_by(id=evidence_id).delete()
    session.commit()
    session.close()


def test_real_redis_queue_enqueue_dequeue_ack():
    queue = AnalysisQueue()
    queue.clear()
    job_id = str(uuid4())
    queue.enqueue(job_id)
    message = queue.dequeue(timeout=1)
    assert message is not None
    assert message.job_id == job_id
    assert queue.client.llen(queue.processing_name) == 1
    queue.acknowledge(message)
    assert queue.client.llen(queue.processing_name) == 0
    queue.clear()


def test_api_creates_job_and_worker_persists_real_fingerprint_result():
    evidence = create_evidence()
    queue = AnalysisQueue()
    job_id = None
    try:
        response = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"]},
        )
        assert response.status_code == 202
        body = response.json()
        job_id = body["job_id"]
        assert body["status"] == "queued"
        assert queue.client.llen(queue.queue_name) == 1

        message = queue.dequeue(timeout=1)
        assert message is not None
        assert process_message(message, queue) == "completed"

        status_response = client.get(f"/api/v1/analysis/jobs/{job_id}")
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] == "completed"
        assert status_body["result"]["sha256"]
        assert status_body["result"]["phash"]

        session = get_session()
        result_count = session.query(AnalysisResult).filter_by(job_id=job_id).count()
        assert result_count == 1
        session.close()
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], job_id)


def test_duplicate_delivery_does_not_create_duplicate_result():
    evidence = create_evidence()
    queue = AnalysisQueue()
    job_id = None
    try:
        response = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"]},
        )
        job_id = response.json()["job_id"]
        first = queue.dequeue(timeout=1)
        assert first is not None
        assert process_message(first, queue) == "completed"

        queue.enqueue(job_id)
        duplicate = queue.dequeue(timeout=1)
        assert duplicate is not None
        assert process_message(duplicate, queue) == "already_completed"

        session = get_session()
        assert session.query(AnalysisResult).filter_by(job_id=job_id).count() == 1
        session.close()
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], job_id)


def test_processing_failure_is_bounded_and_has_no_success_result():
    evidence = create_evidence()
    queue = AnalysisQueue()
    job_id = None
    storage = StorageService()
    storage.delete_object(storage.quarantine_bucket, evidence["storage_key"])
    try:
        response = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"]},
        )
        job_id = response.json()["job_id"]
        outcomes = []
        for _ in range(settings.analysis_max_attempts):
            message = queue.dequeue(timeout=1)
            assert message is not None
            outcomes.append(process_message(message, queue))
        assert outcomes == ["retry", "retry", "failed"]

        status_response = client.get(f"/api/v1/analysis/jobs/{job_id}")
        assert status_response.json()["status"] == "failed"
        assert status_response.json()["result"] is None
        session = get_session()
        assert session.query(AnalysisResult).filter_by(job_id=job_id).count() == 0
        session.close()
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], job_id)


def test_missing_evidence_and_invalid_job_are_rejected():
    missing_evidence = client.post("/api/v1/analysis/jobs", json={"evidence_id": str(uuid4())})
    assert missing_evidence.status_code == 404
    invalid_job = client.get("/api/v1/analysis/jobs/not-a-uuid")
    assert invalid_job.status_code == 422


def test_abandoned_processing_jobs_are_recovered_idempotently():
    evidence = create_evidence()
    queue = AnalysisQueue()
    queue.clear()
    session = get_session()
    job = AnalysisJob(evidence_id=evidence["evidence_id"], status="running", attempt_count=1)
    try:
        session.add(job)
        session.commit()
        session.refresh(job)
        queue.client.rpush(queue.processing_name, json.dumps({"job_id": job.id}))

        assert queue.recover_abandoned(session) == 1
        session.refresh(job)
        assert job.status == "queued"
        assert queue.client.llen(queue.processing_name) == 0
        assert queue.client.llen(queue.queue_name) == 1
        assert queue.recover_abandoned(session) == 0
    finally:
        queue.clear()
        session.close()
        cleanup(evidence["evidence_id"], evidence["storage_key"], job.id)


def test_redis_is_reachable():
    assert redis.Redis.from_url(settings.redis_url).ping() is True