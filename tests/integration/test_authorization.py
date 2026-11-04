"""BE-016 integration + security tests against real PostgreSQL infrastructure."""

import threading
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    Activity,
    AuditLedgerEvent,
    Claim,
    Evidence,
    EvidenceMetadata,
    FusionRun,
    GraphNode,
    GraphRelationship,
    Project,
    ReviewCase,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes(color=(100, 170, 240)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def make_user(username: str) -> User:
    session = get_session()
    try:
        user = User(username=f"{username}-{uuid4().hex[:8]}",
                    email=f"{uuid4().hex[:8]}@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


def assign(user_id: str, role: str, scope: str, scope_id: str | None = None):
    session = get_session()
    try:
        kwargs: dict = {}
        if scope == "ORGANIZATION":
            kwargs["organization_id"] = scope_id
        elif scope == "ORGANIZATIONAL_UNIT":
            kwargs["organizational_unit_id"] = scope_id
        elif scope == "PROJECT":
            kwargs["project_id"] = scope_id
        row, _ = auth_service.assign_role(
            session, user_id=user_id, role_name=role, scope_type=scope, **kwargs)
        session.commit()
        return row
    finally:
        session.close()


def setup_org(code: str):
    session = get_session()
    try:
        org = auth_service.create_organization(
            session, name=f"Org {code}", code=f"org-{code}-{uuid4().hex[:6]}")
        session.commit()
        session.refresh(org)
        session.expunge(org)
        return org
    finally:
        session.close()


def setup_project(owner_id: str, name: str, org_id: str | None = None) -> dict:
    body = {"name": name, "owner_id": owner_id}
    response = client.post("/api/v1/projects", json=body)
    assert response.status_code == 201
    project = response.json()
    if org_id is not None:
        session = get_session()
        try:
            session.execute(
                text("UPDATE projects SET organization_id=:o WHERE id=:i"),
                {"o": org_id, "i": project["id"]},
            )
            session.commit()
        finally:
            session.close()
    return project


def cleanup(user_ids, project_ids, evidence_ids, org_ids, client_ids) -> None:
    storage = StorageService()
    session = get_session()
    try:
        keys = [
            row[0] for row in session.query(Evidence.storage_key)
            .filter(Evidence.id.in_(evidence_ids)).all()
        ] if evidence_ids else []
        for key in keys:
            if storage.object_exists(storage.quarantine_bucket, key):
                storage.delete_object(storage.quarantine_bucket, key)
        if evidence_ids:
            from backend.db.models import DuplicateMatch as _DM

            session.query(_DM).filter(
                _DM.evidence_id.in_(evidence_ids)
                | _DM.matched_evidence_id.in_(evidence_ids)).delete(
                synchronize_session=False)
            entity_ids = list(evidence_ids) + list(project_ids)
            node_ids = [
                row[0] for row in session.query(GraphNode.id)
                .filter(GraphNode.entity_id.in_(entity_ids)).all()
            ]
            if node_ids:
                session.query(GraphRelationship).filter(
                    GraphRelationship.source_node_id.in_(node_ids)
                    | GraphRelationship.target_node_id.in_(node_ids)).delete(
                    synchronize_session=False)
                session.query(GraphNode).filter(GraphNode.id.in_(node_ids)).delete(
                    synchronize_session=False)
            session.query(EvidenceMetadata).filter(
                EvidenceMetadata.evidence_id.in_(evidence_ids)).delete(
                synchronize_session=False)
            session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
                {Evidence.project_id: None, Evidence.claim_id: None},
                synchronize_session=False)
            session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(
                synchronize_session=False)
        if user_ids:
            session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id.in_(user_ids)).delete(synchronize_session=False)
        if client_ids:
            from backend.db.models import ApiClient

            session.query(ApiClient).filter(ApiClient.id.in_(client_ids)).delete(
                synchronize_session=False)
        if project_ids:
            session.query(Activity).filter(Activity.project_id.in_(project_ids)).delete(
                synchronize_session=False)
            session.query(Claim).filter(Claim.project_id.in_(project_ids)).delete(
                synchronize_session=False)
            session.query(Project).filter(Project.id.in_(project_ids)).delete(
                synchronize_session=False)
        if user_ids:
            session.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        if org_ids:
            from backend.db.models import OrganizationalUnit

            session.query(OrganizationalUnit).filter(
                OrganizationalUnit.organization_id.in_(org_ids)).delete(
                synchronize_session=False)
            session.query(Project).filter(Project.organization_id.in_(org_ids)).delete(
                synchronize_session=False)
            from backend.db.models import Organization

            session.query(Organization).filter(Organization.id.in_(org_ids)).delete(
                synchronize_session=False)
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def seed_catalogue():
    session = get_session()
    try:
        auth_service.ensure_default_catalogue(session)
    finally:
        session.close()


