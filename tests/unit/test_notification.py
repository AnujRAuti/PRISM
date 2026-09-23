"""BE-018 unit tests: templates, recipient resolution, preferences, retry backoff, schemas."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.db.models import NOTIFICATION_TYPES
from backend.schemas.notification import (
    NotificationDeliveryResponse,
    NotificationListResponse,
    NotificationPreferenceItem,
    NotificationResponse,
    NotificationType,
)
from backend.services import notification as notif_service
from backend.services.notification import (
    DevEmailProvider,
    InAppProvider,
    compute_next_attempt,
    render_template,
)


def aware(year=2026, month=9, day=23, hour=12):
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def test_render_template_all_types():
    """Verify all 13 controlled notification types have deterministic templates."""
    for ntype in NOTIFICATION_TYPES:
        ctx = {
            "case_id": "test-case-123",
            "request_id": "test-req-456",
            "hold_id": "test-hold-789",
            "project_name": "Project Alpha",
            "project_id": "proj-uuid",
            "priority_band": "HIGH",
            "escalation_reason": "Suspected anomaly",
            "decision": "CONFIRMED",
            "reopen_reason": "New data provided",
            "reason": "Administrative reason",
            "release_reason": "Audit completed",
            "summary": "Suspicious login",
            "details": "Multiple failed attempts",
        }
        title, body, severity = render_template(ntype, ctx)
        assert title and isinstance(title, str)
        assert body and isinstance(body, str)
        assert severity in ("INFO", "WARNING", "CRITICAL")


def test_render_template_severities():
    """High priority case assignment elevates severity to WARNING."""
    title, body, sev_normal = render_template(
        "REVIEW_CASE_ASSIGNED", {"case_id": "c1", "priority_band": "NORMAL"}
    )
    assert sev_normal == "INFO"

    title, body, sev_urgent = render_template(
        "REVIEW_CASE_ASSIGNED", {"case_id": "c1", "priority_band": "URGENT"}
    )
    assert sev_urgent == "WARNING"

    title, body, sev_sec = render_template(
        "SYSTEM_SECURITY_EVENT", {"summary": "Alert", "details": "Breach"}
    )
    assert sev_sec == "CRITICAL"


def test_retry_backoff_schedule():
    """Verify deterministic backoff schedule."""
    t0 = aware(2026, 9, 23, 12)
    # Attempt 0: +0s
    assert compute_next_attempt(0, t0) == t0
    # Attempt 1: +30s
    assert compute_next_attempt(1, t0) == t0 + timedelta(seconds=30)
    # Attempt 2: +300s
    assert compute_next_attempt(2, t0) == t0 + timedelta(seconds=300)
    # Attempt 3: +1800s
    assert compute_next_attempt(3, t0) == t0 + timedelta(seconds=1800)
    # Attempt 4+: terminal failure -> None
    assert compute_next_attempt(4, t0) is None
    assert compute_next_attempt(10, t0) is None


def test_in_app_provider_immediate():
    """In-app provider delivers immediately."""
    provider = InAppProvider()
    class DummyNotif:
        id = "notif-1"
    class DummyDelivery:
        id = "del-1"

    success, msg_id, err = provider.deliver(DummyNotif(), None, DummyDelivery())
    assert success is True
    assert msg_id == "in-app-notif-1"
    assert err is None


def test_dev_email_provider():
    """DevEmailProvider records in-memory deliveries."""
    provider = DevEmailProvider()
    class DummyUser:
        email = "reviewer@example.com"
    class DummyNotif:
        id = "notif-uuid-1234"
        title = "Test Email Notification"
        body = "Email body text"
    class DummyDelivery:
        id = "del-uuid-5678"

    success, msg_id, err = provider.deliver(DummyNotif(), DummyUser(), DummyDelivery())
    assert success is True
    assert msg_id.startswith("dev-msg-")
    assert err is None
    assert len(DevEmailProvider.sent_deliveries) > 0
    last = DevEmailProvider.sent_deliveries[-1]
    assert last["to"] == "reviewer@example.com"
    assert last["title"] == "Test Email Notification"


def test_schema_validations():
    """Verify Pydantic schemas serialize correctly."""
    now = aware()
    notif = NotificationResponse(
        id=str(uuid4()),
        recipient_id=str(uuid4()),
        organization_id=str(uuid4()),
        project_id=str(uuid4()),
        notification_type="REVIEW_CASE_ASSIGNED",
        title="Case Assigned",
        body="You have a case",
        severity="INFO",
        status="UNREAD",
        created_at=now,
    )
    assert notif.status == "UNREAD"
    assert notif.notification_type == NotificationType.REVIEW_CASE_ASSIGNED

    list_resp = NotificationListResponse(
        items=[notif],
        total=1,
        limit=50,
        offset=0,
        unread_count=1,
    )
    assert list_resp.total == 1
    assert list_resp.unread_count == 1

    pref_item = NotificationPreferenceItem(
        notification_type="REVIEW_CASE_ASSIGNED",
        in_app_enabled=True,
        email_enabled=False,
        updated_at=now,
    )
    assert pref_item.email_enabled is False


def test_invalid_event_type_validation():
    """Unknown event types cannot be emitted to outbox."""
    with pytest.raises(ValueError, match="Unknown notification event type"):
        notif_service.emit_notification_event(
            None,
            event_type="INVALID_UNKNOWN_TYPE",
            aggregate_type="REVIEW_CASE",
            aggregate_id=str(uuid4()),
            payload={},
        )

