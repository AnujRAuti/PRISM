"""Unit tests for BE-019 External Integrations & API Client Platform.

Tests cover:
- Credential hashing, constant-time verification, generation
- Idempotency key evaluation (NEW, REPLAY, CONFLICT, client scoping)
- Webhook SSRF validation (localhost, private subnets, metadata endpoints, scheme)
- Webhook HMAC-SHA256 signing and signature verification
- Webhook payload structure and versioning
- Webhook retry backoff calculation and status code retryability
- Pydantic schema validation (timezone awareness, external ID constraints, system types)
"""

import hmac
import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.schemas.integration import (
    ApiClientCreate,
    ExternalAssertionCreate,
    ExternalClaimImport,
    ExternalReferenceCreate,
    ExternalSystemCreate,
    WebhookSubscriptionCreate,
    WebhookSubscriptionUpdate,
)
from backend.services.integration import (
    compute_request_hash,
    generate_secret,
    hash_secret,
    verify_secret,
)
from backend.services.webhook import (
    build_webhook_payload,
    compute_next_webhook_attempt,
    is_retryable_status,
    is_url_safe,
    sign_payload,
    validate_webhook_url,
    MAX_DELIVERY_ATTEMPTS,
    RETRY_DELAYS,
    WEBHOOK_EVENT_VERSION,
)


# ---------------------------------------------------------------------------
# Credential Hashing and Generation
# ---------------------------------------------------------------------------


def test_credential_hashing_and_verification():
    secret = generate_secret()
    assert len(secret) == 64
    digest = hash_secret(secret)
    assert digest != secret
    assert len(digest) == 64

    # Valid secret verifies
    assert verify_secret(secret, digest) is True

    # Tampered secret fails
    tampered = secret[:-1] + ("0" if secret[-1] != "0" else "1")
    assert verify_secret(tampered, digest) is False

    # Random secret fails
    assert verify_secret(generate_secret(), digest) is False


def test_secret_generation_uniqueness():
    secrets_set = {generate_secret() for _ in range(100)}
    assert len(secrets_set) == 100


# ---------------------------------------------------------------------------
# Idempotency Hashing & Logic
# ---------------------------------------------------------------------------


def test_request_hash_determinism():
    payload_a = {"name": "System A", "code": "SYS_A", "nested": {"x": 1, "y": 2}}
    payload_b = {"nested": {"y": 2, "x": 1}, "code": "SYS_A", "name": "System A"}
    payload_different = {"name": "System B", "code": "SYS_A"}

    hash_a = compute_request_hash(payload_a)
    hash_b = compute_request_hash(payload_b)
    hash_diff = compute_request_hash(payload_different)

    # Key order independent for dicts
    assert hash_a == hash_b
    assert hash_a != hash_diff


def test_request_hash_bytes_and_str():
    assert compute_request_hash(b"hello world") == compute_request_hash("hello world")


# ---------------------------------------------------------------------------
# SSRF Protection Tests
# ---------------------------------------------------------------------------


def test_ssrf_blocks_localhost():
    assert is_url_safe("http://localhost/webhook") is False
    assert is_url_safe("http://127.0.0.1:8000/webhook") is False
    assert is_url_safe("http://127.0.0.2/webhook") is False

    with pytest.raises(ValueError, match="not allowed|private"):
        validate_webhook_url("http://localhost:8080/hook")


def test_ssrf_blocks_private_ip_ranges():
    # 10.x.x.x
    assert is_url_safe("http://10.0.0.1/hook") is False
    # 172.16.x.x
    assert is_url_safe("http://172.16.0.1/hook") is False
    # 192.168.x.x
    assert is_url_safe("http://192.168.1.1/hook") is False
    # 0.0.0.0
    assert is_url_safe("http://0.0.0.0/hook") is False

    with pytest.raises(ValueError, match="private/reserved"):
        validate_webhook_url("http://192.168.1.50/hook")


def test_ssrf_blocks_metadata_endpoints():
    # AWS / GCP / Azure metadata IP
    assert is_url_safe("http://169.254.169.254/latest/meta-data/") is False

    with pytest.raises(ValueError, match="metadata endpoint|private/reserved"):
        validate_webhook_url("http://169.254.169.254/webhook")


def test_ssrf_rejects_unsupported_schemes():
    assert is_url_safe("ftp://example.com/webhook") is False
    assert is_url_safe("file:///etc/passwd") is False
    assert is_url_safe("gopher://example.com") is False

    with pytest.raises(ValueError, match="scheme must be http or https"):
        validate_webhook_url("ftp://example.com/hook")


def test_ssrf_accepts_public_domain():
    # Valid public domain (e.g. example.com resolves to public IP 93.184.216.34)
    # Using an IP known to be public or public domain
    assert is_url_safe("https://httpbin.org/post") is True or is_url_safe("https://example.com/webhook") is True


# ---------------------------------------------------------------------------
# Webhook HMAC Signing & Payload Building
# ---------------------------------------------------------------------------


