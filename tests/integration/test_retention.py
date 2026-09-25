"""BE-017 integration tests against real PostgreSQL + MinIO infrastructure."""

import hashlib
import threading
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from backend.app.main import app
from backend.db.models import (
    Activity,
    AuditLedgerEvent,
    Claim,
    DuplicateMatch,
    Evidence,
    EvidenceMetadata,
    FusionRun,
    Project,
    RetentionHold,
    RetentionOperation,
    RetentionPolicy,
    RetentionPolicyVersion,
    RetentionState,
    ReviewCase,
    ReviewCaseEvent,
    User,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service
from backend.services.storage import StorageService


client = TestClient(app)


def image_bytes(color=(110, 180, 250)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(output, format="JPEG")
    return output.getvalue()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_admin(username: str = "retention-admin"):
    session = get_session()
    try:
        auth_service.ensure_default_catalogue(session)
        user = User(username=f"{username}-{uuid4().hex[:8]}",
                    email=f"{uuid4().hex[:8]}@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        auth_service.assign_role(session, user_id=str(user.id),
                                 role_name="ADMINISTRATOR", scope_type="GLOBAL")
        session.commit()
        uid = str(user.id)
    finally:
        session.close()
    return uid, {"Authorization": f"Bearer dev-user-{uid}"}


def make_project(owner_id: str, name: str) -> dict:
    response = client.post("/api/v1/projects", json={"name": name, "owner_id": owner_id})
    assert response.status_code == 201
    return response.json()


def upload(data: bytes, filename: str) -> dict:
    response = client.post("/api/v1/evidence", files={"file": (filename, data, "image/jpeg")})
    assert response.status_code == 201
    return response.json()


def link_evidence(evidence_id: str, project_id: str) -> None:
    session = get_session()
    try:
        session.execute(text("UPDATE evidence SET project_id=:p WHERE id=:e"),
                        {"p": project_id, "e": evidence_id})
        session.commit()
    finally:
        session.close()


def backdate_evidence(evidence_id: str, days: int) -> None:
    session = get_session()
    try:
        session.execute(
            text("UPDATE evidence SET created_at = now() - make_interval(days => :d) "
                 "WHERE id = :e"),
            {"d": days, "e": evidence_id},
        )
        session.commit()
    finally:
        session.close()


def make_policy(headers, resource_type="EVIDENCE", scope="GLOBAL", scope_id=None,
                rules=None, activate=True, project_id=None):
    payload = {"name": f"pol-{uuid4().hex[:8]}", "resource_type": resource_type,
               "scope_type": scope}
    if scope == "PROJECT":
        payload["project_id"] = scope_id or project_id
    elif scope == "ORGANIZATION":
        payload["organization_id"] = scope_id
    elif scope == "ORGANIZATIONAL_UNIT":
        payload["organizational_unit_id"] = scope_id
    policy = client.post("/api/v1/retention/policies", json=payload, headers=headers).json()
    version = client.post(f"/api/v1/retention/policies/{policy['id']}/versions", json={
        "rules": rules or {"retention_days": 365, "archive_after_days": None,
                           "anchor": "INGESTED_AT", "allow_derived_cleanup": False},
    }, headers=headers).json()
    if activate:
        client.post(f"/api/v1/retention/policies/versions/{version['id']}/activate",
                    headers=headers)
    return policy, version


def _purge_all_retention_policies() -> None:
    """Remove every retention policy so a test can assert an empty catalogue.

    Only used by tests whose contract is "no policy applies". Everything else
    scopes its policy to its own project and never needs this.
    """
    session = get_session()
    try:
        policy_ids = [row[0] for row in session.query(RetentionPolicy.id).all()]
        if not policy_ids:
            return
        session.query(RetentionPolicyVersion).filter(
            RetentionPolicyVersion.policy_id.in_(policy_ids)).delete(synchronize_session=False)
        session.query(RetentionPolicy).filter(
            RetentionPolicy.id.in_(policy_ids)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def cleanup(user_ids, project_ids, evidence_ids, policy_ids=None, hold_ids=None) -> None:
    storage = StorageService()
    session = get_session()
    try:
        if evidence_ids:
            keys = [row[0] for row in session.query(Evidence.storage_key)
                    .filter(Evidence.id.in_(evidence_ids)).all()]
            for key in keys:
                for bucket in (storage.quarantine_bucket, storage.evidence_bucket):
                    if storage.object_exists(bucket, key):
                        storage.delete_object(bucket, key)
            # Archive copies live under archive/ in the evidence bucket.
            archived = [f"archive/{eid}/original" for eid in evidence_ids]
            for key in archived:
                if storage.object_exists(storage.evidence_bucket, key):
                    storage.delete_object(storage.evidence_bucket, key)
            session.query(DuplicateMatch).filter(
                (DuplicateMatch.evidence_id.in_(evidence_ids))
                | (DuplicateMatch.matched_evidence_id.in_(evidence_ids))).delete(
                synchronize_session=False)
            session.query(EvidenceMetadata).filter(
                EvidenceMetadata.evidence_id.in_(evidence_ids)).delete(
                synchronize_session=False)
            session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).update(
                {Evidence.project_id: None, Evidence.claim_id: None},
                synchronize_session=False)
            session.query(Evidence).filter(Evidence.id.in_(evidence_ids)).delete(
                synchronize_session=False)
            session.query(RetentionState).filter(
                RetentionState.resource_id.in_(evidence_ids)).delete(synchronize_session=False)
            session.query(RetentionOperation).filter(
                RetentionOperation.resource_id.in_(evidence_ids)).delete(
                synchronize_session=False)
        if hold_ids:
            session.query(RetentionHold).filter(RetentionHold.id.in_(hold_ids)).delete(
                synchronize_session=False)
        if policy_ids:
            versions = [row[0] for row in session.query(RetentionPolicyVersion.id)
                        .filter(RetentionPolicyVersion.policy_id.in_(policy_ids)).all()]
            if versions:
                session.query(RetentionOperation).filter(
                    RetentionOperation.details.is_not(None)).delete(synchronize_session=False) \
                    if False else None
            session.query(RetentionPolicyVersion).filter(
                RetentionPolicyVersion.policy_id.in_(policy_ids)).delete(
                synchronize_session=False)
            session.query(RetentionPolicy).filter(RetentionPolicy.id.in_(policy_ids)).delete(
                synchronize_session=False)
        # Project-scoped role assignments reference the project by FK, so they
        # must be removed BEFORE the projects they point at. Deleting projects
        # first violates that FK and aborts the whole cleanup transaction.
        if user_ids or project_ids:
            from backend.db.models import UserRoleAssignment

            if project_ids:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.project_id.in_(project_ids)).delete(
                    synchronize_session=False)
            if user_ids:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.user_id.in_(user_ids)).delete(
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
        session.commit()
    finally:
        session.close()


def test_policy_lifecycle_and_validation():
    admin_id, headers = make_admin()
    policy_ids, project_ids = [], []
    try:
        # Scoped to its own project so an ACTIVE version here can never collide
        # with another test's policy during evaluation.
        project = make_project(admin_id, "retention lifecycle")
        project_ids.append(project["id"])
        policy, v1 = make_policy(headers, scope="PROJECT",
                                 scope_id=project["id"], activate=False)
        policy_ids.append(policy["id"])
        assert v1["status"] == "DRAFT" and v1["version"] == 1
        assert client.post(f"/api/v1/retention/policies/versions/{v1['id']}/activate",
                           headers=headers).json()["status"] == "ACTIVE"
        history = client.get(f"/api/v1/retention/policies/{policy['id']}/history",
                             headers=headers).json()
        assert [v["version"] for v in history] == [1]
        v2 = client.post(f"/api/v1/retention/policies/{policy['id']}/versions", json={
            "rules": {"retention_days": 100, "archive_after_days": None,
                      "anchor": "INGESTED_AT", "allow_derived_cleanup": False},
        }, headers=headers).json()
        assert v2["version"] == 2
        activated = client.post(f"/api/v1/retention/policies/versions/{v2['id']}/activate",
                                headers=headers).json()
        assert activated["status"] == "ACTIVE"
        history = client.get(f"/api/v1/retention/policies/{policy['id']}/history",
                             headers=headers).json()
        assert [(v["version"], v["status"]) for v in history] == [(1, "SUPERSEDED"), (2, "ACTIVE")]
        # Invalid rules rejected, never clamped.
        bad = client.post(f"/api/v1/retention/policies/{policy['id']}/versions", json={
            "rules": {"retention_days": 10, "archive_after_days": 20,
                      "anchor": "INGESTED_AT", "allow_derived_cleanup": False},
        }, headers=headers)
        assert bad.status_code == 422
        assert client.post("/api/v1/retention/policies", json={
            "name": "bad", "resource_type": "BOGUS", "scope_type": "GLOBAL",
        }, headers=headers).status_code == 422
        # Audit trail for policy lifecycle. v1 is activated here and v2 is
        # activated above, so this policy has TWO activation events -- one per
        # lifecycle operation, as the BE-015 ledger contract requires.
        session = get_session()
        try:
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "RETENTION_POLICY_ACTIVATED",
                AuditLedgerEvent.resource_id == policy["id"]).count() == 2
        finally:
            session.close()
    finally:
        cleanup([admin_id], project_ids, [], policy_ids)


