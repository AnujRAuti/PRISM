"""BE-022 Pydantic v2 schemas for publication governance.

These are EXPLICIT public projections (§5). Internal ORM objects are never
serialized directly as public responses, so every public schema below is
built from an allowlisted field set and can carry no storage key, EXIF,
internal ID, or reviewer-only data.
"""

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PublicationTargetType(str, Enum):
    PROJECT = "PROJECT"
    ACTIVITY = "ACTIVITY"
    CLAIM = "CLAIM"
    EVIDENCE = "EVIDENCE"
    REVIEW_CASE = "REVIEW_CASE"
    FUSION_ASSESSMENT = "FUSION_ASSESSMENT"


class PublicationStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    UNPUBLISHED = "UNPUBLISHED"
    REJECTED = "REJECTED"


class PublicationBlocker(str, Enum):
    """§11 structured releasability blockers (never collapsed to NOT_ALLOWED)."""

    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_PUBLISHABLE_TYPE = "NOT_PUBLISHABLE_TYPE"
    PRIVATE_VISIBILITY = "PRIVATE_VISIBILITY"
    ACTIVE_DISPUTE = "ACTIVE_DISPUTE"
    UNRESOLVED_CORRECTION = "UNRESOLVED_CORRECTION"
    RETENTION_RESTRICTION = "RETENTION_RESTRICTION"
    LEGAL_HOLD = "LEGAL_HOLD"
    MISSING_REQUIRED_APPROVAL = "MISSING_REQUIRED_APPROVAL"
    SENSITIVE_DATA_PRESENT = "SENSITIVE_DATA_PRESENT"
    SOURCE_RESTRICTION = "SOURCE_RESTRICTION"
    UNAVAILABLE_PUBLIC_DERIVATIVE = "UNAVAILABLE_PUBLIC_DERIVATIVE"


