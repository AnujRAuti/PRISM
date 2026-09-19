"""BE-013 integration tests against real PostgreSQL infrastructure."""

import json
import threading
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


def image_bytes(color=(70, 140, 210)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be013-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def api_create_project(user_id: str, name: str = "BE-013 project") -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": user_id})
    assert response.status_code == 201
    return response.json()


def api_create_claim(project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"title": "BE-013 claim", "description": "review test"},
    )
    assert response.status_code == 201
    return response.json()


def api_upload(data: bytes, filename: str) -> dict:
    response = client.post("/api/v1/evidence", files={"file": (filename, data, "image/jpeg")})
    assert response.status_code == 201
    return response.json()


def api_edge(source_type, source_id, target_type, target_id, rel_type, provenance=None):
    return client.post(
        "/api/v1/graph/relationships",
        json={
            "source": {"node_type": source_type, "entity_id": source_id},
            "target": {"node_type": target_type, "entity_id": target_id},
            "relationship_type": rel_type,
            "provenance": provenance or {"source": "human_review", "method": "manual_link"},
        },
    )


def link_evidence(evidence_id: str, project_id: str, claim_id: str | None = None) -> None:
    session = get_session()
    try:
        evidence = session.query(Evidence).filter_by(id=evidence_id).one()
        evidence.project_id = project_id
        evidence.claim_id = claim_id
        session.commit()
    finally:
        session.close()


def cleanup(user_id, project_ids, evidence_ids, config_versions=None) -> None:
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
        claim_ids = [
            row[0] for row in session.query(Claim.id).filter(Claim.project_id.in_(project_ids)).all()
        ]
        run_ids = [
            row[0]
            for row in session.query(FusionRun.id)
            .filter(FusionRun.target_id.in_(claim_ids + evidence_ids))
            .all()
        ]
        conditions = []
        if claim_ids:
            conditions.append(ReviewCase.claim_id.in_(claim_ids))
        if evidence_ids:
            conditions.append(ReviewCase.evidence_id.in_(evidence_ids))
        if project_ids:
            conditions.append(ReviewCase.project_id.in_(project_ids))
        case_ids = []
        if conditions:
            from sqlalchemy import or_

            case_ids = [
                row[0] for row in session.query(ReviewCase.id).filter(or_(*conditions)).all()
            ]
        if case_ids:
            session.query(ReviewCaseEvent).filter(ReviewCaseEvent.case_id.in_(case_ids)).delete(
                synchronize_session=False
            )
            session.query(ReviewCase).filter(ReviewCase.id.in_(case_ids)).delete(
                synchronize_session=False
            )
        gen_ids = [
            row[0]
            for row in session.query(CaseGenerationRun.id)
            .filter(CaseGenerationRun.fusion_run_id.in_(run_ids))
            .all()
        ]
        if gen_ids:
            session.query(CaseGenerationRun).filter(CaseGenerationRun.id.in_(gen_ids)).delete(
                synchronize_session=False
            )
        if run_ids:
            session.query(FusionSignal).filter(FusionSignal.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False
            )
            session.query(IntegrityAssessment).filter(
                IntegrityAssessment.fusion_run_id.in_(run_ids)
            ).delete(synchronize_session=False)
            session.query(ReviewPriority).filter(ReviewPriority.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False
            )
            session.query(FusionRun).filter(FusionRun.id.in_(run_ids)).delete(synchronize_session=False)
        job_ids = [
            row[0]
            for row in session.query(AnalysisJob.id).filter(AnalysisJob.evidence_id.in_(evidence_ids)).all()
        ]
        entity_ids = list(evidence_ids) + list(project_ids) + claim_ids + job_ids
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
            result_ids = [
                row[0]
                for row in session.query(AnalysisResult.id).filter(AnalysisResult.job_id.in_(job_ids)).all()
            ]
            if result_ids:
                session.query(VisionDetection).filter(
                    VisionDetection.analysis_result_id.in_(result_ids)
                ).delete(synchronize_session=False)
            session.query(AnalysisResult).filter(AnalysisResult.job_id.in_(job_ids)).delete(
                synchronize_session=False
            )
            session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(synchronize_session=False)
        session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id.in_(evidence_ids)
            | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        session.query(EvidenceMetadata).filter(EvidenceMetadata.evidence_id.in_(evidence_ids)).delete(
            synchronize_session=False
        )
        session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
            {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False
        )
        session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
        session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        for version in config_versions or []:
            if version != "v1":
                session.query(CaseGenerationConfiguration).filter_by(version=version).delete()
        session.commit()
    finally:
        session.close()


