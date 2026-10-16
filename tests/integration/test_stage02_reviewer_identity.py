"""Stage 02-2: a reviewer signs in as themselves, and that is the identity used.

Audit register rows 1.2/1.3 measured the opposite: the only credential an
``enforcing`` deployment accepted was an API-client ``client_id:secret``, which a
browser may never hold, so there was no way for a human reviewer to act on the
API at all. These tests run the deployed posture end to end — ``auth_mode=
enforcing``, ``auth_dev_tokens_enabled=false``, the identity provider enabled —
and drive real routes with an access token signed by a key set the tests serve
locally, so nothing here reaches the network.

Two halves, both required. The identity half: a mapped reviewer completes a
workflow action and the row records *their* id, while an unlinked subject, an
expired token, a suspended account, a development token and no token at all are
each refused before any handler runs. The authority half: a verified identity is
not a permission — the same signed-in reviewer is denied an action their role
lacks and denied another project's case, each paired with the same caller
succeeding where they are granted, so a refusal can only come from the grant.

Non-vacuity follows the same rule as the rest of stage 02: every refusal below
is checked against rows and grants that genuinely exist, and every "nothing was
written" claim compares real row counts.
"""

import json
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    Project,
    ReviewCase,
    ReviewCaseEvent,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.security import oidc
from backend.services import authorization as auth_service


client = TestClient(app)

ISSUER = "https://poa-reviewer.supabase.co/auth/v1"
JWKS_URI = ISSUER + "/.well-known/jwks.json"
AUDIENCE = "authenticated"
PROVIDER = "supabase"
KID = "stage02-signing-key"

#: The five settings a deployed backend would read from ``.env``.
IDENTITY_SETTINGS = (
    "auth_mode", "auth_dev_tokens_enabled", "auth_oidc_enabled",
    "auth_oidc_issuer", "auth_oidc_jwks_uri", "auth_oidc_audience",
    "auth_oidc_identity_provider", "auth_oidc_algorithms",
    "auth_oidc_jwks_ttl_seconds",
)


@pytest.fixture(scope="module")
def signing_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = KID
    jwk["alg"] = "RS256"
    return private_key, jwk


@pytest.fixture(autouse=True)
def production_identity(signing_key, monkeypatch):
    """Enforcing, no development tokens, identity provider live on a local key set."""
    private_key, jwk = signing_key
    before = {name: getattr(settings, name) for name in IDENTITY_SETTINGS}
    settings.auth_mode = "enforcing"
    settings.auth_dev_tokens_enabled = False
    settings.auth_oidc_enabled = True
    settings.auth_oidc_issuer = ISSUER
    settings.auth_oidc_jwks_uri = JWKS_URI
    settings.auth_oidc_audience = AUDIENCE
    settings.auth_oidc_identity_provider = PROVIDER
    settings.auth_oidc_algorithms = "RS256"
    settings.auth_oidc_jwks_ttl_seconds = 300
    monkeypatch.setattr(oidc, "_fetch_key_set", lambda uri: {"keys": [jwk]})
    oidc.reset_key_cache()
    session = get_session()
    try:
        auth_service.ensure_default_catalogue(session)
    finally:
        session.close()
    try:
        yield private_key
    finally:
        for name, value in before.items():
            setattr(settings, name, value)
        oidc.reset_key_cache()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def access_token(private_key, subject: str, **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": subject, "iss": ISSUER, "aud": AUDIENCE,
        "iat": now, "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256",
                      headers={"kid": KID})


def new_reviewer(auth_subject: str | None, *, label: str = "reviewer",
                 status: str = "ACTIVE", provider: str = PROVIDER) -> str:
    """A PoA account, the way an administrator provisions one: linked first."""
    session = get_session()
    try:
        row = User(username=f"ident-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@stage02.test",
                   external_subject=auth_subject, identity_provider=provider,
                   status=status)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def new_owner() -> str:
    """An unlinked local account, only needed to satisfy projects.owner_id."""
    return new_reviewer(None, label="owner", provider="local")


def new_project(owner_id: str) -> str:
    session = get_session()
    try:
        row = Project(name=f"ident {uuid4().hex[:6]}", owner_id=owner_id)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def grant(user_id: str, role: str, scope_type: str = "GLOBAL",
          project_id: str | None = None) -> None:
    session = get_session()
    try:
        kwargs = {"project_id": project_id} if project_id else {}
        auth_service.assign_role(session, user_id=user_id, role_name=role,
                                 scope_type=scope_type, **kwargs)
        session.commit()
    finally:
        session.close()


