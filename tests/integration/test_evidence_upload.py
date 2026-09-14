from io import BytesIO
from uuid import UUID
from urllib.request import urlopen

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import Evidence
from backend.db.session import get_session
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(20, 120, 220)).save(output, format=image_format)
    return output.getvalue()


def remove_evidence(evidence_id: str) -> None:
    session = get_session()
    evidence = session.query(Evidence).filter_by(id=evidence_id).one_or_none()
    if evidence:
        session.delete(evidence)
        session.commit()
    session.close()


def test_valid_jpeg_upload_persists_database_and_object():
    payload = image_bytes("JPEG")
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("proof.jpg", payload, "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    evidence_id = body["evidence_id"]
    assert str(UUID(evidence_id)) == evidence_id
    assert body["status"] == "uploaded"
    assert body["content_type"] == "image/jpeg"
    assert body["size"] == len(payload)
    assert body["storage_key"] == f"quarantine/{evidence_id}/original"

    storage = StorageService()
    try:
        assert storage.object_exists(storage.quarantine_bucket, body["storage_key"])
        download_url = storage.create_presigned_download_url(
            storage.quarantine_bucket, body["storage_key"]
        )
        with urlopen(download_url, timeout=10) as downloaded:
            assert downloaded.read() == payload

        session = get_session()
        evidence = session.query(Evidence).filter_by(id=evidence_id).one()
        assert evidence.storage_key == body["storage_key"]
        assert evidence.file_size == len(payload)
        assert evidence.content_type == "image/jpeg"
        assert evidence.status == "uploaded_quarantine"
        session.close()
    finally:
        storage.delete_object(storage.quarantine_bucket, body["storage_key"])
        remove_evidence(evidence_id)


@pytest.mark.parametrize(
    ("filename", "content_type", "image_format"),
    [
        ("proof.png", "image/png", "PNG"),
        ("proof.webp", "image/webp", "WEBP"),
    ],
)
def test_supported_image_uploads(filename, content_type, image_format):
    payload = image_bytes(image_format)
    response = client.post(
        "/api/v1/evidence",
        files={"file": (filename, payload, content_type)},
    )
    if image_format == "WEBP" and response.status_code == 415:
        pytest.skip("Pillow WebP support is unavailable")
    assert response.status_code == 201
    body = response.json()
    assert body["content_type"] == content_type
    assert body["size"] == len(payload)
    assert body["storage_key"].startswith(f"quarantine/{body['evidence_id']}/")
    StorageService().delete_object(StorageService().quarantine_bucket, body["storage_key"])
    remove_evidence(body["evidence_id"])


@pytest.mark.parametrize(
    ("filename", "content_type", "payload", "expected_status"),
    [
        ("empty.jpg", "image/jpeg", b"", 400),
        ("notes.txt", "text/plain", b"not an image", 415),
        ("fake.jpg", "image/jpeg", b"not an image", 415),
    ],
)
def test_invalid_uploads_are_rejected(filename, content_type, payload, expected_status):
    response = client.post(
        "/api/v1/evidence",
        files={"file": (filename, payload, content_type)},
    )
    assert response.status_code == expected_status


def test_mime_mismatch_is_rejected():
    payload = image_bytes("PNG")
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("proof.png", payload, "image/jpeg")},
    )
    assert response.status_code == 415
    assert "Content-Type" in response.json()["detail"]


def test_oversized_upload_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size", 32)
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("large.jpg", image_bytes("JPEG"), "image/jpeg")},
    )
    assert response.status_code == 413


def test_truncated_signature_is_rejected():
    payload = b"\xff\xd8\xff" + b"\x00" * 64
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("truncated.jpg", payload, "image/jpeg")},
    )
    assert response.status_code == 415


def test_filename_path_traversal_does_not_control_storage_key():
    payload = image_bytes("PNG")
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("../../evil.jpg", payload, "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["storage_key"] == f"quarantine/{body['evidence_id']}/original"
    assert "evil" not in body["storage_key"]
    StorageService().delete_object(StorageService().quarantine_bucket, body["storage_key"])
    remove_evidence(body["evidence_id"])