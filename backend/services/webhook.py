"""BE-019 webhook service: SSRF protection, HMAC signing, payload building, outbox delivery."""

import hashlib
import hmac
import ipaddress
import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.db.models import WEBHOOK_EVENT_TYPES, WebhookDelivery, WebhookEvent
from backend.repositories import integration as integration_repo


logger = logging.getLogger(__name__)

WEBHOOK_EVENT_VERSION = 1

# Retry delays in seconds: attempt 1, 2, 3, 4... then terminal failure
RETRY_DELAYS = [30, 300, 1800, 7200]
MAX_DELIVERY_ATTEMPTS = len(RETRY_DELAYS) + 1

# HTTP status codes that are retryable
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Private/reserved IP ranges blocked for SSRF protection
_BLOCKED_PREFIXES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / metadata
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space
    ipaddress.ip_network("0.0.0.0/8"),
]

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}

# Cloud metadata endpoints
_BLOCKED_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure
    ipaddress.ip_address("fd00:ec2::254"),    # AWS IPv6
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# SSRF Protection
# ---------------------------------------------------------------------------


def validate_webhook_url(url: str) -> None:
    """Validate a webhook endpoint URL against SSRF risks.

    Raises ValueError with a descriptive message if the URL is blocked.
    No redirects are followed — callers must deliver to the literal URL.
    """
    if not url or not url.strip():
        raise ValueError("Webhook URL must not be empty")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Webhook URL scheme must be http or https, got {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL must have a valid hostname")

    hostname_lower = hostname.lower().rstrip(".")
    if hostname_lower in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Webhook URL hostname {hostname!r} is not allowed")

    # Resolve hostname to IP and check all resolved addresses
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = {ipaddress.ip_address(r[4][0]) for r in results}
    except (socket.gaierror, OSError, ValueError):
        # Cannot resolve — reject conservatively
        raise ValueError(f"Webhook URL hostname {hostname!r} could not be resolved")

    for ip in ips:
        if ip in _BLOCKED_METADATA_IPS:
            raise ValueError(
                f"Webhook URL resolves to blocked metadata endpoint {ip}"
            )
        for prefix in _BLOCKED_PREFIXES:
            if ip in prefix:
                raise ValueError(
                    f"Webhook URL resolves to private/reserved address {ip} — blocked for security"
                )


def is_url_safe(url: str) -> bool:
    """Return True if the URL passes SSRF validation, False otherwise."""
    try:
        validate_webhook_url(url)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# HMAC Signing
# ---------------------------------------------------------------------------


def sign_payload(secret_hash: str, payload_bytes: bytes, timestamp: str) -> str:
    """Produce an HMAC-SHA256 signature over timestamp + "." + payload.

    The secret_hash stored in the DB is itself a SHA-256 hash of the real
    shared secret — we use it directly as the HMAC key so the original
    secret is never needed at delivery time.
    """
    msg = (timestamp + ".").encode("utf-8") + payload_bytes
    return hmac.new(secret_hash.encode("utf-8"), msg, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Payload Building
# ---------------------------------------------------------------------------


def build_webhook_payload(
    event_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    project_id: str | None,
    occurred_at: datetime,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build a versioned, structured webhook payload."""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": WEBHOOK_EVENT_VERSION,
        "occurred_at": occurred_at.isoformat(),
        "resource_type": aggregate_type,
        "resource_id": aggregate_id,
        "project_id": project_id,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Retry Backoff
# ---------------------------------------------------------------------------


def compute_next_webhook_attempt(attempt_count: int) -> datetime | None:
    """Return the datetime for the next retry, or None if max attempts exceeded."""
    if attempt_count >= MAX_DELIVERY_ATTEMPTS:
        return None
    delay = RETRY_DELAYS[min(attempt_count, len(RETRY_DELAYS) - 1)]
    return utc_now() + timedelta(seconds=delay)


def is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES


# ---------------------------------------------------------------------------
# Outbox: Enqueue Webhook Event
# ---------------------------------------------------------------------------


def enqueue_webhook_event(
    db: Session,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    project_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> WebhookEvent:
    """Write a webhook event to the transactional outbox (same DB transaction as domain mutation).

    Raises ValueError if event_type is not in WEBHOOK_EVENT_TYPES.
    """
    if event_type not in WEBHOOK_EVENT_TYPES:
        raise ValueError(f"Unknown webhook event type: {event_type!r}")

    event = integration_repo.insert_webhook_event(
        db,
        event_type=event_type,
        event_version=WEBHOOK_EVENT_VERSION,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        project_id=project_id,
        payload=data or {},
        status="PENDING",
    )
    return event
