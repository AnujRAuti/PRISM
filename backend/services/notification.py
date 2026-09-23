"""BE-018 notification service: templates, recipient resolution, authorization filtering, delivery execution."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import (
    NOTIFICATION_CHANNELS,
    NOTIFICATION_DELIVERY_STATUSES,
    NOTIFICATION_SEVERITIES,
    NOTIFICATION_STATUSES,
    NOTIFICATION_TYPES,
    Notification,
    NotificationDelivery,
    NotificationOutbox,
    NotificationPreference,
    Project,
    User,
    UserRoleAssignment,
)
from backend.repositories import notification as notif_repo
from backend.services import audit_ledger as audit_service
from backend.services import authorization as auth_service
from backend.services.authorization import Principal, Resource, can


logger = logging.getLogger(__name__)

TEMPLATE_VERSION = "v1"

# Delays in seconds before retry attempt 1, 2, 3...
RETRY_DELAYS = [0, 30, 300, 1800]
MAX_DELIVERY_ATTEMPTS = 4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid {name}: {value!r}") from error


def _optional_uuid(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid {name}: {value!r}") from error


# ---------------------------------------------------------------------------
# Versioned Templates (Deterministic, Non-LLM)
# ---------------------------------------------------------------------------


def render_template(
    notification_type: str,
    context: dict[str, Any],
) -> tuple[str, str, str]:
    """Render deterministic notification (title, body, severity) from structured data.

    Returns (title, body, severity).
    """
    ctx = context or {}
    severity = ctx.get("severity") or "INFO"

    if notification_type == "REVIEW_CASE_ASSIGNED":
        case_id = ctx.get("case_id", "UNKNOWN")
        project_name = ctx.get("project_name") or ctx.get("project_id", "Unspecified")
        priority = ctx.get("priority_band", "NORMAL")
        title = f"Review Case Assigned: #{case_id}"
        body = f"You have been assigned to review case #{case_id} for project '{project_name}'. Priority: {priority}."
        if priority in ("HIGH", "URGENT"):
            severity = "WARNING"

    elif notification_type == "REVIEW_CASE_ESCALATED":
        case_id = ctx.get("case_id", "UNKNOWN")
        reason = ctx.get("escalation_reason") or ctx.get("reason", "No reason provided")
        title = f"Review Case Escalated: #{case_id}"
        body = f"Review case #{case_id} has been escalated to supervisory review. Reason: {reason}."
        severity = "WARNING"

    elif notification_type == "REVIEW_CASE_DECISION_PENDING":
        case_id = ctx.get("case_id", "UNKNOWN")
        decision = ctx.get("decision", "RECORDED")
        title = f"Review Case Decision Pending: #{case_id}"
        body = f"A decision ({decision}) has been recorded for review case #{case_id} and is pending resolution."
        severity = "INFO"

    elif notification_type == "REVIEW_CASE_REOPENED":
        case_id = ctx.get("case_id", "UNKNOWN")
        reason = ctx.get("reopen_reason") or ctx.get("reason", "Investigation resumed")
        title = f"Review Case Reopened: #{case_id}"
        body = f"Review case #{case_id} has been reopened for further investigation. Reason: {reason}."
        severity = "WARNING"

    elif notification_type == "EVIDENCE_REQUEST_ISSUED":
        request_id = ctx.get("request_id", "UNKNOWN")
        project_name = ctx.get("project_name") or ctx.get("project_id", "Unspecified")
        items_count = ctx.get("items_count", 1)
        priority = ctx.get("priority", "NORMAL")
        title = f"Evidence Request Issued: #{request_id}"
        body = f"You have received an evidence request (#{request_id}) for project '{project_name}' requesting {items_count} item(s). Priority: {priority}."
        severity = "INFO"

    elif notification_type == "EVIDENCE_REQUEST_ACKNOWLEDGED":
        request_id = ctx.get("request_id", "UNKNOWN")
        title = f"Evidence Request Acknowledged: #{request_id}"
        body = f"Evidence request #{request_id} has been acknowledged by the recipient."
        severity = "INFO"

    elif notification_type == "EVIDENCE_REQUEST_PARTIALLY_FULFILLED":
        request_id = ctx.get("request_id", "UNKNOWN")
        fulfilled = ctx.get("fulfilled_count", 1)
        total = ctx.get("total_count", 1)
        title = f"Evidence Request Partially Fulfilled: #{request_id}"
        body = f"Evidence request #{request_id} has received items ({fulfilled}/{total} items fulfilled)."
        severity = "INFO"

    elif notification_type == "EVIDENCE_REQUEST_FULFILLED":
        request_id = ctx.get("request_id", "UNKNOWN")
        title = f"Evidence Request Fulfilled: #{request_id}"
        body = f"All requested evidence items for request #{request_id} have been provided."
        severity = "INFO"

    elif notification_type == "EVIDENCE_REQUEST_DECLINED":
        request_id = ctx.get("request_id", "UNKNOWN")
        reason = ctx.get("reason", "Declined by recipient")
        title = f"Evidence Request Declined: #{request_id}"
        body = f"Evidence request #{request_id} was declined. Reason: {reason}."
        severity = "WARNING"

    elif notification_type == "EVIDENCE_REQUEST_EXPIRED":
        request_id = ctx.get("request_id", "UNKNOWN")
        title = f"Evidence Request Expired: #{request_id}"
        body = f"Evidence request #{request_id} has expired without complete fulfillment."
        severity = "WARNING"

    elif notification_type == "RETENTION_HOLD_CREATED":
        hold_id = ctx.get("hold_id", "UNKNOWN")
        scope = ctx.get("scope", "RESOURCE")
        reason = ctx.get("reason", "Administrative/legal hold")
        title = f"Retention Hold Placed: #{hold_id}"
        body = f"A retention hold ({scope}) has been placed on resources. Reason: {reason}."
        severity = "WARNING"

    elif notification_type == "RETENTION_HOLD_RELEASED":
        hold_id = ctx.get("hold_id", "UNKNOWN")
        release_reason = ctx.get("release_reason", "Hold released")
        title = f"Retention Hold Released: #{hold_id}"
        body = f"Retention hold #{hold_id} has been released. Reason: {release_reason}."
        severity = "INFO"

    elif notification_type == "SYSTEM_SECURITY_EVENT":
        summary = ctx.get("summary", "Security event detected")
        details = ctx.get("details", "Please review your account and activity logs.")
        title = f"Security Alert: {summary}"
        body = details
        severity = "CRITICAL"

    else:
        title = ctx.get("title") or f"Notification: {notification_type}"
        body = ctx.get("body") or f"An event of type {notification_type} has occurred."
        severity = ctx.get("severity") or "INFO"

    return title, body, severity


# ---------------------------------------------------------------------------
# Recipient Resolution & Authorization Filtering
# ---------------------------------------------------------------------------


def resolve_recipients(
    db: Session,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> list[str]:
    """Resolve prospective recipient user IDs deterministically from workflow context."""
    recipients: set[str] = set()

    # 1. Explicit recipients in payload
    if payload.get("recipients"):
        for r in payload["recipients"]:
            if r:
                recipients.add(str(r))
    if payload.get("recipient_id"):
        recipients.add(str(payload["recipient_id"]))

    # 2. Workflow-specific resolution
    if event_type == "REVIEW_CASE_ASSIGNED":
        assigned_to = payload.get("assigned_to")
        if assigned_to:
            recipients.add(str(assigned_to))

    elif event_type in ("REVIEW_CASE_ESCALATED", "REVIEW_CASE_DECISION_PENDING"):
        # Notify supervisors responsible for this project/scope
        project_id = payload.get("project_id")
        if project_id:
            supervisors = _find_supervisors_for_project(db, project_id)
            recipients.update(supervisors)

    elif event_type == "REVIEW_CASE_REOPENED":
        if payload.get("assigned_to"):
            recipients.add(str(payload["assigned_to"]))
        project_id = payload.get("project_id")
        if project_id:
            supervisors = _find_supervisors_for_project(db, project_id)
            recipients.update(supervisors)

    elif event_type in (
        "EVIDENCE_REQUEST_ACKNOWLEDGED",
        "EVIDENCE_REQUEST_PARTIALLY_FULFILLED",
        "EVIDENCE_REQUEST_FULFILLED",
        "EVIDENCE_REQUEST_DECLINED",
        "EVIDENCE_REQUEST_EXPIRED",
    ):
        created_by = payload.get("created_by")
        if created_by:
            recipients.add(str(created_by))

    elif event_type in ("RETENTION_HOLD_CREATED", "RETENTION_HOLD_RELEASED"):
        # Notify project/organization administrators
        project_id = payload.get("project_id")
        if project_id:
            admins = _find_admins_for_project(db, project_id)
            recipients.update(admins)

    return sorted(list(recipients))


def _find_supervisors_for_project(db: Session, project_id: str) -> list[str]:
    """Find users who hold the SUPERVISOR role covering this project."""
    assignments = (
        db.query(UserRoleAssignment)
        .filter(
            UserRoleAssignment.role_name == "SUPERVISOR",
            UserRoleAssignment.status == "ACTIVE",
        )
        .all()
    )
    user_ids: list[str] = []
    for a in assignments:
        if a.scope_type == "GLOBAL" or (
            a.scope_type == "PROJECT" and str(a.project_id) == str(project_id)
        ):
            user_ids.append(str(a.user_id))
    return user_ids


def _find_admins_for_project(db: Session, project_id: str) -> list[str]:
    """Find users who hold the ADMINISTRATOR role covering this project."""
    assignments = (
        db.query(UserRoleAssignment)
        .filter(
            UserRoleAssignment.role_name == "ADMINISTRATOR",
            UserRoleAssignment.status == "ACTIVE",
        )
        .all()
    )
    user_ids: list[str] = []
    for a in assignments:
        if a.scope_type == "GLOBAL" or (
            a.scope_type == "PROJECT" and str(a.project_id) == str(project_id)
        ):
            user_ids.append(str(a.user_id))
    return user_ids


def filter_authorized_recipients(
    db: Session,
    recipient_ids: list[str],
    resource_type: str | None,
    resource_id: str | None,
    project_id: str | None = None,
) -> list[str]:
    """Filter out recipients who lack permission to view the referenced resource.

    Enforces BE-016 authorization and project boundary isolation (fail closed).
    """
    if not recipient_ids:
        return []

    authorized: list[str] = []
    target_resource = Resource(
        resource_type=resource_type or "project",
        resource_id=resource_id,
        project_id=project_id,
    )

    for uid in recipient_ids:
        user = db.query(User).filter(User.id == uid).one_or_none()
        if user is None or user.status != "ACTIVE":
            continue

        # Build principal for user
        from backend.security.authentication import build_principal_for_user

        principal = build_principal_for_user(db, user)

        # Check permission: if notification references a project/resource,
        # user must have read access for that resource type or project.read
        action = "project.read"
        if resource_type == "review_case":
            action = "review_case.read"
        elif resource_type == "evidence_request":
            action = "evidence_request.read"
        elif resource_type == "evidence":
            action = "evidence.read"
        elif resource_type == "retention":
            action = "retention.read"

        decision = can(principal, action, target_resource)
        if decision.allowed:
            authorized.append(uid)
        else:
            logger.info(
                "Recipient %s denied notification on %s:%s (reason=%s)",
                uid,
                resource_type,
                resource_id,
                decision.reason,
            )

    return authorized


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


def should_deliver_channel(
    db: Session,
    user_id: str,
    notification_type: str,
    channel: str,
) -> bool:
    """Check user preference for a given notification type and channel.

    Default is True for all channels. Critical security events are non-disableable in-app.
    """
    if notification_type == "SYSTEM_SECURITY_EVENT" and channel == "IN_APP":
        return True

    pref = notif_repo.get_user_preference(db, user_id, notification_type)
    if pref is None:
        return True

    if channel == "IN_APP":
        return bool(pref.in_app_enabled)
    if channel == "EMAIL":
        return bool(pref.email_enabled)
    return False


# ---------------------------------------------------------------------------
# Providers Abstraction
# ---------------------------------------------------------------------------


class NotificationProvider(ABC):
    @abstractmethod
    def deliver(
        self,
        notification: Notification,
        recipient_user: User,
        delivery: NotificationDelivery,
    ) -> tuple[bool, str | None, str | None]:
        """Attempt delivery. Return (success, provider_message_id, error_message)."""
        pass


class InAppProvider(NotificationProvider):
    """Immediate in-app delivery (inbox row created in Postgres)."""

    def deliver(
        self,
        notification: Notification,
        recipient_user: User,
        delivery: NotificationDelivery,
    ) -> tuple[bool, str | None, str | None]:
        return True, f"in-app-{notification.id}", None


class EmailProvider(NotificationProvider, ABC):
    pass


class DevEmailProvider(EmailProvider):
    """Development/Testing email provider (logs delivery, records sent messages in memory)."""

    # In-memory delivery history for test assertions
    sent_deliveries: list[dict[str, Any]] = []

    def deliver(
        self,
        notification: Notification,
        recipient_user: User,
        delivery: NotificationDelivery,
    ) -> tuple[bool, str | None, str | None]:
        logger.info(
            "[DEV_EMAIL] To: %s | Subject: %s | Body: %s",
            recipient_user.email,
            notification.title,
            notification.body,
        )
        msg_id = f"dev-msg-{notification.id[:8]}-{delivery.id[:8]}"
        record = {
            "to": recipient_user.email,
            "title": notification.title,
            "body": notification.body,
            "notification_id": notification.id,
            "delivery_id": delivery.id,
            "provider_message_id": msg_id,
            "timestamp": utc_now().isoformat(),
        }
        DevEmailProvider.sent_deliveries.append(record)
        return True, msg_id, None


_EMAIL_PROVIDER: EmailProvider = DevEmailProvider()


def get_email_provider() -> EmailProvider:
    return _EMAIL_PROVIDER


def set_email_provider(provider: EmailProvider) -> None:
    global _EMAIL_PROVIDER
    _EMAIL_PROVIDER = provider


# ---------------------------------------------------------------------------
# Retry Policy
# ---------------------------------------------------------------------------


def compute_next_attempt(attempt: int, moment: datetime | None = None) -> datetime | None:
    """Calculate the next retry timestamp based on attempt count.

    attempt 1: +30s
    attempt 2: +300s
    attempt 3: +1800s
    attempt >= 4: None (terminal failure)
    """
    now = moment or utc_now()
    if attempt >= len(RETRY_DELAYS):
        return None
    delay_seconds = RETRY_DELAYS[attempt]
    return now + timedelta(seconds=delay_seconds)


# ---------------------------------------------------------------------------
# Transactional Outbox & Event Emission
# ---------------------------------------------------------------------------


def emit_notification_event(
    db: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> NotificationOutbox:
    """Append a notification outbox record in the caller's active database transaction."""
    if event_type not in NOTIFICATION_TYPES:
        raise ValueError(f"Unknown notification event type: {event_type!r}")

    outbox = notif_repo.insert_outbox_event(
        db,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=_require_uuid(aggregate_id, "aggregate_id"),
        payload=payload,
    )
    return outbox


