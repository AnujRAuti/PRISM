"""BE-019 webhook service: SSRF protection, HMAC signing, payload building, outbox delivery."""

import hashlib
import hmac
import ipaddress
import logging
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.db.models import WEBHOOK_EVENT_TYPES, WebhookEvent
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
# SSRF-safe transport (closes BE-036-D1)
# ---------------------------------------------------------------------------

#: Hard outbound timeout for a single webhook POST. Kept here so the delivery
#: path and its tests share one value.
WEBHOOK_DELIVERY_TIMEOUT_SECONDS = 10


class WebhookRedirectError(ValueError):
    """Raised when a webhook endpoint answers with an HTTP redirect.

    It subclasses ``ValueError`` deliberately: ``validate_webhook_url`` already
    signals an SSRF rejection with ``ValueError``, and the delivery worker turns
    any ``ValueError`` into a permanent, non-retried failure. A redirect belongs
    in that same bucket — following it is exactly the bypass BE-036-D1 reported,
    because ``urllib``'s default opener transparently follows 3xx responses and
    would then connect to a destination that never passed SSRF validation.
    """


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect instead of following it.

    ``redirect_request`` is what the base handler calls before it opens a second
    connection; raising here means the socket to the redirect target is never
    created. ``handler_order`` is set below the default redirect handler's
    (700) so, when ``build_opener`` installs both, this one is consulted first
    and short-circuits the follow.
    """

    handler_order = 699

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise WebhookRedirectError(
            f"Webhook endpoint returned HTTP {code} redirect to {newurl!r}; "
            "redirects are rejected so a validated destination cannot "
            "redirect toward a prohibited address (BE-036-D1)."
        )


#: A dedicated opener. Using a scoped opener (rather than ``install_opener``)
#: keeps redirect rejection to webhook delivery and never mutates the
#: process-global ``urlopen`` behaviour other code may rely on.
NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def deliver_webhook(
    url: str,
    payload_bytes: bytes,
    headers: dict[str, str],
    timeout: int = WEBHOOK_DELIVERY_TIMEOUT_SECONDS,
) -> int:
    """Validate then POST a webhook through the redirect-refusing opener.

    The literal endpoint URL is re-validated on every attempt (DNS may have
    changed since subscription time) and the request is issued through
    ``NO_REDIRECT_OPENER``, so a 3xx response raises ``WebhookRedirectError``
    instead of silently connecting to a new, unvalidated destination. Returns
    the final HTTP status code for a 2xx response; raises ``urllib.error.*`` for
    transport/HTTP-status outcomes and ``ValueError`` (``WebhookRedirectError``
    or the SSRF validator) for security rejections — the caller maps those.
    """
    validate_webhook_url(url)
    req = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
    req.timeout = timeout
    with NO_REDIRECT_OPENER.open(req) as resp:
        return resp.status


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

