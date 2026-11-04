"""PRISM-2 §5: a credential that is no longer live is refused at the HTTP layer.

The Stage 02 identity suite already proves the accept path and a spread of token
forgery refusals. Three state refusals were still only covered inside helper
functions, never through a route:

* a **DISABLED** account. ``test_stage02_reviewer_identity`` pins the sibling
  case (``SUSPENDED``) but the brief names disabled principals separately, and
  the two statuses reach the same check from different directions — a row can be
  disabled while its provider-side identity stays perfectly valid.
* an **API client** whose credential is still secret-correct while the client
  around it is not ACTIVE. Nothing tested ``resolve_principal``'s
  ``principal.status == "ACTIVE"`` gate for a real ``client_id:secret``, so a
  regression that trusted the hash alone would have been green.
* an **unreachable key set**. ``test_stage02_oidc_verification`` covers
  ``KEY_SET_UNAVAILABLE`` at the verifier, but the brief's "error responses do
  not leak internal details" is about the route: an outage must answer 401 the
  same way a bad token does, must not surface a 500, and must not leave a write
  behind.

Non-vacuity again runs through the row: the reviewer's case exists and is
genuinely decidable by the same principal while ACTIVE/DISABLED is toggled, and
the API-client test replays the *same* secret string either side of the status
change, so the only variable is the state under test.
"""

import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from backend.app.main import app
from backend.core.config import settings
from backend.db.models import (
    ApiClient,
    ApiCredential,
    Evidence,
    Project,
    ReviewCase,
    ReviewCaseEvent,
    User,
    UserRoleAssignment,
)
from backend.db.session import get_session
from backend.security import oidc
from backend.services import authorization as auth_service
from backend.services import integration as integration_service


client = TestClient(app)

ISSUER = "https://poa-state.supabase.co/auth/v1"
JWKS_URI = ISSUER + "/.well-known/jwks.json"
AUDIENCE = "authenticated"
PROVIDER = "supabase"
KID = "prism2-signing-key"

IDENTITY_SETTINGS = (
    "auth_mode", "auth_dev_tokens_enabled", "auth_oidc_enabled",
    "auth_oidc_issuer", "auth_oidc_jwks_uri", "auth_oidc_audience",
    "auth_oidc_identity_provider", "auth_oidc_algorithms",
    "auth_oidc_jwks_ttl_seconds",
)

DECISION_BODY = {"decision": "INCONCLUSIVE", "rationale": "provider outage check"}


@pytest.fixture(scope="module")
def signing_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = KID
    jwk["alg"] = "RS256"
    return private_key, jwk


@pytest.fixture(autouse=True)
def production_identity(signing_key, monkeypatch):
    """The deployed posture: enforcing, no development tokens, provider verified locally."""
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
    claims = {"sub": subject, "iss": ISSUER, "aud": AUDIENCE,
              "iat": now, "exp": now + 300}
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def new_user(label: str, *, external_subject: str | None = None,
             status: str = "ACTIVE") -> str:
    session = get_session()
    try:
        row = User(username=f"prism2-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@prism2.test",
                   external_subject=external_subject,
                   identity_provider=PROVIDER if external_subject else "local",
                   status=status)
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def set_user_status(user_id: str, status: str) -> None:
    session = get_session()
    try:
        row = session.query(User).filter(User.id == user_id).one()
        row.status = status
        session.commit()
    finally:
        session.close()


def set_client_status(client_id: str, status: str) -> None:
    session = get_session()
    try:
        row = session.query(ApiClient).filter(ApiClient.id == client_id).one()
        row.status = status
        session.commit()
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


def new_case(project_id: str) -> str:
    session = get_session()
    try:
        row = ReviewCase(project_id=project_id, origin="AUTHORIZED_USER",
                         status="INVESTIGATING")
        session.add(row)
        session.commit()
        return str(row.id)
    finally:
        session.close()


def decision_state(case_id: str):
    session = get_session()
    try:
        row = session.query(ReviewCase).filter(ReviewCase.id == case_id).one()
        events = session.query(ReviewCaseEvent).filter(
            ReviewCaseEvent.case_id == case_id).count()
        return row.status, row.decided_by, events
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


def cleanup(*, users=(), projects=(), cases=(), clients=(), evidence=()) -> None:
    session = get_session()
    try:
        if cases:
            session.query(ReviewCaseEvent).filter(
                ReviewCaseEvent.case_id.in_(cases)).delete(synchronize_session=False)
            session.query(ReviewCase).filter(
                ReviewCase.id.in_(cases)).delete(synchronize_session=False)
        if evidence:
            session.query(Evidence).filter(Evidence.id.in_(evidence)).delete(
                synchronize_session=False)
        if clients:
            session.query(ApiCredential).filter(
                ApiCredential.client_id.in_(clients)).delete(synchronize_session=False)
            session.query(ApiClient).filter(
                ApiClient.id.in_(clients)).delete(synchronize_session=False)
        if users:
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


