"""BE-018 Pydantic schemas for notifications, delivery, and preferences."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationType(str, Enum):
    REVIEW_CASE_ASSIGNED = "REVIEW_CASE_ASSIGNED"
    REVIEW_CASE_ESCALATED = "REVIEW_CASE_ESCALATED"
    REVIEW_CASE_DECISION_PENDING = "REVIEW_CASE_DECISION_PENDING"
    REVIEW_CASE_REOPENED = "REVIEW_CASE_REOPENED"
    EVIDENCE_REQUEST_ISSUED = "EVIDENCE_REQUEST_ISSUED"
    EVIDENCE_REQUEST_ACKNOWLEDGED = "EVIDENCE_REQUEST_ACKNOWLEDGED"
    EVIDENCE_REQUEST_PARTIALLY_FULFILLED = "EVIDENCE_REQUEST_PARTIALLY_FULFILLED"
    EVIDENCE_REQUEST_FULFILLED = "EVIDENCE_REQUEST_FULFILLED"
    EVIDENCE_REQUEST_DECLINED = "EVIDENCE_REQUEST_DECLINED"
    EVIDENCE_REQUEST_EXPIRED = "EVIDENCE_REQUEST_EXPIRED"
    RETENTION_HOLD_CREATED = "RETENTION_HOLD_CREATED"
    RETENTION_HOLD_RELEASED = "RETENTION_HOLD_RELEASED"
    SYSTEM_SECURITY_EVENT = "SYSTEM_SECURITY_EVENT"


class NotificationStatus(str, Enum):
    UNREAD = "UNREAD"
    READ = "READ"


class NotificationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class NotificationChannel(str, Enum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Notification schemas
# ---------------------------------------------------------------------------


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recipient_id: str
    organization_id: str | None = None
    project_id: str | None = None
    notification_type: str
    title: str
    body: str
    resource_type: str | None = None
    resource_id: str | None = None
    severity: str
    status: str
    read_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkReadResponse(BaseModel):
    notification_id: str
    status: str
    read_at: datetime


class ReadAllResponse(BaseModel):
    marked_read_count: int


# ---------------------------------------------------------------------------
# Delivery schemas
# ---------------------------------------------------------------------------


class NotificationDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    notification_id: str
    channel: str
    status: str
    attempts: int
    provider: str
    provider_message_id: str | None = None
    last_error: str | None = None
    next_attempt_at: datetime | None = None
    created_at: datetime
    delivered_at: datetime | None = None


class NotificationDeliveryListResponse(BaseModel):
    items: list[NotificationDeliveryResponse]


# ---------------------------------------------------------------------------
# Preferences schemas
# ---------------------------------------------------------------------------


class NotificationPreferenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_type: str
    in_app_enabled: bool = True
    email_enabled: bool = True
    updated_at: datetime | None = None


class NotificationPreferencesResponse(BaseModel):
    preferences: list[NotificationPreferenceItem]


class NotificationPreferenceUpdate(BaseModel):
    in_app_enabled: bool | None = None
    email_enabled: bool | None = None


class NotificationPreferenceBulkUpdate(BaseModel):
    preferences: dict[str, NotificationPreferenceUpdate]


# ---------------------------------------------------------------------------
# Outbox schemas
# ---------------------------------------------------------------------------


class NotificationOutboxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any]
    status: str
    attempts: int
    created_at: datetime
    processed_at: datetime | None = None
    last_error: str | None = None

