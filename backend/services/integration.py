"""BE-019 integration service: credential lifecycle, idempotency, external system management."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import ApiClient, ApiCredential, ExternalSystem, IdempotencyKey
from backend.repositories import integration as integration_repo
from backend.schemas.integration import IdempotencyResult
from backend.services import audit_ledger as audit_service


logger = logging.getLogger(__name__)

# Number of bytes for generated secrets (produces 64-char hex string)
SECRET_BYTES = 32

# Idempotency key TTL
IDEMPOTENCY_TTL_HOURS = 24

# Max consecutive failures before auto-disabling a webhook subscription
MAX_CONSECUTIVE_FAILURES = 10


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Credential Hashing (SHA-256; bcrypt not available as dependency)
# ---------------------------------------------------------------------------


def hash_secret(secret: str) -> str:
    """Return a SHA-256 hex digest of the secret. Never store the original."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_secret(secret: str, stored_hash: str) -> bool:
    """Constant-time comparison of secret against stored hash."""
    expected = hash_secret(secret)
    return hmac.compare_digest(expected, stored_hash)


def generate_secret() -> str:
    """Generate a cryptographically secure random secret (64 hex chars)."""
    return secrets.token_hex(SECRET_BYTES)


# ---------------------------------------------------------------------------
# External System Management
# ---------------------------------------------------------------------------


def create_external_system(
    db: Session,
    name: str,
    code: str,
    system_type: str,
    actor_id: str | None = None,
    organization_id: str | None = None,
    description: str | None = None,
    metadata: dict | None = None,
) -> ExternalSystem:
    system = integration_repo.insert_external_system(
        db,
        name=name,
        code=code,
        system_type=system_type,
        organization_id=organization_id,
        description=description,
        metadata_=metadata or {},
    )
    audit_service.append_event(
        db,
        event_type="EXTERNAL_SYSTEM_CREATED",
        action="create",
        resource_type="external_system",
        resource_id=str(system.id),
        actor_id=actor_id,
        project_id=None,
        payload={"name": name, "code": code, "system_type": system_type},
        source="integration_service",
    )
    return system


# ---------------------------------------------------------------------------
# API Client Management
# ---------------------------------------------------------------------------


def create_api_client(
    db: Session,
    name: str,
    actor_id: str | None = None,
    project_id: str | None = None,
    scopes: list[str] | None = None,
) -> tuple[ApiClient, str]:
    """Create an API client and its first credential. Returns (client, plaintext_secret)."""
    client = integration_repo.insert_api_client(
        db,
        name=name,
        scopes=scopes or [],
        project_id=project_id,
        status="ACTIVE",
    )
    plaintext, cred = _issue_credential(db, str(client.id))
    audit_service.append_event(
        db,
        event_type="API_CLIENT_CREATED",
        action="create",
        resource_type="api_client",
        resource_id=str(client.id),
        actor_id=actor_id,
        project_id=project_id,
        payload={"name": name, "scopes": scopes or []},
        source="integration_service",
    )
    return client, plaintext


def _issue_credential(
    db: Session,
    client_id: str,
    expires_at: datetime | None = None,
) -> tuple[str, ApiCredential]:
    """Generate and store a hashed credential. Returns (plaintext_secret, credential_row)."""
    plaintext = generate_secret()
    cred = integration_repo.insert_credential(
        db,
        client_id=client_id,
        credential_hash=hash_secret(plaintext),
        expires_at=expires_at,
    )
    return plaintext, cred


# ---------------------------------------------------------------------------
# Credential Lifecycle
# ---------------------------------------------------------------------------


def create_credential(
    db: Session,
    client_id: str,
    actor_id: str | None = None,
    expires_in_days: int | None = None,
) -> tuple[ApiCredential, str]:
    """Issue a new credential for the given client. Returns (credential, plaintext_secret)."""
    expires_at = utc_now() + timedelta(days=expires_in_days) if expires_in_days else None
    plaintext, cred = _issue_credential(db, client_id, expires_at=expires_at)
    audit_service.append_event(
        db,
        event_type="API_CREDENTIAL_CREATED",
        action="create",
        resource_type="api_credential",
        resource_id=str(cred.id),
        actor_id=actor_id,
        project_id=None,
        payload={"client_id": client_id},
        source="integration_service",
    )
    return cred, plaintext