def test_me_anonymous_and_authenticated():
    body = client.get("/api/v1/auth/me").json()
    assert body["principal_type"] == "ANONYMOUS"
    assert body["authenticated"] is False

    user = make_user("me-user")
    try:
        me = client.get("/api/v1/auth/me", headers=headers_for(str(user.id))).json()
        assert me["principal_type"] == "USER"
        assert me["authenticated"] is True
        assert me["id"] == str(user.id)
        assert me["roles"] == [] and me["permissions"] == []
    finally:
        cleanup([str(user.id)], [], [], [], [])


def test_enforcing_mode_rejects_anonymous_bad_and_disabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "enforcing")
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/projects",
                      headers={"Authorization": "Bearer garbage"}).status_code == 401
    user = make_user("disabled-user")
    try:
        session = get_session()
        try:
            row = session.query(User).filter_by(id=str(user.id)).one()
            row.status = "DISABLED"
            session.commit()
        finally:
            session.close()
        assert client.get("/api/v1/auth/me",
                          headers=headers_for(str(user.id))).status_code == 401
    finally:
        cleanup([str(user.id)], [], [], [], [])


def test_dev_tokens_disabled_rejects_tokens(monkeypatch):
    monkeypatch.setattr(settings, "auth_dev_tokens_enabled", False)
    user = make_user("notoken-user")
    try:
        assert client.get("/api/v1/auth/me",
                          headers=headers_for(str(user.id))).status_code == 401
    finally:
        cleanup([str(user.id)], [], [], [], [])


def test_project_isolation():
    owner = make_user("owner-a")
    user = make_user("proj-user")
    project_ids, org_ids = [], []
    try:
        project_a = setup_project(str(owner.id), "iso A")
        project_b = setup_project(str(owner.id), "iso B")
        project_ids.extend([project_a["id"], project_b["id"]])
        assign(str(user.id), "REVIEWER", "PROJECT", project_a["id"])

        ok = client.get(f"/api/v1/projects/{project_a['id']}",
                        headers=headers_for(str(user.id)))
        assert ok.status_code == 200
        denied = client.get(f"/api/v1/projects/{project_b['id']}",
                            headers=headers_for(str(user.id)))
        assert denied.status_code == 404
        listed = client.get("/api/v1/projects", headers=headers_for(str(user.id))).json()
        assert project_a["id"] in {item["id"] for item in listed["items"]}
        assert project_b["id"] not in {item["id"] for item in listed["items"]}
    finally:
        cleanup([str(owner.id), str(user.id)], project_ids, [], [], [])


def test_organization_isolation():
    owner = make_user("owner-org")
    user = make_user("org-user")
    project_ids, org_ids = [], []
    try:
        org_a = setup_org("A")
        org_b = setup_org("B")
        org_ids.extend([str(org_a.id), str(org_b.id)])
        project_a = setup_project(str(owner.id), "orgA proj", str(org_a.id))
        project_b = setup_project(str(owner.id), "orgB proj", str(org_b.id))
        project_ids.extend([project_a["id"], project_b["id"]])
        assign(str(user.id), "REVIEWER", "ORGANIZATION", str(org_a.id))

        assert client.get(f"/api/v1/projects/{project_a['id']}",
                          headers=headers_for(str(user.id))).status_code == 200
        assert client.get(f"/api/v1/projects/{project_b['id']}",
                          headers=headers_for(str(user.id))).status_code == 404
    finally:
        cleanup([str(owner.id), str(user.id)], project_ids, [], org_ids, [])


