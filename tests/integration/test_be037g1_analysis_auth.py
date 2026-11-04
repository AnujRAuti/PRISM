"""BE-037 G1: the analysis job endpoints are authenticated and authorized.

Root cause measured in Phase B: BE-005 §36 explicitly deferred
authentication/RBAC for these two routes ("must not be implemented here") and
no later milestone rewired them, so ``POST /api/v1/analysis/jobs`` and
``GET /api/v1/analysis/jobs/{job_id}`` ran with no auth dependency at all.
Any caller could enqueue worker/ML jobs over any organization's evidence and
read another organization's analysis results.

Everything here runs under ``AUTH_MODE=enforcing``, the only mode where the
gap is observable: in development mode anonymous requests are documented to
bypass authorization (that behaviour is pinned by the last test so the
permissive default cannot silently change).

Guards under test, both existing permissions chosen by the project owner:
``intelligence.reprocess`` on the body's evidence for creation, and
``evidence.read`` on the job resolved through job -> evidence -> project.
"""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    AnalysisJob,
    AnalysisResult,
    ApiClient,
    Evidence,
    Organization,
    Project,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.services import authorization as auth_service
from backend.services.authorization import resolve_resource_scope

client = TestClient(app)

JOB_TYPE = "fingerprint"


@contextmanager
def enforcing():
    """Run with AUTH_MODE=enforcing so no anonymous bypass exists."""
    original = settings.auth_mode
    settings.auth_mode = "enforcing"
    try:
        yield
    finally:
        settings.auth_mode = original


@pytest.fixture(autouse=True)
def seed_catalogue():
    session = get_session()
    try:
        auth_service.ensure_default_catalogue(session)
    finally:
        session.close()


@pytest.fixture
def isolated_queue(monkeypatch):
    """Keep every enqueued job id off any shared queue.

    The endpoint enqueues by job id, so a name owned by this suite is the one
    cleared here; nothing in the analysis pipeline is disturbed.
    """
    from backend.services.analysis_queue import AnalysisQueue

    monkeypatch.setattr(settings, "analysis_queue_name", f"be037g1:{uuid4().hex}:jobs")
    queue = AnalysisQueue()
    yield queue.queue_name
    queue.client.delete(queue.queue_name, queue.processing_name)


@pytest.fixture
def world():
    return World()


class World:
    """Synthetic organizations/projects/evidence/principals, self-cleaning."""

    def __init__(self) -> None:
        self.org_ids: list[str] = []
        self.project_ids: list[str] = []
        self.evidence_ids: list[str] = []
        self.job_ids: list[str] = []
        self.user_ids: list[str] = []
        self.client_ids: list[str] = []

    def org(self, label: str) -> str:
        session = get_session()
        try:
            org = auth_service.create_organization(
                session, name=f"G1 {label}", code=f"g1-{label}-{uuid4().hex[:8]}")
            session.commit()
            session.refresh(org)
            self.org_ids.append(str(org.id))
            return str(org.id)
        finally:
            session.close()

    def project(self, org_id: str | None) -> str:
        session = get_session()
        try:
            owner = User(username=f"g1-owner-{uuid4().hex[:8]}",
                         email=f"{uuid4().hex[:8]}@example.com")
            session.add(owner)
            session.commit()
            session.refresh(owner)
            self.user_ids.append(str(owner.id))
            project = Project(name=f"G1 project {uuid4().hex[:6]}",
                              owner_id=str(owner.id),
                              organization_id=org_id)
            session.add(project)
            session.commit()
            session.refresh(project)
            self.project_ids.append(str(project.id))
            return str(project.id)
        finally:
            session.close()

    def evidence(self, project_id: str | None) -> str:
        session = get_session()
        try:
            row = Evidence(filename="g1.jpg",
                           content_type="image/jpeg",
                           storage_key=f"quarantine/{uuid4()}/original",
                           file_size=1,
                           status="uploaded_quarantine",
                           sha256=uuid4().hex + uuid4().hex,
                           project_id=project_id)
            session.add(row)
            session.commit()
            session.refresh(row)
            self.evidence_ids.append(str(row.id))
            return str(row.id)
        finally:
            session.close()

    def job(self, evidence_id: str) -> str:
        """Insert a job directly so read-path tests never depend on Redis."""
        session = get_session()
        try:
            row = AnalysisJob(evidence_id=evidence_id, status="queued",
                              attempt_count=0, job_type=JOB_TYPE)
            session.add(row)
            session.commit()
            session.refresh(row)
            self.job_ids.append(str(row.id))
            return str(row.id)
        finally:
            session.close()

    def user(self, label: str) -> str:
        session = get_session()
        try:
            row = User(username=f"g1-{label}-{uuid4().hex[:8]}",
                       email=f"{uuid4().hex[:8]}@example.com")
            session.add(row)
            session.commit()
            session.refresh(row)
            self.user_ids.append(str(row.id))
            return str(row.id)
        finally:
            session.close()

    def grant(self, user_id: str, role: str, scope: str, scope_id: str) -> None:
        session = get_session()
        try:
            kwargs: dict = {}
            if scope == "ORGANIZATION":
                kwargs["organization_id"] = scope_id
            elif scope == "PROJECT":
                kwargs["project_id"] = scope_id
            else:
                raise AssertionError(f"unsupported scope in test: {scope}")
            auth_service.assign_role(session, user_id=user_id, role_name=role,
                                     scope_type=scope, **kwargs)
            session.commit()
        finally:
            session.close()

    def api_client(self, name: str, scopes: list[str], project_id: str | None) -> str:
        session = get_session()
        try:
            row = ApiClient(name=f"g1-{name}-{uuid4().hex[:8]}", scopes=scopes,
                            project_id=project_id, status="ACTIVE")
            session.add(row)
            session.commit()
            session.refresh(row)
            self.client_ids.append(str(row.id))
            return str(row.id)
        finally:
            session.close()

    def job_count(self) -> int:
        session = get_session()
        try:
            return session.query(AnalysisJob).count()
        finally:
            session.close()

    def close(self) -> None:
        session = get_session()
        try:
            if self.job_ids:
                session.query(AnalysisResult).filter(
                    AnalysisResult.job_id.in_(self.job_ids)).delete(
                    synchronize_session=False)
                session.query(AnalysisJob).filter(
                    AnalysisJob.id.in_(self.job_ids)).delete(synchronize_session=False)
            if self.evidence_ids:
                session.query(Evidence).filter(
                    Evidence.id.in_(self.evidence_ids)).delete(synchronize_session=False)
            if self.user_ids:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.user_id.in_(self.user_ids)).delete(
                    synchronize_session=False)
            if self.project_ids:
                session.query(UserRoleAssignment).filter(
                    UserRoleAssignment.project_id.in_(self.project_ids)).delete(
                    synchronize_session=False)
                session.query(ApiClient).filter(
                    ApiClient.project_id.in_(self.project_ids)).delete(
                    synchronize_session=False)
                session.query(Project).filter(
                    Project.id.in_(self.project_ids)).delete(synchronize_session=False)
            if self.user_ids:
                session.query(User).filter(
                    User.id.in_(self.user_ids)).delete(synchronize_session=False)
            if self.client_ids:
                session.query(ApiClient).filter(
                    ApiClient.id.in_(self.client_ids)).delete(synchronize_session=False)
            if self.org_ids:
                session.query(Organization).filter(
                    Organization.id.in_(self.org_ids)).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()


