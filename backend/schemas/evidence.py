from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidenceUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    status: str
    storage_key: str
    content_type: str
    size: int


class EvidenceResponse(BaseModel):
    """Evidence metadata (no storage keys, no binaries, no EXIF payload)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    claim_id: UUID | None = None
    filename: str
    content_type: str | None = None
    file_size: int
    status: str
    created_at: datetime | None = None


class EvidenceDownloadResponse(BaseModel):
    evidence_id: UUID
    download_url: str = Field(description="Short-lived presigned URL issued after authorization")
    expires_in: int = 900