def test_unit_scope_narrowing():
    owner = make_user("owner-unit")
    user = make_user("unit-user")
    project_ids, org_ids = [], []
    try:
        session = get_session()
        try:
            org = auth_service.create_organization(session, name="U", code=f"u-{uuid4().hex[:6]}")
            unit1 = auth_service.create_organizational_unit(
                session, organization_id=str(org.id), name="U1", code="u1")
            unit2 = auth_service.create_organizational_unit(
                session, organization_id=str(org.id), name="U2", code="u2")
            session.commit()
            org_id, unit1_id, unit2_id = str(org.id), str(unit1.id), str(unit2.id)
        finally:
            session.close()
        org_ids.append(org_id)
        project1 = setup_project(str(owner.id), "unit1 proj")
        project2 = setup_project(str(owner.id), "unit2 proj")
        project_ids.extend([project1["id"], project2["id"]])
        session = get_session()
        try:
            session.execute(text("UPDATE projects SET organizational_unit_id=:u WHERE id=:i"),
                            {"u": unit1_id, "i": project1["id"]})
            session.execute(text("UPDATE projects SET organizational_unit_id=:u WHERE id=:i"),
                            {"u": unit2_id, "i": project2["id"]})
            session.commit()
        finally:
            session.close()
        assign(str(user.id), "REVIEWER", "ORGANIZATIONAL_UNIT", unit1_id)

        assert client.get(f"/api/v1/projects/{project1['id']}",
                          headers=headers_for(str(user.id))).status_code == 200
        assert client.get(f"/api/v1/projects/{project2['id']}",
                          headers=headers_for(str(user.id))).status_code == 404
    finally:
        cleanup([str(owner.id), str(user.id)], project_ids, [], org_ids, [])


def _urgent_case(owner_id: str, color=(101, 171, 241)):
    from backend.services.duplicate_intelligence import analyze_duplicates
    from backend.services.fingerprinting import process_evidence

    payload = image_bytes(color)
    first = client.post("/api/v1/evidence",
                        files={"file": ("a.jpg", payload, "image/jpeg")}).json()
    second = client.post("/api/v1/evidence",
                         files={"file": ("b.jpg", payload, "image/jpeg")}).json()
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
    return first, second, run, case


def _drive_case_to_investigating(case_id: str):
    reviewer = make_user("driver")
    assign(str(reviewer.id), "SUPERVISOR", "GLOBAL", None)
    headers = headers_for(str(reviewer.id))
    assert client.post(f"/api/v1/review-cases/{case_id}/assign",
                       json={"assigned_to": str(reviewer.id)}, headers=headers).status_code == 200
    assert client.post(f"/api/v1/review-cases/{case_id}/investigate",
                       headers=headers).status_code == 200
    return reviewer