def test_eligible_and_ineligible_evaluation():
    admin_id, headers = make_admin()
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project = make_project(admin_id, "retention eval")
        project_ids.append(project["id"])
        fresh = upload(image_bytes(), "fresh.jpg")
        old = upload(image_bytes((1, 2, 3)), "old.jpg")
        evidence_ids.extend([fresh["evidence_id"], old["evidence_id"]])
        link_evidence(fresh["evidence_id"], project["id"])
        link_evidence(old["evidence_id"], project["id"])
        backdate_evidence(old["evidence_id"], 400)
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 365, "archive_after_days": None,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": False})
        policy_ids.append(policy["id"])

        fresh_eval = client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": fresh["evidence_id"]},
            headers=headers).json()
        assert fresh_eval["deletion_eligible"] is False
        assert "RETENTION_PERIOD_NOT_REACHED" in fresh_eval["blocking_reasons"]
        assert fresh_eval["state"] == "ACTIVE"

        old_eval = client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": old["evidence_id"]},
            headers=headers).json()
        assert old_eval["deletion_eligible"] is True
        assert old_eval["blocking_reasons"] == []
        assert old_eval["state"] == "ELIGIBLE_FOR_DELETION"
        assert old_eval["policy_version"] == 1

        # Dry-run writes nothing.
        session = get_session()
        try:
            assert session.query(RetentionState).filter(
                RetentionState.resource_id.in_(evidence_ids)).count() == 0
        finally:
            session.close()

        # Unknown target and bad identifiers.
        assert client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE",
            "resource_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers).status_code == 404
        assert client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": "nope"},
            headers=headers).status_code == 422
    finally:
        cleanup([admin_id], project_ids, evidence_ids, policy_ids)