def process_outbox_event(
    db: Session,
    outbox_event: NotificationOutbox,
    email_provider: EmailProvider | None = None,
) -> list[Notification]:
    """Process one outbox event: resolve recipients, enforce authorization,

    create notifications & delivery records, and execute delivery channels.
    """
    ep = email_provider or get_email_provider()
    in_app_provider = InAppProvider()

    event_type = outbox_event.event_type
    payload = outbox_event.payload or {}
    project_id = _optional_uuid(payload.get("project_id"), "project_id")
    organization_id = _optional_uuid(payload.get("organization_id"), "organization_id")
    resource_type = payload.get("resource_type") or outbox_event.aggregate_type.lower()
    resource_id = _optional_uuid(
        payload.get("resource_id") or str(outbox_event.aggregate_id), "resource_id"
    )

    # 1. Resolve prospective recipients
    candidate_recipients = resolve_recipients(
        db, event_type, outbox_event.aggregate_type, str(outbox_event.aggregate_id), payload
    )

    # 2. Filter authorized recipients (fail-closed, no leak)
    authorized_recipients = filter_authorized_recipients(
        db,
        candidate_recipients,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
    )

    created_notifications: list[Notification] = []

    # 3. Create notifications & execute deliveries for authorized recipients
    title, body, severity = render_template(event_type, payload)

    for recipient_id in authorized_recipients:
        user = db.query(User).filter(User.id == recipient_id).one_or_none()
        if user is None:
            continue

        # Channel preferences check
        in_app_wanted = should_deliver_channel(db, recipient_id, event_type, "IN_APP")
        email_wanted = should_deliver_channel(db, recipient_id, event_type, "EMAIL")

        if not in_app_wanted and not email_wanted:
            continue

        # Create notification record (in-app presence)
        notification = notif_repo.insert_notification(
            db,
            recipient_id=recipient_id,
            notification_type=event_type,
            title=title,
            body=body,
            organization_id=organization_id,
            project_id=project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            severity=severity,
        )
        created_notifications.append(notification)

        # IN_APP delivery
        if in_app_wanted:
            delivery = notif_repo.insert_delivery(
                db,
                notification_id=notification.id,
                channel="IN_APP",
                provider="in_app",
                status="DELIVERED",
            )
            delivery.delivered_at = utc_now()
            delivery.attempts = 1
            delivery.provider_message_id = f"in-app-{notification.id}"
            db.flush()

        # EMAIL delivery
        if email_wanted:
            delivery = notif_repo.insert_delivery(
                db,
                notification_id=notification.id,
                channel="EMAIL",
                provider="dev_email",
                status="PENDING",
            )
            # Execute delivery
            delivery.attempts += 1
            try:
                success, msg_id, err = ep.deliver(notification, user, delivery)
                if success:
                    delivery.status = "DELIVERED"
                    delivery.delivered_at = utc_now()
                    delivery.provider_message_id = msg_id
                    audit_service.append_event(
                        db,
                        event_type="NOTIFICATION_DELIVERY_SUCCEEDED",
                        action="deliver",
                        resource_type="notification_deliveries",
                        resource_id=delivery.id,
                        actor_id=recipient_id,
                        project_id=project_id,
                        payload={
                            "notification_id": notification.id,
                            "channel": "EMAIL",
                            "provider_message_id": msg_id,
                        },
                        source="notification_service",
                    )
                else:
                    delivery.last_error = err
                    if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
                        delivery.status = "FAILED"
                    else:
                        delivery.status = "RETRYING"
                        delivery.next_attempt_at = compute_next_attempt(delivery.attempts)
                    audit_service.append_event(
                        db,
                        event_type="NOTIFICATION_DELIVERY_FAILED",
                        action="deliver_fail",
                        resource_type="notification_deliveries",
                        resource_id=delivery.id,
                        actor_id=recipient_id,
                        project_id=project_id,
                        payload={
                            "notification_id": notification.id,
                            "channel": "EMAIL",
                            "attempts": delivery.attempts,
                            "error": err,
                        },
                        source="notification_service",
                    )
            except Exception as exc:
                delivery.last_error = str(exc)
                if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
                    delivery.status = "FAILED"
                else:
                    delivery.status = "RETRYING"
                    delivery.next_attempt_at = compute_next_attempt(delivery.attempts)
                audit_service.append_event(
                    db,
                    event_type="NOTIFICATION_DELIVERY_FAILED",
                    action="deliver_fail",
                    resource_type="notification_deliveries",
                    resource_id=delivery.id,
                    actor_id=recipient_id,
                    project_id=project_id,
                    payload={
                        "notification_id": notification.id,
                        "channel": "EMAIL",
                        "attempts": delivery.attempts,
                        "error": str(exc),
                    },
                    source="notification_service",
                )
            db.flush()

    outbox_event.status = "PUBLISHED"
    outbox_event.processed_at = utc_now()
    db.flush()
    return created_notifications


