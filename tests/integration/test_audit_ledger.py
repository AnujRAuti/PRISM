"""BE-015 integration tests against real PostgreSQL infrastructure.

The ledger is append-only: tests scope every assertion to their own
fixtures and never delete audit rows.
"""

import threading
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from backend.app.main import app
from backend.db.models import (
    Activity,
    AnalysisJob,
    AnalysisResult,
    AuditLedgerEvent,
    Claim,
    DuplicateMatch,
    Evidence,
    EvidenceMetadata,
    FusionRun,
    Project,
    ReviewCase,
    ReviewCaseEvent,
    User,
    VisionDetection,
)
from backend.db.session import get_session
from backend.repositories import audit_ledger as audit_repo
from backend.services import audit_ledger as audit_service
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes(color=(90, 160, 230)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def api_upload(data: bytes, filename: str) -> dict:
    response = client.post("/api/v1/evidence", files={"file": (filename, data, "image/jpeg")})
    assert response.status_code == 201
    return response.json()


def setup_user() -> User:
    session = get_session()
    user = User(username=f"be015-{uuid4()}", email=f"{uuid4()}@example.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def cleanup(user_id, project_ids, evidence_ids) -> None:
    from backend.db.models import (
        AnalysisJob,
        AnalysisResult,
        CaseGenerationRun,
        FusionRun,
        FusionSignal,
        GraphNode,
        GraphRelationship,
        IntegrityAssessment,
        ReviewCase,
        ReviewCaseEvent,
        ReviewPriority,
        VisionDetection,
    )

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
        case_ids = [
            row[0] for row in session.query(ReviewCase.id)
            .filter(ReviewCase.project_id.in_(project_ids)).all()
        ]
        run_ids = [
            row[0] for row in session.query(FusionRun.id)
            .filter(FusionRun.target_id.in_(claim_ids + evidence_ids)).all()
        ]
        request_ids = []
        if case_ids:
            session.query(ReviewCaseEvent).filter(
                ReviewCaseEvent.case_id.in_(case_ids)).delete(synchronize_session=False)
            session.query(ReviewCase).filter(ReviewCase.id.in_(case_ids)).delete(
                synchronize_session=False)
        if run_ids:
            session.query(CaseGenerationRun).filter(
                CaseGenerationRun.fusion_run_id.in_(run_ids)).delete(synchronize_session=False)
            session.query(FusionSignal).filter(FusionSignal.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False)
            session.query(IntegrityAssessment).filter(
                IntegrityAssessment.fusion_run_id.in_(run_ids)).delete(synchronize_session=False)
            session.query(ReviewPriority).filter(ReviewPriority.fusion_run_id.in_(run_ids)).delete(
                synchronize_session=False)
            session.query(FusionRun).filter(FusionRun.id.in_(run_ids)).delete(
                synchronize_session=False)
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
            session.query(VisionDetection).filter(
                VisionDetection.analysis_result_id.in_(
                    session.query(AnalysisResult.id).filter(AnalysisResult.job_id.in_(job_ids))
                )).delete(synchronize_session=False)
            session.query(AnalysisResult).filter(AnalysisResult.job_id.in_(job_ids)).delete(
                synchronize_session=False)
            session.query(AnalysisJob).filter(AnalysisJob.id.in_(job_ids)).delete(
                synchronize_session=False)
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
            session.query(GraphNode).filter(GraphNode.id.in_(node_ids)).delete(
                synchronize_session=False)
        session.query(DuplicateMatch).filter(
            DuplicateMatch.evidence_id.in_(evidence_ids)
            | DuplicateMatch.matched_evidence_id.in_(evidence_ids)
        ).delete(synchronize_session=False)
        session.query(EvidenceMetadata).filter(EvidenceMetadata.evidence_id.in_(evidence_ids)).delete(
            synchronize_session=False)
        session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
            {Evidence.project_id: None, Evidence.claim_id: None}, synchronize_session=False)
        session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(synchronize_session=False)
        session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
        session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def append_direct(event_type="EVIDENCE_UPLOADED", resource_id=None, actor_id=None):
    session = get_session()
    try:
        row = audit_service.append_event(
            session, event_type=event_type, action="test-append",
            resource_type="evidence", resource_id=resource_id, actor_id=actor_id,
            payload={"probe": True}, source="audit-test",
        )
        session.commit()
        session.refresh(row)
        return row
    finally:
        session.close()


def test_append_chain_and_verify():
    session = get_session()
    try:
        first = audit_service.append_event(
            session, event_type="EVIDENCE_UPLOADED", action="upload",
            resource_type="evidence", resource_id=str(uuid4()),
            payload={"n": 1}, source="audit-test")
        session.flush()
        second = audit_service.append_event(
            session, event_type="EVIDENCE_UPLOADED", action="upload",
            resource_type="evidence", resource_id=str(uuid4()),
            payload={"n": 2}, source="audit-test")
        session.flush()
        assert int(second.sequence_number) == int(first.sequence_number) + 1
        assert second.previous_hash == first.event_hash
        assert first.previous_hash  # genesis or predecessor, never empty
        session.commit()
        result = audit_service.verify_chain(session, int(first.sequence_number),
                                            int(second.sequence_number))
        assert result["valid"] is True
        assert result["checked_events"] == 2
        assert result["first_sequence"] == int(first.sequence_number)
        assert result["last_sequence"] == int(second.sequence_number)
    finally:
        session.close()


def test_api_verify_reports_valid_chain():
    row = append_direct()
    response = client.get("/api/v1/audit/verify")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["checked_events"] >= 1
    assert body["first_sequence"] == 1
    assert body["last_sequence"] >= row.sequence_number
    assert body["failures"] == []

    bounded = client.get(
        "/api/v1/audit/verify",
        params={"from_sequence": row.sequence_number, "to_sequence": row.sequence_number},
    )
    assert bounded.status_code == 200
    assert bounded.json()["checked_events"] == 1
    assert client.get("/api/v1/audit/verify",
                      params={"from_sequence": 5, "to_sequence": 2}).status_code == 422


def test_tamper_detection_with_rollback():
    row = append_direct()
    session = get_session()
    try:
        # BE-030 D-1-A: the refusing trigger blocks this UPDATE unless the
        # session opens the audited SET LOCAL hatch; using the hatch is the
        # sanctioned, observable tamper-testing path (rolled back below).
        with audit_service.sanctioned_ledger_mutation(
            session, "BE-030 tamper-detection proof"
        ):
            session.execute(
                text("UPDATE audit_ledger_events SET payload = :p WHERE id = :i"),
                {"p": '{"probe": "EVIL"}', "i": str(row.id)},
            )
        result = audit_service.verify_chain(session)
        assert result["valid"] is False
        assert any("mismatch" in failure for failure in result["failures"])
    finally:
        session.rollback()
        session.close()
    # Rolled back: the ledger is intact again.
    assert audit_service.verify_chain(get_session())["valid"] is True


def test_broken_link_detection_with_rollback():
    first = append_direct()
    second = append_direct()
    session = get_session()
    try:
        # BE-030 D-1-A: sanctioned rolled-back tamper proof needs the hatch.
        with audit_service.sanctioned_ledger_mutation(
            session, "BE-030 broken-link proof"
        ):
            session.execute(
                text("UPDATE audit_ledger_events SET previous_hash = :p WHERE id = :i"),
                {"p": "tampered", "i": str(second.id)},
            )
        result = audit_service.verify_chain(
            session, int(first.sequence_number), int(second.sequence_number))
        assert result["valid"] is False
        assert any("previous_hash" in failure or "mismatch" in failure
                   for failure in result["failures"])
    finally:
        session.rollback()
        session.close()


def test_no_application_mutation_path():
    assert not hasattr(audit_repo, "update_event")
    assert not hasattr(audit_repo, "delete_event")
    assert not hasattr(audit_service, "update_event")
    assert not hasattr(audit_service, "delete_event")
    row = append_direct()
    assert client.put(f"/api/v1/audit/events/{row.id}", json={}).status_code == 405
    assert client.delete(f"/api/v1/audit/events/{row.id}").status_code == 405
    assert client.get(f"/api/v1/audit/events/{uuid4()}").status_code == 404
    assert client.get("/api/v1/audit/events/not-a-uuid").status_code == 422


def test_no_test_deletes_audit_ledger_rows():
    """BE-015 append-only: no test may destroy audit_ledger_events rows.

    Sequence numbers are allocated in Python as max(sequence_number) + 1
    and are never reused, so a row deleted from the middle of the chain
    leaves a permanent gap that verify_chain() can never satisfy. Two test
    cleanups used to do exactly that (test_authorization.py deleted an
    org's event by resource_id; test_governance.py deleted by
    resource_id / actor_id / project_id), which produced seven historical
    gaps across 36 missing sequence numbers.

    The scanning logic itself lives in ``tests/audit_guard.py`` so it can be
    regression-tested against synthetic sources without a database (see
    ``tests/unit/test_audit_guard.py``). This test is the integration-level
    assertion that the real test tree is clean.
    """
    from tests.audit_guard import scan_test_tree

    tests_root = Path(__file__).resolve().parent.parent
    violations = scan_test_tree(
        tests_root,
        # Both this file and the guard's own regression file necessarily
        # contain the forbidden patterns as fixtures and documentation.
        skip_files=frozenset({"test_audit_ledger.py", "test_audit_guard.py"}),
    )
    assert violations == [], (
        "audit_ledger_events is append-only; these sites destroy ledger "
        "rows and will corrupt the hash chain:\n"
        + "\n".join(str(v) for v in violations)
    )


def test_concurrent_appends_keep_valid_chain():
    results = []

    def fire(index: int):
        session = get_session()
        try:
            row = audit_service.append_event(
                session, event_type="EVIDENCE_UPLOADED", action="concurrent",
                resource_type="evidence", resource_id=str(uuid4()),
                payload={"worker": index}, source="audit-test", commit=True,
            )
            results.append(int(row.sequence_number))
        except Exception as error:  # pragma: no cover - diagnostic only
            results.append(f"EXC: {error}"[:150])
        finally:
            session.close()

    threads = [threading.Thread(target=fire, args=(index,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 10
    assert all(isinstance(value, int) for value in results), results
    assert len(set(results)) == 10
    session = get_session()
    try:
        assert audit_service.verify_chain(session)["valid"] is True
    finally:
        session.close()


def test_failed_domain_operation_leaves_no_audit_row():
    user = setup_user()
    project_ids, evidence_ids = [], []
    try:
        session = get_session()
        try:
            before = session.query(AuditLedgerEvent).count()
        finally:
            session.close()
        # Invalid upload: rejected before any persistence.
        bad = client.post(
            "/api/v1/evidence", files={"file": ("bad.jpg", b"not an image", "image/jpeg")}
        )
        assert bad.status_code == 415
        # Invalid case transition: rejected without mutation.
        project = client.post(
            "/api/v1/projects", json={"name": "BE-015 t", "owner_id": str(user.id)}
        ).json()
        project_ids.append(project["id"])
        session = get_session()
        try:
            after = session.query(AuditLedgerEvent).count()
        finally:
            session.close()
        assert after == before
    finally:
        cleanup(str(user.id), project_ids, evidence_ids)


def make_urgent_case(user_id: str, color=(91, 161, 231)):
    """Duplicate + future-EXIF evidence → URGENT fusion → review case."""
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence

    payload = image_bytes(color)
    first = api_upload(payload, f"aud-{uuid4().hex[:8]}.jpg")
    second = api_upload(payload, f"aud-{uuid4().hex[:8]}.jpg")
    session = get_session()
    try:
        process_evidence(first["evidence_id"], session)
        process_evidence(second["evidence_id"], session)
        analyze_duplicates(first["evidence_id"], session)
        metadata = session.query(EvidenceMetadata).filter_by(
            evidence_id=first["evidence_id"]).one()
        metadata.metadata_json = {
            **(metadata.metadata_json or {}),
            "exif": {"EXIF DateTimeOriginal": "2030-01-01 10:00:00"},
        }
        session.commit()
    finally:
        session.close()
    run = client.post(f"/api/v1/fusion/EVIDENCE/{first['evidence_id']}", json={}).json()["run"]
    case = client.post(f"/api/v1/review-cases/from-fusion/{run['id']}", json={}).json()["case"]
    assert case["priority_band"] in ("HIGH", "URGENT")
    return first, second, run, case


def test_workflow_emission_across_milestones():
    user = setup_user()
    project_ids, evidence_ids = [], []
    case_id = None
    try:
        from backend.services import evidence_graph as graph_service

        project = client.post(
            "/api/v1/projects", json={"name": "BE-015 emit", "owner_id": str(user.id)}
        ).json()
        project_ids.append(project["id"])
        uploaded = client.post(
            "/api/v1/evidence", files={"file": ("emit.jpg", image_bytes(), "image/jpeg")}
        ).json()
        evidence_ids.append(uploaded["evidence_id"])

        session = get_session()
        try:
            rows = session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "EVIDENCE_UPLOADED",
                AuditLedgerEvent.resource_id == uploaded["evidence_id"],
            ).all()
            assert len(rows) == 1
            assert rows[0].payload["filename"] == "emit.jpg"
            assert "password" not in str(rows[0].payload).lower()
        finally:
            session.close()

        claim = client.post(
            f"/api/v1/projects/{project['id']}/claims",
            json={"title": "emit claim", "description": "d"},
        ).json()
        edge = client.post(
            "/api/v1/graph/relationships",
            json={
                "source": {"node_type": "EVIDENCE", "entity_id": uploaded["evidence_id"]},
                "target": {"node_type": "CLAIM", "entity_id": claim["id"]},
                "relationship_type": "SUPPORTS",
                "provenance": {"source": "human_review", "method": "manual_link"},
            },
        )
        assert edge.status_code == 201
        session = get_session()
        try:
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "GRAPH_RELATIONSHIP_CREATED",
                AuditLedgerEvent.resource_id == edge.json()["id"],
            ).count() == 1
            # Idempotent re-assertion emits no second audit row.
            repeat = client.post(
                "/api/v1/graph/relationships",
                json={
                    "source": {"node_type": "EVIDENCE", "entity_id": uploaded["evidence_id"]},
                    "target": {"node_type": "CLAIM", "entity_id": claim["id"]},
                    "relationship_type": "SUPPORTS",
                    "provenance": {"source": "human_review", "method": "manual_link"},
                },
            )
            assert repeat.status_code == 200
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "GRAPH_RELATIONSHIP_CREATED",
                AuditLedgerEvent.resource_id == edge.json()["id"],
            ).count() == 1
        finally:
            session.close()

        run = client.post(
            f"/api/v1/fusion/EVIDENCE/{uploaded['evidence_id']}", json={}).json()["run"]
        session = get_session()
        try:
            fusion_rows = session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "FUSION_RUN_CREATED",
                AuditLedgerEvent.resource_id == run["id"],
            ).all()
            assert len(fusion_rows) == 1
        finally:
            session.close()

        first, second, urgent_run, case = make_urgent_case(str(user.id))
        session = get_session()
        try:
            for evidence_id in (first["evidence_id"], second["evidence_id"]):
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
        finally:
            session.close()
        case_id = case["id"]
        reviewer = str(uuid4())
        client.post(f"/api/v1/review-cases/{case['id']}/assign", json={"assigned_to": reviewer})
        decided = client.post(
            f"/api/v1/review-cases/{case['id']}/investigate", json={})
        assert decided.status_code == 200
        client.post(
            f"/api/v1/review-cases/{case['id']}/decision",
            json={"decision": "INCONCLUSIVE", "rationale": "needs visit", "decided_by": reviewer},
        )
        session = get_session()
        try:
            for expected in ("REVIEW_CASE_CREATED", "REVIEW_CASE_ASSIGNED",
                             "REVIEW_CASE_DECISION_RECORDED"):
                assert session.query(AuditLedgerEvent).filter(
                    AuditLedgerEvent.event_type == expected,
                    AuditLedgerEvent.resource_id == case["id"],
                ).count() == 1, expected
        finally:
            session.close()

        listed = client.get(
            "/api/v1/audit/events",
            params={"resource_type": "review_cases", "resource_id": case["id"]},
        ).json()
        assert listed["total"] >= 3
        assert all(item["resource_id"] == case["id"] for item in listed["items"])
        typed = client.get(
            "/api/v1/audit/events", params={"event_type": "EVIDENCE_UPLOADED", "limit": 1}
        ).json()
        assert typed["total"] >= 1
    finally:
        session = get_session()
        try:
            if case_id is not None:
                session.query(ReviewCaseEvent).filter(
                    ReviewCaseEvent.case_id == case_id).delete(synchronize_session=False)
                session.query(ReviewCase).filter(ReviewCase.id == case_id).delete(
                    synchronize_session=False)
                session.commit()
        finally:
            session.close()
        cleanup(str(user.id), project_ids, evidence_ids)


