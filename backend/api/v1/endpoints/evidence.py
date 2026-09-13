from io import BytesIO
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import Evidence
from backend.db.session import get_db
from backend.schemas.evidence import EvidenceUploadResponse
from backend.services.storage import StorageError, StorageService


router = APIRouter()
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/evidence", response_model=EvidenceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> EvidenceUploadResponse:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported image content type")

    data = await file.read(settings.max_upload_size + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=415, detail="Uploaded file is not a valid image")

    evidence_id = str(uuid4())
    storage = StorageService()
    storage_key = storage.quarantine_key(evidence_id)
    filename = file.filename or "unnamed"

    try:
        storage.put_object(
            storage.quarantine_bucket,
            storage_key,
            data,
            content_type=file.content_type,
        )
        evidence = Evidence(
            id=evidence_id,
            filename=filename,
            content_type=file.content_type,
            storage_key=storage_key,
            file_size=len(data),
            status="uploaded_quarantine",
        )
        db.add(evidence)
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.delete_object(storage.quarantine_bucket, storage_key)
        except StorageError:
            pass
        raise

    return EvidenceUploadResponse(
        evidence_id=evidence_id,
        status="uploaded",
        storage_key=storage_key,
        content_type=file.content_type,
        size=len(data),
    )