class LocationPrecision(str, Enum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    AREA = "AREA"
    HIDDEN = "HIDDEN"


class RedactionLevel(str, Enum):
    NONE = "NONE"
    STANDARD = "STANDARD"
    STRICT = "STRICT"


class PublicationAuthorizationLevel(str, Enum):
    REVIEWER = "REVIEWER"
    SUPERVISOR = "SUPERVISOR"
    ADMINISTRATOR = "ADMINISTRATOR"


# ---------------------------------------------------------------------------
# Policy (§9)
# ---------------------------------------------------------------------------


class PublicationPolicyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    version: str = Field(default="1.0", pattern=r"^\d+\.\d+$")
    allowed_target_types: List[PublicationTargetType]
    public_fields: List[str] = Field(default_factory=list)
    prohibited_fields: List[str] = Field(default_factory=list)
    allow_media_exposure: bool = False
    allow_derived_intelligence: bool = False
    allow_review_outcomes: bool = False
    min_authorization_level: PublicationAuthorizationLevel = PublicationAuthorizationLevel.REVIEWER
    required_approvals: int = Field(default=1, ge=1)
    require_separation_of_duties: bool = True
    location_precision: LocationPrecision = LocationPrecision.HIDDEN
    retention_publication_duration_days: Optional[int] = Field(default=None, ge=1)
    geographic_restrictions: Optional[dict[str, Any]] = None
    privacy_restrictions: Optional[dict[str, Any]] = None
    redaction_level: RedactionLevel = RedactionLevel.STANDARD


class PublicationPolicyResponse(BaseModel):
    """Policy identity plus its rules. Administrative surface (internal)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    version: str
    status: str
    allowed_target_types: List[str]
    public_fields: List[str]
    prohibited_fields: List[str]
    allow_media_exposure: bool
    allow_derived_intelligence: bool
    allow_review_outcomes: bool
    min_authorization_level: str
    required_approvals: int
    require_separation_of_duties: bool
    location_precision: str
    retention_publication_duration_days: Optional[int] = None
    geographic_restrictions: Optional[dict[str, Any]] = None
    privacy_restrictions: Optional[dict[str, Any]] = None
    redaction_level: str
    created_at: Optional[datetime] = None


class PublicationPolicyListResponse(BaseModel):
    items: List[PublicationPolicyResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Publication workflow (§6, §7)
# ---------------------------------------------------------------------------


class PublicationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: PublicationTargetType
    target_id: UUID
    policy_id: UUID
    reason: str = Field(min_length=1)


class PublicationResponse(BaseModel):
    """Internal publication view (not the public projection)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    public_id: Optional[str] = None
    current_version_number: int
    status: PublicationStatus
    requested_by: UUID
    reviewer_id: Optional[UUID] = None
    approver_id: Optional[UUID] = None
    publisher_id: Optional[UUID] = None
    reason: str
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    unpublished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PublicationListResponse(BaseModel):
    items: List[PublicationResponse]
    total: int
    limit: int
    offset: int


class PublicationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    publication_id: UUID
    event_type: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    actor_id: Optional[UUID] = None
    reason: Optional[str] = None
    created_at: Optional[datetime] = None


class PublicationHistoryResponse(BaseModel):
    publication_id: UUID
    events: List[PublicationEventResponse]
    total: int


class PublicationVersionResponse(BaseModel):
    """Immutable historical version (internal retrieval, §7)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    publication_id: UUID
    version_number: int
    public_id: str
    target_type: str
    target_id: UUID
    status: str
    snapshot: dict[str, Any]
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    unpublished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Eligibility (§11)
# ---------------------------------------------------------------------------


class EligibilityBlocker(BaseModel):
    code: PublicationBlocker
    detail: Optional[str] = None


class EligibilityResponse(BaseModel):
    publication_id: UUID
    eligible: bool
    blockers: List[EligibilityBlocker] = Field(default_factory=list)
    evaluated_at: Optional[datetime] = None
    policy_version: Optional[str] = None


# ---------------------------------------------------------------------------
# Public projections (§5, §17)
# ---------------------------------------------------------------------------
# These schemas are the ONLY public surface. They intentionally contain no
# internal UUID, storage key, EXIF, reviewer identity, or internal signal.


class PublicProvenance(BaseModel):
    """§25 public-safe provenance: no credentials, workers, or audit payloads."""

    publication_version: int
    source_category: Optional[str] = None
    published_at: Optional[datetime] = None
    human_approval_status: Optional[str] = None
    evidence_collection_date: Optional[datetime] = None


class PublicProjectResponse(BaseModel):
    public_id: str
    name: str
    description: Optional[str] = None
    status: str


class PublicProjectDetailResponse(BaseModel):
    public_id: str
    name: str
    description: Optional[str] = None
    status: str
    published_at: Optional[datetime] = None
    provenance: Optional[PublicProvenance] = None


class PublicActivityResponse(BaseModel):
    public_id: str
    verb: str
    # Never the internal actor_id; public activities are actor-free by default.
    occurred_at: Optional[datetime] = None


class PublicClaimResponse(BaseModel):
    """§23: public claims expose the approved statement and safe dates only."""

    public_id: str
    public_project_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    temporal_start_at: Optional[datetime] = None
    temporal_end_at: Optional[datetime] = None
    status: str


class PublicMediaResponse(BaseModel):
    """§19: media is served by public ID; the storage key is never exposed."""

    public_id: str
    derivative_type: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None


class PublicEvidenceResponse(BaseModel):
    public_id: str
    public_project_id: Optional[str] = None
    status: str
    collected_at: Optional[datetime] = None
    media: List[PublicMediaResponse] = Field(default_factory=list)


class PublicEvidenceDetailResponse(PublicEvidenceResponse):
    filename: Optional[str] = None
    # §22 location privacy: public output carries a precision-reduced value or
    # a coarse area label, never a raw private coordinate pair.
    location_area: Optional[str] = None
    location_precision: str = LocationPrecision.HIDDEN.value
    provenance: Optional[PublicProvenance] = None


class PublicPublicationResponse(BaseModel):
    """§17: the PUBLISHED version snapshot is the source of truth."""

    public_id: str
    target_type: str
    version_number: int
    status: str
    published_at: Optional[datetime] = None
    provenance: Optional[PublicProvenance] = None
    content: dict[str, Any] = Field(default_factory=dict)