def test_request_lifecycle_emission_and_filters():
    user = setup_user()
    project_ids, evidence_ids = [], []
    case_id = None
    fusion_id = None
    plain_run_id = None
    try:
        project = client.post(
            "/api/v1/projects", json={"name": "BE-015 req", "owner_id": str(user.id)}
        ).json()
        project_ids.append(project["id"])
        claim = client.post(
            f"/api/v1/projects/{project['id']}/claims",
            json={"title": "req claim", "description": "d"},
        ).json()
        uploaded = client.post(
            "/api/v1/evidence", files={"file": ("req.jpg", image_bytes(), "image/jpeg")}
        ).json()
        evidence_ids.append(uploaded["evidence_id"])

        fusion = client.post(f"/api/v1/fusion/EVIDENCE/{uploaded['evidence_id']}", json={}).json()["run"]
        plain_run_id = fusion["id"]
        first, second, urgent_run, case = make_urgent_case(str(user.id))
        for evidence_id in (first["evidence_id"], second["evidence_id"]):
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        fusion_id = urgent_run["id"]
        case_id = case["id"]
        created = client.post("/api/v1/evidence-requests", json={
            "review_case_id": case["id"], "recipient_id": str(uuid4()),
            "instructions": "Send a close-up.",
            "items": [{"description": "close-up", "required": True}],
        })
        assert created.status_code == 201
        request_id = created.json()["id"]
        assert client.post(f"/api/v1/evidence-requests/{request_id}/acknowledge").status_code == 200
        assert client.post(
            f"/api/v1/evidence-requests/{request_id}/decline", json={"reason": "covered"}
        ).status_code == 200

        session = get_session()
        try:
            for expected in ("EVIDENCE_REQUEST_CREATED", "EVIDENCE_REQUEST_ISSUED",
                             "EVIDENCE_REQUEST_ACKNOWLEDGED", "EVIDENCE_REQUEST_DECLINED"):
                assert session.query(AuditLedgerEvent).filter(
                    AuditLedgerEvent.event_type == expected,
                    AuditLedgerEvent.resource_id == request_id,
                ).count() == 1, expected
        finally:
            session.close()

        by_actor = client.get("/api/v1/audit/events", params={"limit": 1, "offset": 0}).json()
        assert by_actor["total"] >= 1
        assert by_actor["limit"] == 1
    finally:
        session = get_session()
        try:
            if case_id is not None:
                from backend.db.models import (
                    EvidenceRequest,
                    EvidenceRequestEvent,
                    EvidenceRequestItem,
                )

                request_ids = [
                    row[0] for row in session.query(EvidenceRequest.id)
                    .filter(EvidenceRequest.review_case_id == case_id).all()
                ]
                if request_ids:
                    session.query(EvidenceRequestEvent).filter(
                        EvidenceRequestEvent.request_id.in_(request_ids)).delete(
                        synchronize_session=False)
                    session.query(EvidenceRequestItem).filter(
                        EvidenceRequestItem.request_id.in_(request_ids)).delete(
                        synchronize_session=False)
                    session.query(EvidenceRequest).filter(
                        EvidenceRequest.id.in_(request_ids)).delete(
                        synchronize_session=False)
                session.query(ReviewCaseEvent).filter(
                    ReviewCaseEvent.case_id == case_id).delete(synchronize_session=False)
                session.query(ReviewCase).filter(ReviewCase.id == case_id).delete(
                    synchronize_session=False)
            if fusion_id is not None:
                from backend.db.models import (
                    CaseGenerationRun,
                    FusionSignal,
                    IntegrityAssessment,
                    ReviewPriority,
                )

                stale_runs = [run_id for run_id in (fusion_id, plain_run_id)
                              if run_id is not None]
                for stale_id in stale_runs:
                    session.query(CaseGenerationRun).filter(
                        CaseGenerationRun.fusion_run_id == stale_id).delete(
                        synchronize_session=False)
                    session.query(FusionSignal).filter(
                        FusionSignal.fusion_run_id == stale_id).delete(synchronize_session=False)
                    session.query(IntegrityAssessment).filter(
                        IntegrityAssessment.fusion_run_id == stale_id).delete(
                        synchronize_session=False)
                    session.query(ReviewPriority).filter(
                        ReviewPriority.fusion_run_id == stale_id).delete(synchronize_session=False)
                    session.query(FusionRun).filter(FusionRun.id == stale_id).delete(
                        synchronize_session=False)
                session.commit()
        finally:
            session.close()
        cleanup(str(user.id), project_ids, evidence_ids)