def test_substantive_authority_separation():
    owner = make_user("owner-sub")
    reader = make_user("reader-only")
    supervisor = make_user("supervisor")
    user_ids = [str(owner.id), str(reader.id), str(supervisor.id)]
    project_ids, evidence_ids = [], []
    run = case = None
    try:
        project = setup_project(str(owner.id), "substantive proj")
        project_ids.append(project["id"])
        first, second, run, case = _urgent_case(str(owner.id))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        session = get_session()
        try:
            for eid in (first["evidence_id"], second["evidence_id"]):
                session.execute(text("UPDATE evidence SET project_id=:p WHERE id=:e"),
                                {"p": project["id"], "e": eid})
            session.execute(text("UPDATE review_cases SET project_id=:p WHERE id=:c"),
                            {"p": project["id"], "c": case["id"]})
            session.commit()
        finally:
            session.close()

        # FIELD_OFFICER can read cases but holds no investigate/decide
        # authority: read does not imply substantive action.
        assign(str(reader.id), "FIELD_OFFICER", "PROJECT", project["id"])
        reader_headers = headers_for(str(reader.id))
        assert client.get(f"/api/v1/review-cases/{case['id']}",
                          headers=reader_headers).status_code == 200
        assert client.post(f"/api/v1/review-cases/{case['id']}/investigate",
                           headers=reader_headers).status_code == 403
        decide = client.post(
            f"/api/v1/review-cases/{case['id']}/decision",
            json={"decision": "SUPPORTED", "rationale": "x"},
            headers=reader_headers)
        assert decide.status_code == 403

        # A supervisor with decide permission can invoke the endpoint
        # (through the real lifecycle, which remains authoritative).
        try:
            assign(str(supervisor.id), "SUPERVISOR", "PROJECT", project["id"])
            sup_headers = headers_for(str(supervisor.id))
            assert client.post(
                f"/api/v1/review-cases/{case['id']}/assign",
                json={"assigned_to": str(supervisor.id)}, headers=sup_headers).status_code == 200
            assert client.post(f"/api/v1/review-cases/{case['id']}/investigate",
                               headers=sup_headers).status_code == 200
            decided = client.post(
                f"/api/v1/review-cases/{case['id']}/decision",
                json={"decision": "INCONCLUSIVE", "rationale": "field visit",
                      "decided_by": str(supervisor.id)},
                headers=sup_headers)
            assert decided.status_code == 200
            assert decided.json()["decision"] == "INCONCLUSIVE"
        finally:
            pass
    finally:
        session = get_session()
        try:
            if evidence_ids:
                session.query(Evidence).filter(
                    Evidence.id.in_(evidence_ids)).update(
                    {Evidence.project_id: None}, synchronize_session=False)
            if case is not None:
                session.query(ReviewCase).filter(
                    ReviewCase.id == case["id"]).update(
                    {ReviewCase.project_id: None}, synchronize_session=False)
            session.commit()
        finally:
            session.close()
        from backend.db.models import ReviewCase as _RC, ReviewCaseEvent as _RCE

        session = get_session()
        try:
            if case is not None:
                session.query(_RCE).filter(_RCE.case_id == case["id"]).delete(
                    synchronize_session=False)
                session.query(_RC).filter(_RC.id == case["id"]).delete(
                    synchronize_session=False)
                session.commit()
        finally:
            session.close()
        cleanup(user_ids, project_ids, evidence_ids, [], [])