def make_urgent_evidence_target(payload: bytes | None = None):
    """Two identical evidences + future EXIF on the first → URGENT fusion."""
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence

    payload = payload if payload is not None else image_bytes((71, 141, 211))
    first = api_upload(payload, f"urg-{uuid4().hex[:8]}.jpg")
    second = api_upload(payload, f"urg-{uuid4().hex[:8]}.jpg")
    session = get_session()
    try:
        process_evidence(first["evidence_id"], session)
        process_evidence(second["evidence_id"], session)
        analyze_duplicates(first["evidence_id"], session)
        metadata = (
            session.query(EvidenceMetadata).filter_by(evidence_id=first["evidence_id"]).one()
        )
        metadata.metadata_json = {
            **(metadata.metadata_json or {}),
            "exif": {"EXIF DateTimeOriginal": "2030:01:01 10:00:00"},
        }
        session.commit()
    finally:
        session.close()
    return first, second


def fuse_evidence(evidence_id: str) -> dict:
    response = client.post(f"/api/v1/fusion/EVIDENCE/{evidence_id}", json={})
    assert response.status_code == 200, response.text
    return response.json()["run"]


def test_generation_idempotency_and_priority_snapshot():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = make_urgent_evidence_target()
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        run = fuse_evidence(first["evidence_id"])

        created = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["result"] == "CASE_CREATED"
        case = body["case"]
        assert case["status"] == "OPEN"
        assert case["origin"] == "SYSTEM_SIGNAL"
        assert case["evidence_id"] == first["evidence_id"]
        assert case["fusion_run_id"] == run["id"]
        assert case["priority_band"] in ("HIGH", "URGENT")
        assert case["priority_source"] == "fusion"
        assert case["priority_config_version"] == "v1"
        assert case["decision"] is None
        assert body["generation_run_id"]

        repeat = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={})
        assert repeat.status_code == 200
        assert repeat.json()["result"] == "CASE_ALREADY_EXISTS"
        assert repeat.json()["case"]["id"] == case["id"]

        session = get_session()
        try:
            count = (
                session.query(ReviewCase)
                .filter(
                    ReviewCase.fusion_run_id == run["id"],
                    ReviewCase.origin == "SYSTEM_SIGNAL",
                    ReviewCase.status != "RESOLVED",
                )
                .count()
            )
            assert count == 1
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_concurrent_generation_yields_one_case():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = make_urgent_evidence_target(image_bytes((72, 142, 212)))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        run = fuse_evidence(first["evidence_id"])

        results = []

        def fire():
            try:
                response = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={})
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
        assert {body["case"]["id"] for _, body in results} and len(
            {body["case"]["id"] for _, body in results}
        ) == 1

        session = get_session()
        try:
            assert (
                session.query(ReviewCase)
                .filter(
                    ReviewCase.fusion_run_id == run["id"],
                    ReviewCase.origin == "SYSTEM_SIGNAL",
                    ReviewCase.status != "RESOLVED",
                )
                .count()
                == 1
            )
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_full_lifecycle_with_append_only_history():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = make_urgent_evidence_target(image_bytes((73, 143, 213)))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        run = fuse_evidence(first["evidence_id"])
        case_id = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={}).json()["case"]["id"]
        reviewer = str(uuid4())

        assigned = client.post(
            f"/api/v1/review-cases/{case_id}/assign", json={"assigned_to": reviewer}
        )
        assert assigned.status_code == 200
        assert assigned.json()["status"] == "ASSIGNED"
        assert assigned.json()["assigned_to"] == reviewer

        investigating = client.post(f"/api/v1/review-cases/{case_id}/investigate", json={})
        assert investigating.json()["status"] == "INVESTIGATING"

        decided = client.post(
            f"/api/v1/review-cases/{case_id}/decision",
            json={"decision": "INCONCLUSIVE", "rationale": "needs field visit", "decided_by": reviewer},
        )
        assert decided.status_code == 200
        assert decided.json()["status"] == "DECISION_PENDING"
        assert decided.json()["decision"] == "INCONCLUSIVE"

        resolved = client.post(f"/api/v1/review-cases/{case_id}/resolve", json={})
        assert resolved.json()["status"] == "RESOLVED"
        assert resolved.json()["decision"] == "INCONCLUSIVE"

        history = client.get(f"/api/v1/review-cases/{case_id}/history").json()
        types = [item["event_type"] for item in history["items"]]
        assert types == ["CASE_CREATED", "ASSIGNED", "INVESTIGATION_STARTED",
                         "DECISION_RECORDED", "RESOLVED"]
        assert history["total"] == 5

        # Reopen preserves the prior decision in row + history.
        reopened = client.post(f"/api/v1/review-cases/{case_id}/reopen", json={})
        assert reopened.json()["status"] == "OPEN"
        assert reopened.json()["decision"] == "INCONCLUSIVE"
        # Re-resolution without a NEW decision is rejected.
        assert client.post(f"/api/v1/review-cases/{case_id}/resolve", json={}).status_code == 422
        # Invalid moves never mutate.
        assert client.post(f"/api/v1/review-cases/{case_id}/investigate", json={}).status_code == 422
        history2 = client.get(f"/api/v1/review-cases/{case_id}/history").json()
        assert history2["total"] == 6
        assert history2["items"][-1]["event_type"] == "REOPENED"
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_escalation_preserves_assignment_and_decision():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = make_urgent_evidence_target(image_bytes((74, 144, 214)))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        run = fuse_evidence(first["evidence_id"])
        case_id = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={}).json()["case"]["id"]
        reviewer, lead = str(uuid4()), str(uuid4())

        client.post(f"/api/v1/review-cases/{case_id}/assign", json={"assigned_to": reviewer})
        escalated = client.post(
            f"/api/v1/review-cases/{case_id}/escalate",
            json={"escalated_to": lead, "reason": "jurisdiction question"},
        )
        assert escalated.json()["status"] == "ESCALATED"
        assert escalated.json()["escalated_to"] == lead
        assert escalated.json()["assigned_to"] == reviewer

        back = client.post(
            f"/api/v1/review-cases/{case_id}/assign", json={"assigned_to": reviewer}
        )
        assert back.json()["status"] == "ASSIGNED"
        events = client.get(f"/api/v1/review-cases/{case_id}/history").json()["items"]
        assert [e["event_type"] for e in events] == ["CASE_CREATED", "ASSIGNED", "ESCALATED", "ASSIGNED"]
        assert client.post(
            f"/api/v1/review-cases/{case_id}/escalate", json={"escalated_to": lead, "reason": " "}
        ).status_code == 422
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_failed_and_ineligible_runs_rejected():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        from backend.repositories import fusion as fusion_repo

        project = api_create_project(str(user.id))
        project_ids.append(project["id"])
        claim = api_create_claim(project["id"])

        session = get_session()
        try:
            failed = fusion_repo.insert_run(
                session, target_type="CLAIM", target_id=claim["id"],
                method="deterministic_signal_fusion", method_version="fusion-v1",
                configuration_version="v1", input_snapshot={},
            )
            failed.status = "FAILED"
            failed.error = "boom"
            session.commit()
            failed_id = failed.id
        finally:
            session.close()
        failed_resp = client.post(f"/api/v1/review-cases/from-fusion/{failed_id}", json={})
        assert failed_resp.status_code == 422
        assert "CASE_GENERATION_UNAVAILABLE" in failed_resp.text

        # LOW-priority zero-signal claim → eligible evaluation, no case.
        zero_run = client.post(f"/api/v1/fusion/CLAIM/{claim['id']}", json={}).json()["run"]
        response = client.post(f"/api/v1/review-cases/from-fusion/{zero_run['id']}", json={})
        assert response.status_code == 200
        assert response.json()["result"] == "NOT_ELIGIBLE"
        assert response.json()["case"] is None
        assert response.json()["generation_run_id"]

        session = get_session()
        try:
            assert session.query(ReviewCase).filter(
                ReviewCase.fusion_run_id.in_([failed_id, zero_run["id"]])
            ).count() == 0
            session.query(FusionRun).filter_by(id=failed_id).delete()
            session.commit()
        finally:
            session.close()

        assert client.post(f"/api/v1/review-cases/from-fusion/{uuid4()}", json={}).status_code == 404
        assert client.post("/api/v1/review-cases/from-fusion/not-a-uuid", json={}).status_code == 422
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_lineage_to_explanation_and_target_dedupe():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = make_urgent_evidence_target(image_bytes((75, 145, 215)))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        run = fuse_evidence(first["evidence_id"])
        case = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={}).json()["case"]

        detail = client.get(f"/api/v1/review-cases/{case['id']}").json()
        assert detail["fusion_run_id"] == run["id"]
        assert detail["case_generation_run_id"]
        explanation = client.get(f"/api/v1/explanations/fusion/{run['id']}")
        assert explanation.status_code == 200
        assert explanation.json()["fusion_run_id"] == run["id"]

        # A second eligible run for the same target does not blindly duplicate.
        run2 = fuse_evidence(first["evidence_id"])
        assert run2["id"] != run["id"]
        second_resp = client.post(f"/api/v1/review-cases/from-fusion/{run2['id']}", json={})
        assert second_resp.status_code == 200
        assert second_resp.json()["result"] == "NOT_ELIGIBLE"
        assert second_resp.json()["reason"] == "TARGET_CASE_OPEN"
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_listing_filters_pagination_and_validation():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = make_urgent_evidence_target(image_bytes((76, 146, 216)))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        run = fuse_evidence(first["evidence_id"])
        case = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={}).json()["case"]

        listed = client.get("/api/v1/review-cases", params={"limit": 50, "offset": 0}).json()
        assert listed["total"] >= 1
        assert any(item["id"] == case["id"] for item in listed["items"])
        by_status = client.get("/api/v1/review-cases", params={"status": "OPEN"}).json()
        assert all(item["status"] == "OPEN" for item in by_status["items"])
        by_band = client.get(
            "/api/v1/review-cases", params={"priority_band": case["priority_band"]}
        ).json()
        assert any(item["id"] == case["id"] for item in by_band["items"])
        by_origin = client.get("/api/v1/review-cases", params={"origin": "SYSTEM_SIGNAL"}).json()
        assert any(item["id"] == case["id"] for item in by_origin["items"])
        page = client.get("/api/v1/review-cases", params={"limit": 1, "offset": 0}).json()
        assert len(page["items"]) <= 1
        assert page["total"] >= 1
        assert client.get(f"/api/v1/review-cases/{uuid4()}").status_code == 404
        assert client.get("/api/v1/review-cases/not-a-uuid").status_code == 422
        assert client.get("/api/v1/review-cases", params={"status": "BOGUS"}).status_code == 422
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_invalid_workflow_actions_rejected():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        first, second = make_urgent_evidence_target(image_bytes((77, 147, 217)))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        run = fuse_evidence(first["evidence_id"])
        case_id = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={}).json()["case"]["id"]

        # Resolve/decision/escalate from OPEN are invalid and mutate nothing.
        assert client.post(f"/api/v1/review-cases/{case_id}/resolve", json={}).status_code == 422
        assert client.post(
            f"/api/v1/review-cases/{case_id}/decision",
            json={"decision": "SUPPORTED", "rationale": "x"},
        ).status_code == 422
        assert client.post(
            f"/api/v1/review-cases/{case_id}/decision",
            json={"decision": "BOGUS", "rationale": "x"},
        ).status_code == 422
        assert client.post(
            f"/api/v1/review-cases/{case_id}/decision",
            json={"decision": "SUPPORTED", "rationale": "   "},
        ).status_code == 422
        assert client.post(f"/api/v1/review-cases/{case_id}/assign", json={}).status_code == 422
        assert client.post(
            f"/api/v1/review-cases/{case_id}/assign", json={"assigned_to": "nope"}
        ).status_code == 422

        before = client.get(f"/api/v1/review-cases/{case_id}").json()
        assert before["status"] == "OPEN"
        assert before["decision"] is None
        history = client.get(f"/api/v1/review-cases/{case_id}/history").json()
        assert [e["event_type"] for e in history["items"]] == ["CASE_CREATED"]
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def test_cross_project_case_preserves_ownership():
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence
    from backend.services import evidence_graph as graph_service

    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        project_a = api_create_project(str(user.id), "review proj A")
        project_b = api_create_project(str(user.id), "review proj B")
        project_ids.extend([project_a["id"], project_b["id"]])
        payload = image_bytes((78, 148, 218))
        evidence_a = api_upload(payload, "rc-a.jpg")
        evidence_b = api_upload(payload, "rc-b.jpg")
        evidence_ids.extend([evidence_a["evidence_id"], evidence_b["evidence_id"]])
        link_evidence(evidence_a["evidence_id"], project_a["id"])
        link_evidence(evidence_b["evidence_id"], project_b["id"])

        session = get_session()
        try:
            process_evidence(evidence_a["evidence_id"], session)
            process_evidence(evidence_b["evidence_id"], session)
            analyze_duplicates(evidence_a["evidence_id"], session)
            match = (
                session.query(DuplicateMatch)
                .filter(
                    DuplicateMatch.evidence_id
                    == min(evidence_a["evidence_id"], evidence_b["evidence_id"]),
                    DuplicateMatch.matched_evidence_id
                    == max(evidence_a["evidence_id"], evidence_b["evidence_id"]),
                )
                .one()
            )
            graph_service.record_duplicate_relationship(session, match.id)
        finally:
            session.close()

        session = get_session()
        try:
            metadata = (
                session.query(EvidenceMetadata).filter_by(evidence_id=evidence_a["evidence_id"]).one()
            )
            metadata.metadata_json = {
                **(metadata.metadata_json or {}),
                "exif": {"EXIF DateTimeOriginal": "2030:06:01 10:00:00"},
            }
            session.commit()
        finally:
            session.close()

        run = fuse_evidence(evidence_a["evidence_id"])
        created = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={})
        assert created.status_code == 201, created.text
        case = created.json()["case"]
        assert case["project_id"] == project_a["id"]
        assert case["evidence_id"] == evidence_a["evidence_id"]

        session = get_session()
        try:
            row = session.query(Evidence).filter_by(id=evidence_b["evidence_id"]).one()
            assert str(row.project_id) == project_b["id"]
        finally:
            session.close()
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)