def test_unknown_and_missing_policy_fail_closed():
    admin_id, headers = make_admin()
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project = make_project(admin_id, "retention unknown")
        project_ids.append(project["id"])
        evidence = upload(image_bytes((4, 5, 6)), "unknown.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"])

        # This test asserts NO_APPLICABLE_POLICY, which is only meaningful when
        # no policy can match. The suite runs against a persistent database, and
        # an earlier failing run can leave an ACTIVE policy behind -- a GLOBAL
        # one would then match this evidence and turn the expected
        # NO_APPLICABLE_POLICY into POLICY_CONFLICT. Establish the precondition
        # explicitly instead of inheriting whatever the database happens to hold.
        _purge_all_retention_policies()

        # No policy at all: fail closed.
        body = client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()
        assert body["deletion_eligible"] is False
        assert body["blocking_reasons"] == ["NO_APPLICABLE_POLICY"]

        # CAPTURED_AT anchor with no EXIF: missing anchor, not negative.
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 1, "archive_after_days": None,
            "anchor": "CAPTURED_AT", "allow_derived_cleanup": False})
        policy_ids = [policy["id"]]
        body = client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()
        assert body["deletion_eligible"] is False
        assert body["blocking_reasons"] == ["MISSING_RETENTION_ANCHOR"]
    finally:
        cleanup([admin_id], project_ids, evidence_ids, policy_ids)


