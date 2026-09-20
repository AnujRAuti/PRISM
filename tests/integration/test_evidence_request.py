"""BE-014 integration tests against real PostgreSQL infrastructure."""

import threading
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
    CaseGenerationConfiguration,
    CaseGenerationRun,
    Claim,
    DuplicateMatch,
    Evidence,
    EvidenceMetadata,
    EvidenceRequest,
    EvidenceRequestEvent,
    EvidenceRequestItem,
    FusionRun,
    FusionSignal,
    GraphNode,
    GraphRelationship,
    IntegrityAssessment,
    Project,
    ReviewCase,
    ReviewCaseEvent,
    ReviewPriority,
    User,
    VisionDetection,
)
from backend.db.session import get_session
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes(color=(80, 150, 220)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be014-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def api_create_project(user_id: str, name: str = "BE-014 project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": user_id})
    assert response.status_code == 201
    return response.json()


def api_upload(data: bytes, filename: str) -> dict:
    response = client.post("/api/v1/evidence", files={"file": (filename, data, "image/jpeg")})
    assert response.status_code == 201
    return response.json()


def link_evidence(evidence_id: str, project_id: str) -> None:
    session = get_session()
    try:
        evidence = session.query(Evidence).filter_by(id=evidence_id).one()
        evidence.project_id = project_id
        session.commit()
    finally:
        session.close()


def make_case(user_id: str, color=(81, 151, 221)):
    """Project + duplicate/temporal URGENT evidence + fused review case."""
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence

    project = api_create_project(user_id)
    payload = image_bytes(color)
    first = api_upload(payload, f"req-{uuid4().hex[:8]}.jpg")
    second = api_upload(payload, f"req-{uuid4().hex[:8]}.jpg")
    link_evidence(first["evidence_id"], project["id"])
    link_evidence(second["evidence_id"], project["id"])
    session = get_session()
    try:
        process_evidence(first["evidence_id"], session)
        process_evidence(second["evidence_id"], session)
        analyze_duplicates(first["evidence_id"], session)
        metadata = session.query(EvidenceMetadata).filter_by(evidence_id=first["evidence_id"]).one()
        metadata.metadata_json = {
            **(metadata.metadata_json or {}),
            "exif": {"EXIF DateTimeOriginal": "2030-01-01 10:00:00"},
        }
        session.commit()
    finally:
        session.close()
    run = client.post(f"/api/v1/fusion/EVIDENCE/{first['evidence_id']}", json={}).json()["run"]
    case = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={}).json()["case"]
    return project, first, second, run, case


def create_request(case_id: str, recipient: str | None = None, **overrides):
    payload = {
        "review_case_id": case_id,
        "recipient_id": recipient or str(uuid4()),
        "instructions": "Provide a wide-angle photo of the completed installation.",
        "items": [{"description": "wide-angle photo", "required": True}],
    }
    payload.update(overrides)
    return client.post("/api/v1/evidence-requests", json=payload)


