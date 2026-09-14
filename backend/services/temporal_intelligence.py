"""BE-008 Temporal Intelligence service.

Deterministic temporal facts and consistency signals only.
No fraud / risk / integrity / confidence scores.
Missing timestamps -> explicit UNKNOWN, never guessed.

Timezone policy: EXIF capture times are usually timezone-naive (tz-unknown).
Database timestamps (upload/claim bounds) are timezone-aware. Per the BE-008
spec, naive and aware values are normalized to a common comparison basis
(UTC wall-clock) instead of refusing comparison, and the original timezone
provenance is preserved via ``captured_tz_known`` so consumers know when a
verdict rests on a timezone-unknown capture time. Nothing is fabricated:
missing timestamps still yield UNKNOWN.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import Claim, Evidence, EvidenceMetadata

CAPTURE_KEYS_IN_PRIORITY = (
    "EXIF DateTimeOriginal",
    "EXIF DateTimeDigitized",
    "Image DateTime",
    "EXIF DateTime",
)

OFFSET_KEYS_BY_CAPTURE = {
    "EXIF DateTimeOriginal": ("EXIF OffsetTimeOriginal", "EXIF OffsetTime"),
    "EXIF DateTimeDigitized": ("EXIF OffsetTimeDigitized", "EXIF OffsetTime"),
    "Image DateTime": ("EXIF OffsetTime",),
    "EXIF DateTime": ("EXIF OffsetTime",),
}

_EXIF_FORMATS = (
    "%Y:%m:%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
)


@dataclass(frozen=True)
class CaptureTime:
    value: datetime | None
    tz_known: bool
    source: str | None


def _parse_exif_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Strip trailing timezone designator if embedded (e.g. "+02:00"); offset
    # handled separately via OffsetTime tags, so ignore it here.
    for fmt in _EXIF_FORMATS:
        try:
            return datetime.strptime(text[:19] if "." not in text else text, fmt)
        except ValueError:
            continue
    return None


def _parse_offset(raw: Any) -> timezone | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        sign = 1 if text[0] == "+" else -1 if text[0] == "-" else None
        if sign is None:
            return None
        hours, _, minutes = text[1:].partition(":")
        return timezone(timedelta(hours=sign * int(hours), minutes=sign * int(minutes or 0)))
    except (ValueError, IndexError):
        return None


def extract_capture_time(exif: dict[str, Any]) -> CaptureTime:
    """Return capture datetime from EXIF dict. Naive == timezone-unknown."""
    if not exif:
        return CaptureTime(None, False, None)
    for key in CAPTURE_KEYS_IN_PRIORITY:
        if key not in exif:
            continue
        parsed = _parse_exif_datetime(exif.get(key))
        if parsed is None:
            continue
        tzinfo = None
        for offset_key in OFFSET_KEYS_BY_CAPTURE.get(key, ()):
            tzinfo = _parse_offset(exif.get(offset_key))
            if tzinfo is not None:
                break
        if tzinfo is not None:
            return CaptureTime(parsed.replace(tzinfo=tzinfo), True, key)
        return CaptureTime(parsed, False, key)
    return CaptureTime(None, False, None)


def _wall_clock(value: datetime) -> datetime:
    """Normalize to a common comparison basis (naive UTC wall-clock).

    Aware values are converted to UTC and stripped of tzinfo; naive
    (timezone-unknown) values are used as-is. Callers must surface
    ``captured_tz_known`` so the tz-unknown caveat is never hidden.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _comparable(left: datetime | None, right: datetime | None) -> bool:
    return left is not None and right is not None


def capture_upload_consistency(
    captured: datetime | None,
    uploaded: datetime | None,
) -> str:
    if not _comparable(captured, uploaded):
        return "UNKNOWN"
    assert captured is not None and uploaded is not None
    if _wall_clock(captured) <= _wall_clock(uploaded):
        return "TEMPORALLY_CONSISTENT"
    return "TEMPORAL_INCONSISTENCY"


def order_pair(left: datetime | None, right: datetime | None) -> str:
    if not _comparable(left, right):
        return "UNKNOWN"
    assert left is not None and right is not None
    a, b = _wall_clock(left), _wall_clock(right)
    if a < b:
        return "CAPTURED_BEFORE"
    if a > b:
        return "CAPTURED_AFTER"
    return "SAME_TIME"


def elapsed_breakdown(left: datetime | None, right: datetime | None) -> dict[str, Any] | None:
    if not _comparable(left, right):
        return None
    assert left is not None and right is not None
    seconds = (_wall_clock(right) - _wall_clock(left)).total_seconds()
    return {
        "seconds": seconds,
        "minutes": seconds / 60,
        "hours": seconds / 3600,
        "days": seconds / 86400,
    }


