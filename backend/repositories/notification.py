"""BE-018 notification repository: persistence for notifications, deliveries, preferences, outbox."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.db.models import (
    Notification,
    NotificationDelivery,
    NotificationOutbox,
    NotificationPreference,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def insert_notification(
    db: Session,
    *,
    recipient_id: str,
    notification_type: str,
    title: str,
    body: str,
    organization_id: str | None = None,
    project_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    severity: str = "INFO",
    expires_at: datetime | None = None,
) -> Notification:
    row = Notification(
        recipient_id=recipient_id,
        organization_id=organization_id,
        project_id=project_id,
        notification_type=notification_type,
        title=title,
        body=body,
        resource_type=resource_type,
        resource_id=resource_id,
        severity=severity,
        status="UNREAD",
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    return row


def get_notification(db: Session, notification_id: str) -> Notification | None:
    return db.query(Notification).filter(Notification.id == notification_id).one_or_none()


def list_notifications(
    db: Session,
    *,
    recipient_id: str,
    unread_only: bool = False,
    notification_type: str | None = None,
    project_id: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Notification], int]:
    query = db.query(Notification).filter(Notification.recipient_id == recipient_id)
    if unread_only:
        query = query.filter(Notification.status == "UNREAD")
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    if project_id:
        query = query.filter(Notification.project_id == project_id)
    if from_date:
        query = query.filter(Notification.created_at >= from_date)
    if to_date:
        query = query.filter(Notification.created_at <= to_date)

    total = query.count()
    items = (
        query.order_by(desc(Notification.created_at), desc(Notification.id))
        .offset(offset)
        .limit(limit)
        .all()
    )
    return items, total


def count_unread(db: Session, recipient_id: str) -> int:
    """Fast indexed unread counter."""
    return (
        db.query(func.count(Notification.id))
        .filter(
            Notification.recipient_id == recipient_id,
            Notification.status == "UNREAD",
        )
        .scalar()
        or 0
    )


def mark_notification_read(
    db: Session, notification_id: str, read_at: datetime | None = None
) -> Notification | None:
    row = get_notification(db, notification_id)
    if row is None:
        return None
    if row.status != "READ":
        row.status = "READ"
        row.read_at = read_at or utc_now()
        db.flush()
    return row


def mark_all_notifications_read(
    db: Session, recipient_id: str, read_at: datetime | None = None
) -> int:
    moment = read_at or utc_now()
    count = (
        db.query(Notification)
        .filter(
            Notification.recipient_id == recipient_id,
            Notification.status == "UNREAD",
        )
        .update(
            {"status": "READ", "read_at": moment},
            synchronize_session=False,
        )
    )
    db.flush()
    return count


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------


def insert_delivery(
    db: Session,
    *,
    notification_id: str,
    channel: str,
    provider: str,
    status: str = "PENDING",
) -> NotificationDelivery:
    row = NotificationDelivery(
        notification_id=notification_id,
        channel=channel,
        provider=provider,
        status=status,
    )
    db.add(row)
    db.flush()
    return row


def get_delivery(db: Session, delivery_id: str) -> NotificationDelivery | None:
    return (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.id == delivery_id)
        .one_or_none()
    )


def get_delivery_by_channel(
    db: Session, notification_id: str, channel: str
) -> NotificationDelivery | None:
    return (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification_id,
            NotificationDelivery.channel == channel,
        )
        .one_or_none()
    )


def list_deliveries_for_notification(
    db: Session, notification_id: str
) -> list[NotificationDelivery]:
    return (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == notification_id)
        .order_by(NotificationDelivery.created_at)
        .all()
    )


def update_delivery(
    db: Session,
    delivery_id: str,
    *,
    status: str,
    attempts: int | None = None,
    provider_message_id: str | None = None,
    last_error: str | None = None,
    next_attempt_at: datetime | None = None,
    delivered_at: datetime | None = None,
) -> NotificationDelivery | None:
    row = get_delivery(db, delivery_id)
    if row is None:
        return None
    row.status = status
    if attempts is not None:
        row.attempts = attempts
    if provider_message_id is not None:
        row.provider_message_id = provider_message_id
    if last_error is not None:
        row.last_error = last_error
    if next_attempt_at is not None:
        row.next_attempt_at = next_attempt_at
    if delivered_at is not None:
        row.delivered_at = delivered_at
    db.flush()
    return row


def list_retrying_deliveries(
    db: Session, moment: datetime | None = None, limit: int = 50
) -> list[NotificationDelivery]:
    now = moment or utc_now()
    return (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.status == "RETRYING",
            NotificationDelivery.next_attempt_at <= now,
        )
        .order_by(NotificationDelivery.next_attempt_at)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


def get_user_preferences(db: Session, user_id: str) -> list[NotificationPreference]:
    return (
        db.query(NotificationPreference)
        .filter(NotificationPreference.user_id == user_id)
        .all()
    )


def get_user_preference(
    db: Session, user_id: str, notification_type: str
) -> NotificationPreference | None:
    return (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notification_type,
        )
        .one_or_none()
    )


def upsert_user_preference(
    db: Session,
    *,
    user_id: str,
    notification_type: str,
    in_app_enabled: bool | None = None,
    email_enabled: bool | None = None,
) -> NotificationPreference:
    pref = get_user_preference(db, user_id, notification_type)
    if pref is None:
        pref = NotificationPreference(
            user_id=user_id,
            notification_type=notification_type,
            in_app_enabled=True if in_app_enabled is None else in_app_enabled,
            email_enabled=True if email_enabled is None else email_enabled,
        )
        db.add(pref)
    else:
        if in_app_enabled is not None:
            pref.in_app_enabled = in_app_enabled
        if email_enabled is not None:
            pref.email_enabled = email_enabled
        pref.updated_at = utc_now()
    db.flush()
    return pref


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------


def insert_outbox_event(
    db: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> NotificationOutbox:
    row = NotificationOutbox(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        status="PENDING",
    )
    db.add(row)
    db.flush()
    return row


def fetch_pending_outbox_events(
    db: Session, limit: int = 50
) -> list[NotificationOutbox]:
    return (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.status == "PENDING")
        .order_by(NotificationOutbox.created_at)
        .limit(limit)
        .all()
    )


def update_outbox_event(
    db: Session,
    outbox_id: str,
    *,
    status: str,
    attempts: int | None = None,
    processed_at: datetime | None = None,
    last_error: str | None = None,
) -> NotificationOutbox | None:
    row = (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.id == outbox_id)
        .one_or_none()
    )
    if row is None:
        return None
    row.status = status
    if attempts is not None:
        row.attempts = attempts
    if processed_at is not None:
        row.processed_at = processed_at
    if last_error is not None:
        row.last_error = last_error
    db.flush()
    return row