def test_hold_blocks_and_release_restores():
    admin_id, headers = make_admin()
    project_ids, evidence_ids, policy_ids, hold_ids = [], [], [], []
    try:
        project = make_project(admin_id, "retention hold")
        project_ids.append(project["id"])
        evidence = upload(image_bytes((7, 8, 9)), "held.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"])
        backdate_evidence(evidence["evidence_id"], 400)
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 365, "archive_after_days": None,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": False})
        policy_ids.append(policy["id"])
        assert client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()["deletion_eligible"] is True

        hold = client.post("/api/v1/retention/holds", json={
            "scope": "RESOURCE", "resource_type": "EVIDENCE",
            "resource_id": evidence["evidence_id"], "reason": "dispute filed"},
            headers=headers).json()
        hold_ids.append(hold["id"])
        assert hold["status"] == "ACTIVE"
        blocked = client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()
        assert blocked["deletion_eligible"] is False
        assert blocked["blocking_reasons"] == ["ACTIVE_HOLD"]

        # Deletion attempt fails with structured reasons, nothing removed.
        denied = client.post(f"/api/v1/retention/delete/EVIDENCE/{evidence['evidence_id']}",
                             headers=headers)
        assert denied.status_code == 422
        assert "ACTIVE_HOLD" in denied.text
        session = get_session()
        try:
            assert session.query(Evidence).filter_by(id=evidence["evidence_id"]).count() == 1
        finally:
            session.close()

        released = client.post(f"/api/v1/retention/holds/{hold['id']}/release", json={
            "release_reason": "dispute resolved"}, headers=headers).json()
        assert released["status"] == "RELEASED"
        assert released["release_reason"] == "dispute resolved"
        assert client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()["deletion_eligible"] is True
        history = client.get(f"/api/v1/retention/holds/{hold['id']}", headers=headers).json()
        assert history["status"] == "RELEASED"
    finally:
        cleanup([admin_id], project_ids, evidence_ids, policy_ids, hold_ids)


def test_open_case_and_request_block_deletion():
    admin_id, headers = make_admin()
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project = make_project(admin_id, "retention deps")
        project_ids.append(project["id"])
        evidence = upload(image_bytes((10, 11, 12)), "dep.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"])
        backdate_evidence(evidence["evidence_id"], 400)
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 30, "archive_after_days": None,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": True})
        policy_ids.append(policy["id"])

        session = get_session()
        try:
            from backend.db.models import ReviewCase as _Case

            case = _Case(project_id=project["id"], evidence_id=evidence["evidence_id"],
                         origin="SYSTEM_SIGNAL", status="INVESTIGATING")
            session.add(case)
            session.commit()
            case_id = str(case.id)
        finally:
            session.close()
        blocked = client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()
        assert blocked["deletion_eligible"] is False
        assert "OPEN_REVIEW_CASE" in blocked["blocking_reasons"]

        session = get_session()
        try:
            from backend.db.models import ReviewCase as _Case2

            row = session.query(_Case2).filter_by(id=case_id).one()
            row.status = "RESOLVED"
            row.decision = "INCONCLUSIVE"
            row.decision_rationale = "reviewed"
            row.decided_at = datetime.now(timezone.utc)
            session.commit()
        finally:
            session.close()
        assert client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()["deletion_eligible"] is True

        session = get_session()
        try:
            session.query(_Case).filter(_Case.id == case_id).delete()
            session.commit()
        finally:
            session.close()
    finally:
        cleanup([admin_id], project_ids, evidence_ids, policy_ids)


