"""BE-026 Pydantic v2 schemas for field operations and offline synchronization.

Vocabulary stays explicit: ``sync_status`` is the task §11 response vocabulary
and is deliberately wider than the persisted ``FieldOperationStatus`` (a denial
never mutates domain state, and a dependency outage rolls back). Nothing here
accepts an authorization claim: no ``project_id``, ``organization_id``,
``role``, or ``assignment`` field exists on the synchronization surface, so the
server resolves every scope from its own rows.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FieldAssignmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class FieldSessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"


class FieldOperationStatus(str, Enum):
    #: Internal reservation only; never a response value (see Stage B §6).
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT = "CONFLICT"


class FieldConflictReason(str, Enum):
    PAYLOAD_MISMATCH = "PAYLOAD_MISMATCH"
    ASSIGNMENT_REVOKED = "ASSIGNMENT_REVOKED"
    ASSIGNMENT_EXPIRED = "ASSIGNMENT_EXPIRED"
    SESSION_CLOSED = "SESSION_CLOSED"
    OPERATION_SESSION_MISMATCH = "OPERATION_SESSION_MISMATCH"
    CONTEXT_RESOURCE_MISSING = "CONTEXT_RESOURCE_MISSING"
    ASSIGNMENT_SUPERSEDED = "ASSIGNMENT_SUPERSEDED"


class FieldLocationSource(str, Enum):
    DEVICE_GPS = "DEVICE_GPS"
    DEVICE_MANUAL = "DEVICE_MANUAL"
    CLIENT_INFERRED = "CLIENT_INFERRED"
    UNKNOWN = "UNKNOWN"


class FieldResolutionStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"


class FieldResolutionOutcome(str, Enum):
    DISMISSED = "DISMISSED"
    RESUBMISSION_REQUIRED = "RESUBMISSION_REQUIRED"


class FieldSyncStatus(str, Enum):
    ACCEPTED = "accepted"
    ALREADY_SYNCHRONIZED = "already_synchronized"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    AUTHORIZATION_DENIED = "authorization_denied"
    VALIDATION_FAILED = "validation_failed"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class FieldAssignmentCloseStatus(str, Enum):
    """The only transitions a manager may request; ``EXPIRED`` is server-set."""

    RELEASED = "RELEASED"
    REVOKED = "REVOKED"


# ---------------------------------------------------------------------------
# requests
# ---------------------------------------------------------------------------

class FieldAssignmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    project_id: UUID
    claim_id: UUID | None = None
    activity_id: UUID | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    instructions: str | None = Field(default=None, max_length=4000)


class FieldAssignmentStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FieldAssignmentCloseStatus
    reason: str = Field(min_length=1, max_length=255)


class FieldSessionOpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: UUID
    session_label: str | None = Field(default=None, max_length=128)
    client_device_id: str | None = Field(default=None, max_length=128)


class FieldSessionCloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=255)


class FieldConflictResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: FieldResolutionOutcome
    note: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# responses
# ---------------------------------------------------------------------------

class FieldAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    project_id: UUID
    organization_id: UUID | None = None
    organizational_unit_id: UUID | None = None
    claim_id: UUID | None = None
    activity_id: UUID | None = None
    status: str
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    instructions: str | None = None
    created_by: UUID | None = None
    revoked_by: UUID | None = None
    revoked_at: datetime | None = None
    closed_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FieldAssignmentListResponse(BaseModel):
    items: list[FieldAssignmentResponse]
    total: int
    limit: int
    offset: int


class FieldSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assignment_id: UUID
    user_id: UUID
    project_id: UUID
    organization_id: UUID | None = None
    status: str
    session_label: str | None = None
    client_device_id: str | None = None
    started_at: datetime | None = None
    server_time_at_open: datetime | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None
    last_sync_at: datetime | None = None
    created_at: datetime | None = None


class FieldLocationReport(BaseModel):
    """Client-reported fix as assertion data.

    ``reported`` is false whenever no coordinates were supplied, so a missing
    fix is never representable as ``0,0``; PostGIS on Evidence stays the only
    authoritative location.
    """

    reported: bool
    latitude: float | None = None
    longitude: float | None = None
    capture_accuracy_m: float | None = None
    altitude_m: float | None = None
    location_source: str | None = None
    zero_island_confirmed: bool = False


class FieldCaptureOperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    client_operation_id: str
    client_capture_id: str | None = None
    client_device_id: str | None = None
    session_id: UUID | None = None
    assignment_id: UUID | None = None
    project_id: UUID | None = None
    claim_id: UUID | None = None
    evidence_id: UUID | None = None
    status: str
    resolution_status: str
    resolution_outcome: str | None = None
    resolved_by: UUID | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    conflict_reason: str | None = None
    conflict_detail: dict | None = None
    validation_errors: list[str] = Field(default_factory=list)
    timestamp_flags: list[str] = Field(default_factory=list)
    captured_at: datetime | None = None
    queued_at: datetime | None = None
    uploaded_at: datetime | None = None
    received_at: datetime | None = None
    processed_at: datetime | None = None
    filename: str | None = None
    declared_content_type: str | None = None
    file_size: int
    payload_sha256: str
    request_hash: str
    location_source: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    capture_accuracy_m: float | None = None
    altitude_m: float | None = None
    zero_island_confirmed: bool = False
    sync_count: int
    last_synced_at: datetime | None = None
    created_at: datetime | None = None


class FieldOperationListResponse(BaseModel):
    items: list[FieldCaptureOperationResponse]
    total: int
    limit: int
    offset: int


class FieldSyncResponse(BaseModel):
    """Synchronization outcome for one capture.

    ``captured_at``/``queued_at``/``uploaded_at`` echo exactly what the client
    reported (or ``None`` when it never knew), while ``received_at`` and
    ``processed_at`` are server-observed. No field is ever derived from
    another.
    """

    sync_status: FieldSyncStatus
    operation_id: UUID
    client_operation_id: str
    status: FieldOperationStatus
    evidence_id: UUID | None = None
    evidence_status: str | None = None
    project_id: UUID | None = None
    claim_id: UUID | None = None
    session_id: UUID | None = None
    assignment_id: UUID | None = None
    conflict_reason: FieldConflictReason | None = None
    validation_errors: list[str] = Field(default_factory=list)
    timestamp_flags: list[str] = Field(default_factory=list)
    captured_at: datetime | None = None
    queued_at: datetime | None = None
    uploaded_at: datetime | None = None
    received_at: datetime | None = None
    processed_at: datetime | None = None
    location: FieldLocationReport
    file_size: int
    sync_count: int
    message: str


class WorkProject(BaseModel):
    id: UUID
    name: str


class WorkClaim(BaseModel):
    id: UUID
    title: str


class WorkActivity(BaseModel):
    id: UUID
    verb: str
    created_at: datetime | None = None


class FieldWorkItem(BaseModel):
    """One assigned task, with only the context that assignment names."""

    assignment_id: UUID
    status: str
    project: WorkProject
    organization_id: UUID | None = None
    valid_from: datetime | None = None
    expires_at: datetime | None = None
    instructions: str | None = None
    active_session_id: UUID | None = None
    claim: WorkClaim | None = None
    activity: WorkActivity | None = None


class FieldWorkListResponse(BaseModel):
    items: list[FieldWorkItem]
    total: int
    limit: int
    offset: int