def test_a_disabled_reviewers_token_is_refused_and_writes_nothing(
        production_identity):
    subject = f"prism2-disabled-{uuid4().hex[:12]}"
    owner = new_user("owner")
    reviewer = new_user("reviewer", external_subject=subject)
    project_id = new_project(owner)
    case_id = new_case(project_id)
    token = access_token(production_identity, subject)
    url = f"/api/v1/review-cases/{case_id}/decision"
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)

        # The very same token is accepted while the account is ACTIVE, so the
        # refusal below can only come from the status column.
        accepted = client.post(url, json=DECISION_BODY, headers=bearer(token))
        assert accepted.status_code == 200, accepted.text
        state = decision_state(case_id)
        assert state[0] == "DECISION_PENDING" and state[1] == reviewer, state

        # Put the case back, then disable the account.
        set_user_status(reviewer, "DISABLED")
        session = get_session()
        try:
            row = session.query(ReviewCase).filter(ReviewCase.id == case_id).one()
            row.status = "INVESTIGATING"
            row.decided_by = None
            for event in session.query(ReviewCaseEvent).filter(
                    ReviewCaseEvent.case_id == case_id).all():
                session.delete(event)
            session.commit()
        finally:
            session.close()
        before = decision_state(case_id)
        assert before[0] == "INVESTIGATING"

        refused = client.post(url, json=DECISION_BODY, headers=bearer(token))
        assert refused.status_code == 401, refused.text
        assert decision_state(case_id) == before, \
            "a refused decision must leave the case exactly as it was"
        assert client.get(f"/api/v1/review-cases/{case_id}",
                          headers=bearer(token)).status_code == 401
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])


def test_a_disabled_api_client_credential_is_refused(production_identity):
    """A correct secret on a client that is no longer ACTIVE must not authenticate."""
    owner = new_user("client-owner")
    project_id = new_project(owner)
    evidence_id = None
    client_id = None
    try:
        session = get_session()
        try:
            row = ApiClient(name=f"prism2-{uuid4().hex[:8]}", scopes=["evidence.read"],
                            project_id=None, status="ACTIVE")
            session.add(row)
            session.commit()
            client_id = str(row.id)
            credential, plaintext = integration_service.create_credential(
                session, client_id, actor_id=owner)
            session.commit()
            credential_id = str(credential.id)
        finally:
            session.close()

        evidence = Evidence(project_id=project_id, filename="state.jpg",
                            sha256=uuid4().hex,
                            storage_key=f"quarantine/{uuid4().hex}/original")
        session = get_session()
        try:
            session.add(evidence)
            session.commit()
            evidence_id = str(evidence.id)
        finally:
            session.close()

        credential_header = bearer(f"{client_id}:{plaintext}")
        url = f"/api/v1/evidence/{evidence_id}"
        assert client.get(url, headers=credential_header).status_code == 200

        set_client_status(client_id, "DISABLED")
        refused = client.get(url, headers=credential_header)
        assert refused.status_code == 401, refused.text
        assert refused.json()["detail"] == "Invalid credentials"

        # A revoked credential under an ACTIVE client is refused the same way.
        set_client_status(client_id, "ACTIVE")
        assert client.get(url, headers=credential_header).status_code == 200
        session = get_session()
        try:
            assert integration_service.revoke_credential(
                session, credential_id, actor_id=owner) is True
            session.commit()
        finally:
            session.close()
        assert client.get(url, headers=credential_header).status_code == 401
    finally:
        cleanup(users=[owner], projects=[project_id], clients=[client_id] if client_id else [],
                evidence=[evidence_id] if evidence_id else [])


def test_an_unreachable_key_set_answers_401_not_500_and_writes_nothing(
        production_identity, monkeypatch):
    """A provider outage must not become a stack trace, and must not accept the token."""
    subject = f"prism2-outage-{uuid4().hex[:12]}"
    owner = new_user("outage-owner")
    reviewer = new_user("outage-reviewer", external_subject=subject)
    project_id = new_project(owner)
    case_id = new_case(project_id)
    token = access_token(production_identity, subject)
    url = f"/api/v1/review-cases/{case_id}/decision"
    try:
        grant(reviewer, "SUPERVISOR", "PROJECT", project_id)
        assert client.post(url, json=DECISION_BODY, headers=bearer(token)).status_code == 200

        session = get_session()
        try:
            row = session.query(ReviewCase).filter(ReviewCase.id == case_id).one()
            row.status = "INVESTIGATING"
            row.decided_by = None
            for event in session.query(ReviewCaseEvent).filter(
                    ReviewCaseEvent.case_id == case_id).all():
                session.delete(event)
            session.commit()
        finally:
            session.close()
        before = decision_state(case_id)

        def refuse(uri: str) -> dict:
            raise httpx.ConnectError("identity provider is unreachable")

        monkeypatch.setattr(oidc, "_fetch_key_set", refuse)
        oidc.reset_key_cache()
        refused = client.post(url, json=DECISION_BODY, headers=bearer(token))
        assert refused.status_code == 401, refused.text
        assert refused.json()["detail"] == "Invalid credentials"
        assert "Traceback" not in refused.text
        assert decision_state(case_id) == before

        # A caller presenting no credential at all during the outage is refused
        # identically, so the outage leaks nothing about the provider's state.
        assert client.post(url, json=DECISION_BODY).status_code == 401
    finally:
        cleanup(users=[owner, reviewer], projects=[project_id], cases=[case_id])
