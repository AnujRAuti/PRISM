"""Stage 02-2: ``/metrics`` is an authorized endpoint, not a public one.

The acceptance audit measured ~3 537 lines of Prometheus exposition returned
with no credential at all on the deployed VM, because ``prometheus_enabled``
defaults to True and the route had no dependency. Every test here pins
``auth_mode=enforcing``: under the development default an anonymous caller
bypasses authorization, so a test written in that mode would pass against the
hole it is supposed to close.

Non-vacuity: each refusal is paired with a call in the same test that *does*
receive the exposition, so a 401/403 can never be a missing route, a disabled
flag or an uninstalled client library.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import ApiClient, AUTH_ROLE_PERMISSIONS, User, UserRoleAssignment
from backend.db.session import get_session
from backend.services import authorization as auth_service


client = TestClient(app)

METRICS_PERMISSION = "metrics.read"


@pytest.fixture(autouse=True)
def enforcing():
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


@pytest.fixture(autouse=True)
def metrics_enabled():
    """The exposition must be reachable, so the only variable is the caller."""
    original = settings.prometheus_enabled
    settings.prometheus_enabled = True
    try:
        yield
    finally:
        settings.prometheus_enabled = original


def user_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def client_headers(client_id: str) -> dict:
    return {"Authorization": f"Bearer dev-client-{client_id}"}


def new_user(label: str) -> str:
    session = get_session()
    try:
        row = User(username=f"metrics-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@stage02.test")
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def new_api_client(label: str, scopes: list[str]) -> str:
    session = get_session()
    try:
        row = ApiClient(name=f"metrics-{label}-{uuid4().hex[:8]}", scopes=scopes,
                        status="ACTIVE")
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def grant(user_id: str, role: str) -> None:
    session = get_session()
    try:
        auth_service.assign_role(session, user_id=user_id, role_name=role,
                                 scope_type="GLOBAL")
        session.commit()
    finally:
        session.close()


def cleanup(user_ids: list[str], client_ids: list[str]) -> None:
    session = get_session()
    try:
        if user_ids:
            session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id.in_(user_ids)).delete(synchronize_session=False)
            session.query(User).filter(User.id.in_(user_ids)).delete(
                synchronize_session=False)
        if client_ids:
            session.query(ApiClient).filter(
                ApiClient.id.in_(client_ids)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_metrics_refuses_anonymous_callers_but_serves_an_authorized_scraper():
    """401 for the credential-less probe, 200 for a scoped API client."""
    scraper = new_api_client("scraper", [METRICS_PERMISSION])
    try:
        anonymous = client.get("/metrics")
        assert anonymous.status_code == 401, anonymous.text
        assert "# HELP" not in anonymous.text

        authorized = client.get("/metrics", headers=client_headers(scraper))
        assert authorized.status_code == 200, authorized.text
        assert authorized.text.startswith("# ")
        assert "text/plain" in authorized.headers["content-type"]
    finally:
        cleanup([], [scraper])


def test_a_credential_without_the_permission_is_still_refused():
    """Authentication alone is not authority: FIELD_OFFICER has no metrics.read."""
    officer = new_user("officer")
    scraper = new_api_client("scraper2", [METRICS_PERMISSION])
    try:
        grant(officer, "FIELD_OFFICER")
        denied = client.get("/metrics", headers=user_headers(officer))
        assert denied.status_code == 403, denied.text
        assert "# HELP" not in denied.text

        allowed = client.get("/metrics", headers=client_headers(scraper))
        assert allowed.status_code == 200, allowed.text
    finally:
        cleanup([officer], [scraper])


def test_liveness_and_readiness_probes_stay_anonymous():
    """The load balancer must not need a credential to ask whether we are up."""
    for path in ("/health", "/ready", "/healthz"):
        response = client.get(path)
        assert response.status_code in (200, 503), (path, response.status_code)
        assert response.status_code != 401, f"{path} became authenticated"


def test_metrics_permission_is_granted_to_no_baseline_role():
    """The permission exists to be scoped explicitly, never handed out broadly."""
    assert METRICS_PERMISSION in auth_service.PERMISSIONS
    offenders = {role: permissions for role, permissions in AUTH_ROLE_PERMISSIONS.items()
                 if METRICS_PERMISSION in permissions}
    assert offenders == {}
