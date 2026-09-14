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
CONTENT_TYPE_MAP = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _match_image_content_type(data: bytes, declared_type: str | None) -> str:
    signature_type = _detect_signature_content_type(data)
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            actual_type = CONTENT_TYPE_MAP.get(image.format.upper())
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(status_code=415, detail="Uploaded file is not a valid image") from error

    if actual_type is None:
        raise HTTPException(status_code=415, detail="Uploaded file is not a supported image type")
    if signature_type is not None and signature_type != actual_type:
        raise HTTPException(
            status_code=415,
            detail=f"Image signature mismatch: declared Content-Type {declared_type} does not match actual file content {actual_type}",
        )
    if declared_type is not None and declared_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported image content type")
    if declared_type is not None and declared_type != actual_type:
        raise HTTPException(
            status_code=415,
            detail=f"Content-Type mismatch: declared {declared_type} but actual file is {actual_type}",
        )
    return actual_type


def _detect_signature_content_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/evidence", response_model=EvidenceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> EvidenceUploadResponse:
    declared_type = (file.content_type or "").lower().strip()
    if declared_type and declared_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported image content type")

    data = await file.read(settings.max_upload_size + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    actual_type = _match_image_content_type(data, declared_type)
    if declared_type and declared_type != actual_type:
        raise HTTPException(
            status_code=415,
            detail=f"Content-Type mismatch: declared {declared_type} but actual file is {actual_type}",
        )

    evidence_id = str(uuid4())
    storage = StorageService()
    storage_key = storage.quarantine_key(evidence_id)
    filename = file.filename or "unnamed"

    try:
        storage.put_object(
            storage.quarantine_bucket,
            storage_key,
            data,
            content_type=actual_type,
        )
        evidence = Evidence(
            id=evidence_id,
            filename=filename,
            content_type=actual_type,
            storage_key=storage_key,
            file_size=len(data),
            status="uploaded_quarantine",
        )
        db.add(evidence)
        db.commit()
    except (StorageError, Exception):
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
        content_type=actual_type,
        size=len(data),
    )