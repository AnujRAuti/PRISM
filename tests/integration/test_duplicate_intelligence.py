from io import BytesIO

from PIL import Image

from backend.db.models import AnalysisJob, AnalysisResult, DuplicateMatch, Evidence, EvidenceMetadata
from backend.db.session import get_session
from backend.services.duplicate_intelligence import analyze_duplicates, phash_distance, search_similar_embeddings
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
    job_ids = [row[0] for row in session.query(AnalysisJob.id).filter(AnalysisJob.evidence_id.in_(ids)).all()]
    if job_ids:
        session.query(AnalysisResult).filter(AnalysisResult.job_id.in_(job_ids)).delete(
            synchronize_session=False
        )
        session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(
            synchronize_session=False
        )
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


def test_real_embedding_search_persists_semantic_candidate_and_similarity():
    first = upload(image_bytes((80, 120, 200)), "semantic-first.jpg")
    second = upload(image_bytes((80, 120, 200)), "semantic-second.jpg")
    storage = StorageService()
    session = get_session()
    try:
        first_job = AnalysisJob(evidence_id=first["evidence_id"], status="running")
        second_job = AnalysisJob(evidence_id=second["evidence_id"], status="running")
        session.add_all([first_job, second_job])
        session.commit()
        session.refresh(first_job)
        session.refresh(second_job)

        process_evidence(first["evidence_id"], session, storage)
        analyze_duplicates(first["evidence_id"], session, storage, first_job.id)
        process_evidence(second["evidence_id"], session, storage)
        analysis = analyze_duplicates(second["evidence_id"], session, storage, second_job.id)

        first_result = session.query(AnalysisResult).filter_by(job_id=first_job.id).one()
        second_result = session.query(AnalysisResult).filter_by(job_id=second_job.id).one()
        assert len(first_result.embedding) == 512
        assert len(second_result.embedding) == 512
        assert any(match["evidence_id"] == first["evidence_id"] for match in analysis.semantic_matches)
        assert all(match["evidence_id"] != second["evidence_id"] for match in analysis.semantic_matches)

        pair = session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id == min(first["evidence_id"], second["evidence_id"]),
            DuplicateMatch.matched_evidence_id == max(first["evidence_id"], second["evidence_id"]),
        ).one()
        candidate = next(
            match for match in analysis.semantic_matches if match["evidence_id"] == first["evidence_id"]
        )
        assert pair.embedding_similarity == 1.0 - candidate["distance"]
        assert pair.signals["embedding_distance"] == candidate["distance"]
        assert pair.signals["embedding_similarity"] == pair.embedding_similarity
        assert session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id == min(first["evidence_id"], second["evidence_id"]),
            DuplicateMatch.matched_evidence_id == max(first["evidence_id"], second["evidence_id"]),
        ).count() == 1
    finally:
        session.close()
        cleanup([first, second])


def test_latest_embedding_selection_is_deterministic_when_created_at_ties():
    anchor = upload(image_bytes((60, 80, 150)), "anchor-tie.jpg")
    neighbor = upload(image_bytes((60, 81, 151)), "neighbor-tie.jpg")
    storage = StorageService()
    session = get_session()
    try:
        anchor_job_1 = AnalysisJob(evidence_id=anchor["evidence_id"], status="completed")
        anchor_job_2 = AnalysisJob(evidence_id=anchor["evidence_id"], status="completed")
        neighbor_job = AnalysisJob(evidence_id=neighbor["evidence_id"], status="completed")
        session.add_all([anchor_job_1, anchor_job_2, neighbor_job])
        session.commit()
        session.refresh(anchor_job_1)
        session.refresh(anchor_job_2)
        session.refresh(neighbor_job)

        shared_time = session.query(AnalysisJob.created_at).first()[0]
        # Non-zero, non-parallel vectors so pgvector cosine distances are
        # well-defined (no NaN) and deterministically ordered.
        anchor_result_1 = AnalysisResult(
            job_id=anchor_job_1.id, embedding=[1.0] + [0.0] * 511, created_at=shared_time
        )
        anchor_result_2 = AnalysisResult(
            job_id=anchor_job_2.id, embedding=[0.0, 1.0] + [0.0] * 510, created_at=shared_time
        )
        neighbor_result = AnalysisResult(
            job_id=neighbor_job.id, embedding=[0.0, 0.0, 1.0] + [0.0] * 509, created_at=shared_time
        )
        session.add_all([anchor_result_1, anchor_result_2, neighbor_result])
        session.commit()
        session.refresh(anchor_result_1)
        session.refresh(anchor_result_2)

        candidates = search_similar_embeddings([0.0, 1.0] + [0.0] * 510, session, top_k=10)
        evidence_ids = [row["evidence_id"] for row in candidates]
        assert evidence_ids.count(anchor["evidence_id"]) == 1
        assert anchor["evidence_id"] in evidence_ids
        # The tied latest selection must be deterministic: created_at DESC,
        # result id DESC, so the winner is the tied result with the greater id.
        expected = anchor_result_2 if anchor_result_2.id > anchor_result_1.id else anchor_result_1
        anchor_match = next(row for row in candidates if row["evidence_id"] == anchor["evidence_id"])
        assert anchor_match["job_id"] == expected.job_id
        repeat = search_similar_embeddings([0.0, 1.0] + [0.0] * 510, session, top_k=10)
        assert repeat == candidates
    finally:
        session.close()
        cleanup([anchor, neighbor])