def test_administrator_cannot_decide_but_can_administer():
    owner = make_user("owner-adm")
    admin = make_user("global-admin")
    project_ids, evidence_ids = [], []
    run = case = None
    try:
        project = setup_project(str(owner.id), "admin proj")
        project_ids.append(project["id"])
        first, second, run, case = _urgent_case(str(owner.id))
        evidence_ids.extend([first["evidence_id"], second["evidence_id"]])
        assign(str(admin.id), "ADMINISTRATOR", "GLOBAL", None)
        admin_headers = headers_for(str(admin.id))

        assert client.post(f"/api/v1/review-cases/{case['id']}/investigate",
                           headers=admin_headers).status_code == 403
        decided = client.post(
            f"/api/v1/review-cases/{case['id']}/decision",
            json={"decision": "SUPPORTED", "rationale": "x"},
            headers=admin_headers)
        assert decided.status_code == 403

        org = client.post("/api/v1/auth/organizations",
                          json={"name": "Admin Org", "code": f"adm-{uuid4().hex[:6]}"},
                          headers=admin_headers)
        assert org.status_code == 201
        session = get_session()
        try:
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "ORGANIZATION_CREATED",
                AuditLedgerEvent.resource_id == org.json()["id"],
            ).count() == 1
            # BE-015: the audit ledger is append-only and is deliberately
            # NEVER cleaned up by tests. Deleting this event would leave a
            # permanent sequence gap in the hash chain, because sequence
            # numbers are allocated as max(sequence_number) + 1 and are
            # never reused. The organization row itself is still removed
            # (no FK points at it from the ledger -- audit_ledger_events
            # references its subjects only by id, never by constraint, so
            # an audit row outliving its subject is correct behaviour, not
            # an orphan).
            from backend.db.models import Organization as _O

            session.query(_O).filter(_O.id == org.json()["id"]).delete()
            session.commit()
        finally:
            session.close()
    finally:
        session = get_session()
        try:
            from backend.db.models import (
                CaseGenerationRun,
                FusionRun,
                FusionSignal,
                IntegrityAssessment,
                ReviewCase as _RC,
                ReviewCaseEvent as _RCE,
                ReviewPriority,
            )

            target_runs = [run["id"]] if run else []
            target_cases = [case["id"]] if case else []
            session.query(_RCE).filter(_RCE.case_id.in_(target_cases)).delete(
                synchronize_session=False)
            session.query(_RC).filter(_RC.id.in_(target_cases)).delete(
                synchronize_session=False)
            session.query(CaseGenerationRun).filter(
                CaseGenerationRun.fusion_run_id.in_(target_runs)).delete(
                synchronize_session=False)
            session.query(FusionSignal).filter(
                FusionSignal.fusion_run_id.in_(target_runs)).delete(
                synchronize_session=False)
            session.query(IntegrityAssessment).filter(
                IntegrityAssessment.fusion_run_id.in_(target_runs)).delete(
                synchronize_session=False)
            session.query(ReviewPriority).filter(
                ReviewPriority.fusion_run_id.in_(target_runs)).delete(
                synchronize_session=False)
            session.query(FusionRun).filter(FusionRun.id.in_(target_runs)).delete(
                synchronize_session=False)
            session.commit()
        finally:
            session.close()
        cleanup([str(owner.id), str(admin.id)], project_ids, evidence_ids, [], [])


def test_evidence_download_protection():
    owner = make_user("owner-ev")
    reviewer = make_user("ev-reviewer")
    project_ids, evidence_ids = [], []
    try:
        project = setup_project(str(owner.id), "ev proj")
        project_ids.append(project["id"])
        uploaded = client.post(
            "/api/v1/evidence",
            files={"file": ("prot.jpg", image_bytes(), "image/jpeg")}).json()
        evidence_ids.append(uploaded["evidence_id"])
        link_session = get_session()
        try:
            link_session.execute(text("UPDATE evidence SET project_id=:p WHERE id=:e"),
                                 {"p": project["id"], "e": uploaded["evidence_id"]})
            link_session.commit()
        finally:
            link_session.close()

        # No permission at all -> 403.
        assert client.get(f"/api/v1/evidence/{uploaded['evidence_id']}/download",
                          headers=headers_for(str(reviewer.id))).status_code == 403
        assign(str(reviewer.id), "REVIEWER", "PROJECT", project["id"])
        authorized = client.get(f"/api/v1/evidence/{uploaded['evidence_id']}/download",
                                headers=headers_for(str(reviewer.id)))
        assert authorized.status_code == 200
        assert authorized.json()["download_url"].startswith("http")
        meta = client.get(f"/api/v1/evidence/{uploaded['evidence_id']}",
                          headers=headers_for(str(reviewer.id))).json()
        assert meta["id"] == uploaded["evidence_id"]
        assert "storage_key" not in meta
    finally:
        link_session = get_session()
        try:
            link_session.execute(text("UPDATE evidence SET project_id=NULL WHERE id=:e"),
                                 {"e": evidence_ids[0]})
            link_session.commit()
        finally:
            link_session.close()
        cleanup([str(owner.id), str(reviewer.id)], project_ids, evidence_ids, [], [])


