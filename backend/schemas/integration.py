"""BE-019 Pydantic schemas for external integrations and API client platform."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# External Systems
# ---------------------------------------------------------------------------


class ExternalSystemCreate(BaseModel):
    name: str
    code: str
    system_type: str
    organization_id: UUID | None = None
    description: str | None = None
    metadata: dict[str, Any] = {}

    @field_validator("system_type")
    @classmethod
    def validate_system_type(cls, v: str) -> str:
        valid = {
            "GOVERNMENT_PORTAL", "FIELD_SYSTEM", "PROJECT_MANAGEMENT",
            "DOCUMENT_SYSTEM", "INSPECTION_SYSTEM", "DATA_PLATFORM", "OTHER",
        }
        if v not in valid:
            raise ValueError(f"system_type must be one of {valid}")
        return v


class ExternalSystemResponse(BaseModel):
    id: UUID
    organization_id: UUID | None
    name: str
    code: str
    system_type: str
    status: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# API Clients
# ---------------------------------------------------------------------------


class ApiClientCreate(BaseModel):
    name: str
    external_system_id: UUID | None = None
    project_id: UUID | None = None
    scopes: list[str] = []


class ApiClientResponse(BaseModel):
    id: UUID
    name: str
    scopes: list[str]
    project_id: UUID | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# API Credentials
# ---------------------------------------------------------------------------


class ApiCredentialResponse(BaseModel):
    """Returned on creation only. secret is shown once; never stored plaintext."""

    credential_id: UUID
    client_id: UUID
    secret: str | None = None  # present only on creation
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiCredentialInfo(BaseModel):
    """Public credential metadata (no secret)."""

    credential_id: UUID
    client_id: UUID
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# External References
# ---------------------------------------------------------------------------


class ExternalReferenceCreate(BaseModel):
    external_system_id: UUID
    resource_type: str
    resource_id: UUID
    external_id: str
    external_version: str | None = None

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("external_id must not be empty")
        if len(v) > 512:
            raise ValueError("external_id must not exceed 512 characters")
        return v.strip()


class ExternalReferenceResponse(BaseModel):
    id: UUID
    external_system_id: UUID
    resource_type: str
    resource_id: UUID
    external_id: str
    external_version: str | None
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# External Assertions
# ---------------------------------------------------------------------------


class ExternalAssertionCreate(BaseModel):
    external_system_id: UUID
    resource_type: str | None = None
    resource_id: UUID | None = None
    external_id: str | None = None
    source_timestamp: datetime | None = None
    payload: dict[str, Any]

    @field_validator("source_timestamp")
    @classmethod
    def must_be_tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("source_timestamp must be timezone-aware")
        return v


class ExternalAssertionResponse(BaseModel):
    id: UUID
    external_system_id: UUID
    resource_type: str | None
    resource_id: UUID | None
    external_id: str | None
    source_timestamp: datetime | None
    ingested_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class IdempotencyResult(BaseModel):
    outcome: str  # NEW | REPLAY | CONFLICT
    result_payload: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


class WebhookSubscriptionCreate(BaseModel):
    external_system_id: UUID
    endpoint_url: str
    subscribed_events: list[str]

    @field_validator("subscribed_events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        valid = {
            "review_case.created", "review_case.assigned", "review_case.escalated",
            "review_case.resolved", "evidence_request.issued", "evidence_request.fulfilled",
            "evidence_request.declined", "evidence_request.expired", "fusion.completed",
            "retention.archived", "retention.deleted",
        }
        bad = set(v) - valid
        if bad:
            raise ValueError(f"Unknown event types: {bad}")
        return v


class WebhookSubscriptionUpdate(BaseModel):
    status: str | None = None
    subscribed_events: list[str] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("ACTIVE", "SUSPENDED", "DISABLED"):
            raise ValueError("status must be ACTIVE, SUSPENDED, or DISABLED")
        return v


class WebhookSubscriptionResponse(BaseModel):
    id: UUID
    external_system_id: UUID
    endpoint_url: str
    status: str
    subscribed_events: list[str]
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime
    last_delivery_at: datetime | None

    model_config = {"from_attributes": True}


class WebhookEventResponse(BaseModel):
    id: UUID
    event_type: str
    event_version: int
    aggregate_type: str
    aggregate_id: UUID
    project_id: UUID | None
    status: str
    occurred_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Integration Events
# ---------------------------------------------------------------------------


class IntegrationEventResponse(BaseModel):
    id: UUID
    event_type: str
    event_version: int
    aggregate_type: str
    aggregate_id: UUID
    project_id: UUID | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# External Evidence & Claim Submission
# ---------------------------------------------------------------------------


class ExternalEvidenceSubmit(BaseModel):
    """Provenance metadata for external evidence submission (file sent as multipart)."""

    external_system_id: UUID
    external_evidence_id: str | None = None
    external_project_id: str | None = None
    external_activity_id: str | None = None
    external_claim_id: str | None = None
    source_timestamp: datetime | None = None
    idempotency_key: str | None = None

    @field_validator("source_timestamp")
    @classmethod
    def must_be_tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("source_timestamp must be timezone-aware")
        return v


class ExternalClaimImport(BaseModel):
    """Import an external claim assertion preserving provenance."""

    external_system_id: UUID
    external_reference: str
    claim_type: str
    subject_type: str
    subject_id: UUID
    assertion: dict[str, Any]
    source_timestamp: datetime | None = None
    idempotency_key: str | None = None

    @field_validator("source_timestamp")
    @classmethod
    def must_be_tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("source_timestamp must be timezone-aware")
        return v