def seed_case(project_id: str, status: str) -> str:
    session = get_session()
    try:
        row = ReviewCase(project_id=project_id, origin="AUTHORIZED_USER",
                         status=status)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def case_row(case_id: str):
    session = get_session()
    try:
        row = session.query(ReviewCase).filter(ReviewCase.id == case_id).one()
        return row.status, row.decided_by
    finally:
        session.close()


def case_actors(case_id: str, event_type: str) -> list[str | None]:
    session = get_session()
    try:
        rows = session.query(ReviewCaseEvent).filter(
            ReviewCaseEvent.case_id == case_id,
            ReviewCaseEvent.event_type == event_type).all()
        return [row.actor_id for row in rows]
    finally:
        session.close()


def cleanup(*, users=(), projects=(), cases=()) -> None:
    """FK-safe order: events, then cases, then grants/projects, then users."""
    session = get_session()
    try:
        if cases:
            session.query(ReviewCaseEvent).filter(
                ReviewCaseEvent.case_id.in_(cases)).delete(
                    synchronize_session=False)
            session.query(ReviewCase).filter(
                ReviewCase.id.in_(cases)).delete(synchronize_session=False)
        if users:
            session.query(UserRoleAssignment).filter(
                UserRoleAssignment.user_id.in_(users)).delete(
                    synchronize_session=False)
        if projects:
            session.query(Project).filter(
                Project.id.in_(projects)).delete(synchronize_session=False)
        if users:
            session.query(User).filter(User.id.in_(users)).delete(
                synchronize_session=False)
        session.commit()
    finally:
        session.close()


DECISION_BODY = {"decision": "INCONCLUSIVE", "rationale": "needs a field visit"}


def decision_url(case_id: str) -> str:
    return f"/api/v1/review-cases/{case_id}/decision"


def read_url(case_id: str) -> str:
    return f"/api/v1/review-cases/{case_id}"


# ---------------------------------------------------------------------------
# the identity half: a reviewer's own token is enough, and is the recorded actor
# ---------------------------------------------------------------------------


def test_a_signed_in_reviewer_is_attributed_to_themselves(production_identity):
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        # Non-vacuity: the case is decidable and the caller is granted, so the
        # 200 below can only come from the identity path working.
        assert case_row(case_id) == ("INVESTIGATING", None)

        response = client.post(decision_url(case_id), json=DECISION_BODY,
                               headers=bearer(access_token(private_key, subject)))
        assert response.status_code == 200, response.text
        assert case_row(case_id) == ("DECISION_PENDING", reviewer)
        assert case_actors(case_id, "DECISION_RECORDED") == [reviewer]
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


def test_the_verified_identity_beats_a_forged_actor_field(production_identity):
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    colleague = new_reviewer(str(uuid4()), label="colleague")
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        headers = bearer(access_token(private_key, subject))

        forged = client.post(decision_url(case_id),
                             json={**DECISION_BODY, "decided_by": colleague},
                             headers=headers)
        assert forged.status_code == 403, forged.text
        assert "decided_by" in forged.json()["detail"]
        assert case_row(case_id) == ("INVESTIGATING", None)
        assert case_actors(case_id, "DECISION_RECORDED") == []

        allowed = client.post(decision_url(case_id), json=DECISION_BODY,
                              headers=headers)
        assert allowed.status_code == 200, allowed.text
        assert case_row(case_id) == ("DECISION_PENDING", reviewer)
    finally:
        cleanup(users=[owner, reviewer, colleague], projects=[project_id],
                cases=[case_id])


def test_no_credential_at_all_is_still_refused(production_identity):
    owner = new_owner()
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        assert case_row(case_id)[0] == "INVESTIGATING"
        assert client.get(read_url(case_id)).status_code == 401
        assert client.post(decision_url(case_id), json=DECISION_BODY).status_code == 401
    finally:
        cleanup(users=[owner], projects=[project_id], cases=[case_id])


def test_development_tokens_stay_refused_while_the_provider_is_enabled(
        production_identity):
    """The identity path must not quietly reopen the development door."""
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        dev = bearer(f"dev-user-{reviewer}")
        assert client.get(read_url(case_id), headers=dev).status_code == 401
        assert client.post(decision_url(case_id), json=DECISION_BODY,
                           headers=dev).status_code == 401
        # The very same account is accepted when it presents its own token.
        assert client.get(read_url(case_id), headers=bearer(
            access_token(private_key, subject))).status_code == 200
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