def test_cross_project_graph_redaction():
    owner = make_user("owner-x")
    reviewer = make_user("x-reviewer")
    project_ids, evidence_ids = [], []
    try:
        project_a = setup_project(str(owner.id), "xA")
        project_b = setup_project(str(owner.id), "xB")
        project_ids.extend([project_a["id"], project_b["id"]])
        payload = image_bytes((111, 181, 251))
        ev_a = client.post("/api/v1/evidence",
                           files={"file": ("xa.jpg", payload, "image/jpeg")}).json()
        ev_b = client.post("/api/v1/evidence",
                           files={"file": ("xb.jpg", payload, "image/jpeg")}).json()
        evidence_ids.extend([ev_a["evidence_id"], ev_b["evidence_id"]])
        session = get_session()
        try:
            session.execute(text("UPDATE evidence SET project_id=:p WHERE id=:e"),
                            {"p": project_a["id"], "e": ev_a["evidence_id"]})
            session.execute(text("UPDATE evidence SET project_id=:p WHERE id=:e"),
                            {"p": project_b["id"], "e": ev_b["evidence_id"]})
            session.commit()
        finally:
            session.close()
        edge = client.post("/api/v1/graph/relationships", json={
            "source": {"node_type": "EVIDENCE", "entity_id": ev_a["evidence_id"]},
            "target": {"node_type": "EVIDENCE", "entity_id": ev_b["evidence_id"]},
            "relationship_type": "ASSOCIATED_WITH",
            "provenance": {"source": "human_review", "method": "manual_link"}})
        assert edge.status_code == 201

        assign(str(reviewer.id), "REVIEWER", "PROJECT", project_a["id"])
        reviewer_headers = headers_for(str(reviewer.id))
        traversal = client.get(f"/api/v1/graph/EVIDENCE/{ev_a['evidence_id']}",
                               headers=reviewer_headers).json()
        # The cross-project edge is redacted: no Project B details leak.
        assert all(ev_b["evidence_id"] not in json.dumps(item) for item in traversal["items"])
        assert client.get(f"/api/v1/evidence/{ev_b['evidence_id']}",
                          headers=reviewer_headers).status_code == 404
    finally:
        session = get_session()
        try:
            for eid in evidence_ids:
                session.execute(text("UPDATE evidence SET project_id=NULL WHERE id=:e"),
                                {"e": eid})
            session.commit()
        finally:
            session.close()
        cleanup([str(owner.id), str(reviewer.id)], project_ids, evidence_ids, [], [])


def test_role_assignment_audit_and_concurrency():
    owner = make_user("owner-role")
    target = make_user("role-target")
    admin = make_user("role-admin")
    try:
        assign(str(admin.id), "ADMINISTRATOR", "GLOBAL", None)
        admin_headers = headers_for(str(admin.id))
        created = client.post(
            f"/api/v1/auth/users/{target.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "GLOBAL"},
            headers=admin_headers)
        assert created.status_code == 201
        assignment_id = created.json()["id"]
        session = get_session()
        try:
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "ROLE_ASSIGNED").count() >= 1
        finally:
            session.close()
        repeat = client.post(
            f"/api/v1/auth/users/{target.id}/roles",
            json={"role_name": "REVIEWER", "scope_type": "GLOBAL"},
            headers=admin_headers)
        assert repeat.status_code == 200

        results = []

        def fire():
            try:
                response = client.post(
                    f"/api/v1/auth/users/{target.id}/roles",
                    json={"role_name": "FIELD_OFFICER", "scope_type": "GLOBAL"},
                    headers=admin_headers)
                results.append(response.status_code)
            except Exception as error:  # pragma: no cover - diagnostic only
                results.append(str(error)[:100])

        threads = [threading.Thread(target=fire) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(results) == 10
        assert all(code in (200, 201) for code in results)
        session = get_session()
        try:
            from backend.db.models import Role as _Role

            role_id = session.query(_Role).filter_by(name="FIELD_OFFICER").one().id
            assert session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id == str(target.id),
                UserRoleAssignment.role_id == str(role_id)).count() == 1
            revoked = client.delete(
                f"/api/v1/auth/users/{target.id}/roles/{assignment_id}",
                headers=admin_headers)
            assert revoked.status_code == 204
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "ROLE_REVOKED").count() >= 1
        finally:
            session.close()
    finally:
        cleanup([str(owner.id), str(target.id), str(admin.id)], [], [], [], [])


