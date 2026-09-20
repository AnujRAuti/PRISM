from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.session import get_db
from backend.schemas.evidence import EvidenceUploadResponse
from backend.services.evidence_ingestion import ingest_evidence


router = APIRouter()


@router.post("/evidence", response_model=EvidenceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> EvidenceUploadResponse:
    declared_type = (file.content_type or "").lower().strip()
    # Bounded read: one byte past the limit proves oversize without
    # loading arbitrarily large uploads into memory.
    data = await file.read(settings.max_upload_size + 1)
    evidence = ingest_evidence(data, file.filename or "unnamed", declared_type, db)
    return EvidenceUploadResponse(
        evidence_id=evidence.id,
        status="uploaded",
        storage_key=evidence.storage_key,
        content_type=evidence.content_type,
        size=evidence.file_size,
    )
