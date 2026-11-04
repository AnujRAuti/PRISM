from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import Evidence, EvidenceMetadata
from backend.engines.hashing.perceptual import perceptual_hash
from backend.engines.hashing.sha256 import sha256_digest
from backend.engines.metadata.exif import extract_exif
from backend.services.storage import StorageService


@dataclass(frozen=True)
class FingerprintResult:
    sha256: str
    phash: str | None
    exif: dict[str, Any]
    exif_status: str
    exif_error: str | None = None
    phash_error: str | None = None


def process_evidence(
    evidence_id: str,
    db: Session,
    storage: StorageService | None = None,
) -> FingerprintResult:
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one()
    storage = storage or StorageService()
    data = storage.get_object_bytes(storage.quarantine_bucket, evidence.storage_key)

    digest = sha256_digest(data)
    exif: dict[str, Any] = {}
    exif_status = "success"
    exif_error = None
    try:
        exif = extract_exif(data)
        if not exif:
            exif_status = "no_metadata"
    except Exception as error:
        exif_status = "failed"
        exif_error = str(error)

    phash_value = None
    phash_error = None
    try:
        phash_value = perceptual_hash(data)
    except Exception as error:
        phash_error = str(error)

    evidence.sha256 = digest
    evidence.phash = phash_value
    metadata = db.query(EvidenceMetadata).filter_by(evidence_id=evidence_id).one_or_none()
    metadata_json = {
        "exif": exif,
        "exif_status": exif_status,
        "exif_error": exif_error,
        "phash_status": "success" if phash_value else "failed",
        "phash_error": phash_error,
    }
    if metadata is None:
        metadata = EvidenceMetadata(evidence_id=evidence_id, metadata_json=metadata_json)
        db.add(metadata)
    else:
        metadata.metadata_json = metadata_json
    db.commit()
    return FingerprintResult(digest, phash_value, exif, exif_status, exif_error, phash_error)