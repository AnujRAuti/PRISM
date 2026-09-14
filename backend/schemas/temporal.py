from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TemporalRequest(BaseModel):
    compare_evidence_ids: list[UUID] | None = None


class TemporalRelationship(BaseModel):
    other_evidence_id: UUID
    relationship: str


class TemporalAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: UUID
    captured_at: str | None = None
    captured_source: str | None = None
    captured_tz_known: bool = False
    uploaded_at: str | None = None
    capture_upload: str
    claim_id: UUID | None = None
    claim_window: str
    relationships: list[TemporalRelationship] = []
    time_differences: list[dict] = []
    inconsistencies: list[dict] = []
    status: str
