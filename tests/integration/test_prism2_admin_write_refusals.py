"""PRISM-2 §5: the permission layer is tested through HTTP, and the sensitive
evidence route enforces the sensitive permission.

Two measured gaps in the deployed posture.

First, four administrative write routes were only ever exercised by their
happy path or by their *scope* refusal, never by a caller who simply does not
hold the permission: ``POST /auth/clients`` (test_be025 issues it as a GLOBAL
administrator and then tests what the created client can do),
``POST /integrations/clients/{id}/credentials`` and
``POST /credentials/{id}/revoke`` (test_be019 proves the 404 for an
out-of-scope administrator, which is the scope layer, not the permission layer),
and ``POST /field/assignments`` (test_be026 proves scope and derivation). A
route whose 403 has never been observed is a route whose permission check might
not exist, and the brief requires API-level regression tests wherever coverage
was only indirect.

Second, ``evidence.read_sensitive`` is a real catalogue permission, seeded onto
REVIEWER and SUPERVISOR and mapped in ``ACTION_PERMISSIONS``, and before this
file no endpoint demanded it and no test asserted it. The route that actually
releases evidence bytes — ``GET /evidence/{id}/download``, which hands out a
presigned URL into the quarantine bucket — stood behind ``evidence.read`` alone,
so any project-scoped field officer could obtain the original file. A control
that nothing enforces is not a control.

Each refusal below is paired, in the same test, with the same caller or the same
row succeeding where it is authorized, and every "nothing was written" claim
compares an explicit row count taken before and after the refused calls. A 403
that still inserted the row would otherwise look like a refusal.

Third, a client-supplied person id must be a data reference and never an
authority grant. ``POST /projects/{id}/claims`` carries ``claimant_id``, and —
unlike the audit actor that stage 02-3 pins to the caller — naming another
person there is the product's own intake-on-behalf workflow. What is checked is
that being named confers no read access on that person and that an id naming
nobody is refused without storing a row.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    ApiClient,
    ApiCredential,
    Claim,
    Evidence,
    FieldAssignment,
    Project,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)


@pytest.fixture(autouse=True)
def enforcing():
    """Pin the deployed posture: the development default bypasses all of this."""
    original = settings.auth_mode
    settings.auth_mode = "enforcing"
    try:
        session = get_session()
        try:
            auth_service.ensure_default_catalogue(session)
        finally:
            session.close()
        yield
    finally:
        settings.auth_mode = original


def headers_for(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def new_user(label: str, **columns) -> str:
    session = get_session()
    try:
        row = User(username=f"prism2-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@prism2.test", **columns)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def new_project(owner_id: str) -> str:
    session = get_session()
    try:
        row = Project(name=f"prism2 {uuid4().hex[:6]}", owner_id=owner_id)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def new_evidence(project_id: str) -> str:
    """A metadata row only: a presigned URL is signed locally, no object needed."""
    session = get_session()
    try:
        row = Evidence(project_id=project_id, filename="original.jpg",
                       sha256=uuid4().hex,
                       storage_key=f"quarantine/{uuid4().hex}/original",
                       content_type="image/jpeg", file_size=1024)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def grant(user_id: str, role: str, scope_type: str,
          project_id: str | None = None) -> None:
    session = get_session()
    try:
        kwargs = {"project_id": project_id} if project_id else {}
        auth_service.assign_role(session, user_id=user_id, role_name=role,
                                 scope_type=scope_type, **kwargs)
        session.commit()
    finally:
        session.close()


def count(model, **filters) -> int:
    session = get_session()
    try:
        query = session.query(model)
        for column, value in filters.items():
            query = query.filter(getattr(model, column) == value)
        return query.count()
    finally:
        session.close()


def new_client_row(project_id: str | None, name: str) -> str:
    session = get_session()
    try:
        row = ApiClient(name=name, scopes=["evidence.read"],
                        project_id=project_id, status="ACTIVE")
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def new_credential_row(client_id: str) -> str:
    session = get_session()
    try:
        row = ApiCredential(client_id=client_id, credential_hash=f"sha256${uuid4().hex}")
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def cleanup(*, users=(), projects=(), evidence=(), clients=()) -> None:
    session = get_session()
    try:
        if evidence:
            session.query(Evidence).filter(Evidence.id.in_(evidence)).delete(
                synchronize_session=False)
        if clients:
            session.query(ApiCredential).filter(
                ApiCredential.client_id.in_(clients)).delete(synchronize_session=False)
            session.query(ApiClient).filter(ApiClient.id.in_(clients)).delete(
                synchronize_session=False)
        if users:
            session.query(FieldAssignment).filter(
                FieldAssignment.user_id.in_(users)).delete(synchronize_session=False)
            session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id.in_(users)).delete(synchronize_session=False)
        if projects:
            session.query(Project).filter(Project.id.in_(projects)).delete(
                synchronize_session=False)
        if users:
            session.query(User).filter(User.id.in_(users)).delete(
                synchronize_session=False)
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# the sensitive evidence route
# ---------------------------------------------------------------------------

def test_evidence_bytes_require_the_sensitive_permission():
    """evidence.read opens the metadata; only evidence.read_sensitive opens the file."""
    owner = new_user("owner")
    project_id = new_project(owner)
    evidence_id = new_evidence(project_id)
    officer = new_user("officer")
    reviewer = new_user("reviewer")
    url = f"/api/v1/evidence/{evidence_id}/download"
    try:
        grant(officer, "FIELD_OFFICER", "PROJECT", project_id)
        grant(reviewer, "REVIEWER", "PROJECT", project_id)

        # Both callers are authenticated, in scope, and hold evidence.read, so
        # the difference in the two verdicts below can only be the extra grant.
        assert count(Evidence, id=evidence_id) == 1
        assert client.get(f"/api/v1/evidence/{evidence_id}",
                          headers=headers_for(officer)).status_code == 200
        refused = client.get(url, headers=headers_for(officer))
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"] == "Forbidden"

        allowed = client.get(url, headers=headers_for(reviewer))
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["download_url"].startswith("http")

        # No credential at all is still a 401, not the new 403.
        assert client.get(url).status_code == 401
    finally:
        cleanup(users=[owner, officer, reviewer], projects=[project_id],
                evidence=[evidence_id])


def test_a_sensitive_reader_outside_the_project_still_cannot_reach_the_bytes():
    """The second guard is scoped like the first: the extra grant must cover the row."""
    owner = new_user("owner")
    mine, theirs = new_project(owner), new_project(owner)
    their_evidence = new_evidence(theirs)
    officer = new_user("scoped-officer")
    try:
        grant(officer, "FIELD_OFFICER", "PROJECT", mine)
        assert count(Evidence, id=their_evidence) == 1
        # 404, indistinguishable from absent: scope, not the permission check.
        assert client.get(f"/api/v1/evidence/{their_evidence}/download",
                          headers=headers_for(officer)).status_code == 404
    finally:
        cleanup(users=[owner, officer], projects=[mine, theirs],
                evidence=[their_evidence])


# ---------------------------------------------------------------------------
# administrative writes a caller has no permission for
# ---------------------------------------------------------------------------

def test_registering_an_api_client_is_denied_without_global_user_manage():
    owner = new_user("client-owner")
    project_id = new_project(owner)
    name = f"prism2-forged-{uuid4().hex[:8]}"
    body = {"name": name, "scopes": ["evidence.read"]}
    no_permission = new_user("reviewer-no-manage")
    wrong_shape = new_user("project-admin")
    global_admin = new_user("global-admin")
    registered = []
    try:
        grant(no_permission, "REVIEWER", "GLOBAL")
        # ADMINISTRATOR holds user.manage; granted at PROJECT scope it is the
        # same permission in the same role, so only the GLOBAL requirement can
        # be what refuses this call.
        grant(wrong_shape, "ADMINISTRATOR", "PROJECT", project_id)
        grant(global_admin, "ADMINISTRATOR", "GLOBAL")
        assert count(ApiClient, name=name) == 0

        for user_id in (no_permission, wrong_shape):
            refused = client.post("/api/v1/auth/clients", json=body,
                                  headers=headers_for(user_id))
            assert refused.status_code == 403, (user_id, refused.text)

        assert client.post("/api/v1/auth/clients", json=body).status_code == 401
        assert count(ApiClient, name=name) == 0, "a refusal must not have registered a client"

        # Positive control on the same payload: the GLOBAL grant is the only
        # thing the project administrator above lacked.
        created = client.post("/api/v1/auth/clients", json=body,
                              headers=headers_for(global_admin))
        assert created.status_code == 201, created.text
        registered.append(created.json()["id"])
    finally:
        cleanup(users=[owner, no_permission, wrong_shape, global_admin],
                projects=[project_id], clients=registered)


def test_issuing_and_revoking_credentials_are_denied_without_the_permission():
    owner = new_user("cred-owner")
    project_id = new_project(owner)
    client_name = f"prism2-cred-{uuid4().hex[:8]}"
    client_id = new_client_row(project_id, client_name)
    credential_id = new_credential_row(client_id)
    officer = new_user("officer-no-credential-manage")
    admin = new_user("cred-admin")
    try:
        grant(officer, "FIELD_OFFICER", "PROJECT", project_id)
        grant(admin, "ADMINISTRATOR", "PROJECT", project_id)
        assert count(ApiCredential, id=credential_id) == 1

        issued = client.post(f"/api/v1/integrations/clients/{client_id}/credentials",
                             headers=headers_for(officer))
        assert issued.status_code == 403, issued.text
        # The refused call must not have minted a secret.
        assert count(ApiCredential, client_id=client_id) == 1

        revoked = client.post(f"/api/v1/integrations/credentials/{credential_id}/revoke",
                              headers=headers_for(officer))
        assert revoked.status_code == 403, revoked.text
        session = get_session()
        try:
            row = session.query(ApiCredential).filter(
                ApiCredential.id == credential_id).one()
            assert row.revoked_at is None, "a refusal must not have revoked the credential"
        finally:
            session.close()

        assert client.post(
            f"/api/v1/integrations/clients/{client_id}/credentials").status_code == 401
        assert client.post(
            f"/api/v1/integrations/credentials/{credential_id}/revoke").status_code == 401

        # Positive control: the same two routes accept a holder of the permission.
        fresh = client.post(f"/api/v1/integrations/clients/{client_id}/credentials",
                            headers=headers_for(admin))
        assert fresh.status_code == 201, fresh.text
        new_credential = fresh.json()["credential_id"]
        assert client.post(f"/api/v1/integrations/credentials/{new_credential}/revoke",
                           headers=headers_for(admin)).status_code == 200
    finally:
        cleanup(users=[owner, officer, admin], projects=[project_id], clients=[client_id])


def test_naming_a_claimant_grants_that_person_nothing():
    """A body-supplied person id is a data reference, never an authority grant.

    ``POST /projects/{id}/claims`` accepts ``claimant_id``, and intake on behalf
    of someone else is the product's own workflow — so unlike the audit actor,
    the claimant legitimately names another person. What must not happen is that
    naming them makes them a reader of the project, and what must also not
    happen is a made-up id being stored as though it were a person.
    """
    owner = new_user("claim-owner")
    project_id = new_project(owner)
    officer = new_user("claim-officer")
    named = new_user("named-claimant")
    claim_ids = []
    try:
        grant(officer, "FIELD_OFFICER", "PROJECT", project_id)
        created = client.post(f"/api/v1/projects/{project_id}/claims",
                              json={"title": "Road washed out", "description": "d",
                                    "claimant_id": named},
                              headers=headers_for(officer))
        assert created.status_code == 201, created.text
        claim_id = created.json()["id"]
        claim_ids.append(claim_id)

        # The row really names the person, so the refusals below are not
        # explained by an empty field.
        session = get_session()
        try:
            row = session.query(Claim).filter(Claim.id == claim_id).one()
            assert str(row.claimant_id) == named
        finally:
            session.close()

        # Being the claimant opens nothing: no claim.read, so no item and no
        # collection, while the officer who filed it reads both.
        assert client.get(f"/api/v1/projects/{project_id}/claims/{claim_id}",
                          headers=headers_for(named)).status_code == 403
        assert client.get(f"/api/v1/projects/{project_id}/claims",
                          headers=headers_for(named)).status_code == 403
        assert client.get(f"/api/v1/projects/{project_id}/claims/{claim_id}",
                          headers=headers_for(officer)).status_code == 200

        # An id that names nobody is refused and stores no claim.
        ghost = str(uuid4())
        before = count(Claim, project_id=project_id)
        refused = client.post(f"/api/v1/projects/{project_id}/claims",
                              json={"title": "Ghost", "description": "d",
                                    "claimant_id": ghost},
                              headers=headers_for(officer))
        assert refused.status_code == 404, refused.text
        assert count(Claim, project_id=project_id) == before
    finally:
        session = get_session()
        try:
            if claim_ids:
                session.query(Claim).filter(Claim.id.in_(claim_ids)).delete(
                    synchronize_session=False)
            session.commit()
        finally:
            session.close()
        cleanup(users=[owner, officer, named], projects=[project_id])


def test_creating_a_field_assignment_is_denied_without_field_assignment_manage():
    owner = new_user("assign-owner")
    officer = new_user("assign-target")
    project_id = new_project(owner)
    citizen = new_user("citizen-no-manage")
    admin = new_user("assign-admin")
    body = {"user_id": officer, "project_id": project_id}
    try:
        grant(citizen, "CITIZEN", "GLOBAL")
        grant(admin, "ADMINISTRATOR", "GLOBAL")
        assert count(FieldAssignment, user_id=officer) == 0

        refused = client.post("/api/v1/field/assignments", json=body,
                              headers=headers_for(citizen))
        assert refused.status_code == 403, refused.text
        assert client.post("/api/v1/field/assignments", json=body).status_code == 401
        assert count(FieldAssignment, user_id=officer) == 0, \
            "a refusal must not have created field work"

        created = client.post("/api/v1/field/assignments", json=body,
                              headers=headers_for(admin))
        assert created.status_code == 201, created.text
    finally:
        cleanup(users=[owner, officer, citizen, admin], projects=[project_id])
