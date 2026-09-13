import hashlib
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, TiffImagePlugin

from backend.app.main import app
from backend.db.models import Evidence, EvidenceMetadata
from backend.db.session import get_session
from backend.engines.hashing.sha256 import sha256_digest
from backend.services.fingerprinting import process_evidence
from backend.services.storage import StorageService


client = TestClient(app)


def jpeg_bytes(*, with_exif: bool = False) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (16, 16), color=(20, 120, 220))
    if with_exif:
        exif = image.getexif()
        exif[271] = "Test Make"
        exif[272] = "Test Model"
        exif[306] = "2026:09:13 12:34:56"
        rational = TiffImagePlugin.IFDRational
        exif[34853] = {
            1: "N",
            2: (rational(40, 1), rational(30, 1), rational(0, 1)),
            3: "W",
            4: (rational(74, 1), rational(0, 1), rational(0, 1)),
        }
        image.save(output, format="JPEG", exif=exif.tobytes())
    else:
        image.save(output, format="JPEG")
    return output.getvalue()


def upload(payload: bytes) -> dict:
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("source.jpg", payload, "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def cleanup(evidence_id: str, storage_key: str) -> None:
    storage = StorageService()
    storage.delete_object(storage.quarantine_bucket, storage_key)
    session = get_session()
    session.query(EvidenceMetadata).filter_by(evidence_id=evidence_id).delete()
    session.query(Evidence).filter_by(id=evidence_id).delete()
    session.commit()
    session.close()


def test_sha256_known_value_and_determinism():
    data = b"proof-of-action"
    expected = hashlib.sha256(data).hexdigest()
    assert sha256_digest(data) == expected
    assert sha256_digest(data) == expected
    assert sha256_digest(data + b"!") != expected


def test_fingerprints_use_stored_bytes_and_persist_results():
    payload = jpeg_bytes(with_exif=True)
    body = upload(payload)
    storage = StorageService()
    try:
        stored = storage.get_object_bytes(storage.quarantine_bucket, body["storage_key"])
        assert stored == payload

        session = get_session()
        result = process_evidence(body["evidence_id"], session, storage)
        evidence = session.query(Evidence).filter_by(id=body["evidence_id"]).one()
        metadata = session.query(EvidenceMetadata).filter_by(
            evidence_id=body["evidence_id"]
        ).one()

        assert result.sha256 == hashlib.sha256(payload).hexdigest()
        assert evidence.sha256 == result.sha256
        assert evidence.phash == result.phash
        assert metadata.metadata_json["exif"]["Image Make"] == "Test Make"
        assert metadata.metadata_json["exif"]["Image Model"] == "Test Model"
        assert metadata.metadata_json["exif"]["Image DateTime"] == "2026:09:13 12:34:56"
        assert metadata.metadata_json["exif"]["GPS GPSLatitude"] == "[40, 30, 0]"
        assert metadata.metadata_json["exif"]["GPS GPSLongitude"] == "[74, 0, 0]"
        session.close()

        assert storage.get_object_bytes(storage.quarantine_bucket, body["storage_key"]) == payload
    finally:
        cleanup(body["evidence_id"], body["storage_key"])


def test_missing_exif_is_explicit_and_processing_is_idempotent():
    body = upload(jpeg_bytes())
    storage = StorageService()
    session = get_session()
    try:
        first = process_evidence(body["evidence_id"], session, storage)
        second = process_evidence(body["evidence_id"], session, storage)
        metadata_rows = session.query(EvidenceMetadata).filter_by(
            evidence_id=body["evidence_id"]
        ).all()
        assert first.sha256 == second.sha256
        assert first.phash == second.phash
        assert first.exif == {}
        assert first.exif_status == "no_metadata"
        assert len(metadata_rows) == 1
        assert metadata_rows[0].metadata_json["exif"] == {}
        assert metadata_rows[0].metadata_json["exif_status"] == "no_metadata"
    finally:
        session.close()
        cleanup(body["evidence_id"], body["storage_key"])


def test_phash_failure_does_not_discard_sha256_or_original():
    payload = jpeg_bytes()
    body = upload(payload)
    storage = StorageService()
    session = get_session()
    try:
        with patch("backend.services.fingerprinting.perceptual_hash", side_effect=RuntimeError("pHash failed")):
            result = process_evidence(body["evidence_id"], session, storage)
        evidence = session.query(Evidence).filter_by(id=body["evidence_id"]).one()
        metadata = session.query(EvidenceMetadata).filter_by(
            evidence_id=body["evidence_id"]
        ).one()
        assert result.sha256 == hashlib.sha256(payload).hexdigest()
        assert result.phash is None
        assert evidence.sha256 == result.sha256
        assert evidence.phash is None
        assert metadata.metadata_json["phash_status"] == "failed"
        assert metadata.metadata_json["phash_error"] == "pHash failed"
        assert storage.get_object_bytes(storage.quarantine_bucket, body["storage_key"]) == payload
    finally:
        session.close()
        cleanup(body["evidence_id"], body["storage_key"])