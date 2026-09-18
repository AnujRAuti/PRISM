"""BE-009 integration tests: real YOLO inference over real evidence images."""

import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import AnalysisJob, AnalysisResult, Evidence, VisionDetection
from backend.db.session import get_session
from backend.services.analysis_queue import AnalysisQueue
from backend.services.storage import StorageService
from backend.services.vision_intelligence import analyze_vision
from backend.workers.analysis_worker import process_message


client = TestClient(app)
FIXTURE_PHOTO = Path(__file__).parents[2] / "test-image.jpg"


def photo_bytes() -> bytes:
    return FIXTURE_PHOTO.read_bytes()


def blank_bytes(size: tuple[int, int] = (640, 480)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(128, 128, 128)).save(output, format="JPEG")
    return output.getvalue()


def upload(data: bytes, filename: str, content_type: str = "image/jpeg") -> dict:
    response = client.post(
        "/api/v1/evidence",
        files={"file": (filename, data, content_type)},
    )
    assert response.status_code == 201
    return response.json()


def cleanup(evidence_id: str, storage_key: str, job_ids: list[str] | None = None) -> None:
    storage = StorageService()
    if storage.object_exists(storage.quarantine_bucket, storage_key):
        storage.delete_object(storage.quarantine_bucket, storage_key)
    session = get_session()
    try:
        if job_ids:
            result_ids = [
                row[0]
                for row in session.query(AnalysisResult.id)
                .filter(AnalysisResult.job_id.in_(job_ids))
                .all()
            ]
            if result_ids:
                session.query(VisionDetection).filter(
                    VisionDetection.analysis_result_id.in_(result_ids)
                ).delete(synchronize_session=False)
            session.query(AnalysisResult).filter(AnalysisResult.job_id.in_(job_ids)).delete(
                synchronize_session=False
            )
            session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(
                synchronize_session=False
            )
        session.query(Evidence).filter_by(id=evidence_id).delete()
        session.commit()
    finally:
        session.close()


def run_job_to_completion(queue: AnalysisQueue, job_id: str) -> str:
    message = queue.dequeue(timeout=5)
    assert message is not None
    assert message.job_id == job_id
    return process_message(message, queue)


def test_vision_job_runs_real_inference_and_persists_observations():
    assert FIXTURE_PHOTO.exists(), "test-image.jpg fixture is required"
    evidence = upload(photo_bytes(), "street.jpg")
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    try:
        response = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        assert run_job_to_completion(queue, job_id) == "completed"

        status_response = client.get(f"/api/v1/analysis/jobs/{job_id}")
        assert status_response.status_code == 200
        result = status_response.json()["result"]
        assert result["analysis_type"] == "vision_detection"
        assert result["model"]["name"] == settings.vision_model_name
        assert result["model"]["device"] in {"cpu", "cuda"}
        assert result["image"] == {"width": 640, "height": 479}
        assert result["detection_count"] >= 1
        assert result["status"] == "success"
        assert not (set(result) & {"fraud_score", "risk_score", "authenticity_score", "trust_score", "compliance_score"})

        session = get_session()
        try:
            rows = (
                session.query(VisionDetection)
                .join(AnalysisResult, AnalysisResult.id == VisionDetection.analysis_result_id)
                .filter(AnalysisResult.job_id == job_id)
                .all()
            )
            assert len(rows) == result["detection_count"]
            for row in rows:
                assert row.confidence >= settings.vision_conf_threshold
                assert 0.0 <= row.x_min < row.x_max <= 1.0
                assert 0.0 <= row.y_min < row.y_max <= 1.0
                assert row.class_name
        finally:
            session.close()
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], [job_id] if job_id else None)


def test_vision_retrieval_endpoint_with_pagination_and_provenance():
    evidence = upload(photo_bytes(), "street-page.jpg")
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    try:
        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        assert run_job_to_completion(queue, job_id) == "completed"

        full = client.get(f"/api/v1/evidence/{evidence['evidence_id']}/vision")
        assert full.status_code == 200
        body = full.json()
        assert body["evidence_id"] == evidence["evidence_id"]
        assert body["job_id"] == job_id
        assert body["result"]["model"]["name"] == settings.vision_model_name
        assert body["total"] == body["result"]["detection_count"] >= 1

        page = client.get(
            f"/api/v1/evidence/{evidence['evidence_id']}/vision",
            params={"limit": 1, "offset": 0},
        )
        assert page.status_code == 200
        page_body = page.json()
        assert page_body["total"] == body["total"]
        assert len(page_body["detections"]) == 1
        box = page_body["detections"][0]["bounding_box"]
        assert 0.0 <= box["x_min"] < box["x_max"] <= 1.0
        assert 0.0 <= box["y_min"] < box["y_max"] <= 1.0
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], [job_id] if job_id else None)


