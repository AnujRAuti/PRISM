from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import app
from backend.db.models import (
    Activity,
    AnalysisJob,
    AnalysisResult,
    Claim,
    DuplicateMatch,
    Evidence,
    EvidenceMetadata,
    Project,
    User,
)
from backend.db.session import get_session
from backend.services.analysis_queue import AnalysisQueue
from backend.services.storage import StorageService
from backend.services.temporal_intelligence import (
    capture_upload_consistency,
    claim_window_status,
    compare_pair,
    elapsed_breakdown,
    extract_capture_time,
    order_pair,
)
from backend.workers.analysis_worker import process_message


client = TestClient(app)


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(10, 80, 150)).save(output, format="JPEG")
    return output.getvalue()


def make_user() -> User:
    session = get_session()
    user = User(username=f"be008-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def upload_evidence() -> dict:
    response = client.post(
        "/api/v1/evidence",
        files={"file": ("be008.jpg", image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 201
    return response.json()


def set_capture(evidence_id: str, exif: dict) -> None:
    session = get_session()
    row = session.query(EvidenceMetadata).filter_by(evidence_id=evidence_id).one_or_none()
    payload = {"exif": exif, "exif_status": "success" if exif else "no_metadata"}
    if row is None:
        session.add(EvidenceMetadata(evidence_id=evidence_id, metadata_json=payload))
    else:
        row.metadata_json = payload
    session.commit()
    session.close()


def set_upload_time(evidence_id: str, value: datetime) -> None:
    session = get_session()
    evidence = session.query(Evidence).filter_by(id=evidence_id).one()
    evidence.created_at = value
    session.commit()
    session.close()


def cleanup(user_id=None, project_ids=None, evidence=None, job_ids=None):
    project_ids = project_ids or []
    evidence = evidence or []
    job_ids = job_ids or []
    storage = StorageService()
    session = get_session()
    for item in evidence:
        try:
            if storage.object_exists(storage.quarantine_bucket, item["storage_key"]):
                storage.delete_object(storage.quarantine_bucket, item["storage_key"])
        except Exception:
            pass
    evidence_ids = [item["evidence_id"] for item in evidence]
    if job_ids:
        session.query(AnalysisResult).filter(AnalysisResult.job_id.in_(job_ids)).delete(synchronize_session=False)
        session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(synchronize_session=False)
    if evidence_ids:
        session.query(DuplicateMatch).filter(
            (DuplicateMatch.evidence_id.in_(evidence_ids))
            | (DuplicateMatch.matched_evidence_id.in_(evidence_ids))
        ).delete(synchronize_session=False)
        session.query(EvidenceMetadata).filter(EvidenceMetadata.evidence_id.in_(evidence_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
            {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False
        )
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(synchronize_session=False)
    if project_ids:
        session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
    if user_id is not None:
        session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    session.commit()
    session.close()


def test_timestamp_availability_capture_present_and_absent():
    user = make_user()
    items = [upload_evidence(), upload_evidence()]
    try:
        set_capture(items[0]["evidence_id"], {"EXIF DateTimeOriginal": "2026:01:10 10:00:00"})
        set_capture(items[1]["evidence_id"], {})
        first = client.post(f"/api/v1/analysis/temporal/{items[0]['evidence_id']}", json={})
        second = client.post(f"/api/v1/analysis/temporal/{items[1]['evidence_id']}", json={})
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["captured_at"] is not None
        assert first.json()["captured_source"] == "EXIF DateTimeOriginal"
        assert first.json()["captured_tz_known"] is False
        assert second.json()["captured_at"] is None
        assert second.json()["capture_upload"] == "UNKNOWN"
        assert second.json()["status"] == "unknown"
        # Upload timestamp always present via created_at
        assert first.json()["uploaded_at"] is not None
    finally:
        cleanup(str(user.id), [], items)


def test_ordering_before_after_equal():
    assert order_pair(datetime(2026, 1, 10), datetime(2026, 2, 15)) == "CAPTURED_BEFORE"
    assert order_pair(datetime(2026, 2, 15), datetime(2026, 1, 10)) == "CAPTURED_AFTER"
    assert order_pair(datetime(2026, 2, 15, 10, 0, 0), datetime(2026, 2, 15, 10, 0, 0)) == "SAME_TIME"
    assert order_pair(None, datetime(2026, 2, 15)) == "UNKNOWN"
    assert order_pair(datetime(2026, 2, 15), None) == "UNKNOWN"


def test_evidence_to_evidence_ordering_via_api():
    user = make_user()
    project_id = None
    items = []
    try:
        project = client.post("/api/v1/projects", json={"name": "BE-008 order", "owner_id": str(user.id)}).json()
        project_id = project["id"]
        items = [upload_evidence(), upload_evidence(), upload_evidence()]
        set_capture(items[0]["evidence_id"], {"EXIF DateTimeOriginal": "2026:01:10 10:00:00"})
        set_capture(items[1]["evidence_id"], {"EXIF DateTimeOriginal": "2026:02:15 10:00:00"})
        set_capture(items[2]["evidence_id"], {"EXIF DateTimeOriginal": "2026:02:15 10:00:00"})
        for item in items:
            assert client.patch(
                f"/api/v1/evidence/{item['evidence_id']}/context",
                json={"project_id": project_id},
            ).status_code == 200
        response = client.post(
            f"/api/v1/analysis/temporal/{items[0]['evidence_id']}",
            json={"compare_evidence_ids": [items[1]["evidence_id"], items[2]["evidence_id"]]},
        )
        assert response.status_code == 200
        body = response.json()
        by_other = {rel["other_evidence_id"]: rel["relationship"] for rel in body["relationships"]}
        assert by_other[items[1]["evidence_id"]] == "CAPTURED_BEFORE"
        assert by_other[items[2]["evidence_id"]] == "CAPTURED_BEFORE"
        assert len(body["time_differences"]) == 2
        # Equal timestamps represented explicitly
        equal = client.post(
            f"/api/v1/analysis/temporal/{items[1]['evidence_id']}",
            json={"compare_evidence_ids": [items[2]["evidence_id"]]},
        ).json()
        assert equal["relationships"][0]["relationship"] == "SAME_TIME"
    finally:
        cleanup(str(user.id), [project_id] if project_id else [], items)


def test_capture_upload_consistency_cases():
    upload = datetime(2026, 3, 1, 12, 0, 0)
    assert capture_upload_consistency(datetime(2026, 2, 1, 12, 0, 0), upload) == "TEMPORALLY_CONSISTENT"
    assert capture_upload_consistency(upload, upload) == "TEMPORALLY_CONSISTENT"
    assert capture_upload_consistency(datetime(2026, 4, 1, 12, 0, 0), upload) == "TEMPORAL_INCONSISTENCY"
    assert capture_upload_consistency(None, upload) == "UNKNOWN"


def test_capture_upload_via_api_including_inconsistency():
    user = make_user()
    items = [upload_evidence(), upload_evidence(), upload_evidence()]
    try:
        upload_time = datetime(2026, 3, 1, 12, 0, 0)
        for item in items:
            set_upload_time(item["evidence_id"], upload_time)
        set_capture(items[0]["evidence_id"], {"EXIF DateTimeOriginal": "2026:02:01 12:00:00"})
        set_capture(items[1]["evidence_id"], {"EXIF DateTimeOriginal": "2026:03:01 12:00:00"})
        set_capture(items[2]["evidence_id"], {"EXIF DateTimeOriginal": "2026:04:01 12:00:00"})
        assert client.post(f"/api/v1/analysis/temporal/{items[0]['evidence_id']}", json={}).json()["capture_upload"] == "TEMPORALLY_CONSISTENT"
        assert client.post(f"/api/v1/analysis/temporal/{items[1]['evidence_id']}", json={}).json()["capture_upload"] == "TEMPORALLY_CONSISTENT"
        body = client.post(f"/api/v1/analysis/temporal/{items[2]['evidence_id']}", json={}).json()
        assert body["capture_upload"] == "TEMPORAL_INCONSISTENCY"
        assert body["status"] == "temporal_inconsistency"
        assert body["inconsistencies"] and body["inconsistencies"][0]["type"] == "TEMPORAL_INCONSISTENCY"
    finally:
        cleanup(str(user.id), [], items)


def test_time_difference_units():
    start = datetime(2026, 1, 1, 0, 0, 0)
    assert elapsed_breakdown(start, start + timedelta(seconds=90))["seconds"] == 90
    assert elapsed_breakdown(start, start + timedelta(minutes=5))["minutes"] == 5
    assert elapsed_breakdown(start, start + timedelta(hours=2))["hours"] == 2
    assert elapsed_breakdown(start, start + timedelta(days=36))["days"] == 36
    assert elapsed_breakdown(None, start) is None


def test_timezone_equivalent_offsets_and_unknown():
    aware_plus2 = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    aware_utc = datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc)
    assert order_pair(aware_plus2, aware_utc) == "SAME_TIME"
    gap = elapsed_breakdown(aware_plus2, aware_utc)
    assert gap is not None and gap["seconds"] == 0
    # Naive (tz-unknown) EXIF capture is normalized to UTC wall-clock for
    # comparison; the tz-unknown caveat is disclosed, not hidden.
    assert capture_upload_consistency(
        datetime(2026, 1, 10, 12, 0, 0),
        datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
    ) == "TEMPORALLY_CONSISTENT"
    assert claim_window_status(
        datetime(2026, 1, 10, 12, 0, 0),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    ) == "WITHIN_CLAIM_WINDOW"
    # Missing timestamps still yield UNKNOWN, never guessed
    assert capture_upload_consistency(None, aware_utc) == "UNKNOWN"
    assert claim_window_status(None, aware_utc, aware_utc) == "UNKNOWN"
    # Aware vs aware comparison works
    assert capture_upload_consistency(aware_utc, aware_utc) == "TEMPORALLY_CONSISTENT"


def test_claim_temporal_context_windows_and_missing():
    user = make_user()
    project_id = None
    items = []
    try:
        project = client.post("/api/v1/projects", json={"name": "BE-008 claim", "owner_id": str(user.id)}).json()
        project_id = project["id"]
        claim = client.post(
            f"/api/v1/projects/{project_id}/claims",
            json={
                "title": "Bounded claim",
                "temporal_start_at": "2026-01-01T00:00:00Z",
                "temporal_end_at": "2026-02-01T00:00:00Z",
            },
        )
        assert claim.status_code == 201
        claim_id = claim.json()["id"]
        assert claim.json()["temporal_start_at"] is not None
        unbounded = client.post(f"/api/v1/projects/{project_id}/claims", json={"title": "No bounds"}).json()

        within = upload_evidence()
        before = upload_evidence()
        after = upload_evidence()
        nobounds = upload_evidence()
        items = [within, before, after, nobounds]
        set_capture(within["evidence_id"], {"EXIF DateTimeOriginal": "2026:01:15 10:00:00"})
        set_capture(before["evidence_id"], {"EXIF DateTimeOriginal": "2025:12:15 10:00:00"})
        set_capture(after["evidence_id"], {"EXIF DateTimeOriginal": "2026:03:01 10:00:00"})
        assert claim_window_status(
            datetime(2026, 1, 15, 10, 0, 0), datetime(2026, 1, 1), datetime(2026, 2, 1)
        ) == "WITHIN_CLAIM_WINDOW"
        assert claim_window_status(
            datetime(2025, 12, 15), datetime(2026, 1, 1), datetime(2026, 2, 1)
        ) == "BEFORE_CLAIM_WINDOW"
        assert claim_window_status(
            datetime(2026, 3, 1), datetime(2026, 1, 1), datetime(2026, 2, 1)
        ) == "AFTER_CLAIM_WINDOW"
        assert claim_window_status(None, datetime(2026, 1, 1), datetime(2026, 2, 1)) == "UNKNOWN"
        assert claim_window_status(datetime(2026, 1, 15), None, None) == "UNKNOWN"

        for item in [within, before, after]:
            assert client.patch(
                f"/api/v1/evidence/{item['evidence_id']}/context",
                json={"project_id": project_id, "claim_id": claim_id},
            ).status_code == 200
        assert client.post(f"/api/v1/analysis/temporal/{within['evidence_id']}", json={}).json()["claim_window"] == "WITHIN_CLAIM_WINDOW"
        assert client.post(f"/api/v1/analysis/temporal/{before['evidence_id']}", json={}).json()["claim_window"] == "BEFORE_CLAIM_WINDOW"
        assert client.post(f"/api/v1/analysis/temporal/{after['evidence_id']}", json={}).json()["claim_window"] == "AFTER_CLAIM_WINDOW"
        assert client.patch(
            f"/api/v1/evidence/{nobounds['evidence_id']}/context",
            json={"project_id": project_id, "claim_id": unbounded["id"]},
        ).status_code == 200
        # Claim without bounds -> UNKNOWN, persisted claim has no bounds
        body = client.post(f"/api/v1/analysis/temporal/{nobounds['evidence_id']}", json={}).json()
        assert body["claim_window"] == "UNKNOWN"

        # Explicit null removes a stored boundary
        patched = client.patch(
            f"/api/v1/projects/{project_id}/claims/{claim_id}",
            json={"temporal_start_at": None, "temporal_end_at": None},
        )
        assert patched.status_code == 200
        assert patched.json()["temporal_start_at"] is None
        assert patched.json()["temporal_end_at"] is None

        # Invalid bounds rejected, nothing inferred from title
        invalid = client.post(
            f"/api/v1/projects/{project_id}/claims",
            json={
                "title": "2020 claim",
                "temporal_start_at": "2026-02-01T00:00:00Z",
                "temporal_end_at": "2026-01-01T00:00:00Z",
            },
        )
        assert invalid.status_code == 422
    finally:
        cleanup(str(user.id), [project_id] if project_id else [], items)


def test_project_isolation_and_invalid_ids():
    user = make_user()
    project_ids = []
    items = []
    try:
        project_a = client.post("/api/v1/projects", json={"name": "PA", "owner_id": str(user.id)}).json()
        project_b = client.post("/api/v1/projects", json={"name": "PB", "owner_id": str(user.id)}).json()
        project_ids = [project_a["id"], project_b["id"]]
        items = [upload_evidence(), upload_evidence()]
        set_capture(items[0]["evidence_id"], {"EXIF DateTimeOriginal": "2026:01:10 10:00:00"})
        set_capture(items[1]["evidence_id"], {"EXIF DateTimeOriginal": "2026:02:15 10:00:00"})
        assert client.patch(
            f"/api/v1/evidence/{items[0]['evidence_id']}/context", json={"project_id": project_a["id"]}
        ).status_code == 200
        assert client.patch(
            f"/api/v1/evidence/{items[1]['evidence_id']}/context", json={"project_id": project_b["id"]}
        ).status_code == 200

        session = get_session()
        pair = compare_pair(items[0]["evidence_id"], items[1]["evidence_id"], session)
        session.close()
        assert pair["relationship"] == "UNKNOWN"
        assert pair["reason"] == "different_projects"

        via_api = client.post(
            f"/api/v1/analysis/temporal/{items[0]['evidence_id']}",
            json={"compare_evidence_ids": [items[1]["evidence_id"]]},
        ).json()
        assert via_api["relationships"] == []

        missing = client.post(f"/api/v1/analysis/temporal/{uuid4()}", json={})
        assert missing.status_code == 404
        assert client.post("/api/v1/analysis/temporal/not-a-uuid", json={}).status_code == 422
        assert client.post(
            f"/api/v1/analysis/temporal/{items[0]['evidence_id']}",
            json={"compare_evidence_ids": ["not-a-uuid"]},
        ).status_code == 422
        try:
            session = get_session()
            compare_pair(items[0]["evidence_id"], str(uuid4()), session)
            raise AssertionError("expected LookupError")
        except LookupError:
            pass
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, items)


def test_api_response_structure_and_persistence():
    user = make_user()
    items = [upload_evidence()]
    job_ids = []
    try:
        set_capture(items[0]["evidence_id"], {"EXIF DateTimeOriginal": "2026:01:10 10:00:00"})
        body = client.post(f"/api/v1/analysis/temporal/{items[0]['evidence_id']}", json={})
        assert body.status_code == 200
        payload = body.json()
        for key in (
            "evidence_id",
            "captured_at",
            "uploaded_at",
            "capture_upload",
            "claim_window",
            "relationships",
            "time_differences",
            "inconsistencies",
            "status",
        ):
            assert key in payload
        assert payload["status"] in ("temporally_consistent", "temporal_inconsistency", "unknown")
        assert "risk" not in payload and "integrity" not in payload and "confidence" not in payload

        # Worker persists temporal output inside the existing AnalysisResult
        created = client.post("/api/v1/analysis/jobs", json={"evidence_id": items[0]["evidence_id"]})
        assert created.status_code == 202
        job_ids.append(created.json()["job_id"])
        queue = AnalysisQueue()
        message = queue.dequeue(timeout=2)
        assert message is not None
        assert process_message(message, queue) == "completed"
        queue.clear()
        stored = client.get(f"/api/v1/analysis/jobs/{job_ids[0]}").json()
        assert stored["result"]["temporal_analysis"]["status"] in (
            "temporally_consistent",
            "temporal_inconsistency",
            "unknown",
        )
        assert stored["result"]["temporal_analysis"]["capture_upload"] in (
            "TEMPORALLY_CONSISTENT",
            "TEMPORAL_INCONSISTENCY",
            "UNKNOWN",
        )
    finally:
        queue = AnalysisQueue()
        try:
            queue.clear()
        except Exception:
            pass
        cleanup(str(user.id), [], items, job_ids)


def test_exif_priority_and_no_fabrication():
    capture = extract_capture_time({"Image DateTime": "2026:09:13 12:34:56"})
    assert capture.value == datetime(2026, 9, 13, 12, 34, 56)
    assert capture.tz_known is False
    assert extract_capture_time({}).value is None
    assert extract_capture_time({"Image DateTime": "not-a-date"}).value is None