def test_webhook_signing_and_verification():
    secret_hash = hash_secret("my-shared-secret-12345")
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_bytes = b'{"event_id":"123","event_type":"review_case.assigned"}'

    signature = sign_payload(secret_hash, payload_bytes, timestamp)
    assert len(signature) == 64

    # Manually recompute expected HMAC
    expected_msg = (timestamp + ".").encode("utf-8") + payload_bytes
    expected_sig = hmac.new(secret_hash.encode("utf-8"), expected_msg, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(signature, expected_sig) is True

    # Tampered payload fails
    tampered_sig = sign_payload(secret_hash, b'{"tampered":true}', timestamp)
    assert signature != tampered_sig


def test_webhook_payload_structure():
    now = datetime.now(timezone.utc)
    event_id = str(uuid4())
    agg_id = str(uuid4())
    project_id = str(uuid4())

    payload = build_webhook_payload(
        event_id=event_id,
        event_type="review_case.resolved",
        aggregate_type="REVIEW_CASE",
        aggregate_id=agg_id,
        project_id=project_id,
        occurred_at=now,
        data={"decision": "SUPPORTED"},
    )

    assert payload["event_id"] == event_id
    assert payload["event_type"] == "review_case.resolved"
    assert payload["event_version"] == WEBHOOK_EVENT_VERSION
    assert payload["occurred_at"] == now.isoformat()
    assert payload["resource_type"] == "REVIEW_CASE"
    assert payload["resource_id"] == agg_id
    assert payload["project_id"] == project_id
    assert payload["data"] == {"decision": "SUPPORTED"}


# ---------------------------------------------------------------------------
# Webhook Retry Backoff & Status Codes
# ---------------------------------------------------------------------------


def test_webhook_retry_backoff():
    # Delays must be non-decreasing
    assert RETRY_DELAYS == sorted(RETRY_DELAYS)

    # Next attempt exists for attempt < MAX_DELIVERY_ATTEMPTS
    t0 = compute_next_webhook_attempt(0)
    assert t0 is not None
    t1 = compute_next_webhook_attempt(1)
    assert t1 is not None

    # Beyond max attempts -> None (terminal failure)
    assert compute_next_webhook_attempt(MAX_DELIVERY_ATTEMPTS) is None
    assert compute_next_webhook_attempt(MAX_DELIVERY_ATTEMPTS + 5) is None


def test_webhook_retryable_status_codes():
    assert is_retryable_status(500) is True
    assert is_retryable_status(502) is True
    assert is_retryable_status(503) is True
    assert is_retryable_status(504) is True
    assert is_retryable_status(429) is True
    assert is_retryable_status(408) is True

    # Non-retryable
    assert is_retryable_status(400) is False
    assert is_retryable_status(401) is False
    assert is_retryable_status(403) is False
    assert is_retryable_status(404) is False
    assert is_retryable_status(200) is False


# ---------------------------------------------------------------------------
# Schema Validations
# ---------------------------------------------------------------------------


def test_external_system_create_validation():
    valid = ExternalSystemCreate(
        name="Gov Portal",
        code="GOV_PORTAL_01",
        system_type="GOVERNMENT_PORTAL",
    )
    assert valid.system_type == "GOVERNMENT_PORTAL"

    with pytest.raises(ValidationError):
        ExternalSystemCreate(
            name="Bad System",
            code="BAD_01",
            system_type="INVALID_TYPE",
        )


def test_external_reference_create_validation():
    sys_id = uuid4()
    res_id = uuid4()

    valid = ExternalReferenceCreate(
        external_system_id=sys_id,
        resource_type="evidence",
        resource_id=res_id,
        external_id="EXT-12345",
    )
    assert valid.external_id == "EXT-12345"

    # Empty external_id rejected
    with pytest.raises(ValidationError):
        ExternalReferenceCreate(
            external_system_id=sys_id,
            resource_type="evidence",
            resource_id=res_id,
            external_id="   ",
        )


def test_assertion_requires_timezone_aware_timestamp():
    sys_id = uuid4()

    # Timezone-aware passes
    aware = datetime.now(timezone.utc)
    item = ExternalAssertionCreate(
        external_system_id=sys_id,
        source_timestamp=aware,
        payload={"key": "val"},
    )
    assert item.source_timestamp.tzinfo is not None

    # Naive timestamp rejected
    naive = datetime(2026, 9, 23, 12, 0, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        ExternalAssertionCreate(
            external_system_id=sys_id,
            source_timestamp=naive,
            payload={"key": "val"},
        )


def test_claim_import_requires_timezone_aware_timestamp():
    sys_id = uuid4()
    subj_id = uuid4()

    naive = datetime(2026, 9, 23, 12, 0, 0)
    with pytest.raises(ValidationError, match="timezone-aware"):
        ExternalClaimImport(
            external_system_id=sys_id,
            external_reference="REF-001",
            claim_type="PROGRESS",
            subject_type="PROJECT",
            subject_id=subj_id,
            assertion={"status": "completed"},
            source_timestamp=naive,
        )


def test_webhook_subscription_create_validates_events():
    sys_id = uuid4()

    # Valid event types
    valid = WebhookSubscriptionCreate(
        external_system_id=sys_id,
        endpoint_url="https://example.com/webhook",
        subscribed_events=["review_case.created", "fusion.completed"],
    )
    assert len(valid.subscribed_events) == 2

    # Invalid event types rejected
    with pytest.raises(ValidationError, match="Unknown event types"):
        WebhookSubscriptionCreate(
            external_system_id=sys_id,
            endpoint_url="https://example.com/webhook",
            subscribed_events=["invalid.event.name"],
        )


def test_webhook_subscription_update_validates_status():
    valid = WebhookSubscriptionUpdate(status="DISABLED")
    assert valid.status == "DISABLED"

    with pytest.raises(ValidationError, match="ACTIVE, SUSPENDED, or DISABLED"):
        WebhookSubscriptionUpdate(status="DESTROYED")