def cleanup(user_id, project_ids, evidence_ids) -> None:
    storage = StorageService()
    session = get_session()
    try:
        keys = [
            row[0]
            for row in session.query(Evidence.storage_key)
            .filter(Evidence.id.in_(evidence_ids))
            .all()
        ]
        for key in keys:
            if storage.object_exists(storage.quarantine_bucket, key):
                storage.delete_object(storage.quarantine_bucket, key)
        request_ids = [
            row[0]
            for row in session.query(EvidenceRequest.id)
            .filter(
                EvidenceRequest.project_id.in_(project_ids) if project_ids
                else EvidenceRequest.id.is_(None)
            )
            .all()
        ]
        case_ids = [
            row[0] for row in session.query(ReviewCase.id)
            .filter(ReviewCase.project_id.in_(project_ids) if project_ids else ReviewCase.id.is_(None))
            .all()
        ]
        if case_ids:
            extra = [
                row[0] for row in session.query(EvidenceRequest.id)
                .filter(EvidenceRequest.review_case_id.in_(case_ids)).all()
            ]
            request_ids = list(set(request_ids) | set(extra))
        if request_ids:
            session.query(EvidenceRequestEvent).filter(
                EvidenceRequestEvent.request_id.in_(request_ids)).delete(synchronize_session=False)
            session.query(EvidenceRequestItem).filter(
                EvidenceRequestItem.request_id.in_(request_ids)).delete(synchronize_session=False)
            session.query(EvidenceRequest).filter(EvidenceRequest.id.in_(request_ids)).delete(
                synchronize_session=False)
        if case_ids:
            session.query(ReviewCaseEvent).filter(ReviewCaseEvent.case_id.in_(case_ids)).delete(
                synchronize_session=False)
            session.query(ReviewCase).filter(ReviewCase.id.in_(case_ids)).delete(
                synchronize_session=False)
        run_ids = [
            row[0] for row in session.query(FusionRun.id)
            .filter(FusionRun.target_id.in_(evidence_ids)).all()
        ]
        if run_ids:
            session.query(CaseGenerationRun).filter(
                CaseGenerationRun.fusion_run_id.in_(run_ids)).delete(synchronize_session=False)
            session.query(FusionSignal).filter(FusionSignal.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False)
            session.query(IntegrityAssessment).filter(
                IntegrityAssessment.fusion_run_id.in_(run_ids)).delete(synchronize_session=False)
            session.query(ReviewPriority).filter(ReviewPriority.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False)
            session.query(FusionRun).filter(FusionRun.id.in_(run_ids)).delete(synchronize_session=False)
        job_ids = [
            row[0]
            for row in session.query(AnalysisJob.id).filter(AnalysisJob.evidence_id.in_(evidence_ids)).all()
        ]
        entity_ids = list(evidence_ids) + list(project_ids) + job_ids
        if job_ids:
            entity_ids.extend(
                row[0]
                for row in session.query(AnalysisResult.id).filter(AnalysisResult.job_id.in_(job_ids)).all()
            )
        entity_ids.extend(
            row[0]
            for row in session.query(DuplicateMatch.id)
            .filter(
                DuplicateMatch.evidence_id.in_(evidence_ids)
                | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
            )
            .all()
        )
        node_ids = [
            row[0] for row in session.query(GraphNode.id).filter(GraphNode.entity_id.in_(entity_ids)).all()
        ]
        if node_ids:
            session.query(GraphRelationship).filter(
                GraphRelationship.source_node_id.in_(node_ids)
                | GraphRelationship.target_node_id.in_(node_ids)
            ).delete(synchronize_session=False)
            session.query(GraphNode).filter(GraphNode.id.in_(node_ids)).delete(synchronize_session=False)
        if job_ids:
            session.query(AnalysisResult).filter(AnalysisResult.job_id.in_(job_ids)).delete(
                synchronize_session=False)
            session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(synchronize_session=False)
        session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id.in_(evidence_ids)
            | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        session.query(EvidenceMetadata).filter(EvidenceMetadata.evidence_id.in_(evidence_ids)).delete(
            synchronize_session=False)
        session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
            {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
        session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_creation_open_and_draft_states():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])

        created = create_request(case["id"])
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "OPEN"
        assert body["review_case_id"] == case["id"]
        assert body["project_id"] == project["id"]
        assert len(body["items"]) == 1
        assert body["items"][0]["item_status"] == "REQUESTED"
        assert body["items"][0]["required"] is True

        draft = create_request(case["id"], issue=False)
        assert draft.json()["status"] == "DRAFT"
        issued = client.post(f"/api/v1/evidence-requests/{draft.json()['id']}/issue")
        assert issued.json()["status"] == "OPEN"

        history = client.get(f"/api/v1/evidence-requests/{body['id']}/history").json()
        assert [e["event_type"] for e in history["items"]] == ["REQUEST_CREATED", "REQUEST_ISSUED"]

        # Validation: missing instructions/items/recipient/case.
        assert create_request(case["id"], instructions="  ").status_code == 422
        assert create_request(case["id"], items=[]).status_code == 422
        assert create_request(case["id"], recipient_id="nope").status_code == 422
        assert create_request(str(uuid4())).status_code == 404
        assert create_request(case["id"], due_at="2030-01-01T00:00:00").status_code == 422
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_full_lifecycle_to_fulfilled():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (82, 152, 222))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        request_id = create_request(
            case["id"], items=[
                {"description": "front view", "required": True},
                {"description": "rear view", "required": True},
                {"description": "context (optional)", "required": False},
            ],
        ).json()["id"]

        assert client.post(f"/api/v1/evidence-requests/{request_id}/acknowledge").json()["status"] \
            == "ACKNOWLEDGED"
        # Idempotent re-acknowledge: no new event.
        before = client.get(f"/api/v1/evidence-requests/{request_id}/history").json()["total"]
        client.post(f"/api/v1/evidence-requests/{request_id}/acknowledge")
        after = client.get(f"/api/v1/evidence-requests/{request_id}/history").json()["total"]
        assert before == after

        extra_a = api_upload(image_bytes((1, 2, 3)), "fill-a.jpg")
        extra_b = api_upload(image_bytes((4, 5, 6)), "fill-b.jpg")
        evidence_ids.extend([extra_a["evidence_id"], extra_b["evidence_id"]])
        link_evidence(extra_a["evidence_id"], project["id"])
        link_evidence(extra_b["evidence_id"], project["id"])

        link_a = client.post(f"/api/v1/evidence-requests/{request_id}/evidence/{extra_a['evidence_id']}")
        assert link_a.status_code == 201
        assert link_a.json()["item"]["item_status"] == "RECEIVED"
        # Re-link is idempotent.
        relink = client.post(f"/api/v1/evidence-requests/{request_id}/evidence/{extra_a['evidence_id']}")
        assert relink.status_code == 200
        assert relink.json()["created"] is False

        item_id = link_a.json()["item"]["id"]
        accepted = client.post(f"/api/v1/evidence-requests/{request_id}/items/{item_id}/accept")
        assert accepted.json()["item_status"] == "ACCEPTED_FOR_REQUEST"
        assert client.get(f"/api/v1/evidence-requests/{request_id}").json()["status"] \
            == "PARTIALLY_FULFILLED"

        link_b = client.post(f"/api/v1/evidence-requests/{request_id}/evidence/{extra_b['evidence_id']}")
        client.post(f"/api/v1/evidence-requests/{request_id}/items/{link_b.json()['item']['id']}/accept")
        final = client.get(f"/api/v1/evidence-requests/{request_id}").json()
        assert final["status"] == "FULFILLED"

        # Fulfillment changes nothing about the case or analytics.
        case_body = client.get(f"/api/v1/review-cases/{case['id']}").json()
        assert case_body["status"] == "OPEN"
        assert case_body["decision"] is None

        events = client.get(f"/api/v1/evidence-requests/{request_id}/history").json()["items"]
        assert [e["event_type"] for e in events] == [
            "REQUEST_CREATED", "REQUEST_ISSUED", "REQUEST_ACKNOWLEDGED",
            "EVIDENCE_LINKED", "ITEM_ACCEPTED", "PARTIAL_FULFILLMENT",
            "EVIDENCE_LINKED", "ITEM_ACCEPTED", "FULFILLED",
        ]
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_rejected_items_do_not_fulfill_and_evidence_stays_valid():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (83, 153, 223))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        request_id = create_request(case["id"]).json()["id"]
        extra = api_upload(image_bytes((7, 8, 9)), "rej.jpg")
        evidence_ids.append(extra["evidence_id"])
        link_evidence(extra["evidence_id"], project["id"])

        item_id = client.post(
            f"/api/v1/evidence-requests/{request_id}/evidence/{extra['evidence_id']}"
        ).json()["item"]["id"]
        rejected = client.post(f"/api/v1/evidence-requests/{request_id}/items/{item_id}/reject")
        assert rejected.json()["item_status"] == "REJECTED_FOR_REQUEST"
        assert client.get(f"/api/v1/evidence-requests/{request_id}").json()["status"] == "OPEN"
        # Rejected evidence remains a valid, usable evidence object.
        session = get_session()
        try:
            assert session.query(Evidence).filter_by(id=extra["evidence_id"]).one() is not None
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_decline_cancel_expire_rules():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (84, 154, 224))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])

        request_id = create_request(case["id"]).json()["id"]
        assert client.post(
            f"/api/v1/evidence-requests/{request_id}/decline", json={"reason": "  "}
        ).status_code == 422
        declined = client.post(
            f"/api/v1/evidence-requests/{request_id}/decline", json={"reason": "duplicate coverage"}
        )
        assert declined.json()["status"] == "DECLINED"
        # Terminal: nothing further allowed.
        assert client.post(f"/api/v1/evidence-requests/{request_id}/acknowledge").status_code == 422
        assert client.post(f"/api/v1/evidence-requests/{request_id}/cancel").status_code == 422

        draft_id = create_request(case["id"], issue=False).json()["id"]
        assert client.post(f"/api/v1/evidence-requests/{draft_id}/cancel").json()["status"] == "CANCELLED"

        past_id = create_request(
            case["id"], due_at="2020-01-01T00:00:00+00:00").json()["id"]
        assert client.post(f"/api/v1/evidence-requests/{past_id}/expire").json()["status"] == "EXPIRED"
        nodue_id = create_request(case["id"]).json()["id"]
        assert client.post(f"/api/v1/evidence-requests/{nodue_id}/expire").status_code == 422
        # Second expiration is idempotent.
        assert client.post(f"/api/v1/evidence-requests/{past_id}/expire").json()["status"] == "EXPIRED"
        events = client.get(f"/api/v1/evidence-requests/{past_id}/history").json()["items"]
        assert sum(1 for e in events if e["event_type"] == "EXPIRED") == 1
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_submissions_use_existing_pipeline():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (85, 155, 225))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        request_id = create_request(case["id"]).json()["id"]

        submitted = client.post(
            f"/api/v1/evidence-requests/{request_id}/submissions",
            files={"file": ("submitted.jpg", image_bytes((21, 22, 23)), "image/jpeg")},
        )
        assert submitted.status_code == 201, submitted.text
        assert submitted.json()["item"]["item_status"] == "RECEIVED"
        session = get_session()
        try:
            item_id = submitted.json()["item"]["id"]
            evidence_id = (
                session.query(EvidenceRequestItem).filter_by(id=item_id).one().evidence_id
            )
            evidence = session.query(Evidence).filter_by(id=evidence_id).one()
            assert evidence.status == "uploaded_quarantine"
            assert evidence.sha256 is None  # unanalyzed: no trust conferred
            evidence_ids.append(evidence_id)
        finally:
            session.close()

        # Invalid uploads fail through the same pipeline (no link created).
        bad = client.post(
            f"/api/v1/evidence-requests/{request_id}/submissions",
            files={"file": ("bad.jpg", b"not an image", "image/jpeg")},
        )
        assert bad.status_code == 415
        # The single item is already filled: ingestion succeeds but linking
        # is rejected, leaving valid quarantined evidence behind (tracked).
        full = client.post(
            f"/api/v1/evidence-requests/{request_id}/submissions",
            files={"file": ("full-slot.jpg", image_bytes((22, 23, 24)), "image/jpeg")},
        )
        assert full.status_code == 422
        session = get_session()
        try:
            orphan = session.query(Evidence).filter_by(filename="full-slot.jpg").one()
            evidence_ids.append(orphan.id)
            assert orphan.status == "uploaded_quarantine"
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_duplicate_and_concurrent_links_safe():
    import threading

    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (86, 156, 226))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        request_id = create_request(
            case["id"],
            items=[{"description": "a", "required": True}, {"description": "b", "required": True}],
        ).json()["id"]
        extra = api_upload(image_bytes((31, 32, 33)), "conc.jpg")
        evidence_ids.append(extra["evidence_id"])
        link_evidence(extra["evidence_id"], project["id"])

        results = []

        def fire():
            try:
                response = client.post(
                    f"/api/v1/evidence-requests/{request_id}/evidence/{extra['evidence_id']}"
                )
                results.append((response.status_code, response.json()))
            except Exception as error:  # pragma: no cover - diagnostic only
                results.append(("EXC", str(error)[:150]))

        threads = [threading.Thread(target=fire) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(results) == 10
        assert all(code in (200, 201) for code, _ in results)
        item_ids = {body["item"]["id"] for _, body in results}
        assert len(item_ids) == 1

        session = get_session()
        try:
            from backend.db.models import EvidenceRequestItem as Item

            assert (
                session.query(Item)
                .filter(Item.request_id == request_id, Item.evidence_id == extra["evidence_id"])
                .count()
                == 1
            )
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_scope_isolation_and_lineage():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (87, 157, 227))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        other_project = api_create_project(str(user.id), "BE-014 other")
        project_ids.append(other_project["id"])
        foreign = api_upload(image_bytes((41, 42, 43)), "foreign.jpg")
        evidence_ids.append(foreign["evidence_id"])
        link_evidence(foreign["evidence_id"], other_project["id"])

        request_id = create_request(case["id"]).json()["id"]
        # Cross-project evidence link rejected.
        assert client.post(
            f"/api/v1/evidence-requests/{request_id}/evidence/{foreign['evidence_id']}"
        ).status_code == 422
        # Cross-project claim scope rejected.
        session = get_session()
        try:
            from backend.db.models import Claim as ClaimModel

            claim = ClaimModel(project_id=other_project["id"], title="foreign claim")
            session.add(claim)
            session.commit()
            session.refresh(claim)
            foreign_claim_id = claim.id
        finally:
            session.close()
        bad = create_request(
            case["id"], project_id=project["id"], claim_id=foreign_claim_id)
        assert bad.status_code == 422
        # Unknown scope entities rejected.
        assert create_request(case["id"], claim_id=str(uuid4())).status_code == 404

        # Lineage: request → case → fusion → explanation.
        detail = client.get(f"/api/v1/evidence-requests/{request_id}").json()
        assert detail["review_case_id"] == case["id"]
        case_body = client.get(f"/api/v1/review-cases/{case['id']}").json()
        explanation = client.get(f"/api/v1/explanations/fusion/{case_body['fusion_run_id']}")
        assert explanation.status_code == 200
        assert explanation.json()["fusion_run_id"] == case_body["fusion_run_id"]
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_invalid_transitions_change_nothing():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (88, 158, 228))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        request_id = create_request(case["id"]).json()["id"]

        # Link while DRAFT-adjacent invalid states, unknown evidence, bad item.
        assert client.post(
            f"/api/v1/evidence-requests/{request_id}/evidence/{uuid4()}").status_code == 404
        draft_id = create_request(case["id"], issue=False).json()["id"]
        assert client.post(
            f"/api/v1/evidence-requests/{draft_id}/evidence/{first['evidence_id']}"
        ).status_code == 422
        assert client.post(
            f"/api/v1/evidence-requests/{request_id}/items/{uuid4()}/accept"
        ).status_code == 404
        # Accept before RECEIVED is invalid.
        item_id = client.get(f"/api/v1/evidence-requests/{request_id}").json()["items"][0]["id"]
        assert client.post(
            f"/api/v1/evidence-requests/{request_id}/items/{item_id}/accept"
        ).status_code == 422

        before = client.get(f"/api/v1/evidence-requests/{request_id}").json()
        assert before["status"] == "OPEN"
        history = client.get(f"/api/v1/evidence-requests/{request_id}/history").json()
        assert [e["event_type"] for e in history["items"]] == ["REQUEST_CREATED", "REQUEST_ISSUED"]
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_listing_filters_and_pagination():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project, first, second, run, case = make_case(str(user.id), (89, 159, 229))
        project_ids.append(project["id"])
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        request_id = create_request(
            case["id"], priority="HIGH",
            due_at="2031-05-01T00:00:00+00:00").json()["id"]

        listed = client.get("/api/v1/evidence-requests", params={"limit": 50, "offset": 0}).json()
        assert listed["total"] >= 1
        assert any(item["id"] == request_id for item in listed["items"])
        assert client.get("/api/v1/evidence-requests",
                          params={"project_id": project["id"]}).json()["total"] >= 1
        assert client.get("/api/v1/evidence-requests",
                          params={"review_case_id": case["id"]}).json()["total"] == 1
        assert client.get("/api/v1/evidence-requests",
                          params={"status": "OPEN"}).json()["total"] >= 1
        assert client.get("/api/v1/evidence-requests",
                          params={"priority": "HIGH"}).json()["total"] >= 1
        assert client.get("/api/v1/evidence-requests",
                          params={"due_before": "2032-01-01T00:00:00+00:00"}).json()["total"] >= 1
        assert client.get("/api/v1/evidence-requests",
                          params={"due_after": "2032-01-01T00:00:00+00:00"}).json()["total"] == 0
        page = client.get("/api/v1/evidence-requests", params={"limit": 1, "offset": 0}).json()
        assert len(page["items"]) <= 1
        assert client.get("/api/v1/evidence-requests",
                          params={"status": "BOGUS"}).status_code == 422
        assert client.get(f"/api/v1/evidence-requests/{uuid4()}").status_code == 404
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)
