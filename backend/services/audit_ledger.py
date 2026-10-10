"""BE-015 tamper-evident audit ledger (append-only hash chain).

Records security/governance-relevant actions; it never judges whether the
underlying action was substantively correct. Ordering comes from the
database-assigned ``sequence_number`` (unique, monotonic), never from
timestamps. Each event's SHA-256 hash covers the canonical serialization
of all protected fields and chains to its predecessor.

Concurrency: appends serialize on a PostgreSQL advisory transaction lock,
so concurrent writers receive distinct sequences with correct predecessor
hashes (no Python locks, no MAX()+1 races, no gaps from rollbacks — the
sequence is derived from committed rows only, inside the lock).

Callers append within their own domain transaction (same commit), so a
failed domain operation can never leave a successful audit record behind.
There is intentionally no generic append endpoint: events are emitted by
domain services.
"""

import hashlib
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.db.models import (
    AUDIT_EVENT_TYPES,
    AUDIT_GENESIS_HASH,
    AUDIT_HASH_ALGORITHM,
    AUDIT_LEDGER_VERSION,
    AuditLedgerEvent,
)
from backend.repositories import audit_ledger as audit_repo


logger = logging.getLogger(__name__)

EVENT_TYPES = frozenset(AUDIT_EVENT_TYPES)
HASH_ALGORITHM = AUDIT_HASH_ALGORITHM
LEDGER_VERSION = AUDIT_LEDGER_VERSION
GENESIS_HASH = AUDIT_GENESIS_HASH

APPEND_LOCK_KEY = "poa_audit_ledger_append"


class LedgerIntegrityError(RuntimeError):
    """BE-030: the append path refuses to write onto history it cannot trust."""


class PredecessorInvalid(LedgerIntegrityError):
    """BE-030 D-2-A: the immediate predecessor's stored hash fails recomputation.

    This is the re-basing attack (F-5/F-6) caught at the honest write that follows
    the damage. It is a *one-shot* control — it refuses the first append onto a
    damaged tail, and after that the writer re-bases onto a valid row — so the
    durable detection of mid-chain tampering is §9's anchored verification, not
    this check. A database with gaps but intact rows does NOT trip it: gaps are
    missing sequences, not corrupted content, so a gapped database stays writable.
    """