def test_stale_assignment_loses_access_immediately():
    owner = make_user("owner-stale")
    user = make_user("stale-user")
    project_ids = []
    try:
        project = setup_project(str(owner.id), "stale proj")
        project_ids.append(project["id"])
        assign(str(user.id), "REVIEWER", "PROJECT", project["id"])
        headers = headers_for(str(user.id))
        assert client.get(f"/api/v1/projects/{project['id']}", headers=headers).status_code == 200
        session = get_session()
        try:
            deleted = session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id == str(user.id)).delete(synchronize_session=False)
            assert deleted == 1
            session.commit()
        finally:
            session.close()
        # No caching: the revoked permission is denied at once.
        denied = client.get(f"/api/v1/projects/{project['id']}", headers=headers)
        assert denied.status_code in (403, 404)
    finally:
        cleanup([str(owner.id), str(user.id)], project_ids, [], [], [])


def test_forged_scope_and_role_ignored():
    owner = make_user("owner-forge")
    user = make_user("forge-user")
    project_ids = []
    try:
        project_a = setup_project(str(owner.id), "forge A")
        project_b = setup_project(str(owner.id), "forge B")
        project_ids.extend([project_a["id"], project_b["id"]])
        assign(str(user.id), "REVIEWER", "PROJECT", project_a["id"])
        headers = headers_for(str(user.id))
        # Extra body fields claiming other roles/projects change nothing.
        response = client.get(f"/api/v1/projects/{project_b['id']}", headers=headers)
        assert response.status_code == 404
        forged = client.patch(
            f"/api/v1/projects/{project_b['id']}",
            json={"name": "hijacked", "role": "ADMINISTRATOR",
                  "project_id": project_a["id"], "permission": "project.update"},
            headers=headers)
        assert forged.status_code in (403, 404, 422)
        session = get_session()
        try:
            name = session.execute(
                text("SELECT name FROM projects WHERE id=:i"),
                {"i": project_b["id"]}).scalar()
            assert name == "forge B"
        finally:
            session.close()
    finally:
        cleanup([str(owner.id), str(user.id)], project_ids, [], [], [])


def test_citizen_is_sharply_limited():
    owner = make_user("owner-cit")
    citizen = make_user("citizen")
    project_ids = []
    try:
        project = setup_project(str(owner.id), "citizen proj")
        project_ids.append(project["id"])
        assign(str(citizen.id), "CITIZEN", "PROJECT", project["id"])
        headers = headers_for(str(citizen.id))
        assert client.get("/api/v1/graph/EVIDENCE/" + str(uuid4()),
                          headers=headers).status_code in (403, 404)
        assert client.get("/api/v1/audit/events", headers=headers).status_code == 403
        assert client.post("/api/v1/fusion/configurations", json={
            "version": "citizen-cfg", "name": "x",
            "weights": {"GRAPH_SUPPORT": 0.5},
            "thresholds": {"low_max": 0.25, "normal_max": 0.5, "high_max": 0.75},
            "priority": {"base": 0.0}}, headers=headers).status_code == 403
    finally:
        cleanup([str(owner.id), str(citizen.id)], project_ids, [], [], [])


