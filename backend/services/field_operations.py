"""BE-026 field operations service: assignments, sessions, and offline sync.

Containment (the load-bearing rule): ``field_assignments`` grants nothing.
Authority continues to come only from ``user_role_assignments`` evaluated by
``can()``. A session open or a synchronization succeeds when the permission
gate (enforced at the endpoint by ``require``), the server-resolved scope gate
(``evidence.create`` over the assignment's own project), and one ACTIVE,
non-expired assignment row for this officer all hold. The assignment is
re-read on every request, so a stale client snapshot is data, never a
credential.

Transaction shape: ``ingest_evidence`` commits the Evidence row itself, so the
operation identity is committed *before* ingestion runs (status ``PENDING``).
That reservation is what makes it physically impossible for a retry or a
concurrent duplicate to create a second Evidence row.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.models import (
    FieldAssignment,
    FieldCaptureOperation,
    FieldSession,
)
from backend.engines.hashing.sha256 import sha256_digest
from backend.repositories import authorization as auth_repo
from backend.repositories import field_operations as field_repo
from backend.security.authorization import visible_project_ids
from backend.services import audit_ledger as audit_service
from backend.services import integration as integration_service
from backend.services.authorization import Principal, can, resolve_resource_scope
from backend.services.evidence_ingestion import ingest_evidence
from backend.services.storage import StorageError


#: How long a ``PENDING`` reservation is considered live. Within the window a
#: duplicate caller is told ``temporarily_unavailable`` (one execution is in
#: flight); after it, a matching retry adopts the abandoned reservation and
#: re-runs ingestion, so a crashed request cannot wedge an operation identity
#: forever.
STALE_PENDING_SECONDS = 900

#: Client clocks drift; a slightly-future capture is flagged, never rejected.
FUTURE_CAPTURE_TOLERANCE = timedelta(seconds=30)

SYNC_STATUS_VOCABULARY = (
    "accepted",
    "already_synchronized",
    "rejected",
    "conflict",
    "authorization_denied",
    "validation_failed",
    "temporarily_unavailable",
)

LOCATION_SOURCES = ("DEVICE_GPS", "DEVICE_MANUAL", "CLIENT_INFERRED", "UNKNOWN")


class FieldOperationError(Exception):
    """Deterministic field-operations failure carrying its HTTP mapping."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        sync_status: str | None = None,
        validation_errors: list[str] | None = None,
    ) -> None:
        if sync_status is not None and sync_status not in SYNC_STATUS_VOCABULARY:
            raise ValueError(f"Unknown sync status: {sync_status!r}")
        self.status_code = status_code
        self.detail = detail
        self.sync_status = sync_status
        self.validation_errors = validation_errors or []
        super().__init__(detail)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


# ---------------------------------------------------------------------------
# principals, scope gates, audit
# ---------------------------------------------------------------------------

