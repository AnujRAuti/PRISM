from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    owner_id: UUID


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner_id: UUID
    created_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    limit: int
    offset: int
    total: int


class ActivityCreate(BaseModel):
    actor_id: UUID | None = Field(
        default=None,
        description="Must equal the authenticated user principal; the actor is derived "
                    "from the credential. API clients record no actor, because "
                    "activities.actor_id references users.",
    )
    verb: str = Field(min_length=1, max_length=128)
    details: dict | None = None


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    actor_id: UUID | None
    verb: str
    details: dict | None
    created_at: datetime


class ActivityListResponse(BaseModel):
    items: list[ActivityResponse]
    limit: int
    offset: int
    total: int


class ClaimCreate(BaseModel):
    claimant_id: UUID | None = None
    title: str = Field(min_length=1, max_length=512)
    description: str | None = None
    temporal_start_at: datetime | None = None
    temporal_end_at: datetime | None = None


class ClaimUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    temporal_start_at: datetime | None = None
    temporal_end_at: datetime | None = None


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    claimant_id: UUID | None
    title: str
    description: str | None
    temporal_start_at: datetime | None = None
    temporal_end_at: datetime | None = None
    created_at: datetime


class ClaimListResponse(BaseModel):
    items: list[ClaimResponse]
    limit: int
    offset: int
    total: int


class EvidenceContextUpdate(BaseModel):
    project_id: UUID
    claim_id: UUID | None = None


class EvidenceContextResponse(BaseModel):
    evidence_id: UUID
    project_id: UUID | None
    claim_id: UUID | None


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class LocationResponse(BaseModel):
    evidence_id: UUID
    location: dict[str, float]


class NearbyEvidenceItem(BaseModel):
    evidence_id: UUID
    project_id: UUID | None
    claim_id: UUID | None
    latitude: float
    longitude: float
    distance_meters: float


class NearbyEvidenceResponse(BaseModel):
    items: list[NearbyEvidenceItem]
    limit: int
    offset: int
    total: int