def test_api_client_scopes():
    owner = make_user("owner-client")
    project_ids, client_ids = [], []
    try:
        project = setup_project(str(owner.id), "client proj")
        project_ids.append(project["id"])
        session = get_session()
        try:
            from backend.services import authorization as auth_svc

            auth_svc.ensure_default_catalogue(session)
            reader = auth_svc.create_api_client(
                session, name=f"reader-{uuid4().hex[:8]}",
                scopes=["evidence.read"], project_id=project["id"])
            decider = auth_svc.create_api_client(
                session, name=f"decider-{uuid4().hex[:8]}",
                scopes=["evidence.read"], project_id=project["id"])
            session.commit()
            reader_id, decider_id = str(reader.id), str(decider.id)
        finally:
            session.close()
        client_ids.extend([reader_id, decider_id])
        uploaded = client.post(
            "/api/v1/evidence",
            files={"file": ("client.jpg", image_bytes(), "image/jpeg")}).json()
        session = get_session()
        try:
            session.execute(text("UPDATE evidence SET project_id=:p WHERE id=:e"),
                            {"p": project["id"], "e": uploaded["evidence_id"]})
            session.commit()
        finally:
            session.close()
        reader_headers = {"Authorization": f"Bearer dev-client-{reader_id}"}
        assert client.get(f"/api/v1/evidence/{uploaded['evidence_id']}",
                          headers=reader_headers).status_code == 200
        # evidence.read never implies review_case.decide.
        assert client.get(f"/api/v1/audit/events",
                          headers=reader_headers).status_code == 403
        assert client.get("/api/v1/auth/me", headers=reader_headers).json()[
            "principal_type"] == "API_CLIENT"
        evidence_ids = [uploaded["evidence_id"]]
    finally:
        session = get_session()
        try:
            session.execute(text("UPDATE evidence SET project_id=NULL WHERE id=:e"),
                            {"e": evidence_ids[0]})
            session.commit()
        finally:
            session.close()
        cleanup([str(owner.id)], project_ids, evidence_ids, [], client_ids)


def test_global_principal_cross_project_allowed():
    owner = make_user("owner-global")
    supervisor = make_user("global-sup")
    project_ids = []
    try:
        project_a = setup_project(str(owner.id), "global A")
        project_b = setup_project(str(owner.id), "global B")
        project_ids.extend([project_a["id"], project_b["id"]])
        assign(str(supervisor.id), "SUPERVISOR", "GLOBAL", None)
        headers = headers_for(str(supervisor.id))
        assert client.get(f"/api/v1/projects/{project_a['id']}",
                          headers=headers).status_code == 200
        assert client.get(f"/api/v1/projects/{project_b['id']}",
                          headers=headers).status_code == 200
    finally:
        cleanup([str(owner.id), str(supervisor.id)], project_ids, [], [], [])


def test_user_and_org_admin_endpoints():
    admin = make_user("user-admin")
    try:
        assign(str(admin.id), "ADMINISTRATOR", "GLOBAL", None)
        headers = headers_for(str(admin.id))
        created = client.post("/api/v1/auth/users", json={
            "username": f"managed-{uuid4().hex[:8]}",
            "email": f"{uuid4().hex[:8]}@example.com"}, headers=headers)
        assert created.status_code == 201
        managed_id = created.json()["id"]
        assert client.get(f"/api/v1/auth/users/{managed_id}",
                          headers=headers).status_code == 200
        assert client.get("/api/v1/auth/roles", headers=headers).status_code == 200
        assert client.get("/api/v1/auth/permissions", headers=headers).status_code == 200
        roles = client.get("/api/v1/auth/roles", headers=headers).json()
        assert {role["name"] for role in roles} >= {
            "CITIZEN", "FIELD_OFFICER", "REVIEWER", "SUPERVISOR", "ADMINISTRATOR"}
        session = get_session()
        try:
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "USER_CREATED",
                AuditLedgerEvent.resource_id == managed_id).count() == 1
            session.query(User).filter(User.id == managed_id).delete()
            session.commit()
        finally:
            session.close()
        # Non-admin cannot manage users.
        outsider = make_user("outsider")
        try:
            assert client.post("/api/v1/auth/users", json={
                "username": "x", "email": "x@example.com"},
                headers=headers_for(str(outsider.id))).status_code == 403
        finally:
            cleanup([str(outsider.id)], [], [], [], [])
    finally:
        cleanup([str(admin.id)], [], [], [], [])
