from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnalysisJobCreate(BaseModel):
    evidence_id: str


class AnalysisJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    evidence_id: str
    status: str
    attempt_count: int
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict | None = None