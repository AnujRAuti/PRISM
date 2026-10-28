from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import Evidence
from backend.db.session import get_db
from backend.schemas.evidence import (
    EvidenceDownloadResponse,
    EvidenceResponse,
    EvidenceUploadResponse,
)
from backend.security.authorization import require
from backend.services.evidence_ingestion import ingest_evidence
from backend.services.storage import StorageService
from backend.services.authorization import Principal


router = APIRouter()


@router.post("/evidence", response_model=EvidenceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("evidence.create")),
) -> EvidenceUploadResponse:
    declared_type = (file.content_type or "").lower().strip()
    # Bounded read: one byte past the limit proves oversize without
    # loading arbitrarily large uploads into memory.
    data = await file.read(settings.max_upload_size + 1)
    evidence = ingest_evidence(data, file.filename or "unnamed", declared_type, db,
                               actor_id=principal.principal_id)
    return EvidenceUploadResponse(
        evidence_id=evidence.id,
        status="uploaded",
        storage_key=evidence.storage_key,
        content_type=evidence.content_type,
        size=evidence.file_size,
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=EvidenceResponse,
    summary="Retrieve evidence metadata (requires evidence.read)",
)
def get_evidence(
    evidence_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("evidence.read", "evidence", "evidence_id")),
) -> EvidenceResponse:
    evidence = db.query(Evidence).filter(Evidence.id == str(evidence_id)).one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return EvidenceResponse.model_validate(evidence)


@router.get(
    "/evidence/{evidence_id}/download",
    response_model=EvidenceDownloadResponse,
    summary="Issue a presigned download URL (requires evidence.read and "
            "evidence.read_sensitive)",
    description="This route releases the original bytes, so it demands the "
    "sensitive-evidence permission on top of the read permission that opens the "
    "metadata. 401 without credentials (enforcing mode). 403 without either "
    "permission. 404 when the evidence is absent or outside the caller's scope.",
)
def download_evidence(
    evidence_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require("evidence.read", "evidence", "evidence_id")),
    _: Principal = Depends(
        require("evidence.read_sensitive", "evidence", "evidence_id")),
) -> EvidenceDownloadResponse:
    evidence = db.query(Evidence).filter(Evidence.id == str(evidence_id)).one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    storage = StorageService()
    url = storage.create_presigned_download_url(
        storage.quarantine_bucket, evidence.storage_key)
    return EvidenceDownloadResponse(evidence_id=evidence_id, download_url=url)
