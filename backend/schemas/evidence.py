from pydantic import BaseModel, ConfigDict


class EvidenceUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: str
    status: str
    storage_key: str
    content_type: str
    size: int