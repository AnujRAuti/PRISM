"""Shared evidence ingestion pipeline (BE-003 logic, reused by BE-014).

This module holds the exact validation/storage/persistence flow originally
implemented in the evidence upload endpoint: bounded reads happen at the
caller, while MIME/signature/Pillow validation, quarantine storage, and
database persistence with failure cleanup live here. Both the public
``POST /api/v1/evidence`` endpoint and evidence-request submissions call
this service, so requested evidence enters the identical pipeline —
validation, quarantine, and analysis eligibility — as any other evidence.

Nothing here trusts a submission source: requested evidence is validated
exactly like direct uploads and is never marked trusted or true.
"""

from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import Evidence
from backend.services import audit_ledger as audit_service
from backend.services.storage import StorageError, StorageService


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
CONTENT_TYPE_MAP = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def detect_signature_content_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def match_image_content_type(data: bytes, declared_type: str | None) -> str:
    signature_type = detect_signature_content_type(data)
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            image.verify()
        actual_type = CONTENT_TYPE_MAP.get(image_format)
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


def ingest_evidence(
    data: bytes,
    filename: str,
    declared_type: str | None,
    db: Session,
    storage: StorageService | None = None,
    actor_id: str | None = None,
) -> Evidence:
    """Validate, quarantine-store, and persist one evidence image.

    Raises HTTPException (400/413/415) for invalid uploads and propagates
    storage/database failures without claiming success. Returns the
    persisted ``Evidence`` row (committed).

    ``actor_id`` is the verified caller's principal id, never a request-body
    field; it stays NULL only where the caller genuinely holds no credential.
    """
    if declared_type and declared_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported image content type")
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    actual_type = match_image_content_type(data, declared_type)

    evidence_id = str(uuid4())
    storage = storage or StorageService()
    storage_key = storage.quarantine_key(evidence_id)

    try:
        storage.put_object(
            storage.quarantine_bucket,
            storage_key,
            data,
            content_type=actual_type,
        )
        evidence = Evidence(
            id=evidence_id,
            filename=filename or "unnamed",
            content_type=actual_type,
            storage_key=storage_key,
            file_size=len(data),
            status="uploaded_quarantine",
        )
        db.add(evidence)
        # The audit twin commits in the same transaction: a failed commit
        # rolls back both rows, so success is never reported without proof.
        audit_service.append_event(
            db,
            event_type="EVIDENCE_UPLOADED",
            action="upload",
            resource_type="evidence",
            resource_id=evidence_id,
            actor_id=actor_id,
            project_id=None,
            payload={"evidence_id": evidence_id, "filename": evidence.filename,
                     "content_type": actual_type, "file_size": len(data)},
            source="evidence_ingestion_service",
        )
        db.commit()
    except StorageError:
        # Storage failed: no Evidence row was committed; report the failure
        # without claiming the upload succeeded.
        db.rollback()
        try:
            storage.delete_object(storage.quarantine_bucket, storage_key)
        except StorageError:
            pass
        raise
    except SQLAlchemyError:
        # Database persistence failed after (or before) the object landed in
        # quarantine: roll back and remove the orphaned object best-effort.
        db.rollback()
        try:
            storage.delete_object(storage.quarantine_bucket, storage_key)
        except StorageError:
            pass
        raise
    db.refresh(evidence)
    return evidence
