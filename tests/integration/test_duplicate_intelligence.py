from io import BytesIO

from PIL import Image

from backend.db.models import DuplicateMatch, Evidence, EvidenceMetadata
from backend.db.session import get_session
from backend.services.duplicate_intelligence import analyze_duplicates, phash_distance
from backend.services.fingerprinting import process_evidence
from backend.services.storage import StorageService


def image_bytes(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def upload(data: bytes, filename: str) -> dict:
    from fastapi.testclient import TestClient
    from backend.app.main import app

    response = TestClient(app).post(
        "/api/v1/evidence",
        files={"file": (filename, data, "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def cleanup(items: list[dict]) -> None:
    storage = StorageService()
    session = get_session()
    ids = [item["evidence_id"] for item in items]
    for item in items:
        if storage.object_exists(storage.quarantine_bucket, item["storage_key"]):
            storage.delete_object(storage.quarantine_bucket, item["storage_key"])
    session.query(DuplicateMatch).filter(
        DuplicateMatch.evidence_id.in_(ids) | DuplicateMatch.matched_evidence_id.in_(ids)
    ).delete(synchronize_session=False)
    session.query(EvidenceMetadata).filter(EvidenceMetadata.evidence_id.in_(ids)).delete(
        synchronize_session=False
    )
    session.query(Evidence).filter(Evidence.id.in_(ids)).delete(synchronize_session=False)
    session.commit()
    session.close()


def test_exact_sha_match_and_phash_distance_are_persisted_idempotently():
    payload = image_bytes((20, 100, 200))
    first = upload(payload, "first.jpg")
    second = upload(payload, "second.jpg")
    session = get_session()
    try:
        for item in (first, second):
            process_evidence(item["evidence_id"], session)

        first_evidence = session.query(Evidence).filter_by(id=first["evidence_id"]).one()
        second_evidence = session.query(Evidence).filter_by(id=second["evidence_id"]).one()
        assert phash_distance(first_evidence.phash, second_evidence.phash) == 0
        result = analyze_duplicates(first["evidence_id"], session)
        assert second["evidence_id"] in result.exact_matches
        assert any(match["evidence_id"] == second["evidence_id"] for match in result.perceptual_matches)
        analyze_duplicates(first["evidence_id"], session)
        assert session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id == min(first["evidence_id"], second["evidence_id"]),
            DuplicateMatch.matched_evidence_id == max(first["evidence_id"], second["evidence_id"]),
        ).count() == 1
    finally:
        session.close()
        cleanup([first, second])