def test_vision_rerun_is_idempotent():
    evidence = upload(photo_bytes(), "street-rerun.jpg")
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    try:
        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        assert run_job_to_completion(queue, job_id) == "completed"

        session = get_session()
        try:
            first = analyze_vision(evidence["evidence_id"], session, StorageService(), job_id)
            second = analyze_vision(evidence["evidence_id"], session, StorageService(), job_id)
            assert first.result_id == second.result_id
            assert session.query(AnalysisResult).filter_by(job_id=job_id).count() == 1
            assert (
                session.query(VisionDetection)
                .filter_by(analysis_result_id=first.result_id)
                .count()
                == second.detection_count
            )
        finally:
            session.close()
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], [job_id] if job_id else None)


def test_vision_blank_image_yields_honest_empty_success():
    evidence = upload(blank_bytes(), "blank.jpg")
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    try:
        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        assert run_job_to_completion(queue, job_id) == "completed"
        result = client.get(f"/api/v1/analysis/jobs/{job_id}").json()["result"]
        assert result["status"] == "success"
        assert result["detection_count"] == 0
        body = client.get(f"/api/v1/evidence/{evidence['evidence_id']}/vision").json()
        assert body["total"] == 0
        assert body["detections"] == []
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], [job_id] if job_id else None)


def test_vision_missing_object_fails_without_success_result():
    evidence = upload(photo_bytes(), "doomed.jpg")
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    storage = StorageService()
    storage.delete_object(storage.quarantine_bucket, evidence["storage_key"])
    try:
        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        outcomes = []
        for _ in range(settings.analysis_max_attempts):
            message = queue.dequeue(timeout=5)
            assert message is not None
            outcomes.append(process_message(message, queue))
        assert outcomes == ["retry", "retry", "failed"]
        status_body = client.get(f"/api/v1/analysis/jobs/{job_id}").json()
        assert status_body["status"] == "failed"
        assert status_body["result"] is None
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], [job_id] if job_id else None)


def test_fingerprint_jobs_still_work_after_vision_integration():
    evidence = upload(photo_bytes(), "fingerprint-still.jpg")
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    try:
        response = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"]},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert run_job_to_completion(queue, job_id) == "completed"
        result = client.get(f"/api/v1/analysis/jobs/{job_id}").json()["result"]
        assert result["sha256"]
        assert result["phash"]
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], [job_id] if job_id else None)


def test_vision_api_validation():
    assert client.get("/api/v1/evidence/not-a-uuid/vision").status_code == 422
    assert client.get(f"/api/v1/evidence/{uuid4()}/vision").status_code == 404
    assert (
        client.post("/api/v1/analysis/jobs", json={"evidence_id": str(uuid4()), "job_type": "vision"}).status_code
        == 404
    )
    evidence = upload(photo_bytes(), "no-vision-yet.jpg")
    try:
        assert client.get(f"/api/v1/evidence/{evidence['evidence_id']}/vision").status_code == 404
        bad_type = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "segmentation"},
        )
        assert bad_type.status_code == 422
    finally:
        cleanup(evidence["evidence_id"], evidence["storage_key"], None)


def test_vision_result_contains_no_verdict_fields():
    evidence = upload(photo_bytes(), "no-verdict.jpg")
    queue = AnalysisQueue()
    queue.clear()
    job_id = None
    try:
        job_id = client.post(
            "/api/v1/analysis/jobs",
            json={"evidence_id": evidence["evidence_id"], "job_type": "vision"},
        ).json()["job_id"]
        assert run_job_to_completion(queue, job_id) == "completed"
        raw = client.get(f"/api/v1/analysis/jobs/{job_id}").json()["result"]
        serialized = json.dumps(raw).lower()
        for forbidden in ("fraud", "risk_score", "authenticity", "trust_score", "compliance", "verdict"):
            assert forbidden not in serialized
    finally:
        queue.clear()
        cleanup(evidence["evidence_id"], evidence["storage_key"], [job_id] if job_id else None)