def user_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def client_headers(client_id: str) -> dict:
    return {"Authorization": f"Bearer dev-client-{client_id}"}


def create_job(evidence_id: str, headers: dict | None = None, job_type: str = JOB_TYPE):
    body = {"evidence_id": evidence_id, "job_type": job_type}
    return client.post("/api/v1/analysis/jobs", json=body, headers=headers or {})


def read_job(job_id: str, headers: dict | None = None):
    return client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers or {})


# ---------------------------------------------------------------------------
# missing / invalid credentials
# ---------------------------------------------------------------------------

def test_anonymous_requests_are_rejected(world):
    with enforcing():
        evidence_id = world.evidence(world.project(None))
        job_id = world.job(evidence_id)
        assert create_job(evidence_id).status_code == 401
        assert read_job(job_id).status_code == 401


def test_invalid_credentials_are_rejected(world):
    with enforcing():
        evidence_id = world.evidence(world.project(None))
        job_id = world.job(evidence_id)
        bad = [
            {"Authorization": "Bearer garbage-token"},
            {"Authorization": f"Bearer dev-user-{uuid4().hex[:6]}"},
            {"Authorization": f"Bearer dev-client-{uuid4()}"},
            {"Authorization": f"Basic {uuid4().hex}"},
        ]
        for headers in bad:
            assert create_job(evidence_id, headers).status_code == 401, headers
            assert read_job(job_id, headers).status_code == 401, headers


def test_malformed_identifiers_rejected_before_any_lookup(world):
    with enforcing():
        project_id = world.project(None)
        user_id = world.user("officer")
        world.grant(user_id, "FIELD_OFFICER", "PROJECT", project_id)
        headers = user_headers(user_id)
        assert create_job("not-a-uuid", headers).status_code == 422
        assert read_job("not-a-uuid", headers).status_code == 422


# ---------------------------------------------------------------------------
# forbidden / authorized
# ---------------------------------------------------------------------------

def test_authenticated_user_without_permission_is_forbidden(world):
    with enforcing():
        evidence_id = world.evidence(world.project(None))
        job_id = world.job(evidence_id)
        user_id = world.user("no-role")
        headers = user_headers(user_id)
        assert create_job(evidence_id, headers).status_code == 403
        assert read_job(job_id, headers).status_code == 403


def test_authorized_officer_creates_job_for_own_evidence(world, isolated_queue):
    with enforcing():
        project_id = world.project(None)
        evidence_id = world.evidence(project_id)
        user_id = world.user("officer")
        world.grant(user_id, "FIELD_OFFICER", "PROJECT", project_id)

        response = create_job(evidence_id, user_headers(user_id))

        assert response.status_code == 202, response.text
        body = response.json()
        world.job_ids.append(body["job_id"])
        assert body["status"] == "queued"
        assert body["evidence_id"] == evidence_id