def test_archive_restore_sha_preserved():
    admin_id, headers = make_admin()
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project = make_project(admin_id, "retention archive")
        project_ids.append(project["id"])
        payload = image_bytes((13, 14, 15))
        evidence = upload(payload, "arch.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"])
        backdate_evidence(evidence["evidence_id"], 100)
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 365, "archive_after_days": 30,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": False})
        policy_ids.append(policy["id"])

        evaluation = client.post("/api/v1/retention/evaluate", json={
            "resource_type": "EVIDENCE", "resource_id": evidence["evidence_id"]},
            headers=headers).json()
        assert evaluation["archive_eligible"] is True
        assert evaluation["state"] == "ELIGIBLE_FOR_ARCHIVE"

        archived = client.post(
            f"/api/v1/retention/archive/EVIDENCE/{evidence['evidence_id']}",
            headers=headers).json()
        assert archived["result"] == "ARCHIVED"
        storage = StorageService()
        archived_bytes = storage.get_object_bytes(
            storage.evidence_bucket, archived["storage_key"])
        assert sha256_bytes(archived_bytes) == sha256_bytes(payload)
        session = get_session()
        try:
            assert session.query(Evidence).filter_by(id=evidence["evidence_id"]).count() == 1
        finally:
            session.close()

        repeat = client.post(
            f"/api/v1/retention/archive/EVIDENCE/{evidence['evidence_id']}",
            headers=headers).json()
        assert repeat["result"] == "ALREADY_ARCHIVED"

        restored = client.post(
            f"/api/v1/retention/restore/EVIDENCE/{evidence['evidence_id']}",
            headers=headers).json()
        assert restored["result"] == "RESTORED"
        restored_bytes = storage.get_object_bytes(
            storage.quarantine_bucket, restored["storage_key"])
        assert sha256_bytes(restored_bytes) == sha256_bytes(payload)
        assert restored["storage_key"].startswith("quarantine/")
        again = client.post(
            f"/api/v1/retention/restore/EVIDENCE/{evidence['evidence_id']}",
            headers=headers).json()
        assert again["result"] == "NOT_ARCHIVED"
    finally:
        cleanup([admin_id], project_ids, evidence_ids, policy_ids)


def test_controlled_deletion_end_to_end():
    admin_id, headers = make_admin()
    user_ids = [admin_id]
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project = make_project(admin_id, "retention delete")
        project_ids.extend([project["id"]])
        payload = image_bytes((16, 17, 18))
        evidence = upload(payload, "doomed.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"])
        backdate_evidence(evidence["evidence_id"], 400)
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 30, "archive_after_days": None,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": True})
        policy_ids.append(policy["id"])

        deleted = client.post(
            f"/api/v1/retention/delete/EVIDENCE/{evidence['evidence_id']}",
            headers=headers).json()
        assert deleted["result"] == "DELETED"
        storage = StorageService()
        assert storage.object_exists(
            storage.quarantine_bucket, f"quarantine/{evidence['evidence_id']}/original") is False
        session = get_session()
        try:
            assert session.query(Evidence).filter_by(id=evidence["evidence_id"]).count() == 0
            assert session.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.event_type == "RESOURCE_DELETED",
                AuditLedgerEvent.resource_id == evidence["evidence_id"]).count() == 1
        finally:
            session.close()

        # Idempotent re-delete: deterministic already-completed result.
        again = client.post(
            f"/api/v1/retention/delete/EVIDENCE/{evidence['evidence_id']}",
            headers=headers).json()
        assert again["result"] == "ALREADY_DELETED"
        # Presigned URLs can no longer be issued after deletion. ADMINISTRATOR
        # is an administrative role and deliberately does NOT hold evidence.read
        # (models.py AUTH_ROLE_PERMISSIONS), so asking it would be denied with
        # 403 NO_PERMISSION before existence is ever considered. A CITIZEN does
        # hold evidence.read, so for that principal the 404 is the genuine
        # "no such evidence" signal this assertion is about.
        reader_id, reader_headers = make_admin("retention-evidence-reader")
        user_ids.append(reader_id)
        session = get_session()
        try:
            auth_service.assign_role(session, user_id=reader_id, role_name="CITIZEN",
                                     scope_type="GLOBAL")
            session.commit()
        finally:
            session.close()
        assert client.get(f"/api/v1/evidence/{evidence['evidence_id']}/download",
                          headers=reader_headers).status_code == 404
        # And the administrative role is still correctly denied.
        assert client.get(f"/api/v1/evidence/{evidence['evidence_id']}/download",
                          headers=headers).status_code == 403
        evidence_ids.remove(evidence["evidence_id"])
    finally:
        cleanup(user_ids, project_ids, evidence_ids, policy_ids)


