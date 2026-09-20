"""BE-014 Pydantic v2 schemas for evidence requests.

A request asks for evidence during an investigation. Fulfillment never
implies truth, support, or contradiction, and requested evidence enters
the standard ingestion pipeline untrusted.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RequestStatus(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FULFILLED = "FULFILLED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class RequestPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class RequestItemStatus(str, Enum):
    REQUESTED = "REQUESTED"
    RECEIVED = "RECEIVED"
    ACCEPTED_FOR_REQUEST = "ACCEPTED_FOR_REQUEST"
    REJECTED_FOR_REQUEST = "REJECTED_FOR_REQUEST"


class EvidenceRequestItemCreate(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    required: bool = True


class EvidenceRequestCreate(BaseModel):
    review_case_id: UUID
    recipient_id: UUID
    instructions: str = Field(min_length=1, max_length=8000)
    items: list[EvidenceRequestItemCreate] = Field(min_length=1, max_length=50)
    requester_id: UUID | None = None
    due_at: AwareDatetime | None = Field(
        default=None, description="Timezone-aware deadline; naive timestamps rejected"
    )
    priority: RequestPriority = RequestPriority.NORMAL
    project_id: UUID | None = None
    activity_id: UUID | None = None
    claim_id: UUID | None = None
    evidence_id: UUID | None = None
    issue: bool = Field(default=True, description="False keeps the request in DRAFT")


class EvidenceRequestItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str | None = None
    required: bool
    evidence_id: UUID | None = None
    item_status: RequestItemStatus
    linked_by: UUID | None = None
    notes: str | None = None


class EvidenceRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    review_case_id: UUID | None = None
    project_id: UUID | None = None
    activity_id: UUID | None = None
    claim_id: UUID | None = None
    evidence_id: UUID | None = None
    requester_id: UUID | None = None
    recipient_id: UUID | None = None
    instructions: str
    due_at: datetime | None = None
    priority: RequestPriority
    status: RequestStatus
    items: list[EvidenceRequestItemResponse] = Field(default_factory=list)


class EvidenceRequestListResponse(BaseModel):
    items: list[EvidenceRequestResponse]
    limit: int
    offset: int
    total: int


class EvidenceRequestEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    from_status: RequestStatus | None = None
    to_status: RequestStatus | None = None
    actor_id: UUID | None = None
    created_at: str | None = None


class EvidenceRequestHistoryResponse(BaseModel):
    request_id: UUID
    items: list[EvidenceRequestEventItem]
    total: int


class EvidenceRequestDeclineRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    actor_id: UUID | None = None


class EvidenceRequestLinkResponse(BaseModel):
    item: EvidenceRequestItemResponse
    created: bool = Field(description="False when the link already existed (idempotent)")
    request_status: RequestStatus


class EvidenceRequestResponseAction(BaseModel):
    actor_id: UUID | None = None