def test_organization_grant_reaches_org_evidence_and_jobs(world, isolated_queue):
    """Org-level authorization: one grant covers the org's projects."""
    with enforcing():
        org_id = world.org("a")
        project_id = world.project(org_id)
        evidence_id = world.evidence(project_id)
        user_id = world.user("org-officer")
        world.grant(user_id, "FIELD_OFFICER", "ORGANIZATION", org_id)
        headers = user_headers(user_id)

        created = create_job(evidence_id, headers)
        assert created.status_code == 202, created.text
        job_id = created.json()["job_id"]
        world.job_ids.append(job_id)

        assert read_job(job_id, headers).status_code == 200


def test_citizen_reads_job_but_cannot_enqueue(world):
    """Pins the owner's decision: creation needs intelligence.reprocess."""
    with enforcing():
        project_id = world.project(None)
        evidence_id = world.evidence(project_id)
        job_id = world.job(evidence_id)
        user_id = world.user("citizen")
        world.grant(user_id, "CITIZEN", "PROJECT", project_id)
        headers = user_headers(user_id)

        assert read_job(job_id, headers).status_code == 200
        assert create_job(evidence_id, headers).status_code == 403
        assert world.job_ids == [job_id]


# ---------------------------------------------------------------------------
# cross-organization access
# ---------------------------------------------------------------------------

def test_cross_organization_enqueue_is_hidden_and_has_no_side_effect(world):
    with enforcing():
        org_a = world.org("a")
        org_b = world.org("b")
        project_a = world.project(org_a)
        evidence_a = world.evidence(project_a)
        intruder = world.user("other-org-officer")
        world.grant(intruder, "FIELD_OFFICER", "ORGANIZATION", org_b)

        before = world.job_count()
        response = create_job(evidence_a, user_headers(intruder))

        assert response.status_code == 404
        # Denial happens before the insert: no worker work was queued.
        assert world.job_count() == before


def test_cross_organization_job_read_is_hidden(world):
    with enforcing():
        org_a = world.org("a")
        org_b = world.org("b")
        job_id = world.job(world.evidence(world.project(org_a)))
        intruder = world.user("other-org-officer")
        world.grant(intruder, "FIELD_OFFICER", "ORGANIZATION", org_b)

        response = read_job(job_id, user_headers(intruder))

        assert response.status_code == 404
        assert "result" not in response.json()


def test_unscoped_evidence_denies_scoped_caller(world):
    """Evidence with no project fails closed rather than leaking."""
    with enforcing():
        project_id = world.project(None)
        evidence_id = world.evidence(None)
        user_id = world.user("officer")
        world.grant(user_id, "FIELD_OFFICER", "PROJECT", project_id)

        assert create_job(evidence_id, user_headers(user_id)).status_code == 404


# ---------------------------------------------------------------------------
# service-to-service: explicit authorized mechanism
# ---------------------------------------------------------------------------

def test_project_bound_api_client_can_enqueue(world, isolated_queue):
    """A client carrying intelligence.reprocess is the authorized mechanism."""
    with enforcing():
        org_a = world.org("a")
        org_b = world.org("b")
        project_a = world.project(org_a)
        project_b = world.project(org_b)
        evidence_a = world.evidence(project_a)
        evidence_b = world.evidence(project_b)
        client_id = world.api_client(
            "analysis", ["intelligence.reprocess", "evidence.read"], project_a)
        headers = client_headers(client_id)

        created = create_job(evidence_a, headers)
        assert created.status_code == 202, created.text
        job_id = created.json()["job_id"]
        world.job_ids.append(job_id)
        assert read_job(job_id, headers).status_code == 200

        # Bound to project A: another project is invisible, not merely denied.
        assert create_job(evidence_b, headers).status_code == 404
        assert read_job(world.job(evidence_b), headers).status_code == 404


# ---------------------------------------------------------------------------
# scope resolution + the preserved development-mode contract
# ---------------------------------------------------------------------------

def test_analysis_job_resolves_through_its_evidence(world):
    organization_id = world.org("a")
    project_id = world.project(organization_id)
    evidence_id = world.evidence(project_id)
    job_id = world.job(evidence_id)

    session = get_session()
    try:
        resource = resolve_resource_scope(session, "analysis_job", job_id)
    finally:
        session.close()

    # The job has no scope columns, so it resolves through its evidence exactly
    # like reprocessing_request/publication do: the returned resource is the
    # evidence's, and the enforcement decision is made from its scope.
    assert resource.resource_type == "evidence"
    assert resource.resource_id == evidence_id
    assert resource.project_id == project_id
    assert resource.organization_id == organization_id


def test_development_mode_anonymous_behavior_unchanged(world, isolated_queue):
    """AUTH_MODE=development keeps the documented anonymous bypass."""
    project_id = world.project(None)
    evidence_id = world.evidence(project_id)

    assert settings.auth_mode == "development"
    created = create_job(evidence_id)
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]
    world.job_ids.append(job_id)
    assert read_job(job_id).status_code == 200


@pytest.fixture(autouse=True)
def cleanup_world(world):
    yield
    world.close()