# Payload keys that must never reach the ledger even if a caller passes
# them (defense in depth; emission sites already pass minimal payloads).
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "jwt",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "secret",
        "client_secret",
        "authorization",
        "cookie",
        "set_cookie",
        "presigned_url",
        "signed_url",
        "private_key",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def _optional_uuid(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _require_uuid(value, label)


# ---------------------------------------------------------------------------
# Canonicalization (pure, unit-testable)
# ---------------------------------------------------------------------------


def normalize_value(value):
    """Recursively normalize a value for deterministic JSON serialization."""
    if isinstance(value, dict):
        return {str(key): normalize_value(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are rejected (timezone-aware UTC required)")
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Non-finite floats cannot be canonicalized")
        return value
    raise ValueError(f"Unserializable value of type {type(value).__name__}")


def scrub_sensitive(mapping: dict) -> dict:
    """Drop sensitive keys (case-insensitive) from a payload mapping."""
    return {
        key: value
        for key, value in mapping.items()
        if str(key).lower() not in SENSITIVE_KEYS
    }


def canonical_json(value) -> str:
    """Deterministic canonical serialization: sorted keys, UTF-8, compact."""
    return json.dumps(
        normalize_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    )


def hash_event(canonical_body: str) -> str:
    return hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()


def protected_fields(
    *,
    event_id: str,
    sequence_number: int,
    event_type: str,
    action: str,
    actor_id: str | None,
    resource_type: str,
    resource_id: str | None,
    payload: dict,
    created_at: datetime,
    previous_hash: str,
) -> dict:
    """The exact protected field set covered by every event hash."""
    return {
        "event_id": event_id,
        "sequence_number": sequence_number,
        "event_type": event_type,
        "action": action,
        "actor_id": actor_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "payload": payload,
        "created_at": normalize_value(created_at),
        "previous_hash": previous_hash,
        "hash_algorithm": HASH_ALGORITHM,
        "ledger_version": LEDGER_VERSION,
    }


def compute_event_hash(**fields) -> str:
    return hash_event(canonical_json(protected_fields(**fields)))


# ---------------------------------------------------------------------------
# Append (chain-consistent under concurrency)
# ---------------------------------------------------------------------------


def _request_id() -> str | None:
    try:
        from backend.core.logging import request_id_ctx

        return request_id_ctx.get(None)
    except Exception:
        return None


def append_event(
    db: Session,
    *,
    event_type: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor_id: str | None = None,
    project_id: str | None = None,
    payload: dict | None = None,
    request_id: str | None = None,
    source: str | None = None,
    commit: bool = False,
):
    """Append one chained event in the caller's transaction.

    The advisory lock serializes sequence assignment; the event is flushed
    (not committed unless asked) so domain services keep single-transaction
    semantics: domain mutation + audit row commit or roll back together.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown audit event type: {event_type!r}")
    if not action or not str(action).strip():
        raise ValueError("Audit action is required")
    if not resource_type or not str(resource_type).strip():
        raise ValueError("Audit resource_type is required")
    clean_payload = scrub_sensitive(dict(payload or {}))
    event_id = str(uuid.uuid4())
    created_at = utc_now()
    resource_id = _optional_uuid(resource_id, "resource_id")
    actor_id = _optional_uuid(actor_id, "actor_id")
    project_id = _optional_uuid(project_id, "project_id")

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": APPEND_LOCK_KEY}
    )
    predecessor = audit_repo.latest(db)
    if predecessor is None:
        sequence_number = 1
        previous_hash = GENESIS_HASH
    else:
        # D-2-A: recompute the tail's own hash before trusting it as the anchor.
        # The old code copied ``predecessor.event_hash`` verbatim (F-5), so a row
        # whose content was edited kept chaining happily — the new event simply
        # inherited the tampered hash. Refusing here is the one-shot write guard.
        ok, failure = verify_event(predecessor)
        if not ok:
            raise PredecessorInvalid(
                f"refusing to append onto sequence {predecessor.sequence_number}: "
                f"{failure}")
        sequence_number = int(predecessor.sequence_number) + 1
        previous_hash = str(predecessor.event_hash)
    event_hash = compute_event_hash(
        event_id=event_id,
        sequence_number=sequence_number,
        event_type=event_type,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=clean_payload,
        created_at=created_at,
        previous_hash=previous_hash,
    )
    row = audit_repo.insert_event(
        db,
        id=event_id,
        sequence_number=sequence_number,
        event_type=event_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        project_id=project_id,
        payload=clean_payload,
        event_metadata={
            "request_id": request_id if request_id is not None else _request_id(),
            "source": source,
        },
        previous_hash=previous_hash,
        event_hash=event_hash,
        hash_algorithm=HASH_ALGORITHM,
        ledger_version=LEDGER_VERSION,
        created_at=created_at,
    )
    if commit:
        db.commit()
        db.refresh(row)
    logger.info("audit appended seq=%d type=%s resource=%s:%s",
                sequence_number, event_type, resource_type, resource_id)
    return row


# ---------------------------------------------------------------------------
# Verification (pure recomputation over persisted rows)
# ---------------------------------------------------------------------------


def verify_event(row, expected_previous_hash: str | None = None) -> tuple[bool, str | None]:
    """Recompute one event's hash and (optionally) its chain link."""
    try:
        recomputed = compute_event_hash(
            event_id=str(row.id),
            sequence_number=int(row.sequence_number),
            event_type=str(row.event_type),
            action=str(row.action),
            actor_id=str(row.actor_id) if row.actor_id else None,
            resource_type=str(row.resource_type),
            resource_id=str(row.resource_id) if row.resource_id else None,
            payload=dict(row.payload or {}),
            created_at=row.created_at,
            previous_hash=str(row.previous_hash),
        )
    except (ValueError, TypeError, AttributeError) as error:
        return False, f"unverifiable event {row.id}: {error}"
    if recomputed != str(row.event_hash):
        return False, f"event_hash mismatch at sequence {row.sequence_number}"
    if expected_previous_hash is not None and str(row.previous_hash) != expected_previous_hash:
        return False, f"previous_hash mismatch at sequence {row.sequence_number}"
    return True, None


def verify_chain(
    db: Session, from_sequence: int | None = None, to_sequence: int | None = None
) -> dict:
    """Verify hash + linkage + continuity over a bounded range (read-only)."""
    if (
        (from_sequence is not None and from_sequence < 1)
        or (to_sequence is not None and to_sequence < 1)
        or (
            from_sequence is not None
            and to_sequence is not None
            and from_sequence > to_sequence
        )
    ):
        raise ValueError("Invalid verification sequence range")
    rows = audit_repo.range_query(db, from_sequence, to_sequence).all()
    if not rows:
        return {"valid": True, "checked_events": 0, "first_sequence": from_sequence,
                "last_sequence": to_sequence, "failures": []}
    # A bounded range must still anchor to its real predecessor: event N
    # must reference event N-1, even when N-1 sits outside the range.
    anchor = None
    if rows[0].sequence_number > 1:
        anchor = (
            db.query(AuditLedgerEvent)
            .filter(AuditLedgerEvent.sequence_number == rows[0].sequence_number - 1)
            .one_or_none()
        )
        if anchor is None:
            return {"valid": False, "checked_events": 0,
                    "first_sequence": rows[0].sequence_number,
                    "last_sequence": rows[-1].sequence_number,
                    "failures": [f"missing predecessor for sequence {rows[0].sequence_number}"]}
    expected_previous = (
        GENESIS_HASH if rows[0].sequence_number == 1 else str(anchor.event_hash)
    )
    failures: list[str] = []
    previous_sequence = rows[0].sequence_number - 1
    for row in rows:
        if int(row.sequence_number) != previous_sequence + 1:
            failures.append(
                f"sequence gap before {row.sequence_number} "
                f"(expected {previous_sequence + 1})"
            )
            previous_sequence = int(row.sequence_number)
            expected_previous = str(row.event_hash)
            continue
        ok, failure = verify_event(row, expected_previous)
        if not ok and failure:
            failures.append(failure)
        previous_sequence = int(row.sequence_number)
        expected_previous = str(row.event_hash)
    return {
        "valid": not failures,
        "checked_events": len(rows),
        "first_sequence": rows[0].sequence_number,
        "last_sequence": rows[-1].sequence_number,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# BE-030 §9: anchored verification, checkpoint digest, audited mutation hatch
# ---------------------------------------------------------------------------

#: Must equal ``HATCH_GUC`` in migration ``t0u1v2w3x030``. A §13 test pins it.
HATCH_GUC = "poa.ledger_mutation_exception"


@contextmanager
def sanctioned_ledger_mutation(db: Session, reason: str):
    """Open the D-1-A exception hatch for one sanctioned, rolled-back-safe edit.

    The refusing trigger blocks every ``UPDATE``/``DELETE`` unless the session
    sets ``poa.ledger_mutation_exception``. That escape is deliberately narrow and
    observable: it is ``SET LOCAL`` (a plain ``SET`` leaks the hatch for the whole
    pooled connection — measured §2c), it is scoped to the caller's transaction, and
    its use is recorded application-side because §7.7 forbids the trigger itself
    from writing to the ledger. Callers are the sanctioned tamper tests and, if the
    owner ever approves one, a dedicated repair tool — never ordinary request code.
    """
    logger.warning(
        "AUDIT_LEDGER_HATCH_OPEN reason=%r request_id=%r (SET LOCAL %s)",
        reason, _request_id(), HATCH_GUC,
    )
    db.execute(text(f"SET LOCAL {HATCH_GUC} = 'true'"))
    try:
        yield
    finally:
        # SET LOCAL is transaction-scoped: commit or rollback discards it. Nothing to
        # undo mid-transaction; this line only records that the sanctioned scope ended.
        logger.warning(
            "AUDIT_LEDGER_HATCH_EXIT reason=%r request_id=%r "
            "(hatch lives only until the enclosing transaction ends)",
            reason, _request_id(),
        )


def ledger_checkpoint(db: Session) -> dict:
    """The chain's current head as a small, loggable digest.

    The point of publishing this *outside* the database (application log / metrics)
    is the measured TRUNCATE hole (§2f): a ``FOR EACH ROW`` trigger does not fire on
    ``TRUNCATE``, so a wiped ledger plus a few fresh appends rebuilds a chain that
    ``verify_chain`` reports ``valid=True`` starting again at sequence 1. A stored
    digest lets an operator tell a genuine continuation from a silent reset.
    """
    head = audit_repo.latest(db)
    row_count = int(db.query(AuditLedgerEvent).count())
    if head is None:
        return {"rows": row_count, "min_sequence": None, "max_sequence": None,
                "tail_event_hash": None, "tail_previous_hash": None}
    return {
        "rows": row_count,
        "min_sequence": int(
            db.query(func.min(AuditLedgerEvent.sequence_number)).scalar() or 0),
        "max_sequence": int(head.sequence_number),
        "tail_event_hash": str(head.event_hash),
        "tail_previous_hash": str(head.previous_hash),
    }


def verify_chain_anchored(db: Session) -> dict:
    """Verify the WHOLE chain from sequence 1 (or its earliest survivor) and publish
    the checkpoint digest. This is the durable read-path control behind D-2-A.

    A bounded window can say ``valid`` while the full range has gaps (F-6): the
    immediate-predecessor writer check is one-shot (§2e), so this anchored walk —
    not a windowed probe — is what an operator or scheduler must run to detect
    tampering that no longer touches the tail.
    """
    result = verify_chain(db)
    checkpoint = ledger_checkpoint(db)
    logger.info(
        "audit ledger anchored verify: valid=%s checked=%d first=%s last=%s "
        "failures=%d checkpoint=(rows=%d min_seq=%s tail_hash=%s)",
        result["valid"], result["checked_events"], result["first_sequence"],
        result["last_sequence"], len(result["failures"]), checkpoint["rows"],
        checkpoint["min_sequence"], (checkpoint["tail_event_hash"] or "")[:12],
    )
    return {**result, "checkpoint": checkpoint}