# ---------------------------------------------------------------------------
# the identity half, refusals: each is the layer that stops it, not the row
# ---------------------------------------------------------------------------


def test_a_valid_token_with_no_linked_account_is_refused_without_writing(
        production_identity):
    private_key = production_identity
    owner = new_owner()
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        response = client.post(decision_url(case_id), json=DECISION_BODY,
                               headers=bearer(access_token(private_key, str(uuid4()))))
        assert response.status_code == 401, response.text
        assert "No account is linked" in response.json()["detail"]
        assert case_row(case_id) == ("INVESTIGATING", None)
        assert case_actors(case_id, "DECISION_RECORDED") == []
    finally:
        cleanup(users=[owner], projects=[project_id], cases=[case_id])


def test_an_expired_token_for_a_mapped_reviewer_is_refused(production_identity):
    """The account exists and is granted; only the token has run out."""
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    now = int(time.time())
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        assert client.get(read_url(case_id), headers=bearer(
            access_token(private_key, subject))).status_code == 200

        expired = client.get(read_url(case_id), headers=bearer(access_token(
            private_key, subject, iat=now - 7200, exp=now - 3600)))
        assert expired.status_code == 401, expired.text
        assert "No account is linked" not in expired.json()["detail"]
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


def test_a_suspended_reviewers_token_is_refused(production_identity):
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject, status="SUSPENDED")
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        response = client.post(decision_url(case_id), json=DECISION_BODY,
                               headers=bearer(access_token(private_key, subject)))
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Invalid credentials"
        assert case_row(case_id) == ("INVESTIGATING", None)
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


def test_a_token_signed_for_another_audience_is_refused(production_identity):
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        response = client.get(read_url(case_id), headers=bearer(access_token(
            private_key, subject, aud="service-role")))
        assert response.status_code == 401, response.text
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


def test_a_refresh_token_is_not_accepted_as_a_signed_in_session(
        production_identity):
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        response = client.get(read_url(case_id), headers=bearer(access_token(
            private_key, subject, use="refresh")))
        assert response.status_code == 401, response.text
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


def test_a_link_is_per_provider_so_the_same_subject_cannot_cross_over(
        production_identity):
    """users(external_subject) is only unique together with its provider."""
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject, label="supabase-side")
    other = new_reviewer(subject, label="other-side", provider="another-provider")
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        # Granted as `reviewer`, so this resolves to reviewer's id, never other's.
        response = client.post(decision_url(case_id), json=DECISION_BODY,
                               headers=bearer(access_token(private_key, subject)))
        assert response.status_code == 200, response.text
        assert case_row(case_id) == ("DECISION_PENDING", reviewer)
        assert case_row(case_id)[1] != other
    finally:
        cleanup(users=[owner, reviewer, other], projects=[project_id],
                cases=[case_id])


# ---------------------------------------------------------------------------
# the authority half: a verified identity is not a permission
# ---------------------------------------------------------------------------


def test_a_signed_in_reviewer_still_lacks_ungranted_actions(production_identity):
    """REVIEWER may read and investigate a case, never decide it."""
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    project_id = new_project(owner)
    case_id = seed_case(project_id, "INVESTIGATING")
    try:
        grant(reviewer, "REVIEWER", "PROJECT", project_id)
        headers = bearer(access_token(private_key, subject))
        assert client.get(read_url(case_id), headers=headers).status_code == 200
        denied = client.post(decision_url(case_id), json=DECISION_BODY, headers=headers)
        assert denied.status_code == 403, denied.text
        assert case_row(case_id) == ("INVESTIGATING", None)
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


def test_a_signed_in_reviewer_cannot_reach_a_foreign_project(production_identity):
    private_key = production_identity
    owner = new_owner()
    subject = str(uuid4())
    reviewer = new_reviewer(subject)
    mine, theirs = new_project(owner), new_project(owner)
    their_case = seed_case(theirs, "INVESTIGATING")
    my_case = seed_case(mine, "INVESTIGATING")
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", mine)
        headers = bearer(access_token(private_key, subject))
        assert client.get(read_url(their_case), headers=headers).status_code in (403, 404)
        # Same caller, same route, only the project differs.
        assert client.get(read_url(my_case), headers=headers).status_code == 200
    finally:
        cleanup(users=[owner, reviewer], projects=[mine, theirs],
                cases=[their_case, my_case])