def retry_delivery(
    db: Session,
    delivery: NotificationDelivery,
    email_provider: EmailProvider | None = None,
) -> bool:
    """Attempt a retry for a failed/retrying delivery record."""
    ep = email_provider or get_email_provider()
    notification = notif_repo.get_notification(db, str(delivery.notification_id))
    if notification is None:
        delivery.status = "FAILED"
        delivery.last_error = "Notification not found"
        db.flush()
        return False

    recipient = db.query(User).filter(User.id == notification.recipient_id).one_or_none()
    if recipient is None:
        delivery.status = "FAILED"
        delivery.last_error = "Recipient user not found"
        db.flush()
        return False

    delivery.attempts += 1
    try:
        success, msg_id, err = ep.deliver(notification, recipient, delivery)
        if success:
            delivery.status = "DELIVERED"
            delivery.delivered_at = utc_now()
            delivery.provider_message_id = msg_id
            delivery.last_error = None
            delivery.next_attempt_at = None
            audit_service.append_event(
                db,
                event_type="NOTIFICATION_DELIVERY_SUCCEEDED",
                action="deliver",
                resource_type="notification_deliveries",
                resource_id=delivery.id,
                actor_id=str(recipient.id),
                project_id=str(notification.project_id) if notification.project_id else None,
                payload={
                    "notification_id": notification.id,
                    "channel": delivery.channel,
                    "provider_message_id": msg_id,
                },
                source="notification_service",
            )
            db.flush()
            return True
        else:
            delivery.last_error = err
            if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
                delivery.status = "FAILED"
                delivery.next_attempt_at = None
            else:
                delivery.status = "RETRYING"
                delivery.next_attempt_at = compute_next_attempt(delivery.attempts)
            audit_service.append_event(
                db,
                event_type="NOTIFICATION_DELIVERY_FAILED",
                action="deliver_fail",
                resource_type="notification_deliveries",
                resource_id=delivery.id,
                actor_id=str(recipient.id),
                project_id=str(notification.project_id) if notification.project_id else None,
                payload={
                    "notification_id": notification.id,
                    "channel": delivery.channel,
                    "attempts": delivery.attempts,
                    "error": err,
                },
                source="notification_service",
            )
            db.flush()
            return False
    except Exception as exc:
        delivery.last_error = str(exc)
        if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
            delivery.status = "FAILED"
            delivery.next_attempt_at = None
        else:
            delivery.status = "RETRYING"
            delivery.next_attempt_at = compute_next_attempt(delivery.attempts)
        db.flush()
        return False

