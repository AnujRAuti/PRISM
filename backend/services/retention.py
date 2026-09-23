"""BE-017 policy-driven retention, archival, and controlled deletion.

Answers how long a resource is retained and whether it is eligible for
archive or deletion — never whether evidence is true, fraudulent, or
risky. Analytical conclusions (scores, matches, priorities, decisions)
are never inputs to eligibility.

Fail-closed throughout: missing policy, anchor, scope, or conflicting
policies all yield NOT ELIGIBLE, never DELETE. Evaluation is read-only;
execution re-evaluates inside the deletion transaction (two-phase safety)
with row locking against concurrent lifecycle changes.

Conventions: ``ValueError`` for invalid input/semantic failures,
``LookupError`` for missing rows.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_ as sqlalchemy_or
from sqlalchemy.orm import Session

from backend.db.models import (
    RETENTION_ANCHORS,
    RETENTION_HOLD_SCOPES,
    RETENTION_HOLD_STATUSES,
    RETENTION_OPERATION_STATUSES,
    RETENTION_OPERATION_TYPES,
    RETENTION_POLICY_STATUSES,
    RETENTION_RESOURCE_TYPES,
    RETENTION_STATES,
    AnalysisJob,
    AnalysisResult,
    Claim,
    DuplicateMatch,
    Evidence,
    EvidenceMetadata,
    EvidenceRequest,
    FusionRun,
    Organization,
    OrganizationalUnit,
    Project,
    ReviewCase,
    VisionDetection,
)
from backend.repositories import retention as retention_repo
from backend.services import audit_ledger as audit_service


logger = logging.getLogger(__name__)

RESOURCE_TYPES = frozenset(RETENTION_RESOURCE_TYPES)
STATES = frozenset(RETENTION_STATES)
ANCHORS = frozenset(RETENTION_ANCHORS)
HOLD_STATUSES = frozenset(RETENTION_HOLD_STATUSES)
OPEN_CASE_STATUSES = frozenset({"OPEN", "ASSIGNED", "INVESTIGATING", "DECISION_PENDING", "ESCALATED"})
OPEN_REQUEST_STATUSES = frozenset({"OPEN", "ACKNOWLEDGED", "PARTIALLY_FULFILLED"})

ARCHIVE_PREFIX = "archive"

# Scope specificity for deterministic precedence (PROJECT first).
SCOPE_SPECIFICITY = {"PROJECT": 3, "ORGANIZATIONAL_UNIT": 2, "ORGANIZATION": 1, "GLOBAL": 0}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str, label: str) -> str:
    from uuid import UUID

    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error


def _optional_uuid(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _require_uuid(value, label)


# ---------------------------------------------------------------------------
# Pure policy rules (unit-testable without a database)
# ---------------------------------------------------------------------------


def validate_policy_rules(rules: dict) -> dict:
    """Validate retention rules (fail clearly, never silently clamp)."""
    if not isinstance(rules, dict):
        raise ValueError("Policy rules must be a mapping")
    days = rules.get("retention_days")
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        raise ValueError("rules.retention_days must be a positive integer")
    archive_after = rules.get("archive_after_days")
    if archive_after is not None:
        if (not isinstance(archive_after, int) or isinstance(archive_after, bool)
                or archive_after < 1):
            raise ValueError("rules.archive_after_days must be a positive integer or null")
        if archive_after >= days:
            raise ValueError("rules.archive_after_days must precede retention_days")
    anchor = rules.get("anchor")
    if anchor not in ANCHORS:
        raise ValueError(f"Unknown retention anchor: {anchor!r}")
    if not isinstance(rules.get("allow_derived_cleanup", False), bool):
        raise ValueError("rules.allow_derived_cleanup must be a boolean")
    return rules


def compute_expiry(anchor_timestamp: datetime, retention_days: int) -> datetime:
    """Deterministic expiry arithmetic (anchor + whole days)."""
    return anchor_timestamp + timedelta(days=int(retention_days))


def select_policy(candidates: list) -> object | None | str:
    """Deterministic scope precedence over matched (policy, version) pairs.

    Each candidate carries ``scope_specificity`` (3..0). Returns the single
    winner, None when nothing applies, or the string ``"POLICY_CONFLICT"``
    when several candidates tie at the most-specific level (fail closed).
    """
    if not candidates:
        return None
    best = max(candidate["scope_specificity"] for candidate in candidates)
    winners = [candidate for candidate in candidates if candidate["scope_specificity"] == best]
    if len(winners) > 1:
        return "POLICY_CONFLICT"
    return winners[0]


# ---------------------------------------------------------------------------
# Policy administration
# ---------------------------------------------------------------------------


def create_policy(
    db: Session, *, name: str, description: str | None, resource_type: str,
    scope_type: str, organization_id: str | None = None,
    organizational_unit_id: str | None = None, project_id: str | None = None,
    created_by: str | None = None,
):
    """Create a policy identity (rules arrive via versions, never edits)."""
    if resource_type not in RESOURCE_TYPES:
        raise ValueError(f"Unknown resource type: {resource_type!r}")
    if scope_type not in ("GLOBAL", "ORGANIZATION", "ORGANIZATIONAL_UNIT", "PROJECT"):
        raise ValueError(f"Unknown scope type: {scope_type!r}")
    if not name or not str(name).strip():
        raise ValueError("Policy name is required")
    organization_id = _optional_uuid(organization_id, "organization_id")
    organizational_unit_id = _optional_uuid(organizational_unit_id, "organizational_unit_id")
    project_id = _optional_uuid(project_id, "project_id")
    if scope_type == "GLOBAL" and any((organization_id, organizational_unit_id, project_id)):
        raise ValueError("GLOBAL policies must not carry scope identifiers")
    if scope_type == "ORGANIZATION" and (organization_id is None
                                         or organizational_unit_id is not None
                                         or project_id is not None):
        raise ValueError("ORGANIZATION policies require exactly organization_id")
    if scope_type == "ORGANIZATIONAL_UNIT" and (organizational_unit_id is None
                                                or project_id is not None):
        raise ValueError("ORGANIZATIONAL_UNIT policies require exactly organizational_unit_id")
    if scope_type == "PROJECT" and (project_id is None or organization_id is not None
                                    or organizational_unit_id is not None):
        raise ValueError("PROJECT policies require exactly project_id")
    if organization_id is not None and db.query(Organization).filter(
        Organization.id == organization_id
    ).one_or_none() is None:
        raise LookupError(f"Organization not found: {organization_id}")
    if organizational_unit_id is not None and db.query(OrganizationalUnit).filter(
        OrganizationalUnit.id == organizational_unit_id
    ).one_or_none() is None:
        raise LookupError(f"Organizational unit not found: {organizational_unit_id}")
    if project_id is not None and db.query(Project).filter(
        Project.id == project_id
    ).one_or_none() is None:
        raise LookupError(f"Project not found: {project_id}")
    row = retention_repo.insert_policy(
        db, name=str(name).strip(), description=description,
        resource_type=resource_type, scope_type=scope_type,
        organization_id=organization_id, organizational_unit_id=organizational_unit_id,
        project_id=project_id, created_by=_optional_uuid(created_by, "created_by"),
    )
    db.commit()
    audit_service.append_event(
        db, event_type="RETENTION_POLICY_CREATED", action="create",
        resource_type="retention_policies", resource_id=row.id,
        actor_id=_optional_uuid(created_by, "created_by"), project_id=project_id,
        payload={"policy_id": row.id, "name": str(name).strip(),
                 "resource_type": resource_type, "scope_type": scope_type},
        source="retention_service",
    )
    db.commit()
    db.refresh(row)
    return row


def create_policy_version(
    db: Session, *, policy_id: str, rules: dict,
    effective_from: datetime | None = None, effective_until: datetime | None = None,
    created_by: str | None = None,
):
    """Append an immutable rules version (DRAFT; activation is explicit)."""
    policy_id = _require_uuid(policy_id, "policy_id")
    if retention_repo.get_policy(db, policy_id) is None:
        raise LookupError(f"Retention policy not found: {policy_id}")
    payload = validate_policy_rules(rules)
    existing = retention_repo.versions_for_policy(db, policy_id)
    version = (max(row.version for row in existing) + 1) if existing else 1
    for bound, label in ((effective_from, "effective_from"), (effective_until, "effective_until")):
        if bound is not None and (not isinstance(bound, datetime) or bound.tzinfo is None):
            raise ValueError(f"{label} must be timezone-aware")
    if (effective_from is not None and effective_until is not None
            and effective_until <= effective_from):
        raise ValueError("effective_until must be after effective_from")
    row = retention_repo.insert_version(
        db, policy_id=policy_id, version=version, rules=dict(payload),
        effective_from=effective_from, effective_until=effective_until,
        created_by=_optional_uuid(created_by, "created_by"),
    )
    db.commit()
    db.refresh(row)
    return row


def activate_policy_version(db: Session, version_id: str, actor_id: str | None = None):
    """Activate one version; siblings become SUPERSEDED (history preserved)."""
    from backend.db.models import RetentionPolicyVersion

    version_id = _require_uuid(version_id, "version_id")
    row = db.query(RetentionPolicyVersion).filter(
        RetentionPolicyVersion.id == version_id).one_or_none()
    if row is None:
        raise LookupError(f"Policy version not found: {version_id}")
    if row.status == "RETIRED":
        raise ValueError("Retired versions cannot be reactivated")
    siblings = retention_repo.versions_for_policy(db, str(row.policy_id))
    for sibling in siblings:
        if sibling.id != row.id and sibling.status == "ACTIVE":
            sibling.status = "SUPERSEDED"
    row.status = "ACTIVE"
    audit_service.append_event(
        db, event_type="RETENTION_POLICY_ACTIVATED", action="activate",
        resource_type="retention_policies", resource_id=str(row.policy_id),
        actor_id=_optional_uuid(actor_id, "actor_id"), project_id=None,
        payload={"policy_id": str(row.policy_id), "version": row.version},
        source="retention_service",
    )
    db.commit()
    db.refresh(row)
    return row


def retire_policy_version(db: Session, version_id: str, actor_id: str | None = None):
    """Retire a version without deleting history (DRAFT/ACTIVE -> RETIRED)."""
    from backend.db.models import RetentionPolicyVersion

    version_id = _require_uuid(version_id, "version_id")
    row = db.query(RetentionPolicyVersion).filter(
        RetentionPolicyVersion.id == version_id).one_or_none()
    if row is None:
        raise LookupError(f"Policy version not found: {version_id}")
    if row.status == "RETIRED":
        return row
    row.status = "RETIRED"
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Scope, anchors, holds, dependencies (read-only helpers)
# ---------------------------------------------------------------------------


def resource_scope(db: Session, resource_type: str, resource_id: str) -> dict:
    """Server-resolved scope chain for a resource (never client-trusted)."""
    scope: dict[str, str | None] = {
        "project_id": None, "organization_id": None, "organizational_unit_id": None,
    }
    project_id: str | None = None
    if resource_type == "EVIDENCE":
        row = db.query(Evidence).filter(Evidence.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"EVIDENCE not found: {resource_id}")
        project_id = str(row.project_id) if row.project_id else None
    elif resource_type == "ANALYSIS_RESULT":
        from backend.db.models import AnalysisJob as _Job
        from backend.db.models import AnalysisResult as _Result

        row = db.query(_Result).filter(_Result.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"ANALYSIS_RESULT not found: {resource_id}")
        job = db.query(_Job).filter(_Job.id == row.job_id).one_or_none()
        if job is not None:
            evidence = db.query(Evidence).filter(Evidence.id == job.evidence_id).one_or_none()
            project_id = str(evidence.project_id) if evidence and evidence.project_id else None
    elif resource_type == "FUSION_RUN":
        from backend.db.models import FusionRun as _Run

        row = db.query(_Run).filter(_Run.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"FUSION_RUN not found: {resource_id}")
        project_id = _fusion_target_project(db, row.target_type, str(row.target_id))
    elif resource_type == "REVIEW_CASE":
        from backend.db.models import ReviewCase as _Case

        row = db.query(_Case).filter(_Case.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"REVIEW_CASE not found: {resource_id}")
        project_id = str(row.project_id) if row.project_id else None
    elif resource_type == "EVIDENCE_REQUEST":
        from backend.db.models import EvidenceRequest as _Request

        row = db.query(_Request).filter(_Request.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"EVIDENCE_REQUEST not found: {resource_id}")
        project_id = str(row.project_id) if row.project_id else None
    elif resource_type == "AUDIT_LEDGER_EVENT":
        raise ValueError("Audit ledger events are never eligible for retention action")
    else:
        raise ValueError(f"Unsupported resource type: {resource_type!r}")
    if project_id is not None:
        project = db.query(Project).filter(Project.id == project_id).one_or_none()
        if project is not None:
            scope["project_id"] = project_id
            scope["organization_id"] = (
                str(project.organization_id) if project.organization_id else None)
            scope["organizational_unit_id"] = (
                str(project.organizational_unit_id) if project.organizational_unit_id else None)
    return scope


def _fusion_target_project(db: Session, target_type: str, target_id: str) -> str | None:
    if target_type == "CLAIM":
        claim = db.query(Claim).filter(Claim.id == target_id).one_or_none()
        return str(claim.project_id) if claim else None
    if target_type == "EVIDENCE":
        evidence = db.query(Evidence).filter(Evidence.id == target_id).one_or_none()
        return str(evidence.project_id) if evidence and evidence.project_id else None
    return None


def resolve_anchor(db: Session, resource_type: str, resource_id: str, anchor: str):
    """Resolve an explicit retention anchor (missing anchors stay missing)."""
    if anchor not in ("INGESTED_AT", "CAPTURED_AT", "CASE_RESOLVED_AT", "DECISION_AT",
                      "REQUEST_FULFILLED_AT"):
        if anchor in ("PROJECT_COMPLETED_AT", "SUPERSEDED_AT", "CUSTOM_POLICY_EVENT"):
            return None
        raise ValueError(f"Unknown retention anchor: {anchor!r}")
    if resource_type == "EVIDENCE":
        row = db.query(Evidence).filter(Evidence.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"EVIDENCE not found: {resource_id}")
        if anchor == "INGESTED_AT":
            return row.created_at
        from backend.services.temporal_intelligence import get_capture_time

        capture = get_capture_time(resource_id, db)
        return capture.value
    if resource_type == "ANALYSIS_RESULT":
        from backend.db.models import AnalysisResult as _Result

        row = db.query(_Result).filter(_Result.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"ANALYSIS_RESULT not found: {resource_id}")
        return row.created_at if anchor == "INGESTED_AT" else None
    if resource_type == "FUSION_RUN":
        from backend.db.models import FusionRun as _Run

        row = db.query(_Run).filter(_Run.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"FUSION_RUN not found: {resource_id}")
        return row.created_at if anchor == "INGESTED_AT" else None
    if resource_type == "REVIEW_CASE":
        from backend.db.models import ReviewCase as _Case

        row = db.query(_Case).filter(_Case.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"REVIEW_CASE not found: {resource_id}")
        if anchor == "INGESTED_AT":
            return row.created_at
        if anchor == "CASE_RESOLVED_AT":
            return row.resolved_at
        if anchor == "DECISION_AT":
            return row.decided_at
        return None
    if resource_type == "EVIDENCE_REQUEST":
        from backend.db.models import EvidenceRequest as _Request

        row = db.query(_Request).filter(_Request.id == resource_id).one_or_none()
        if row is None:
            raise LookupError(f"EVIDENCE_REQUEST not found: {resource_id}")
        if anchor == "INGESTED_AT":
            return row.created_at
        if anchor == "REQUEST_FULFILLED_AT":
            return row.updated_at if row.status == "FULFILLED" else None
        return None
    raise ValueError(f"Unsupported resource type: {resource_type!r}")


def _hold_is_live(hold, now: datetime) -> bool:
    if hold.status != "ACTIVE":
        return False
    expires_at = hold.expires_at
    if expires_at is not None:
        moment = expires_at if expires_at.tzinfo is not None else expires_at.replace(
            tzinfo=timezone.utc)
        if moment <= now:
            return False
    return True


def holds_blocking(db: Session, resource_type: str, resource_id: str,
                   scope: dict, now: datetime) -> list:
    """ACTIVE unexpired holds covering a resource (deterministic order)."""
    holds = retention_repo.active_holds(db)
    matched = []
    for hold in holds:
        if not _hold_is_live(hold, now):
            continue
        hit = False
        if hold.scope == "RESOURCE":
            hit = (hold.resource_type == resource_type
                   and str(hold.resource_id or "") == resource_id)
        elif hold.scope == "PROJECT":
            hit = (scope.get("project_id") is not None
                   and str(hold.project_id or "") == scope["project_id"])
        elif hold.scope == "CASE" and hold.case_id is not None:
            from backend.db.models import ReviewCase as _Case

            case = db.query(_Case).filter(_Case.id == hold.case_id).one_or_none()
            case_project = str(case.project_id) if case and case.project_id else None
            hit = case_project is not None and case_project == scope.get("project_id")
        elif hold.scope == "CLAIM" and hold.claim_id is not None:
            claim = db.query(Claim).filter(Claim.id == hold.claim_id).one_or_none()
            claim_project = str(claim.project_id) if claim else None
            if claim_project is None:
                continue
            if claim_project == scope.get("project_id"):
                hit = True
            elif resource_type == "EVIDENCE":
                # Evidence filed under the held claim is covered even when
                # its own project link is absent.
                row = db.query(Evidence).filter(Evidence.id == resource_id).one_or_none()
                hit = row is not None and str(row.claim_id or "") == str(hold.claim_id)
        elif hold.scope == "ORGANIZATION" and hold.organization_id is not None:
            hit = (scope.get("organization_id") is not None
                   and str(hold.organization_id) == scope["organization_id"])
        if hit:
            matched.append(hold)
    matched.sort(key=lambda hold: (str(hold.created_at), str(hold.id)))
    return matched


def evidence_dependencies(db: Session, evidence_id: str) -> dict:
    """Dependent records for an evidence item (read-only, explicit)."""
    from backend.db.models import AnalysisJob as _Job
    from backend.db.models import AnalysisResult as _Result
    from backend.db.models import ReviewCase as _Case
    from backend.db.models import EvidenceRequest as _Request
    from backend.db.models import VisionDetection as _Detection

    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    if evidence is None:
        raise LookupError(f"EVIDENCE not found: {evidence_id}")
    case_predicates = [_Case.evidence_id == evidence_id]
    if evidence.claim_id:
        case_predicates.append(_Case.claim_id == evidence.claim_id)
    open_cases = (
        db.query(_Case)
        .filter(
            sqlalchemy_or(*case_predicates),
            _Case.status.in_(("OPEN", "ASSIGNED", "INVESTIGATING",
                              "DECISION_PENDING", "ESCALATED")),
        )
        .order_by(_Case.created_at, _Case.id)
        .all()
    )
    # Requests whose items reference this evidence and are still open.
    from backend.db.models import EvidenceRequestItem as _Item

    unresolved_requests = (
        db.query(_Request)
        .join(_Item, _Item.request_id == _Request.id)
        .filter(_Item.evidence_id == evidence_id,
                _Request.status.in_(("OPEN", "ACKNOWLEDGED", "PARTIALLY_FULFILLED")))
        .order_by(_Request.created_at, _Request.id)
        .all()
    )
    job_ids = [
        row[0] for row in db.query(_Job.id).filter(_Job.evidence_id == evidence_id).all()
    ]
    results = (
        db.query(_Result).filter(_Result.job_id.in_(job_ids)).all() if job_ids else []
    )
    matches = (
        db.query(DuplicateMatch)
        .filter((DuplicateMatch.evidence_id == evidence_id)
                | (DuplicateMatch.matched_evidence_id == evidence_id))
        .all()
    )
    detections = []
    if results:
        result_ids = [row.id for row in results]
        detections = (
            db.query(_Detection)
            .filter(_Detection.analysis_result_id.in_(result_ids)).all()
        )
    fusion_runs = (
        db.query(FusionRun)
        .filter(FusionRun.target_type == "EVIDENCE", FusionRun.target_id == evidence_id)
        .order_by(FusionRun.created_at, FusionRun.id)
        .all()
    )
    from backend.db.models import GraphNode as _Node
    from backend.db.models import GraphRelationship as _Edge

    node_ids = [
        row[0] for row in db.query(_Node.id)
        .filter(_Node.node_type == "EVIDENCE", _Node.entity_id == evidence_id).all()
    ]
    edges = []
    if node_ids:
        edges = (
            db.query(_Edge)
            .filter((_Edge.source_node_id.in_(node_ids))
                    | (_Edge.target_node_id.in_(node_ids)),
                    _Edge.relationship_status == "ACTIVE")
            .order_by(_Edge.created_at, _Edge.id)
            .all()
        )
    return {
        "open_cases": open_cases,
        "unresolved_requests": unresolved_requests,
        "fusion_runs": fusion_runs,
        "results": results,
        "matches": matches,
        "detections": detections,
        "active_edges": edges,
    }


# ---------------------------------------------------------------------------
# Holds
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Evaluation (read-only; never mutates)
# ---------------------------------------------------------------------------


def evaluate(
    db: Session, resource_type: str, resource_id: str, now: datetime | None = None
) -> dict:
    """Determine archive/deletion eligibility without modifying anything."""
    if resource_type not in RESOURCE_TYPES:
        raise ValueError(f"Unsupported resource type: {resource_type!r}")
    resource_id = _require_uuid(resource_id, "resource_id")
    moment = now or utc_now()
    if resource_type == "AUDIT_LEDGER_EVENT":
        return {
            "eligible": False, "archive_eligible": False, "deletion_eligible": False,
            "state": "ACTIVE", "anchor": None, "anchor_timestamp": None,
            "expiry_timestamp": None, "policy_id": None, "policy_version": None,
            "blocking_reasons": ["AUDIT_LEDGER_RETAINED"],
            "details": {}, "evaluated_at": moment.isoformat(),
        }
    scope = resource_scope(db, resource_type, resource_id)
    candidates = _applicable_policies(db, resource_type, scope, moment)
    selected = select_policy(candidates)
    if selected is None:
        return _evaluation(
            moment, state="ACTIVE", anchor=None, anchor_ts=None, expiry=None,
            policy=None, version=None, reasons=["NO_APPLICABLE_POLICY"], details={},
        )
    if selected == "POLICY_CONFLICT":
        return _evaluation(
            moment, state="ACTIVE", anchor=None, anchor_ts=None, expiry=None,
            policy=None, version=None, reasons=["POLICY_CONFLICT"], details={},
        )
    policy, version = selected["policy"], selected["version"]
    rules = version.rules or {}
    anchor = rules.get("anchor")
    anchor_ts = resolve_anchor(db, resource_type, resource_id, anchor)
    if anchor_ts is None:
        return _evaluation(
            moment, state="ACTIVE", anchor=anchor, anchor_ts=None, expiry=None,
            policy=policy, version=version, reasons=["MISSING_RETENTION_ANCHOR"],
            details={"policy_id": str(policy.id), "policy_version": version.version},
        )
    expiry = compute_expiry(anchor_ts, int(rules["retention_days"]))
    archive_after = rules.get("archive_after_days")
    archive_expiry = (
        compute_expiry(anchor_ts, int(archive_after)) if archive_after is not None else None
    )
    reasons: list[str] = []
    details: dict = {
        "policy_id": str(policy.id), "policy_version": version.version,
        "retention_days": int(rules["retention_days"]),
    }
    if moment < expiry:
        reasons.append("RETENTION_PERIOD_NOT_REACHED")
    holds = holds_blocking(db, resource_type, resource_id, scope, moment)
    if holds:
        reasons.append("ACTIVE_HOLD")
        details["hold_ids"] = sorted(str(hold.id) for hold in holds)
    dependencies: dict = {}
    if resource_type == "EVIDENCE":
        dependencies = evidence_dependencies(db, resource_id)
        if dependencies["open_cases"]:
            reasons.append("OPEN_REVIEW_CASE")
            details["open_case_ids"] = sorted(str(row.id) for row in dependencies["open_cases"])
        if dependencies["unresolved_requests"]:
            reasons.append("UNRESOLVED_REQUEST")
            details["unresolved_request_ids"] = sorted(
                str(row.id) for row in dependencies["unresolved_requests"])
        if dependencies["fusion_runs"]:
            reasons.append("ACTIVE_DEPENDENCY")
            details["fusion_run_ids"] = sorted(
                str(row.id) for row in dependencies["fusion_runs"])
        derived = (
            dependencies["results"] + dependencies["matches"]
            + dependencies["detections"] + dependencies["active_edges"]
        )
        if derived and not rules.get("allow_derived_cleanup", False):
            reasons.append("ACTIVE_DEPENDENCY")
            details["derived_count"] = len(derived)
        elif derived:
            details["derived_cleanup_count"] = len(derived)
    archive_eligible = (
        archive_expiry is not None and moment >= archive_expiry and not holds
        and resource_type == "EVIDENCE"
    )
    deletion_eligible = not reasons and resource_type == "EVIDENCE"
    if resource_type != "EVIDENCE":
        deletion_eligible = False
        if not reasons:
            reasons.append("EXECUTION_NOT_SUPPORTED")
    if deletion_eligible:
        state = "ELIGIBLE_FOR_DELETION"
    elif archive_eligible:
        state = "ELIGIBLE_FOR_ARCHIVE"
    else:
        state = "ACTIVE"
    return _evaluation(
        moment, state=state, anchor=anchor, anchor_ts=anchor_ts, expiry=expiry,
        policy=policy, version=version, reasons=reasons, details=details,
        archive_eligible=archive_eligible, deletion_eligible=deletion_eligible,
    )


def _evaluation(
    moment, *, state, anchor, anchor_ts, expiry, policy, version, reasons, details,
    archive_eligible=False, deletion_eligible=False,
):
    def _iso(value):
        return value.isoformat() if isinstance(value, datetime) else value

    return {
        "eligible": deletion_eligible,
        "archive_eligible": archive_eligible,
        "deletion_eligible": deletion_eligible,
        "state": state,
        "anchor": anchor,
        "anchor_timestamp": _iso(anchor_ts),
        "expiry_timestamp": _iso(expiry),
        "policy_id": str(policy.id) if policy else None,
        "policy_version": version.version if version else None,
        "blocking_reasons": list(reasons),
        "details": details,
        "evaluated_at": moment.isoformat(),
    }


def _applicable_policies(db: Session, resource_type: str, scope: dict, moment):
    """Policies matching type + scope with ACTIVE in-window versions."""
    candidates = []
    for policy, version in retention_repo.active_version_candidates(db, resource_type, moment):
        level = _scope_match(policy, scope)
        if level is None:
            continue
        candidates.append({
            "policy": policy, "version": version, "scope_specificity": level,
        })
    candidates.sort(key=lambda item: (-item["scope_specificity"], str(item["policy"].id)))
    return candidates


def _scope_match(policy, scope: dict) -> int | None:
    """Specificity level when a policy covers a resource scope (else None)."""
    if policy.scope_type == "GLOBAL":
        return 0
    if policy.scope_type == "PROJECT":
        if scope.get("project_id") and str(policy.project_id) == scope["project_id"]:
            return 3
        return None
    if policy.scope_type == "ORGANIZATIONAL_UNIT":
        if (scope.get("organizational_unit_id")
                and str(policy.organizational_unit_id) == scope["organizational_unit_id"]):
            return 2
        return None
    if policy.scope_type == "ORGANIZATION":
        if (scope.get("organization_id")
                and str(policy.organization_id) == scope["organization_id"]):
            return 1
        return None
    return None


def _holds_for_generic(db, resource_type, resource_id, scope, moment):
    return holds_blocking(db, resource_type, resource_id, scope, moment)


# ---------------------------------------------------------------------------
# Holds (first-class, history preserved, never deleted)
# ---------------------------------------------------------------------------


def create_hold(
    db: Session, *, scope: str, reason: str, resource_type: str | None = None,
    resource_id: str | None = None, project_id: str | None = None,
    claim_id: str | None = None, case_id: str | None = None,
    organization_id: str | None = None, authority: str | None = None,
    expires_at: datetime | None = None, created_by: str | None = None,
):
    """Create a hold (RETENTION_HOLD_CREATED audit; blocks deletion)."""
    if scope not in ("RESOURCE", "PROJECT", "CASE", "CLAIM", "ORGANIZATION"):
        raise ValueError(f"Unknown hold scope: {scope!r}")
    if reason is None or not str(reason).strip():
        raise ValueError("Hold reason is required and must not be empty")
    resource_type = resource_type or None
    if resource_type is not None and resource_type not in RESOURCE_TYPES:
        raise ValueError(f"Unknown resource type: {resource_type!r}")
    resource_id = _optional_uuid(resource_id, "resource_id")
    project_id = _optional_uuid(project_id, "project_id")
    claim_id = _optional_uuid(claim_id, "claim_id")
    case_id = _optional_uuid(case_id, "case_id")
    organization_id = _optional_uuid(organization_id, "organization_id")
    if scope == "RESOURCE" and (resource_type is None or resource_id is None):
        raise ValueError("RESOURCE holds require resource_type and resource_id")
    if scope == "PROJECT" and project_id is None:
        raise ValueError("PROJECT holds require project_id")
    if scope == "CASE" and case_id is None:
        raise ValueError("CASE holds require case_id")
    if scope == "CLAIM" and claim_id is None:
        raise ValueError("CLAIM holds require claim_id")
    if scope == "ORGANIZATION" and organization_id is None:
        raise ValueError("ORGANIZATION holds require organization_id")
    if project_id is not None and db.query(Project).filter(
        Project.id == project_id
    ).one_or_none() is None:
        raise LookupError(f"Project not found: {project_id}")
    if claim_id is not None and db.query(Claim).filter(
        Claim.id == claim_id
    ).one_or_none() is None:
        raise LookupError(f"Claim not found: {claim_id}")
    if case_id is not None:
        from backend.db.models import ReviewCase as _Case

        if db.query(_Case).filter(_Case.id == case_id).one_or_none() is None:
            raise LookupError(f"Review case not found: {case_id}")
    if organization_id is not None and db.query(Organization).filter(
        Organization.id == organization_id
    ).one_or_none() is None:
        raise LookupError(f"Organization not found: {organization_id}")
    if resource_id is not None and resource_type == "EVIDENCE":
        if db.query(Evidence).filter(Evidence.id == resource_id).one_or_none() is None:
            raise LookupError(f"EVIDENCE not found: {resource_id}")
    if expires_at is not None:
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
    row = retention_repo.insert_hold(
        db, scope=scope, resource_type=resource_type, resource_id=resource_id,
        project_id=project_id, claim_id=claim_id, case_id=case_id,
        organization_id=organization_id, reason=str(reason).strip(),
        authority=authority, expires_at=expires_at,
        created_by=_optional_uuid(created_by, "created_by"),
    )
    audit_service.append_event(
        db, event_type="RETENTION_HOLD_CREATED", action="create",
        resource_type="retention_holds", resource_id=row.id,
        actor_id=_optional_uuid(created_by, "created_by"), project_id=project_id,
        payload={"hold_id": row.id, "scope": scope, "reason": str(reason).strip()},
        source="retention_service",
    )
    try:
        from backend.services import notification as notif_service

        notif_service.emit_notification_event(
            db,
            event_type="RETENTION_HOLD_CREATED",
            aggregate_type="RETENTION_HOLD",
            aggregate_id=str(row.id),
            payload={
                "hold_id": str(row.id),
                "scope": scope,
                "reason": str(reason).strip(),
                "project_id": str(project_id) if project_id else None,
                "resource_type": "retention",
                "resource_id": str(row.id),
            },
        )
    except Exception as exc:
        logger.warning("Failed to emit notification for hold %s: %s", row.id, exc)
    db.commit()
    db.refresh(row)
    return row


def release_hold(db: Session, hold_id: str, release_reason: str,
                 released_by: str | None = None):
    """Release a hold (history preserved; release itself audited)."""
    hold_id = _require_uuid(hold_id, "hold_id")
    hold = retention_repo.get_hold(db, hold_id)
    if hold is None:
        raise LookupError(f"Retention hold not found: {hold_id}")
    if hold.status != "ACTIVE":
        raise ValueError(f"Only ACTIVE holds can be released (current: {hold.status})")
    if release_reason is None or not str(release_reason).strip():
        raise ValueError("Release reason is required and must not be empty")
    hold.status = "RELEASED"
    hold.released_by = _optional_uuid(released_by, "released_by")
    hold.release_reason = str(release_reason).strip()
    hold.released_at = utc_now()
    audit_service.append_event(
        db, event_type="RETENTION_HOLD_RELEASED", action="release",
        resource_type="retention_holds", resource_id=hold.id,
        actor_id=_optional_uuid(released_by, "released_by"), project_id=None,
        payload={"hold_id": hold.id, "release_reason": hold.release_reason},
        source="retention_service",
    )
    try:
        from backend.services import notification as notif_service

        notif_service.emit_notification_event(
            db,
            event_type="RETENTION_HOLD_RELEASED",
            aggregate_type="RETENTION_HOLD",
            aggregate_id=str(hold.id),
            payload={
                "hold_id": str(hold.id),
                "release_reason": hold.release_reason,
                "project_id": str(hold.project_id) if hold.project_id else None,
                "resource_type": "retention",
                "resource_id": str(hold.id),
            },
        )
    except Exception as exc:
        logger.warning("Failed to emit notification for hold release %s: %s", hold.id, exc)
    db.commit()
    db.refresh(hold)
    return hold


def cancel_hold(db: Session, hold_id: str, actor_id: str | None = None):
    """Cancel a hold (terminal CANCELLED state; record retained)."""
    hold_id = _require_uuid(hold_id, "hold_id")
    hold = retention_repo.get_hold(db, hold_id)
    if hold is None:
        raise LookupError(f"Retention hold not found: {hold_id}")
    if hold.status != "ACTIVE":
        raise ValueError(f"Only ACTIVE holds can be cancelled (current: {hold.status})")
    hold.status = "CANCELLED"
    hold.released_by = _optional_uuid(actor_id, "actor_id")
    hold.released_at = utc_now()
    audit_service.append_event(
        db, event_type="RETENTION_HOLD_RELEASED", action="cancel",
        resource_type="retention_holds", resource_id=hold.id,
        actor_id=_optional_uuid(actor_id, "actor_id"), project_id=None,
        payload={"hold_id": hold.id, "mode": "cancel"},
        source="retention_service",
    )
    db.commit()
    db.refresh(hold)
    return hold


def list_holds(db: Session, *, status: str | None = None,
               project_id: str | None = None, limit: int = 50, offset: int = 0):
    if status is not None and status not in HOLD_STATUSES:
        raise ValueError(f"Unknown hold status: {status!r}")
    if limit < 1 or offset < 0:
        raise ValueError("Invalid pagination")
    query = retention_repo.list_holds_query(
        db, status=status,
        project_id=_optional_uuid(project_id, "project_id"),
    )
    return query.offset(offset).limit(limit).all(), query.count()


# ---------------------------------------------------------------------------
# Archive / restore / delete execution (EVIDENCE only in V1)
# ---------------------------------------------------------------------------


def _locate_object(storage, storage_key: str) -> str | None:
    """Find which configured bucket currently holds a key (None if absent)."""
    if storage.object_exists(storage.quarantine_bucket, storage_key):
        return storage.quarantine_bucket
    if storage.object_exists(storage.evidence_bucket, storage_key):
        return storage.evidence_bucket
    return None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fail_operation(db, operation, error: Exception):
    operation.status = "FAILED"
    operation.error = f"{type(error).__name__}: {error}"
    operation.completed_at = utc_now()
    db.commit()
    db.refresh(operation)
    return operation


def archive_evidence(db: Session, evidence_id: str, actor_id: str | None,
                     storage=None) -> dict:
    """Move an evidence object to archive storage (logical retention kept).

    Idempotent: already-ARCHIVED resources return ALREADY_ARCHIVED without
    duplicate moves. SHA-256 verified before and after the move.
    """
    from backend.services.storage import StorageService

    evidence_id = _require_uuid(evidence_id, "evidence_id")
    storage = storage or StorageService()
    evaluation = evaluate(db, "EVIDENCE", evidence_id)
    state_row = retention_repo.get_state(db, "EVIDENCE", evidence_id)
    if state_row is not None and state_row.state == "ARCHIVED":
        return {"result": "ALREADY_ARCHIVED", "evaluation": evaluation,
                "storage_key": state_row.previous_storage_key}
    if not evaluation["archive_eligible"]:
        raise ValueError(
            "Archive not eligible: "
            + ", ".join(evaluation["blocking_reasons"] or ["policy conditions unmet"])
        )
    operation = retention_repo.insert_operation(
        db, resource_type="EVIDENCE", resource_id=evidence_id, operation="ARCHIVE",
        policy_version_id=None, actor_id=_optional_uuid(actor_id, "actor_id"),
        details={"evaluation": evaluation},
    )
    db.flush()
    try:
        evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
        if evidence is None:
            raise LookupError(f"EVIDENCE not found: {evidence_id}")
        source_bucket = _locate_object(storage, evidence.storage_key)
        if source_bucket is None:
            raise ValueError("Evidence object is missing from storage; cannot archive")
        before = storage.get_object_bytes(source_bucket, evidence.storage_key)
        if evidence.sha256 and _sha256_bytes(before) != evidence.sha256:
            raise ValueError("Storage object identity mismatch; refusing to archive")
        archive_key = f"{ARCHIVE_PREFIX}/{evidence_id}/original"
        storage.copy_object(source_bucket, evidence.storage_key,
                            storage.evidence_bucket, archive_key)
        after = storage.get_object_bytes(storage.evidence_bucket, archive_key)
        if after != before:
            try:
                storage.delete_object(storage.evidence_bucket, archive_key)
            except Exception:
                pass
            raise ValueError("Archive copy identity mismatch; source left untouched")
        storage.delete_object(source_bucket, evidence.storage_key)
        previous_key = f"{source_bucket}:{evidence.storage_key}"
        evidence.storage_key = archive_key
        retention_repo.upsert_state(
            db, resource_type="EVIDENCE", resource_id=evidence_id,
            project_id=str(evidence.project_id) if evidence.project_id else None,
            organization_id=None, state="ARCHIVED",
            policy_version_id=None,
            anchor=evaluation["anchor"], anchor_timestamp=_parse_dt(evaluation["anchor_timestamp"]),
            expiry_timestamp=_parse_dt(evaluation["expiry_timestamp"]),
            previous_storage_key=previous_key, evaluated_at=utc_now(),
        )
        operation.status = "COMPLETED"
        operation.completed_at = utc_now()
        operation.details = {**operation.details, "archive_key": archive_key,
                             "previous_storage_key": previous_key}
        audit_service.append_event(
            db, event_type="RESOURCE_ARCHIVED", action="archive",
            resource_type="evidence", resource_id=evidence_id, actor_id=None,
            project_id=str(evidence.project_id) if evidence.project_id else None,
            payload={"evidence_id": evidence_id, "archive_key": archive_key,
                     "sha256": evidence.sha256},
            source="retention_service",
        )
        try:
            from backend.services import webhook as webhook_service

            webhook_service.enqueue_webhook_event(
                db,
                event_type="retention.archived",
                aggregate_type="RETENTION",
                aggregate_id=str(evidence_id),
                project_id=str(evidence.project_id) if evidence.project_id else None,
                data={"resource_type": "evidence", "evidence_id": str(evidence_id)},
            )
        except Exception as exc:
            logger.warning("Failed to emit webhook for archived resource %s: %s", evidence_id, exc)
        db.commit()
    except Exception as error:
        db.rollback()
        _fail_operation(db, retention_repo.insert_operation(
            db, resource_type="EVIDENCE", resource_id=evidence_id, operation="ARCHIVE",
            policy_version_id=None,
            actor_id=_optional_uuid(actor_id, "actor_id"),
            details={"evaluation": evaluation}), error)
        logger.exception("archive failed evidence_id=%s", evidence_id)
        raise
    db.refresh(operation)
    return {"result": "ARCHIVED", "operation_id": operation.id,
            "storage_key": archive_key, "evaluation": evaluation}


def restore_evidence(db: Session, evidence_id: str, actor_id: str | None,
                     storage=None) -> dict:
    """Restore an archived object to its recorded previous location."""
    from backend.services.storage import StorageService

    evidence_id = _require_uuid(evidence_id, "evidence_id")
    storage = storage or StorageService()
    state_row = retention_repo.get_state(db, "EVIDENCE", evidence_id)
    if state_row is None or state_row.state != "ARCHIVED":
        return {"result": "NOT_ARCHIVED"}
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    if evidence is None:
        raise LookupError(f"EVIDENCE not found: {evidence_id}")
    previous = state_row.previous_storage_key or ""
    previous_bucket, _, previous_key = previous.partition(":")
    if previous_bucket not in (storage.quarantine_bucket, storage.evidence_bucket) or not previous_key:
        raise ValueError("Archived location record is invalid; cannot restore safely")
    operation = retention_repo.insert_operation(
        db, resource_type="EVIDENCE", resource_id=evidence_id, operation="RESTORE",
        policy_version_id=None, actor_id=_optional_uuid(actor_id, "actor_id"),
        details={"previous_storage_key": previous},
    )
    db.flush()
    try:
        current_bucket = _locate_object(storage, evidence.storage_key)
        if current_bucket is None:
            raise ValueError("Archived object is missing from storage; cannot restore")
        data = storage.get_object_bytes(current_bucket, evidence.storage_key)
        if evidence.sha256 and _sha256_bytes(data) != evidence.sha256:
            raise ValueError("Archived object identity mismatch; refusing to restore")
        storage.copy_object(current_bucket, evidence.storage_key,
                            previous_bucket, previous_key)
        storage.delete_object(current_bucket, evidence.storage_key)
        evidence.storage_key = previous_key
        retention_repo.upsert_state(
            db, resource_type="EVIDENCE", resource_id=evidence_id,
            project_id=str(evidence.project_id) if evidence.project_id else None,
            organization_id=None, state="ACTIVE", policy_version_id=None,
            anchor=None, anchor_timestamp=None, expiry_timestamp=None,
            previous_storage_key=None, evaluated_at=utc_now(),
        )
        operation.status = "COMPLETED"
        operation.completed_at = utc_now()
        audit_service.append_event(
            db, event_type="RESOURCE_RESTORED", action="restore",
            resource_type="evidence", resource_id=evidence_id, actor_id=None,
            project_id=str(evidence.project_id) if evidence.project_id else None,
            payload={"evidence_id": evidence_id, "storage_key": previous_key,
                     "sha256": evidence.sha256},
            source="retention_service",
        )
        db.commit()
    except Exception as error:
        db.rollback()
        _fail_operation(db, retention_repo.insert_operation(
            db, resource_type="EVIDENCE", resource_id=evidence_id, operation="RESTORE",
            policy_version_id=None,
            actor_id=_optional_uuid(actor_id, "actor_id"), details={}), error)
        logger.exception("restore failed evidence_id=%s", evidence_id)
        raise
    db.refresh(operation)
    return {"result": "RESTORED", "operation_id": operation.id,
            "storage_key": previous_key}


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def delete_evidence(db: Session, evidence_id: str, actor_id: str | None,
                    storage=None) -> dict:
    """Controlled two-phase deletion (re-evaluated under a row lock).

    Already-deleted resources return ALREADY_DELETED when a COMPLETED
    deletion operation exists; otherwise missing resources are 404s.
    Derived intelligence is removed only when the policy explicitly allows
    it; fusion history always blocks; graph edges are INVALIDATED (history
    preserved), never silently deleted.
    """
    from sqlalchemy.exc import IntegrityError as _IntegrityError

    from backend.services.storage import StorageService
    from backend.services import evidence_graph as graph_service

    evidence_id = _require_uuid(evidence_id, "evidence_id")
    storage = storage or StorageService()
    operation = retention_repo.insert_operation(
        db, resource_type="EVIDENCE", resource_id=evidence_id, operation="DELETE",
        policy_version_id=None,
        actor_id=_optional_uuid(actor_id, "actor_id"), details={},
    )
    db.flush()
    # Emit DELETION_REQUESTED audit event before evaluation
    evidence_for_audit = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    audit_service.append_event(
        db, event_type="DELETION_REQUESTED", action="delete",
        resource_type="evidence", resource_id=evidence_id,
        actor_id=_optional_uuid(actor_id, "actor_id"),
        project_id=str(evidence_for_audit.project_id) if evidence_for_audit and evidence_for_audit.project_id else None,
        payload={"evidence_id": evidence_id},
        source="retention_service",
    )
    try:
        evidence = (
            db.query(Evidence).filter(Evidence.id == evidence_id)
            .with_for_update().one_or_none()
        )
        if evidence is None:
            if retention_repo.completed_delete_for(db, "EVIDENCE", evidence_id) is not None:
                operation.status = "COMPLETED"
                operation.completed_at = utc_now()
                operation.details = {"result": "ALREADY_DELETED"}
                db.commit()
                db.refresh(operation)
                return {"result": "ALREADY_DELETED", "operation_id": operation.id}
            raise LookupError(f"EVIDENCE not found: {evidence_id}")
        evaluation = evaluate(db, "EVIDENCE", evidence_id)
        if not evaluation["deletion_eligible"]:
            operation.status = "FAILED"
            operation.error = "Deletion blocked: " + ", ".join(
                evaluation["blocking_reasons"] or ["policy conditions unmet"])
            operation.completed_at = utc_now()
            audit_service.append_event(
                db, event_type="DELETION_BLOCKED", action="delete",
                resource_type="evidence", resource_id=evidence_id,
                actor_id=_optional_uuid(actor_id, "actor_id"),
                project_id=str(evidence.project_id) if evidence.project_id else None,
                payload={"evidence_id": evidence_id,
                         "blocking_reasons": evaluation["blocking_reasons"]},
                source="retention_service",
            )
            db.commit()
            db.refresh(operation)
            raise ValueError(
                "Deletion blocked: " + ", ".join(evaluation["blocking_reasons"]))
        details = {
            "evaluation": evaluation,
            "sha256": evidence.sha256,
            "storage_key": evidence.storage_key,
        }
        bucket = _locate_object(storage, evidence.storage_key)
        if bucket is not None:
            storage.delete_object(bucket, evidence.storage_key)
            details["storage_deleted"] = f"{bucket}:{evidence.storage_key}"
        else:
            details["storage_deleted"] = None
        _cleanup_derived(db, evidence_id)
        project_id = str(evidence.project_id) if evidence.project_id else None
        db.query(EvidenceMetadata).filter(
            EvidenceMetadata.evidence_id == evidence_id).delete(synchronize_session=False)
        db.query(Evidence).filter(Evidence.id == evidence_id).delete(synchronize_session=False)
        retention_repo.upsert_state(
            db, resource_type="EVIDENCE", resource_id=evidence_id,
            project_id=project_id, organization_id=None, state="DELETED",
            policy_version_id=None, anchor=evaluation["anchor"],
            anchor_timestamp=_parse_dt(evaluation["anchor_timestamp"]),
            expiry_timestamp=_parse_dt(evaluation["expiry_timestamp"]),
            previous_storage_key=None, evaluated_at=utc_now(),
        )
        operation.status = "COMPLETED"
        operation.completed_at = utc_now()
        operation.details = details
        audit_service.append_event(
            db, event_type="RESOURCE_DELETED", action="delete",
            resource_type="evidence", resource_id=evidence_id,
            actor_id=_optional_uuid(actor_id, "actor_id"), project_id=project_id,
            payload={"evidence_id": evidence_id, "sha256": details["sha256"]},
            source="retention_service",
        )
        try:
            from backend.services import webhook as webhook_service

            webhook_service.enqueue_webhook_event(
                db,
                event_type="retention.deleted",
                aggregate_type="RETENTION",
                aggregate_id=str(evidence_id),
                project_id=str(project_id) if project_id else None,
                data={"resource_type": "evidence", "evidence_id": str(evidence_id)},
            )
        except Exception as exc:
            logger.warning("Failed to emit webhook for deleted resource %s: %s", evidence_id, exc)
        db.commit()
    except (LookupError, ValueError):
        raise
    except _IntegrityError as error:
        db.rollback()
        _fail_operation(db, retention_repo.insert_operation(
            db, resource_type="EVIDENCE", resource_id=evidence_id, operation="DELETE",
            policy_version_id=None,
            actor_id=_optional_uuid(actor_id, "actor_id"), details={}), error)
        raise
    except Exception as error:
        db.rollback()
        _fail_operation(db, retention_repo.insert_operation(
            db, resource_type="EVIDENCE", resource_id=evidence_id, operation="DELETE",
            policy_version_id=None,
            actor_id=_optional_uuid(actor_id, "actor_id"), details={}), error)
        logger.exception("delete failed evidence_id=%s", evidence_id)
        raise
    db.refresh(operation)
    return {"result": "DELETED", "operation_id": operation.id}


def _cleanup_derived(db: Session, evidence_id: str) -> dict:
    """Remove derived intelligence rows and invalidate ACTIVE graph edges.

    Only called when the evaluated policy explicitly allows derived
    cleanup; fusion runs always block before this point, so history there
    is never touched.
    """
    from backend.db.models import AnalysisJob as _Job
    from backend.db.models import AnalysisResult as _Result
    from backend.db.models import VisionDetection as _Detection

    counts: dict[str, int] = {}
    job_ids = [row[0] for row in db.query(_Job.id).filter(
        _Job.evidence_id == evidence_id).all()]
    result_ids = []
    if job_ids:
        result_ids = [row[0] for row in db.query(_Result.id).filter(
            _Result.job_id.in_(job_ids)).all()]
        counts["detections"] = db.query(_Detection).filter(
            _Detection.analysis_result_id.in_(result_ids)).delete(
            synchronize_session=False) if result_ids else 0
        counts["analysis_results"] = db.query(_Result).filter(
            _Result.job_id.in_(job_ids)).delete(synchronize_session=False)
        counts["analysis_jobs"] = db.query(_Job).filter(
            _Job.id.in_(job_ids)).delete(synchronize_session=False)
    else:
        counts.update({"detections": 0, "analysis_results": 0, "analysis_jobs": 0})
    counts["duplicate_matches"] = db.query(DuplicateMatch).filter(
        (DuplicateMatch.evidence_id == evidence_id)
        | (DuplicateMatch.matched_evidence_id == evidence_id)).delete(
        synchronize_session=False)
    invalidated = 0
    try:
        from backend.db.models import GraphNode as _Node
        from backend.services import evidence_graph as graph_service

        node = graph_service.resolve_node(db, "EVIDENCE", evidence_id, create=False)
        if node is not None:
            rows, _ = graph_service.list_for_entity(
                db, "EVIDENCE", evidence_id, direction="both",
                relationship_status="ACTIVE", limit=1000, offset=0)
            for row in rows:
                graph_service.set_relationship_status(db, row.id, "INVALIDATED")
                invalidated += 1
    except (ValueError, LookupError):
        pass
    counts["graph_edges_invalidated"] = invalidated
    return counts


# ---------------------------------------------------------------------------
# Sweep (worker-suitable, explicit opt-in for deletion)
# ---------------------------------------------------------------------------


def run_sweep_once(db: Session, storage=None, *, actor_id: str | None = None,
                   auto_delete: bool = False, limit: int = 200) -> dict:
    """Evaluate indexed expiry candidates; archive eligible, optionally delete.

    Deletion only runs with explicit ``auto_delete=True``. Every action is
    audited through the operation it creates. Returns deterministic stats.
    """
    from backend.services.storage import StorageService

    storage = storage or StorageService()
    moment = utc_now()
    stats = {"evaluated": 0, "archived": 0, "deleted": 0, "blocked": 0, "failed": 0,
             "resource_ids": []}
    for state_row in retention_repo.states_expiring_before(db, moment, limit=limit):
        stats["evaluated"] += 1
        stats["resource_ids"].append(str(state_row.resource_id))
        try:
            evaluation = evaluate(db, state_row.resource_type, str(state_row.resource_id),
                                  moment)
        except (LookupError, ValueError):
            stats["failed"] += 1
            continue
        try:
            if evaluation["archive_eligible"] and state_row.state != "ARCHIVED":
                archive_evidence(db, str(state_row.resource_id), actor_id, storage)
                stats["archived"] += 1
            elif evaluation["deletion_eligible"] and auto_delete:
                delete_evidence(db, str(state_row.resource_id), actor_id, storage)
                stats["deleted"] += 1
            elif not evaluation["archive_eligible"] and not evaluation["deletion_eligible"]:
                stats["blocked"] += 1
        except (LookupError, ValueError):
            stats["blocked"] += 1
        except Exception:
            logger.exception("sweep failed resource=%s:%s", state_row.resource_type,
                             state_row.resource_id)
            stats["failed"] += 1
    stats["resource_ids"] = sorted(set(stats["resource_ids"]))
    logger.info("retention sweep evaluated=%d archived=%d deleted=%d blocked=%d failed=%d",
                stats["evaluated"], stats["archived"], stats["deleted"],
                stats["blocked"], stats["failed"])
    return stats