def revoke_credential(
    db: Session,
    credential_id: str,
    actor_id: str | None = None,
) -> bool:
    """Revoke a credential immediately. Returns True if revoked, False if already revoked."""
    cred = integration_repo.revoke_credential(db, credential_id)
    if cred is None:
        return False
    audit_service.append_event(
        db,
        event_type="API_CREDENTIAL_REVOKED",
        action="revoke",
        resource_type="api_credential",
        resource_id=credential_id,
        actor_id=actor_id,
        project_id=None,
        payload={"client_id": str(cred.client_id)},
        source="integration_service",
    )
    return True


def rotate_credential(
    db: Session,
    client_id: str,
    revoke_old_after_seconds: int = 0,
    actor_id: str | None = None,
) -> tuple[ApiCredential, str]:
    """Create a new credential. If revoke_old_after_seconds==0, immediately revoke all old ones."""
    new_cred, plaintext = create_credential(db, client_id, actor_id=actor_id)
    if revoke_old_after_seconds == 0:
        # Immediately revoke all other active credentials
        old_creds = integration_repo.list_active_credentials(db, client_id)
        for cred in old_creds:
            if str(cred.id) != str(new_cred.id):
                integration_repo.revoke_credential(db, str(cred.id))
    return new_cred, plaintext


def authenticate_api_client(
    db: Session,
    client_id: str,
    secret: str,
) -> ApiClient | None:
    """Validate client + secret against stored credential hashes.

    Returns the ApiClient if authentication succeeds, None otherwise.
    Credentials are verified constant-time; timing attacks are mitigated.
    """
    client = integration_repo.get_api_client(db, client_id)
    if client is None or client.status != "ACTIVE":
        return None
    active_creds = integration_repo.list_active_credentials(db, client_id)
    for cred in active_creds:
        if verify_secret(secret, cred.credential_hash):
            integration_repo.touch_credential_used(db, str(cred.id))
            return client
    return None


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def compute_request_hash(body: bytes | str | dict) -> str:
    """Hash a request body for idempotency conflict detection."""
    if isinstance(body, dict):
        import json
        raw = json.dumps(body, sort_keys=True, ensure_ascii=True)
    elif isinstance(body, bytes):
        raw = body.decode("utf-8", errors="replace")
    else:
        raw = str(body)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_idempotency(
    db: Session,
    client_id: str,
    key: str,
    request_hash: str,
) -> IdempotencyResult:
    """Check whether a request is new, a valid replay, or a conflicting replay.

    - NEW: key not seen before
    - REPLAY: same key, same body hash — return stored result
    - CONFLICT: same key, different body hash — 409 should be raised by caller
    """
    existing = integration_repo.get_idempotency_key(db, client_id, key)
    if existing is None:
        return IdempotencyResult(outcome="NEW")
    if existing.request_hash == request_hash:
        return IdempotencyResult(outcome="REPLAY", result_payload=existing.result_payload)
    return IdempotencyResult(outcome="CONFLICT")


def record_idempotency(
    db: Session,
    client_id: str,
    key: str,
    request_hash: str,
    result_payload: dict | None = None,
) -> IdempotencyKey:
    """Persist an idempotency key after a successful operation."""
    expires_at = utc_now() + timedelta(hours=IDEMPOTENCY_TTL_HOURS)
    try:
        return integration_repo.insert_idempotency_key(
            db,
            client_id=client_id,
            key=key,
            request_hash=request_hash,
            result_payload=result_payload,
            expires_at=expires_at,
        )
    except IntegrityError:
        db.rollback()
        # Race condition: record was inserted concurrently; return existing
        existing = integration_repo.get_idempotency_key(db, client_id, key)
        return existing  # type: ignore[return-value]


def update_idempotency_result(
    db: Session, client_id: str, key: str, result_payload: dict
) -> None:
    record = integration_repo.get_idempotency_key(db, client_id, key)
    if record:
        integration_repo.update_idempotency_result(db, record, result_payload)