def claim_window_status(
    captured: datetime | None,
    start: datetime | None,
    end: datetime | None,
) -> str:
    if captured is None or (start is None and end is None):
        return "UNKNOWN"
    assert captured is not None
    moment = _wall_clock(captured)
    norm_start = _wall_clock(start) if start is not None else None
    norm_end = _wall_clock(end) if end is not None else None
    if norm_start is not None and norm_end is not None and norm_start > norm_end:
        return "UNKNOWN"
    if norm_start is not None and moment < norm_start:
        return "BEFORE_CLAIM_WINDOW"
    if norm_end is not None and moment > norm_end:
        return "AFTER_CLAIM_WINDOW"
    return "WITHIN_CLAIM_WINDOW"


def get_upload_time(evidence: Evidence) -> datetime | None:
    created = evidence.created_at
    if created is None:
        return None
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created)
        except ValueError:
            return None
    return created


def get_capture_time(evidence_id: str, db: Session) -> CaptureTime:
    row = db.query(EvidenceMetadata).filter_by(evidence_id=evidence_id).one_or_none()
    exif: dict[str, Any] = {}
    if row is not None and isinstance(row.metadata_json, dict):
        raw_exif = row.metadata_json.get("exif")
        if isinstance(raw_exif, dict):
            exif = raw_exif
    return extract_capture_time(exif)


def analyze_single(evidence_id: str, db: Session) -> dict[str, Any]:
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    if evidence is None:
        raise LookupError("Evidence not found")
    capture = get_capture_time(evidence_id, db)
    uploaded = get_upload_time(evidence)
    consistency = capture_upload_consistency(capture.value, uploaded)

    claim_status = "UNKNOWN"
    claim: Claim | None = None
    if evidence.claim_id is not None:
        claim = db.query(Claim).filter(Claim.id == evidence.claim_id).one_or_none()
        if claim is not None:
            claim_status = claim_window_status(capture.value, claim.temporal_start_at, claim.temporal_end_at)

    inconsistencies: list[dict[str, str]] = []
    if consistency == "TEMPORAL_INCONSISTENCY":
        inconsistencies.append(
            {
                "type": "TEMPORAL_INCONSISTENCY",
                "explanation": "Capture time is after upload time.",
            }
        )

    if consistency == "TEMPORAL_INCONSISTENCY":
        status = "temporal_inconsistency"
    elif capture.value is None:
        status = "unknown"
    else:
        status = "temporally_consistent"

    return {
        "evidence_id": evidence_id,
        "captured_at": capture.value.isoformat() if capture.value else None,
        "captured_source": capture.source,
        "captured_tz_known": capture.tz_known,
        "uploaded_at": uploaded.isoformat() if uploaded else None,
        "capture_upload": consistency,
        "claim_id": evidence.claim_id,
        "claim_window": claim_status,
        "relationships": [],
        "time_differences": [],
        "inconsistencies": inconsistencies,
        "status": status,
    }


def compare_pair(a_id: str, b_id: str, db: Session) -> dict[str, Any]:
    a = db.query(Evidence).filter(Evidence.id == a_id).one_or_none()
    b = db.query(Evidence).filter(Evidence.id == b_id).one_or_none()
    if a is None or b is None:
        raise LookupError("Evidence not found")
    # Project isolation: never fabricate ordering across different projects.
    if a.project_id is not None and b.project_id is not None and a.project_id != b.project_id:
        return {
            "evidence_a": a_id,
            "evidence_b": b_id,
            "relationship": "UNKNOWN",
            "reason": "different_projects",
            "time_difference": None,
        }
    cap_a = get_capture_time(a_id, db)
    cap_b = get_capture_time(b_id, db)
    relationship = order_pair(cap_a.value, cap_b.value)
    return {
        "evidence_a": a_id,
        "evidence_b": b_id,
        "relationship": relationship,
        "reason": None if relationship != "UNKNOWN" else "missing_timestamps",
        "time_difference": elapsed_breakdown(cap_a.value, cap_b.value),
    }


def analyze_evidence(
    evidence_id: str,
    db: Session,
    compare_ids: list[str] | None = None,
) -> dict[str, Any]:
    result = analyze_single(evidence_id, db)
    relationships: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    for other_id in compare_ids or []:
        if other_id == evidence_id:
            continue
        pair = compare_pair(evidence_id, other_id, db)
        if pair["relationship"] in ("CAPTURED_BEFORE", "CAPTURED_AFTER", "SAME_TIME"):
            relationships.append(
                {
                    "other_evidence_id": other_id,
                    "relationship": pair["relationship"],
                }
            )
            if pair["time_difference"] is not None:
                differences.append(
                    {
                        "other_evidence_id": other_id,
                        **pair["time_difference"],
                    }
                )
    result["relationships"] = relationships
    result["time_differences"] = differences
    return result