def _uuid_id(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _require_uuid(value: Any, label: str) -> str:
    resolved = _uuid_id(value)
    if resolved is None:
        raise FieldOperationError(
            422, f"Invalid {label}", validation_errors=[f"{label.upper()}_INVALID"]
        )
    return resolved


def _require_principal(principal: Principal) -> str:
    """The acting officer's user id, or a 401.

    Development bypass hands out an anonymous principal with no id. Field
    surfaces bind rows to a real officer, so they refuse it rather than fall
    back to unrestricted access.
    """
    resolved = _uuid_id(getattr(principal, "principal_id", None))
    if resolved is None:
        raise FieldOperationError(401, "Authentication required")
    return resolved


def _nullable_actor(principal: Principal | None) -> str | None:
    if principal is None:
        return None
    return _uuid_id(getattr(principal, "principal_id", None))


def _audit(
    db: Session,
    event_type: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    actor_id: str | None,
    project_id: str | None,
    payload: dict,
    *,
    commit: bool = False,
) -> None:
    """Append one ledger event carrying ids, hashes, statuses and reasons only.

    Never raw bytes, tokens, credentials, presigned URLs or file contents.
    """
    audit_service.append_event(
        db,
        event_type=event_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        project_id=project_id,
        payload=payload,
        source="field_operations_service",
        commit=commit,
    )


def _denial_error(reason: str) -> FieldOperationError:
    """Map an ``enforce()``-equivalent denial exactly like BE-016 does."""
    if reason in ("SCOPE_DENIED", "RESOURCE_UNSCOPEABLE"):
        return FieldOperationError(404, "Not found", sync_status="authorization_denied")
    if reason == "UNAUTHENTICATED":
        return FieldOperationError(
            401, "Authentication required", sync_status="authorization_denied"
        )
    return FieldOperationError(403, "Forbidden", sync_status="authorization_denied")


def _assert_project_authority(
    db: Session, principal: Principal, project_id: str, *, action: str
) -> None:
    """Scope gate: the caller's own role grant must cover the resolved project."""
    decision = can(principal, action, resolve_resource_scope(db, "project", project_id))
    if not decision.allowed:
        raise _denial_error(decision.reason)


def _visible_projects_or_deny(
    db: Session, principal: Principal | None, permission: str
) -> set[str] | None:
    """Projects a listing may expose; ``None`` means unrestricted (GLOBAL grant)."""
    if principal is None:
        return None
    if permission not in principal.permissions:
        raise FieldOperationError(403, "Forbidden")
    return visible_project_ids(db, principal, permission)


# ---------------------------------------------------------------------------
# assignment lifecycle
# ---------------------------------------------------------------------------

def _check_window(valid_from, expires_at) -> None:
    for label, value in (("valid_from", valid_from), ("expires_at", expires_at)):
        if value is not None and not _is_aware(value):
            raise FieldOperationError(
                422,
                f"{label} must be timezone-aware",
                validation_errors=[f"{label.upper()}_NAIVE_TIMESTAMP"],
            )
    if (
        valid_from is not None
        and expires_at is not None
        and _aware(expires_at) <= _aware(valid_from)
    ):
        raise FieldOperationError(
            422,
            "expires_at must be after valid_from",
            validation_errors=["EXPIRY_NOT_AFTER_START"],
        )


def create_assignment(
    db: Session,
    *,
    user_id: str,
    project_id: str,
    claim_id: str | None = None,
    activity_id: str | None = None,
    valid_from: datetime | None = None,
    expires_at: datetime | None = None,
    instructions: str | None = None,
    actor: Principal | None = None,
    project_permission: str = "field_assignment.manage",
) -> FieldAssignment:
    """Create field work. Organizational scope is derived, never supplied."""
    user_id = _require_uuid(user_id, "user_id")
    project_id = _require_uuid(project_id, "project_id")
    claim_id = _require_uuid(claim_id, "claim_id") if claim_id else None
    activity_id = _require_uuid(activity_id, "activity_id") if activity_id else None
    _check_window(valid_from, expires_at)

    visible = _visible_projects_or_deny(db, actor, project_permission)
    if visible is not None and project_id not in visible:
        raise FieldOperationError(404, "Not found")
    if auth_repo.get_user(db, user_id) is None:
        raise FieldOperationError(404, "Not found")
    project = field_repo.projects_by_ids(db, [project_id]).get(project_id)
    if project is None:
        raise FieldOperationError(404, "Not found")
    if claim_id is not None:
        claim = field_repo.claims_by_ids(db, [claim_id]).get(claim_id)
        if claim is None or str(claim.project_id) != project_id:
            raise FieldOperationError(
                422,
                "claim_id must reference a claim in this project",
                validation_errors=["CLAIM_NOT_IN_PROJECT"],
            )
    if activity_id is not None:
        activity = field_repo.activities_by_ids(db, [activity_id]).get(activity_id)
        if activity is None or str(activity.project_id) != project_id:
            raise FieldOperationError(
                422,
                "activity_id must reference an activity in this project",
                validation_errors=["ACTIVITY_NOT_IN_PROJECT"],
            )

    actor_id = _nullable_actor(actor)
    try:
        row = field_repo.insert_assignment(
            db,
            user_id=user_id,
            project_id=project_id,
            organization_id=str(project.organization_id) if project.organization_id else None,
            organizational_unit_id=(
                str(project.organizational_unit_id) if project.organizational_unit_id else None
            ),
            claim_id=claim_id,
            activity_id=activity_id,
            valid_from=valid_from,
            expires_at=expires_at,
            instructions=instructions,
            created_by=actor_id,
        )
    except IntegrityError as error:
        db.rollback()
        raise FieldOperationError(
            409, "An active assignment already covers this officer, project and claim"
        ) from error
    _audit(
        db,
        "FIELD_ASSIGNMENT_CREATED",
        "create",
        "field_assignment",
        row.id,
        actor_id,
        project_id,
        {
            "assignment_id": row.id,
            "user_id": user_id,
            "project_id": project_id,
            "claim_id": claim_id,
            "activity_id": activity_id,
            "status": "ACTIVE",
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def change_assignment_status(
    db: Session,
    *,
    assignment_id: str,
    new_status: str,
    reason: str,
    actor: Principal | None = None,
    project_permission: str,
) -> FieldAssignment:
    """Close an assignment. Never deletes: history has to survive revocation."""
    if new_status not in ("RELEASED", "REVOKED"):
        raise FieldOperationError(
            422,
            "Only RELEASED or REVOKED may be requested",
            validation_errors=["STATUS_NOT_REQUESTABLE"],
        )
    assignment_id = _require_uuid(assignment_id, "assignment_id")
    actor_id = _nullable_actor(actor)
    row = field_repo.lock_assignment(db, assignment_id)
    if row is None:
        raise FieldOperationError(404, "Not found")
    visible = _visible_projects_or_deny(db, actor, project_permission)
    if visible is not None and str(row.project_id) not in visible:
        raise FieldOperationError(404, "Not found")
    if row.status != "ACTIVE":
        raise FieldOperationError(409, f"Assignment is already closed ({row.status})")
    before = row.status
    row.status = new_status
    row.closed_reason = reason
    if new_status == "REVOKED":
        row.revoked_by = actor_id
        row.revoked_at = utc_now()
    _audit(
        db,
        "FIELD_ASSIGNMENT_STATUS_CHANGED",
        "update",
        "field_assignment",
        row.id,
        actor_id,
        str(row.project_id),
        {
            "assignment_id": row.id,
            "before_status": before,
            "after_status": new_status,
            "reason": reason,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def get_assignment(
    db: Session, *, assignment_id: str, actor: Principal | None, project_permission: str
) -> FieldAssignment:
    assignment_id = _require_uuid(assignment_id, "assignment_id")
    row = field_repo.get_assignment(db, assignment_id)
    if row is None:
        raise FieldOperationError(404, "Not found")
    visible = _visible_projects_or_deny(db, actor, project_permission)
    if visible is not None and str(row.project_id) not in visible:
        # Out of scope is indistinguishable from absent.
        raise FieldOperationError(404, "Not found")
    _audit(
        db,
        "FIELD_ASSIGNMENT_ACCESSED",
        "read",
        "field_assignment",
        row.id,
        _nullable_actor(actor),
        str(row.project_id),
        {"assignment_id": row.id, "access": "administrative_read"},
        commit=True,
    )
    return row


def list_assignments(
    db: Session,
    *,
    actor: Principal | None,
    project_permission: str,
    user_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FieldAssignment], int]:
    """Manager listing, authorization-filtered before counting."""
    visible = _visible_projects_or_deny(db, actor, project_permission)
    if project_id is not None:
        project_id = _require_uuid(project_id, "project_id")
        if visible is not None and project_id not in visible:
            raise FieldOperationError(404, "Not found")
    if user_id is not None:
        user_id = _require_uuid(user_id, "user_id")
    query = field_repo.assignment_query(
        db, user_id=user_id, project_id=project_id, project_ids=visible, status=status
    )
    rows, total = field_repo.paginate(query, limit, offset)
    _audit(
        db,
        "FIELD_ASSIGNMENT_ACCESSED",
        "read",
        "field_assignment",
        None,
        _nullable_actor(actor),
        project_id,
        {
            "access": "administrative_list",
            "filters": {"user_id": user_id, "project_id": project_id, "status": status},
            "returned": len(rows),
            "total": total,
        },
        commit=True,
    )
    return rows, total


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

def open_session(
    db: Session,
    *,
    assignment_id: str,
    session_label: str | None,
    client_device_id: str | None,
    principal: Principal,
) -> FieldSession:
    """Mint the server-side execution context for one of the caller's assignments."""
    assignment_id = _require_uuid(assignment_id, "assignment_id")
    principal_id = _require_principal(principal)
    assignment = field_repo.get_assignment(db, assignment_id)
    if assignment is None or str(assignment.user_id) != principal_id:
        _audit(
            db,
            "FIELD_ASSIGNMENT_SECURITY_FAILURE",
            "denied",
            "field_assignment",
            assignment_id,
            principal_id,
            None,
            {"failure": "FOREIGN_OR_MISSING_ASSIGNMENT", "client_device_id": client_device_id},
            commit=True,
        )
        raise FieldOperationError(404, "Not found", sync_status="authorization_denied")

    _expire_if_needed(db, assignment, principal_id)
    try:
        _assert_project_authority(
            db, principal, str(assignment.project_id), action="evidence.create"
        )
    except FieldOperationError as error:
        # Task §16 minimum coverage names assignment-related security failures, and
        # a cross-organization session attempt is one. The synchronization route
        # audits this same gate; this route must not stay silent. No domain row is
        # written, so the denial event commits on its own.
        _audit(
            db,
            "FIELD_ASSIGNMENT_SECURITY_FAILURE",
            "denied",
            "field_assignment",
            assignment_id,
            principal_id,
            str(assignment.project_id),
            {
                "failure": "SCOPE_GATE_DENIED",
                "assignment_id": assignment_id,
                "project_id": str(assignment.project_id),
                "client_device_id": client_device_id,
                "status": "authorization_denied",
            },
            commit=True,
        )
        raise
    if assignment.status != "ACTIVE":
        raise FieldOperationError(409, f"Assignment is not active ({assignment.status})")
    if client_device_id and field_repo.open_session_for_device(
        db, assignment_id=assignment_id, client_device_id=client_device_id
    ):
        raise FieldOperationError(
            409, "A session is already open on this device for this assignment"
        )

    row = field_repo.insert_session(
        db,
        assignment_id=assignment_id,
        user_id=principal_id,
        project_id=str(assignment.project_id),
        organization_id=(
            str(assignment.organization_id) if assignment.organization_id else None
        ),
        session_label=session_label,
        client_device_id=client_device_id,
    )
    _audit(
        db,
        "FIELD_ASSIGNMENT_ACCESSED",
        "read",
        "field_assignment",
        assignment_id,
        principal_id,
        str(assignment.project_id),
        {"access": "session_open", "session_id": row.id},
    )
    _audit(
        db,
        "FIELD_SESSION_OPENED",
        "create",
        "field_session",
        row.id,
        principal_id,
        str(assignment.project_id),
        {
            "session_id": row.id,
            "assignment_id": assignment_id,
            "client_device_id": client_device_id,
            "status": "ACTIVE",
        },
    )
    db.commit()
    db.refresh(row)
    return row


def close_session(
    db: Session, *, session_id: str, reason: str, principal: Principal
) -> FieldSession:
    """Close the caller's own session. A foreign session is reported as absent."""
    session_id = _require_uuid(session_id, "session_id")
    principal_id = _require_principal(principal)
    row = field_repo.lock_session(db, session_id)
    if row is None or str(row.user_id) != principal_id:
        raise FieldOperationError(404, "Not found")
    if row.status != "ACTIVE":
        raise FieldOperationError(409, f"Session is already closed ({row.status})")
    row.status = "CLOSED"
    row.closed_at = utc_now()
    row.close_reason = reason
    _audit(
        db,
        "FIELD_SESSION_CLOSED",
        "update",
        "field_session",
        row.id,
        principal_id,
        str(row.project_id),
        {"session_id": row.id, "status": "CLOSED", "reason": reason},
    )
    db.commit()
    db.refresh(row)
    return row


def _expire_if_needed(
    db: Session, assignment: FieldAssignment, actor_id: str | None
) -> FieldAssignment:
    """Server-side lazy expiry: an elapsed window becomes EXPIRED, audited."""
    if (
        assignment.status == "ACTIVE"
        and assignment.expires_at is not None
        and _aware(assignment.expires_at) <= utc_now()
    ):
        assignment.status = "EXPIRED"
        assignment.closed_reason = "validity window elapsed"
        _audit(
            db,
            "FIELD_ASSIGNMENT_EXPIRED",
            "update",
            "field_assignment",
            assignment.id,
            actor_id,
            str(assignment.project_id),
            {"assignment_id": assignment.id, "after_status": "EXPIRED"},
        )
        db.commit()
    return assignment


# ---------------------------------------------------------------------------
# assigned-work feed (data minimization)
# ---------------------------------------------------------------------------

def work_feed(
    db: Session,
    *,
    principal: Principal,
    assignment_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """The caller's own ACTIVE assignments and nothing else.

    No other project or activity, no claim the assignment does not name, no
    derived intelligence, no review or dispute content, no evidence belonging to
    anyone else, no counts outside the caller's rows.
    """
    principal_id = _require_principal(principal)
    query = field_repo.assignment_query(
        db, user_id=principal_id, project_id=None, project_ids=None, status="ACTIVE"
    )
    if assignment_id is not None:
        query = query.filter(
            FieldAssignment.id == _require_uuid(assignment_id, "assignment_id")
        )
    rows, total = field_repo.paginate(query, limit, offset)

    projects = field_repo.projects_by_ids(db, [str(row.project_id) for row in rows])
    claims = field_repo.claims_by_ids(
        db, [str(row.claim_id) for row in rows if row.claim_id]
    )
    activities = field_repo.activities_by_ids(
        db, [str(row.activity_id) for row in rows if row.activity_id]
    )
    sessions = {
        str(session.assignment_id): session
        for session in field_repo.open_sessions_for_user(db, principal_id)
    }
    items: list[dict] = []
    for row in rows:
        _expire_if_needed(db, row, principal_id)
        if row.status != "ACTIVE":
            # Elapsed while being listed: it is no longer assigned work.
            total = max(total - 1, 0)
            continue
        project = projects.get(str(row.project_id))
        claim = claims.get(str(row.claim_id)) if row.claim_id else None
        activity = activities.get(str(row.activity_id)) if row.activity_id else None
        session = sessions.get(str(row.id))
        items.append(
            {
                "assignment_id": row.id,
                "status": row.status,
                "project": {
                    "id": str(row.project_id),
                    "name": project.name if project else "unknown",
                },
                "organization_id": (
                    str(row.organization_id) if row.organization_id else None
                ),
                "valid_from": row.valid_from,
                "expires_at": row.expires_at,
                "instructions": row.instructions,
                "active_session_id": session.id if session else None,
                "claim": {"id": claim.id, "title": claim.title} if claim else None,
                "activity": (
                    {
                        "id": activity.id,
                        "verb": activity.verb,
                        "created_at": activity.created_at,
                    }
                    if activity
                    else None
                ),
            }
        )
    return items, total


# ---------------------------------------------------------------------------
# operation reads
# ---------------------------------------------------------------------------

def get_capture_by_client_id(
    db: Session, *, principal: Principal, client_operation_id: str
) -> FieldCaptureOperation:
    """Retry-after-timeout recovery: the caller's own operation, or 404."""
    if len(client_operation_id or "") < 8:
        raise FieldOperationError(
            422,
            "client_operation_id must be at least 8 characters",
            validation_errors=["CLIENT_OPERATION_ID_TOO_SHORT"],
        )
    if len(client_operation_id or "") > SYNC_FORM_WIDTHS["client_operation_id"]:
        # No such label can be stored, and comparing an over-wide literal against
        # the column would fail in the driver instead of here.
        raise FieldOperationError(
            422,
            "client_operation_id is too long",
            validation_errors=["CLIENT_OPERATION_ID_TOO_LONG"],
        )
    principal_id = _require_principal(principal)
    row = field_repo.get_operation_by_client_id(
        db, user_id=principal_id, client_operation_id=client_operation_id
    )
    if row is None:
        raise FieldOperationError(404, "Not found")
    return row


def list_operations(
    db: Session,
    *,
    actor: Principal | None,
    project_permission: str,
    user_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    status: str | None = None,
    resolution_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FieldCaptureOperation], int]:
    """Manager visibility over synchronization outcomes and open conflicts."""
    visible = _visible_projects_or_deny(db, actor, project_permission)
    if project_id is not None:
        project_id = _require_uuid(project_id, "project_id")
        if visible is not None and project_id not in visible:
            raise FieldOperationError(404, "Not found")
    query = field_repo.operation_query(
        db,
        user_id=_require_uuid(user_id, "user_id") if user_id else None,
        project_id=project_id,
        project_ids=visible,
        session_id=_require_uuid(session_id, "session_id") if session_id else None,
        status=status,
        resolution_status=resolution_status,
    )
    rows, total = field_repo.paginate(query, limit, offset)
    _audit(
        db,
        "FIELD_ASSIGNMENT_ACCESSED",
        "read",
        "field_capture_operation",
        None,
        _nullable_actor(actor),
        project_id,
        {
            "access": "operation_list",
            "filters": {
                "user_id": user_id,
                "project_id": project_id,
                "status": status,
                "resolution_status": resolution_status,
            },
            "returned": len(rows),
            "total": total,
        },
        commit=True,
    )
    return rows, total


def resolve_conflict(
    db: Session,
    *,
    operation_id: str,
    outcome: str,
    note: str,
    actor: Principal | None,
    project_permission: str,
) -> FieldCaptureOperation:
    """Annotate a conflict terminally.

    Resolution ingests nothing, mutates no Evidence, and never clears the
    conflict fields: the annotated row stays as the historical record, and the
    capture itself must be re-submitted under a new ``client_operation_id``.
    """
    if outcome not in ("DISMISSED", "RESUBMISSION_REQUIRED"):
        raise FieldOperationError(
            422,
            "outcome must be DISMISSED or RESUBMISSION_REQUIRED",
            validation_errors=["RESOLUTION_OUTCOME_INVALID"],
        )
    operation_id = _require_uuid(operation_id, "operation_id")
    row = field_repo.lock_operation(db, operation_id)
    if row is None:
        raise FieldOperationError(404, "Not found")
    visible = _visible_projects_or_deny(db, actor, project_permission)
    if visible is not None and str(row.project_id) not in visible:
        raise FieldOperationError(404, "Not found")
    if row.status != "CONFLICT":
        raise FieldOperationError(409, "Only a conflict record can be resolved")
    if row.resolution_status == "RESOLVED":
        raise FieldOperationError(409, "Conflict is already resolved")
    actor_id = _nullable_actor(actor)
    row.resolution_status = "RESOLVED"
    row.resolution_outcome = outcome
    row.resolution_note = note
    row.resolved_by = actor_id
    row.resolved_at = utc_now()
    _audit(
        db,
        "FIELD_SYNC_CONFLICT_RESOLVED",
        "update",
        "field_capture_operation",
        row.id,
        actor_id,
        str(row.project_id) if row.project_id else None,
        {
            "operation_id": row.id,
            "client_operation_id": row.client_operation_id,
            "conflict_reason": row.conflict_reason,
            "resolution_outcome": outcome,
            "resolution_status": "RESOLVED",
        },
    )
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# request normalization
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _SyncRequest:
    """One normalized multipart synchronization request."""

    principal_id: str
    data: bytes
    filename: str | None
    declared_content_type: str | None
    client_operation_id: str
    client_capture_id: str | None
    client_device_id: str | None
    session_id: str | None
    captured_at: str | None
    queued_at: str | None
    uploaded_at: str | None
    latitude: str | None
    longitude: str | None
    capture_accuracy_m: str | None
    altitude_m: str | None
    location_source: str | None
    zero_island_confirmed: bool
    payload_sha256: str
    request_hash: str
    received_at: datetime

    def identity_fields(self) -> dict:
        """Columns that define the operation identity, independent of context."""
        return {
            "user_id": self.principal_id,
            "client_operation_id": self.client_operation_id,
            "client_capture_id": self.client_capture_id,
            "client_device_id": self.client_device_id,
            "session_id": self.session_id,
            "request_hash": self.request_hash,
            "payload_sha256": self.payload_sha256,
            "declared_content_type": self.declared_content_type,
            "filename": self.filename,
            "file_size": len(self.data),
            "received_at": self.received_at,
        }


def _norm_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


#: The multipart synchronization form has no schema, so its bounds come from the
#: columns that store it. Unguarded, an over-wide value reaches Postgres and
#: fails as a driver error: a 500 for what is a client mistake (design §12).
SYNC_FORM_WIDTHS = {
    "client_operation_id": FieldCaptureOperation.client_operation_id.type.length,
    "client_capture_id": FieldCaptureOperation.client_capture_id.type.length,
    "client_device_id": FieldCaptureOperation.client_device_id.type.length,
    "declared_content_type": FieldCaptureOperation.declared_content_type.type.length,
    "filename": FieldCaptureOperation.filename.type.length,
}


def _bounded_form_text(name: str, value: Any) -> str | None:
    text_value = _norm_str(value)
    if text_value is None:
        return None
    limit = SYNC_FORM_WIDTHS[name]
    if len(text_value) > limit:
        raise FieldOperationError(
            422,
            f"{name} must be at most {limit} characters",
            sync_status="validation_failed",
            validation_errors=[f"{name.upper()}_TOO_LONG"],
        )
    return text_value


def _session_identifier(value: Any) -> str | None:
    """A session identifier is a UUID or a refusal, never free text in a query.

    A recovery label may be any client string, but the synchronization form's
    ``session_id`` is read with a UUID equality, so it is canonicalised here or
    refused: passing the raw text through would reach Postgres and surface as a
    driver error.
    """
    text_value = _norm_str(value)
    if text_value is None:
        return None
    try:
        return str(UUID(text_value)).lower()
    except (ValueError, TypeError):
        raise FieldOperationError(
            422,
            "session_id must name one of this officer's field sessions",
            sync_status="validation_failed",
            validation_errors=["SESSION_ID_MALFORMED"],
        ) from None


def _parse_timestamp_value(text: str) -> datetime | None:
    """Timezone-aware ISO-8601 only; a naive value is not silently assumed UTC."""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if _is_aware(parsed) else None


def _parse_decimal_value(text: str) -> tuple[Decimal | None, bool]:
    """Return (value, unparseable)."""
    try:
        return Decimal(text).normalize(), False
    except (InvalidOperation, ValueError, TypeError):
        return None, True


def _parse_bool(text: Any) -> tuple[bool, bool]:
    """Return (value, invalid). Absent or empty means false, not an error."""
    value = _norm_str(text)
    if value is None:
        return False, False
    lowered = value.lower()
    if lowered in ("true", "1", "yes"):
        return True, False
    if lowered in ("false", "0", "no"):
        return False, False
    return False, True


def _canonical_timestamp(value: Any) -> str | None:
    text = _norm_str(value)
    if text is None:
        return None
    parsed = _parse_timestamp_value(text)
    return parsed.isoformat() if parsed else text


def _canonical_decimal(value: Any) -> str | None:
    text = _norm_str(value)
    if text is None:
        return None
    parsed, _invalid = _parse_decimal_value(text)
    return str(parsed) if parsed is not None else text


def build_sync_request(
    *,
    principal: Principal,
    data: bytes,
    filename: str | None,
    declared_content_type: str | None,
    client_operation_id: str,
    client_capture_id: str | None = None,
    client_device_id: str | None = None,
    session_id: str | None = None,
    captured_at: str | None = None,
    queued_at: str | None = None,
    uploaded_at: str | None = None,
    latitude: str | None = None,
    longitude: str | None = None,
    capture_accuracy_m: str | None = None,
    altitude_m: str | None = None,
    location_source: str | None = None,
    zero_island_confirmed: str | None = None,
) -> _SyncRequest:
    """Hash the request over metadata *and* a digest of the bytes.

    Covering ``payload_sha256`` is what turns "same client operation identity,
    different bytes" into the same explicit conflict as "same identity,
    different metadata" — never a silent overwrite of server state.
    """
    payload_sha256 = sha256_digest(data)
    confirmed, _invalid = _parse_bool(zero_island_confirmed)
    operation_id = _bounded_form_text("client_operation_id", client_operation_id)
    capture_id = _bounded_form_text("client_capture_id", client_capture_id)
    device_id = _bounded_form_text("client_device_id", client_device_id)
    upload_name = _bounded_form_text("filename", filename)
    declared = _bounded_form_text("declared_content_type", declared_content_type)
    session = _session_identifier(session_id)
    source = _norm_str(location_source)
    canonical = {
        "client_operation_id": operation_id,
        "client_capture_id": capture_id,
        "client_device_id": device_id,
        "session_id": session,
        "filename": upload_name,
        "declared_content_type": declared.lower() if declared else None,
        "file_size": len(data),
        "captured_at": _canonical_timestamp(captured_at),
        "queued_at": _canonical_timestamp(queued_at),
        "uploaded_at": _canonical_timestamp(uploaded_at),
        "latitude": _canonical_decimal(latitude),
        "longitude": _canonical_decimal(longitude),
        "capture_accuracy_m": _canonical_decimal(capture_accuracy_m),
        "altitude_m": _canonical_decimal(altitude_m),
        "location_source": source.upper() if source else None,
        "zero_island_confirmed": bool(confirmed),
        "payload_sha256": payload_sha256,
    }
    request_hash = integration_service.compute_request_hash(
        {key: canonical[key] for key in sorted(canonical)}
    )
    return _SyncRequest(
        principal_id=_require_principal(principal),
        data=data,
        filename=upload_name,
        declared_content_type=declared.lower() if declared else None,
        client_operation_id=operation_id or "",
        client_capture_id=capture_id,
        client_device_id=device_id,
        session_id=session,
        captured_at=_norm_str(captured_at),
        queued_at=_norm_str(queued_at),
        uploaded_at=_norm_str(uploaded_at),
        latitude=_norm_str(latitude),
        longitude=_norm_str(longitude),
        capture_accuracy_m=_norm_str(capture_accuracy_m),
        altitude_m=_norm_str(altitude_m),
        location_source=source.upper() if source else None,
        zero_island_confirmed=bool(confirmed),
        payload_sha256=payload_sha256,
        request_hash=request_hash,
        received_at=utc_now(),
    )


# ---------------------------------------------------------------------------
# synchronization
# ---------------------------------------------------------------------------

def sync_capture(
    db: Session, req: _SyncRequest, principal: Principal
) -> tuple[dict, int]:
    """Synchronize exactly one offline capture (Stage B §5 algorithm).

    Design 6 makes a dependency failure on this path answer 503
    ``temporarily_unavailable`` with no row and no audit, and design 12 forbids
    any failure collapsing into a 500. The phase before ingestion and
    finalization is a plain sequence of reads, so its lost database has to be
    translated here rather than reaching the application's generic handler.
    Nothing durable is written when this fires, so the identity stays retryable
    (R1).
    """
    try:
        return _sync_capture(db, req, principal)
    except (FieldOperationError, HTTPException):
        # Declared denials (R2) and the reused validator's 400/413/415 (R3)
        # keep the contracts they already carry.
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise FieldOperationError(
            503,
            "Synchronization is temporarily unavailable",
            sync_status="temporarily_unavailable",
        ) from error


def _sync_capture(
    db: Session, req: _SyncRequest, principal: Principal
) -> tuple[dict, int]:
    """The §5 algorithm itself: settle a replay, or reserve, ingest, finalize."""
    # The identity read is locked: the replay decision below writes back to this
    # same row (sync_count, adoption), so it must serialize per identity.
    existing = field_repo.lock_operation_by_client_id(
        db, user_id=req.principal_id, client_operation_id=req.client_operation_id
    )
    if existing is not None:
        return _settle_existing(db, req, existing)

    context = _resolve_sync_context(db, req, principal)
    if context.conflict_reason is not None:
        return _record_conflict(db, req, context)

    checked = _validate_metadata(req)
    if checked.errors:
        return _record_validation_failure(db, req, context, checked)

    reserved = _reserve(db, req, context, checked)
    if isinstance(reserved, tuple):
        return reserved
    return _execute(db, req, reserved)


@dataclass(frozen=True)
class _SyncContext:
    assignment: FieldAssignment | None
    session: FieldSession | None
    project_id: str | None
    conflict_reason: str | None = None
    conflict_detail: dict | None = None

    def domain_fields(self) -> dict:
        return {
            "assignment_id": str(self.assignment.id) if self.assignment else None,
            "project_id": self.project_id,
            "claim_id": (
                str(self.assignment.claim_id)
                if self.assignment and self.assignment.claim_id
                else None
            ),
        }


@dataclass(frozen=True)
class _CheckedMetadata:
    errors: list[str]
    flags: list[str]
    captured_at: datetime | None
    queued_at: datetime | None
    uploaded_at: datetime | None
    latitude: Decimal | None
    longitude: Decimal | None
    capture_accuracy_m: Decimal | None
    altitude_m: Decimal | None
    location_source: str | None

    def persisted_fields(self) -> dict:
        return {
            "captured_at": self.captured_at,
            "queued_at": self.queued_at,
            "uploaded_at": self.uploaded_at,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "capture_accuracy_m": self.capture_accuracy_m,
            "altitude_m": self.altitude_m,
            "location_source": self.location_source,
            "timestamp_flags": self.flags,
        }


def _deny(
    db: Session,
    req: _SyncRequest,
    *,
    failure: str,
    detail: str,
    status_code: int,
    project_id: str | None = None,
    assignment_id: str | None = None,
) -> None:
    """R2: a denied request never mutates domain state, but it is still audited.

    The ledger is append-only and no domain row is written, so the denial
    events commit on their own.
    """
    payload = {
        "client_operation_id": req.client_operation_id,
        "request_hash": req.request_hash,
        "failure": failure,
        "project_id": project_id,
        "assignment_id": assignment_id,
        "session_id": req.session_id,
        "status": "authorization_denied",
    }
    _audit(
        db,
        "FIELD_SYNC_REJECTED",
        "denied",
        "field_capture_operation",
        None,
        req.principal_id,
        project_id,
        payload,
    )
    _audit(
        db,
        "FIELD_ASSIGNMENT_SECURITY_FAILURE",
        "denied",
        "field_assignment",
        assignment_id,
        req.principal_id,
        project_id,
        {**payload, "resource": "field_assignment"},
        commit=True,
    )
    raise FieldOperationError(status_code, detail, sync_status="authorization_denied")


def _resolve_sync_context(
    db: Session, req: _SyncRequest, principal: Principal
) -> _SyncContext:
    """Re-evaluate *current* authority and execution context at sync time."""
    session: FieldSession | None = None
    if req.session_id is not None:
        session = field_repo.get_session(db, req.session_id)
        if session is None or str(session.user_id) != req.principal_id:
            _deny(
                db,
                req,
                failure="FOREIGN_OR_MISSING_SESSION",
                detail="Not found",
                status_code=404,
            )
        assignment = field_repo.get_assignment(db, str(session.assignment_id))
    else:
        candidates = field_repo.active_assignments_for_user(db, req.principal_id)
        if not candidates:
            _deny(
                db,
                req,
                failure="NO_ACTIVE_ASSIGNMENT",
                detail="No active field assignment covers this capture",
                status_code=403,
            )
        if len(candidates) > 1:
            # Not a durable decision about a capture: the request never said
            # which assignment it belongs to. No row is written, so the client
            # can correct itself and retry under the same operation identity.
            _audit(
                db,
                "FIELD_SYNC_REJECTED",
                "denied",
                "field_capture_operation",
                None,
                req.principal_id,
                None,
                {
                    "client_operation_id": req.client_operation_id,
                    "request_hash": req.request_hash,
                    "failure": "AMBIGUOUS_ACTIVE_ASSIGNMENT",
                    "status": "validation_failed",
                },
                commit=True,
            )
            raise FieldOperationError(
                422,
                "session_id is required while more than one assignment is active",
                sync_status="validation_failed",
                validation_errors=["AMBIGUOUS_ACTIVE_ASSIGNMENT"],
            )
        assignment = candidates[0]

    if assignment is None or str(assignment.user_id) != req.principal_id:
        _deny(
            db,
            req,
            failure="FOREIGN_ASSIGNMENT",
            detail="Not found",
            status_code=404,
            assignment_id=str(assignment.id) if assignment is not None else None,
            project_id=str(assignment.project_id) if assignment is not None else None,
        )
    assert assignment is not None
    project_id = str(assignment.project_id)
    # Scope gate first: without a covering role grant this is a plain denial,
    # which must not leave a row behind even when the context is also stale.
    try:
        _assert_project_authority(
            db, principal, project_id, action="evidence.create"
        )
    except FieldOperationError as error:
        _deny(
            db,
            req,
            failure="SCOPE_GATE_DENIED",
            detail=error.detail,
            status_code=error.status_code,
            project_id=project_id,
            assignment_id=str(assignment.id),
        )
    _expire_if_needed(db, assignment, req.principal_id)

    detail = {
        "assignment_id": str(assignment.id),
        "assignment_status": assignment.status,
        "session_id": str(session.id) if session else None,
        "session_status": session.status if session else None,
    }
    if assignment.status == "REVOKED":
        return _SyncContext(assignment, session, project_id, "ASSIGNMENT_REVOKED", detail)
    if assignment.status == "EXPIRED":
        return _SyncContext(assignment, session, project_id, "ASSIGNMENT_EXPIRED", detail)
    if assignment.status != "ACTIVE":
        # RELEASED: current state moved on past what this client queued.
        return _SyncContext(assignment, session, project_id, "ASSIGNMENT_SUPERSEDED", detail)
    if session is not None and session.status != "ACTIVE":
        return _SyncContext(assignment, session, project_id, "SESSION_CLOSED", detail)
    if field_repo.newer_active_assignment(db, assignment) is not None:
        return _SyncContext(assignment, session, project_id, "ASSIGNMENT_SUPERSEDED", detail)
    if assignment.claim_id and not field_repo.claims_by_ids(
        db, [str(assignment.claim_id)]
    ).get(str(assignment.claim_id)):
        detail["missing_claim_id"] = str(assignment.claim_id)
        return _SyncContext(
            assignment, session, project_id, "CONTEXT_RESOURCE_MISSING", detail
        )
    if assignment.activity_id and not field_repo.activities_by_ids(
        db, [str(assignment.activity_id)]
    ).get(str(assignment.activity_id)):
        detail["missing_activity_id"] = str(assignment.activity_id)
        return _SyncContext(
            assignment, session, project_id, "CONTEXT_RESOURCE_MISSING", detail
        )
    return _SyncContext(assignment, session, project_id)


def _validate_metadata(req: _SyncRequest) -> _CheckedMetadata:
    """Validate client-asserted metadata without ever rewriting it.

    A missing value stays missing. An impossible combination (half a GPS fix,
    an unconfirmed 0,0, a naive timestamp) is refused explicitly rather than
    coerced into something the client never sent.
    """
    errors: list[str] = []

    def timestamp(field: str, raw: str | None) -> datetime | None:
        if raw is None:
            return None
        parsed = _parse_timestamp_value(raw)
        if parsed is not None:
            return parsed
        try:
            datetime.fromisoformat(raw)
            errors.append(f"{field.upper()}_NAIVE_TIMESTAMP")
        except ValueError:
            errors.append(f"{field.upper()}_UNPARSEABLE")
        return None

    def decimal(field: str, raw: str | None, low: Decimal, high: Decimal):
        if raw is None:
            return None
        parsed, invalid = _parse_decimal_value(raw)
        if invalid:
            errors.append(f"{field.upper()}_UNPARSEABLE")
            return None
        if parsed < low or parsed > high:
            errors.append(f"{field.upper()}_OUT_OF_RANGE")
            return None
        return parsed

    captured_at = timestamp("captured_at", req.captured_at)
    queued_at = timestamp("queued_at", req.queued_at)
    uploaded_at = timestamp("uploaded_at", req.uploaded_at)
    latitude = decimal("latitude", req.latitude, Decimal("-90"), Decimal("90"))
    longitude = decimal("longitude", req.longitude, Decimal("-180"), Decimal("180"))
    accuracy = decimal(
        "capture_accuracy_m", req.capture_accuracy_m, Decimal("0.000001"), Decimal("100000")
    )
    altitude = decimal("altitude_m", req.altitude_m, Decimal("-1000"), Decimal("10000"))

    has_lat = req.latitude is not None
    has_lng = req.longitude is not None
    if has_lat != has_lng:
        errors.append("GPS_PARTIAL_FIX")
    elif has_lat and has_lng:
        if latitude is None or longitude is None:
            errors.append("GPS_UNPARSEABLE")
        elif latitude == 0 and longitude == 0 and not req.zero_island_confirmed:
            errors.append("ZERO_ISLAND_UNCONFIRMED")
    if accuracy is not None and (latitude is None or longitude is None):
        errors.append("ACCURACY_WITHOUT_FIX")
    located = latitude is not None and longitude is not None
    if located and not req.location_source:
        errors.append("LOCATION_SOURCE_REQUIRED")
    if req.location_source and req.location_source not in LOCATION_SOURCES:
        errors.append("LOCATION_SOURCE_INVALID")

    flags: list[str] = []
    if captured_at and captured_at > req.received_at + FUTURE_CAPTURE_TOLERANCE:
        flags.append("FUTURE_CAPTURE")
    if captured_at and queued_at and _aware(queued_at) < _aware(captured_at):
        flags.append("QUEUE_BEFORE_CAPTURE")
    if uploaded_at and _aware(uploaded_at) > _aware(req.received_at):
        flags.append("UPLOAD_AFTER_RECEIPT")
    if uploaded_at and queued_at and _aware(uploaded_at) < _aware(queued_at):
        flags.append("UPLOAD_BEFORE_QUEUE")

    location_source = (
        req.location_source if req.location_source in LOCATION_SOURCES else None
    )
    if any(
        error.startswith(("GPS_", "ZERO_ISLAND_", "LOCATION_SOURCE_", "LATITUDE_", "LONGITUDE_"))
        or error in ("ACCURACY_WITHOUT_FIX", "CAPTURE_ACCURACY_M_OUT_OF_RANGE",
                     "CAPTURE_ACCURACY_M_UNPARSEABLE")
        for error in errors
    ):
        # An unusable fix is never stored partially: the row keeps the bytes
        # and metadata it can vouch for and nothing else.
        latitude = longitude = accuracy = None
        location_source = None

    return _CheckedMetadata(
        errors=errors,
        flags=flags,
        captured_at=captured_at,
        queued_at=queued_at,
        uploaded_at=uploaded_at,
        latitude=latitude,
        longitude=longitude,
        capture_accuracy_m=accuracy,
        altitude_m=altitude,
        location_source=location_source,
    )


def _best_effort_timestamp(raw: str | None) -> datetime | None:
    """For durable non-accepted rows: keep what parses, drop what does not."""
    return _parse_timestamp_value(raw) if raw else None


# ---------------------------------------------------------------------------
# durable outcomes
# ---------------------------------------------------------------------------

def _record_conflict(
    db: Session, req: _SyncRequest, context: _SyncContext
) -> tuple[dict, int]:
    """Synchronizing against superseded state is explicit, auditable, durable."""
    row = field_repo.insert_operation(
        db,
        **req.identity_fields(),
        **context.domain_fields(),
        status="CONFLICT",
        conflict_reason=context.conflict_reason,
        conflict_detail=context.conflict_detail or {},
        captured_at=_best_effort_timestamp(req.captured_at),
        queued_at=_best_effort_timestamp(req.queued_at),
        uploaded_at=_best_effort_timestamp(req.uploaded_at),
    )
    _audit(
        db,
        "FIELD_SYNC_CONFLICT",
        "conflict",
        "field_capture_operation",
        row.id,
        req.principal_id,
        context.project_id,
        {
            "operation_id": row.id,
            "client_operation_id": req.client_operation_id,
            "affected_resource": (
                str(context.assignment.id) if context.assignment else None
            ),
            "server_state": context.conflict_detail,
            "conflict_reason": context.conflict_reason,
            "request_hash": req.request_hash,
            "status": "CONFLICT",
            "resolution_status": "UNRESOLVED",
        },
    )
    db.commit()
    db.refresh(row)
    return (
        _sync_payload(
            row,
            sync_status="conflict",
            message=f"Synchronization conflict: {context.conflict_reason}",
        ),
        409,
    )


def _record_validation_failure(
    db: Session, req: _SyncRequest, context: _SyncContext, checked: _CheckedMetadata
) -> tuple[dict, int]:
    row = field_repo.insert_operation(
        db,
        **req.identity_fields(),
        **context.domain_fields(),
        **checked.persisted_fields(),
        status="VALIDATION_FAILED",
        validation_errors=checked.errors,
        zero_island_confirmed=req.zero_island_confirmed,
    )
    _audit(
        db,
        "FIELD_SYNC_REJECTED",
        "reject",
        "field_capture_operation",
        row.id,
        req.principal_id,
        context.project_id,
        {
            "operation_id": row.id,
            "client_operation_id": req.client_operation_id,
            "request_hash": req.request_hash,
            "validation_errors": checked.errors,
            "timestamp_flags": checked.flags,
            "status": "VALIDATION_FAILED",
        },
    )
    db.commit()
    db.refresh(row)
    return (
        _sync_payload(
            row,
            sync_status="validation_failed",
            message="Capture metadata failed validation",
        ),
        422,
    )


def _reserve(
    db: Session,
    req: _SyncRequest,
    context: _SyncContext,
    checked: _CheckedMetadata,
) -> FieldCaptureOperation | tuple[dict, int]:
    """Commit the operation identity before ingestion can create Evidence."""
    try:
        row = field_repo.insert_operation(
            db,
            **req.identity_fields(),
            **context.domain_fields(),
            **checked.persisted_fields(),
            status="PENDING",
            zero_island_confirmed=req.zero_island_confirmed,
        )
    except IntegrityError as error:
        # Concurrent first submission of the same identity.
        db.rollback()
        existing = field_repo.lock_operation_by_client_id(
            db, user_id=req.principal_id, client_operation_id=req.client_operation_id
        )
        if existing is None:
            raise FieldOperationError(
                503,
                "Synchronization is temporarily unavailable",
                sync_status="temporarily_unavailable",
            ) from error
        return _settle_existing(db, req, existing)
    db.commit()
    db.refresh(row)
    return row


def _settle_existing(
    db: Session, req: _SyncRequest, existing: FieldCaptureOperation
) -> tuple[dict, int]:
    """Idempotency evaluator: REPLAY or CONFLICT against the operation ledger."""
    if existing.request_hash != req.request_hash:
        _audit(
            db,
            "FIELD_SYNC_CONFLICT",
            "conflict",
            "field_capture_operation",
            existing.id,
            req.principal_id,
            str(existing.project_id) if existing.project_id else None,
            {
                "operation_id": existing.id,
                "client_operation_id": req.client_operation_id,
                "affected_resource": str(existing.evidence_id or existing.id),
                "stored_request_hash": existing.request_hash,
                "submitted_request_hash": req.request_hash,
                "conflict_reason": "PAYLOAD_MISMATCH",
                "server_state": {"status": existing.status},
                "resolution_status": existing.resolution_status,
            },
            commit=True,
        )
        # The stored record is authoritative and stays exactly as it was.
        return (
            _sync_payload(
                existing,
                sync_status="conflict",
                conflict_reason="PAYLOAD_MISMATCH",
                message=(
                    "client_operation_id was already used with different content; "
                    "resubmit under a new client_operation_id"
                ),
            ),
            409,
        )

    if (
        existing.session_id
        and req.session_id
        and str(existing.session_id) != str(req.session_id)
    ):
        _audit(
            db,
            "FIELD_SYNC_CONFLICT",
            "conflict",
            "field_capture_operation",
            existing.id,
            req.principal_id,
            str(existing.project_id) if existing.project_id else None,
            {
                "operation_id": existing.id,
                "client_operation_id": req.client_operation_id,
                "stored_session_id": str(existing.session_id),
                "submitted_session_id": str(req.session_id),
                "conflict_reason": "OPERATION_SESSION_MISMATCH",
                "server_state": {"status": existing.status},
            },
            commit=True,
        )
        return (
            _sync_payload(
                existing,
                sync_status="conflict",
                conflict_reason="OPERATION_SESSION_MISMATCH",
                message="This operation identity is bound to another field session",
            ),
            409,
        )

    if existing.status == "PENDING":
        age = (_aware(req.received_at) - _aware(existing.received_at)).total_seconds()
        if age < STALE_PENDING_SECONDS:
            raise FieldOperationError(
                503,
                "Synchronization for this operation identity is already in progress",
                sync_status="temporarily_unavailable",
            )
        # Abandoned reservation from a crashed execution: adopt it and re-run,
        # so the identity still resolves to exactly one outcome.
        _claim_stale_reservation(db, req, existing)
        return _execute(db, req, existing)

    _register_duplicate(db, existing, req)
    if existing.status == "ACCEPTED":
        return (
            _sync_payload(
                existing,
                sync_status="already_synchronized",
                message="Already synchronized; no duplicate evidence was created",
            ),
            200,
        )
    if existing.status == "VALIDATION_FAILED":
        return (
            _sync_payload(
                existing,
                sync_status="validation_failed",
                message="Stored validation failure replayed unchanged",
            ),
            422,
        )
    return (
        _sync_payload(
            existing,
            sync_status="conflict",
            message="Stored synchronization conflict replayed unchanged",
        ),
        409,
    )


def _claim_stale_reservation(
    db: Session, req: _SyncRequest, existing: FieldCaptureOperation
) -> None:
    """Take ownership of an abandoned reservation, or lose the race cleanly.

    ``ingest_evidence`` commits, so no row lock can span adoption and
    re-ingestion: a lock taken here would be released by the first commit
    inside the ingestion call. The claim is therefore a compare-and-set on the
    reservation's own stale clock. Exactly one concurrent execution can move
    ``received_at`` from the observed stale value to its own, and doing so makes
    the reservation young again, so the others answer with the documented
    "one execution is in flight" refusal instead of starting a second ingestion
    of the same identity (which could leave the identity with no decision at
    all). ``received_at`` stays a server-observed time: after adoption it
    belongs to the execution that actually reached a decision.
    """
    claimed = db.execute(
        update(FieldCaptureOperation)
        .where(
            FieldCaptureOperation.id == existing.id,
            FieldCaptureOperation.status == "PENDING",
            FieldCaptureOperation.received_at == existing.received_at,
        )
        .values(received_at=req.received_at)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise FieldOperationError(
            503,
            "Synchronization for this operation identity is already in progress",
            sync_status="temporarily_unavailable",
        )
    db.commit()
    existing.received_at = req.received_at


def _register_duplicate(
    db: Session, existing: FieldCaptureOperation, req: _SyncRequest
) -> None:
    """Count the retry. An ordinary duplicate is not a conflict and re-ingests nothing."""
    existing.sync_count = int(existing.sync_count or 1) + 1
    existing.last_synced_at = req.received_at
    if existing.session_id:
        session = field_repo.get_session(db, str(existing.session_id))
        if session is not None:
            session.last_sync_at = req.received_at
    _audit(
        db,
        "FIELD_SYNC_DUPLICATE",
        "replay",
        "field_capture_operation",
        existing.id,
        req.principal_id,
        str(existing.project_id) if existing.project_id else None,
        {
            "operation_id": existing.id,
            "client_operation_id": existing.client_operation_id,
            "request_hash": existing.request_hash,
            "status": existing.status,
            "sync_count": existing.sync_count,
            "evidence_id": str(existing.evidence_id) if existing.evidence_id else None,
        },
    )
    db.commit()


def _execute(
    db: Session, req: _SyncRequest, row: FieldCaptureOperation
) -> tuple[dict, int]:
    """Ingest through the reused BE-003 pipeline, then associate and finalize."""
    try:
        evidence = ingest_evidence(
            req.data, req.filename or "unnamed", req.declared_content_type, db,
            actor_id=req.principal_id,
        )
    except HTTPException as error:
        # 400/413/415 from the existing validator, which raises before it stores
        # or commits anything. The response contract stays identical to
        # POST /evidence, and the reservation is dropped so a retry answers with
        # the same code instead of a stored-status divergence.
        _drop_reservation(db, row)
        raise
    except StorageError as error:
        _drop_reservation(db, row)
        raise FieldOperationError(
            503,
            "Evidence storage is temporarily unavailable",
            sync_status="temporarily_unavailable",
        ) from error
    except SQLAlchemyError as error:
        _drop_reservation(db, row)
        raise FieldOperationError(
            503,
            "Synchronization is temporarily unavailable",
            sync_status="temporarily_unavailable",
        ) from error

    # Association in the same transaction as finalization, per BE-014's
    # established pattern: a field capture is never left unscopeable.
    #
    # The whole finalization phase is guarded, not just the commit: the audit
    # writes below flush the pending ACCEPTED update, so a dependency failure
    # surfaces here first. Design 6/12 make that answer 503
    # ``temporarily_unavailable`` and never a 500, and the reservation stays
    # PENDING so the identity stays retryable either way.
    try:
        if row.project_id:
            evidence.project_id = str(row.project_id)
        if row.claim_id:
            evidence.claim_id = str(row.claim_id)
        if row.latitude is not None and row.longitude is not None:
            # PostGIS stays the only authoritative location.
            evidence.location = func.ST_SetSRID(
                func.ST_MakePoint(float(row.longitude), float(row.latitude)), 4326
            )
        row.evidence_id = str(evidence.id)
        row.status = "ACCEPTED"
        row.processed_at = utc_now()
        row.last_synced_at = row.processed_at
        if row.session_id:
            session = field_repo.get_session(db, str(row.session_id))
            if session is not None:
                session.last_sync_at = row.processed_at
        _audit(
            db,
            "FIELD_SYNC_ACCEPTED",
            "create",
            "field_capture_operation",
            row.id,
            req.principal_id,
            str(row.project_id) if row.project_id else None,
            {
                "operation_id": row.id,
                "client_operation_id": row.client_operation_id,
                "evidence_id": str(evidence.id),
                "request_hash": row.request_hash,
                "payload_sha256": row.payload_sha256,
                "file_size": row.file_size,
                "status": "ACCEPTED",
                "has_location": row.latitude is not None,
                "timestamp_flags": list(row.timestamp_flags or []),
            },
        )
        _audit(
            db,
            "FIELD_EVIDENCE_ASSOCIATED",
            "update",
            "evidence",
            str(evidence.id),
            req.principal_id,
            str(row.project_id) if row.project_id else None,
            {
                "evidence_id": str(evidence.id),
                "operation_id": row.id,
                "project_id": str(row.project_id) if row.project_id else None,
                "claim_id": str(row.claim_id) if row.claim_id else None,
                "evidence_status": evidence.status,
            },
        )
        db.commit()
        db.refresh(row)
        db.refresh(evidence)
    except SQLAlchemyError as error:  # pragma: no cover - dependency failure
        db.rollback()
        raise FieldOperationError(
            503,
            "Synchronization is temporarily unavailable",
            sync_status="temporarily_unavailable",
        ) from error
    return (
        _sync_payload(
            row,
            sync_status="accepted",
            message="Capture accepted and stored in quarantine",
            evidence=evidence,
        ),
        201,
    )


def _drop_reservation(db: Session, row: FieldCaptureOperation) -> None:
    """Remove a reservation that never became a durable decision.

    Both ``temporarily_unavailable`` and a structural rejection by the reused
    validator mean *no decision was reached*, so the identity has to stay
    retryable; R1 says a row exists if and only if the server decided.
    """
    db.rollback()
    try:
        live = field_repo.get_operation(db, str(row.id))
        if live is not None and live.status == "PENDING":
            db.delete(live)
        db.commit()
    except SQLAlchemyError:  # pragma: no cover - dependency failure
        db.rollback()


def _sync_payload(
    row: FieldCaptureOperation,
    *,
    sync_status: str,
    message: str,
    conflict_reason: str | None = None,
    evidence=None,
) -> dict:
    has_fix = row.latitude is not None and row.longitude is not None
    return {
        "sync_status": sync_status,
        "operation_id": row.id,
        "client_operation_id": row.client_operation_id,
        "status": row.status,
        "evidence_id": str(row.evidence_id) if row.evidence_id else None,
        "evidence_status": (
            getattr(evidence, "status", None) if evidence is not None else None
        ),
        "project_id": str(row.project_id) if row.project_id else None,
        "claim_id": str(row.claim_id) if row.claim_id else None,
        "session_id": str(row.session_id) if row.session_id else None,
        "assignment_id": str(row.assignment_id) if row.assignment_id else None,
        "conflict_reason": conflict_reason or row.conflict_reason,
        "validation_errors": list(row.validation_errors or []),
        "timestamp_flags": list(row.timestamp_flags or []),
        "captured_at": row.captured_at,
        "queued_at": row.queued_at,
        "uploaded_at": row.uploaded_at,
        "received_at": row.received_at,
        "processed_at": row.processed_at,
        "location": {
            "reported": bool(has_fix),
            "latitude": float(row.latitude) if row.latitude is not None else None,
            "longitude": float(row.longitude) if row.longitude is not None else None,
            "capture_accuracy_m": (
                float(row.capture_accuracy_m)
                if row.capture_accuracy_m is not None
                else None
            ),
            "altitude_m": float(row.altitude_m) if row.altitude_m is not None else None,
            "location_source": row.location_source,
            "zero_island_confirmed": bool(row.zero_island_confirmed),
        },
        "file_size": int(row.file_size),
        "sync_count": int(row.sync_count or 1),
        "message": message,
    }