def test_concurrent_deletion_single_winner():
    import threading

    admin_id, headers = make_admin()
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project = make_project(admin_id, "retention race")
        project_ids.append(project["id"])
        evidence = upload(image_bytes((19, 20, 21)), "racy.jpg")
        evidence_ids.append(evidence["evidence_id"])
        link_evidence(evidence["evidence_id"], project["id"])
        backdate_evidence(evidence["evidence_id"], 400)
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 30, "archive_after_days": None,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": True})
        policy_ids.append(policy["id"])

        results = []

        def fire():
            try:
                response = client.post(
                    f"/api/v1/retention/delete/EVIDENCE/{evidence['evidence_id']}",
                    headers=headers)
                results.append((response.status_code, response.json().get("result")))
            except Exception as error:  # pragma: no cover - diagnostic only
                results.append(("EXC", str(error)[:150]))

        threads = [threading.Thread(target=fire) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(results) == 10
        assert all(code == 200 for code, _ in results)
        outcomes = sorted(result for _, result in results)
        assert outcomes.count("DELETED") == 1
        assert outcomes.count("ALREADY_DELETED") == 9
        evidence_ids.remove(evidence["evidence_id"])
    finally:
        cleanup([admin_id], project_ids, evidence_ids, policy_ids)


def test_authorization_scoping():
    owner_id, _ = make_admin("retention-owner")
    scoped_id, _ = make_admin("retention-scoped")
    # Strip the global grant: project-scoped administrator only.
    session = get_session()
    try:
        from backend.db.models import UserRoleAssignment

        session.query(UserRoleAssignment).filter(
            UserRoleAssignment.user_id == scoped_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project_a = make_project(owner_id, "retention A")
        project_b = make_project(owner_id, "retention B")
        project_ids.extend([project_a["id"], project_b["id"]])
        session = get_session()
        try:
            from backend.services import authorization as auth_service

            admin_id, headers = scoped_id, {"Authorization": f"Bearer dev-user-{scoped_id}"}
            evidence = upload(image_bytes((22, 23, 24)), "scoped.jpg")
            evidence_ids.append(evidence["evidence_id"])
            link_evidence(evidence["evidence_id"], project_a["id"])

            from backend.services import authorization as auth_service

            # The project-scoped principal is `scoped_id`, whose GLOBAL grant was
            # stripped above so it holds ADMINISTRATOR only within Project A. Using
            # `owner_id` here would be meaningless: `make_admin` gave it a GLOBAL
            # ADMINISTRATOR grant, and a GLOBAL assignment legitimately covers
            # every project, so a Project-B policy would be correctly allowed (201)
            # and the cross-project assertion could never hold.
            auth_service.assign_role(
                session, user_id=scoped_id, role_name="ADMINISTRATOR",
                scope_type="PROJECT", project_id=project_a["id"])
            session.commit()
        finally:
            session.close()
        scoped_headers = {"Authorization": f"Bearer dev-user-{scoped_id}"}

        policy = client.post("/api/v1/retention/policies", json={
            "name": "scoped-pol", "resource_type": "EVIDENCE", "scope_type": "PROJECT",
            "project_id": project_a["id"]}, headers=scoped_headers)
        assert policy.status_code == 201
        policy_ids.append(policy.json()["id"])
        foreign = client.post("/api/v1/retention/policies", json={
            "name": "foreign-pol", "resource_type": "EVIDENCE", "scope_type": "PROJECT",
            "project_id": project_b["id"]}, headers=scoped_headers)
        assert foreign.status_code in (403, 404)

        hold = client.post("/api/v1/retention/holds", json={
            "scope": "PROJECT", "project_id": project_a["id"], "reason": "audit"},
            headers=scoped_headers)
        assert hold.status_code == 201
        hold_ids = [hold.json()["id"]]
        foreign_hold = client.post("/api/v1/retention/holds", json={
            "scope": "PROJECT", "project_id": project_b["id"], "reason": "audit"},
            headers=scoped_headers)
        assert foreign_hold.status_code in (403, 404)
        assert client.post(f"/api/v1/retention/delete/EVIDENCE/{evidence['evidence_id']}",
                           headers=scoped_headers).status_code in (403, 404, 422)
    finally:
        session = get_session()
        try:
            session.query(RetentionHold).filter(
                RetentionHold.project_id.in_(project_ids)).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()
        cleanup([owner_id, scoped_id], project_ids, evidence_ids, policy_ids)


def test_fusion_history_preserved_and_audit_chain_intact():
    admin_id, headers = make_admin()
    project_ids, evidence_ids, policy_ids = [], [], []
    try:
        project = make_project(admin_id, "retention fusion")
        project_ids.append(project["id"])
        payload = image_bytes((25, 26, 27))
        keep = upload(payload, "keep.jpg")
        doomed = upload(payload, "doomed2.jpg")
        evidence_ids.extend([keep["evidence_id"], doomed["evidence_id"]])
        link_evidence(keep["evidence_id"], project["id"])
        link_evidence(doomed["evidence_id"], project["id"])
        backdate_evidence(doomed["evidence_id"], 400)
        policy, _ = make_policy(headers, scope="PROJECT", scope_id=project["id"], rules={
            "retention_days": 30, "archive_after_days": None,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": True})
        policy_ids.append(policy["id"])

        run = client.post(f"/api/v1/fusion/EVIDENCE/{keep['evidence_id']}", json={}).json()["run"]
        session = get_session()
        try:
            fusion_before = session.query(FusionRun).filter_by(id=run["id"]).count()
        finally:
            session.close()
        assert fusion_before == 1

        assert client.post(
            f"/api/v1/retention/delete/EVIDENCE/{doomed['evidence_id']}",
            headers=headers).json()["result"] == "DELETED"
        evidence_ids.remove(doomed["evidence_id"])

        session = get_session()
        try:
            assert session.query(FusionRun).filter_by(id=run["id"]).count() == 1
            verify = client.get("/api/v1/audit/verify", headers=headers).json()
            assert verify["valid"] is True
        finally:
            session.close()
    finally:
        session = get_session()
        try:
            from backend.db.models import (
                FusionSignal, IntegrityAssessment, ReviewPriority)
            # Only this test's fusion artifacts (tracked run ids would be
            # ideal; scope to runs targeting this test's evidences).
            doomed_runs = [row[0] for row in session.query(FusionRun.id).filter(
                FusionRun.target_id.in_(evidence_ids)).all()]
            for rid in doomed_runs:
                session.query(FusionSignal).filter(
                    FusionSignal.fusion_run_id == rid).delete(synchronize_session=False)
                session.query(IntegrityAssessment).filter(
                    IntegrityAssessment.fusion_run_id == rid).delete(
                    synchronize_session=False)
                session.query(ReviewPriority).filter(
                    ReviewPriority.fusion_run_id == rid).delete(synchronize_session=False)
                session.query(FusionRun).filter(FusionRun.id == rid).delete(
                    synchronize_session=False)
            session.commit()
        finally:
            session.close()
        cleanup([admin_id], project_ids, evidence_ids, policy_ids)
