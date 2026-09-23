"""BE-013 review-case service: policy-gated generation + human workflow.

Consumes persisted BE-011 fusion outputs only (assessment/priority values
are copied, never recalculated). A case means a human review workflow was
initiated because configured conditions indicate investigation may be
useful — never a determination of truth, fraud, or authenticity, and the
automatic engine never populates human decision fields.

Conventions: ``ValueError`` for invalid input/semantic failures,
``LookupError`` for missing rows. Generation is idempotent per fusion run
(DB partial-unique + IntegrityError retry); workflow transitions are
explicit and append-only.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    CASE_GENERATION_DEFAULT_CONFIG_VERSION,
    CASE_GENERATION_METHOD,
    CASE_GENERATION_METHOD_VERSION,
    REVIEW_CASE_DECISIONS,
    REVIEW_CASE_ORIGINS,
    REVIEW_CASE_STATUSES,
    Claim,
    Evidence,
    IntegrityAssessment,
    ReviewCase,
    ReviewPriority,
)
from backend.repositories import fusion as fusion_repo
from backend.repositories import review_case as case_repo
from backend.services import audit_ledger as audit_service


logger = logging.getLogger(__name__)

ORIGINS = frozenset(REVIEW_CASE_ORIGINS)
STATUSES = frozenset(REVIEW_CASE_STATUSES)
DECISIONS = frozenset(REVIEW_CASE_DECISIONS)

METHOD = CASE_GENERATION_METHOD
METHOD_VERSION = CASE_GENERATION_METHOD_VERSION
DEFAULT_CONFIG_VERSION = CASE_GENERATION_DEFAULT_CONFIG_VERSION

RESULT_CREATED = "CASE_CREATED"
RESULT_EXISTS = "CASE_ALREADY_EXISTS"
RESULT_NOT_ELIGIBLE = "NOT_ELIGIBLE"
RESULT_UNAVAILABLE = "UNAVAILABLE"

# Domain event -> audit event mapping. Only explicit vocabulary entries are
# emitted; other workflow events stay domain history (incremental by design).
CASE_AUDIT_TYPES = {
    "CASE_CREATED": "REVIEW_CASE_CREATED",
    "ASSIGNED": "REVIEW_CASE_ASSIGNED",
    "DECISION_RECORDED": "REVIEW_CASE_DECISION_RECORDED",
    "ESCALATED": "REVIEW_CASE_ESCALATED",
    "RESOLVED": "REVIEW_CASE_RESOLVED",
    "REOPENED": "REVIEW_CASE_REOPENED",
}


def _audit_case_event(
    db: Session, case, event_type: str, actor_id: str | None,
    action: str, extra_payload: dict | None = None,
) -> None:
    """Emit the audit twin of a case event in the same transaction."""
    audit_type = CASE_AUDIT_TYPES.get(event_type)
    if audit_type is None:
        return
    audit_service.append_event(
        db,
        event_type=audit_type,
        action=action,
        resource_type="review_cases",
        resource_id=case.id,
        actor_id=actor_id,
        project_id=str(case.project_id) if case.project_id else None,
        payload={"review_case_id": case.id, "status": case.status,
                 **(extra_payload or {})},
        source="review_case_service",
    )

# Explicit lifecycle matrix: current status -> allowed next statuses.
TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"ASSIGNED", "ESCALATED"}),
    "ASSIGNED": frozenset({"OPEN", "INVESTIGATING", "ESCALATED"}),
    "INVESTIGATING": frozenset({"DECISION_PENDING", "ESCALATED"}),
    "DECISION_PENDING": frozenset({"RESOLVED", "ESCALATED"}),
    "ESCALATED": frozenset({"ASSIGNED", "INVESTIGATING"}),
    "RESOLVED": frozenset({"OPEN"}),
}

DEFAULT_POLICY_V1: dict = {
    "version": "v1",
    "name": "case-generation-v1 defaults",
    "generate_bands": ["URGENT", "HIGH"],
    "include_normal": False,
    "dedupe_open_cases_per_target": True,
}


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
# Pure policy and lifecycle rules (unit-testable without a database)
# ---------------------------------------------------------------------------


def validate_policy(policy: dict) -> dict:
    """Validate a case-generation policy mapping (fail clearly, never clamp)."""
    if not isinstance(policy, dict):
        raise ValueError("Case-generation policy must be a mapping")
    bands = policy.get("generate_bands")
    if not isinstance(bands, list) or not bands:
        raise ValueError("Policy requires a non-empty 'generate_bands' list")
    unknown = set(bands) - {"LOW", "NORMAL", "HIGH", "URGENT"}
    if unknown:
        raise ValueError(f"Unknown priority bands in policy: {sorted(unknown)}")
    if not isinstance(policy.get("include_normal", False), bool):
        raise ValueError("Policy 'include_normal' must be a boolean")
    if not isinstance(policy.get("dedupe_open_cases_per_target", True), bool):
        raise ValueError("Policy 'dedupe_open_cases_per_target' must be a boolean")
    return policy


def evaluate_policy(
    assessment_value: str | None,
    priority_band: str | None,
    policy: dict,
) -> tuple[bool, str]:
    """Decide eligibility from persisted fusion outputs (no recalculation).

    Returns ``(eligible, reason)``. Band-driven only by documented V1
    design; the assessment value is preserved in the snapshot, never gated.
    """
    bands = set(policy.get("generate_bands", []))
    if priority_band in bands:
        return True, "BAND_ELIGIBLE"
    if priority_band == "NORMAL" and policy.get("include_normal", False):
        return True, "NORMAL_INCLUDED"
    return False, "BAND_NOT_INCLUDED"


def validate_transition(from_status: str, to_status: str) -> None:
    """Reject any lifecycle move outside the explicit matrix (no DB touch)."""
    if from_status not in STATUSES:
        raise ValueError(f"Unknown case status: {from_status!r}")
    if to_status not in STATUSES:
        raise ValueError(f"Unknown case status: {to_status!r}")
    if to_status not in TRANSITIONS.get(from_status, frozenset()):
        raise ValueError(f"Invalid transition: {from_status} -> {to_status}")


def validate_decision(decision: str | None, rationale: str | None) -> tuple[str, str]:
    """Human decisions must be explicit, vocabular-bound, and reasoned."""
    if decision not in DECISIONS:
        raise ValueError(
            f"Invalid decision: {decision!r} (expected one of {sorted(DECISIONS)})"
        )
    if rationale is None or not str(rationale).strip():
        raise ValueError("Decision rationale is required and must not be empty")
    return decision, str(rationale).strip()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def get_policy(db: Session, version: str | None = None) -> tuple[object, dict]:
    """Fetch and validate the policy (default v1, created once when absent)."""
    version = version or DEFAULT_CONFIG_VERSION
    row = case_repo.get_configuration(db, version)
    if row is None:
        if version != DEFAULT_CONFIG_VERSION:
            raise LookupError(f"Case-generation configuration not found: {version}")
        row = case_repo.insert_configuration(
            db,
            version=DEFAULT_POLICY_V1["version"],
            name=DEFAULT_POLICY_V1["name"],
            configuration={
                "generate_bands": list(DEFAULT_POLICY_V1["generate_bands"]),
                "include_normal": DEFAULT_POLICY_V1["include_normal"],
                "dedupe_open_cases_per_target": DEFAULT_POLICY_V1[
                    "dedupe_open_cases_per_target"
                ],
            },
            enabled=True,
        )
        db.commit()
        db.refresh(row)
    if not row.enabled:
        raise ValueError(f"Case-generation configuration is disabled: {version}")
    return row, validate_policy(dict(row.configuration or {}))


def create_policy_configuration(
    db: Session, *, version: str, name: str, configuration: dict, enabled: bool = True
):
    """Store a new immutable policy version (validated; never mutated later)."""
    if not version or not str(version).strip():
        raise ValueError("Configuration version is required")
    if not name or not str(name).strip():
        raise ValueError("Configuration name is required")
    if case_repo.get_configuration(db, version) is not None:
        raise ValueError(f"Case-generation configuration already exists: {version}")
    payload = validate_policy(configuration)
    row = case_repo.insert_configuration(
        db, version=version, name=str(name).strip(), configuration=dict(payload),
        enabled=enabled,
    )
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _target_scope(db: Session, target_type: str, target_id: str) -> dict:
    """Resolve project/claim/evidence scope for a fusion target (read-only)."""
    if target_type == "CLAIM":
        claim = db.query(Claim).filter(Claim.id == target_id).one_or_none()
        if claim is None:
            raise LookupError(f"CLAIM not found: {target_id}")
        return {
            "project_id": str(claim.project_id),
            "claim_id": target_id,
            "evidence_id": None,
        }
    evidence = db.query(Evidence).filter(Evidence.id == target_id).one_or_none()
    if evidence is None:
        raise LookupError(f"EVIDENCE not found: {target_id}")
    return {
        "project_id": str(evidence.project_id) if evidence.project_id else None,
        "claim_id": str(evidence.claim_id) if evidence.claim_id else None,
        "evidence_id": target_id,
    }


def _fail_generation(
    db: Session, fusion_run_id: str, configuration_id: str, snapshot: dict, error: Exception
):
    row = case_repo.insert_generation_run(
        db, fusion_run_id=fusion_run_id, configuration_id=configuration_id,
        method=METHOD, method_version=METHOD_VERSION, input_snapshot=snapshot,
    )
    row.status = "FAILED"
    row.error = f"{type(error).__name__}: {error}"
    row.completed_at = utc_now()
    db.commit()
    db.refresh(row)
    return row


def generate_for_fusion(
    db: Session, fusion_run_id: str, *, policy_version: str | None = None
) -> tuple[ReviewCase | None, object, str, str]:
    """Evaluate one fusion run and create a case when policy allows.

    Returns ``(case_or_None, generation_run, result_state, reason)`` with
    result states CASE_CREATED / CASE_ALREADY_EXISTS / NOT_ELIGIBLE.
    Unusable inputs raise before any write (UNAVAILABLE). Each call appends
    a generation run except the idempotent fast path, which returns the
    existing case; concurrent winners are resolved by the DB constraint.
    """
    fusion_run_id = _require_uuid(fusion_run_id, "fusion_run_id")
    run = fusion_repo.get_run(db, fusion_run_id)
    if run is None:
        raise LookupError(f"Fusion run not found: {fusion_run_id}")
    if run.status != "COMPLETED":
        raise ValueError(
            f"CASE_GENERATION_UNAVAILABLE: fusion run {fusion_run_id} is {run.status}"
        )
    assessment = (
        db.query(IntegrityAssessment).filter_by(fusion_run_id=fusion_run_id).one_or_none()
    )
    return _generate(db, run, assessment, policy_version)


def _generate(db: Session, run, assessment, policy_version: str | None):
    priority = (
        db.query(ReviewPriority).filter(ReviewPriority.fusion_run_id == run.id).one_or_none()
    )
    if assessment is None or priority is None:
        raise ValueError(
            f"CASE_GENERATION_UNAVAILABLE: fusion run {run.id} has no persisted "
            "assessment/priority outputs"
        )
    config_row, policy = get_policy(db, policy_version)
    scope = _target_scope(db, run.target_type, str(run.target_id))

    existing = case_repo.active_system_case_for_run(db, run.id)
    if existing is not None:
        return existing, None, RESULT_EXISTS, "ACTIVE_CASE_FOR_RUN"

    eligible, reason = evaluate_policy(
        assessment.assessment_value, priority.priority, policy
    )
    snapshot = {
        "target_type": run.target_type,
        "target_id": str(run.target_id),
        "project_id": scope["project_id"],
        "fusion_run_id": run.id,
        "assessment": {
            "value": assessment.assessment_value,
            "status": assessment.assessment_status,
            "integrity_score": assessment.integrity_score,
        },
        "priority": {"band": priority.priority, "priority_score": float(priority.priority_score)},
        "policy_version": config_row.version,
        "method_version": METHOD_VERSION,
    }
    if not eligible:
        gen = case_repo.insert_generation_run(
            db, fusion_run_id=run.id, configuration_id=config_row.id,
            method=METHOD, method_version=METHOD_VERSION,
            input_snapshot={**snapshot, "eligibility_result": RESULT_NOT_ELIGIBLE,
                            "reason": reason},
        )
        gen.status = "COMPLETED"
        gen.completed_at = utc_now()
        db.commit()
        db.refresh(gen)
        return None, gen, RESULT_NOT_ELIGIBLE, reason
    if policy.get("dedupe_open_cases_per_target", True):
        open_cases = case_repo.open_cases_for_target(db, run.target_type, str(run.target_id))
        if open_cases:
            gen = case_repo.insert_generation_run(
                db, fusion_run_id=run.id, configuration_id=config_row.id,
                method=METHOD, method_version=METHOD_VERSION,
                input_snapshot={**snapshot, "eligibility_result": RESULT_NOT_ELIGIBLE,
                                "reason": "TARGET_CASE_OPEN",
                                "open_case_id": open_cases[0].id},
            )
            gen.status = "COMPLETED"
            gen.completed_at = utc_now()
            db.commit()
            db.refresh(gen)
            return None, gen, RESULT_NOT_ELIGIBLE, "TARGET_CASE_OPEN"

    snapshot = {**snapshot, "eligibility_result": RESULT_CREATED, "reason": reason,
                "triggering_conditions": {
                    "priority_band": priority.priority,
                    "assessment": assessment.assessment_value,
                }}
    try:
        gen = case_repo.insert_generation_run(
            db, fusion_run_id=run.id, configuration_id=config_row.id,
            method=METHOD, method_version=METHOD_VERSION, input_snapshot=snapshot,
        )
        case = case_repo.insert_case(
            db,
            project_id=scope["project_id"],
            claim_id=scope["claim_id"],
            evidence_id=scope["evidence_id"],
            fusion_run_id=run.id,
            case_generation_run_id=gen.id,
            origin="SYSTEM_SIGNAL",
            status="OPEN",
            priority_band=priority.priority,
            priority_value=float(priority.priority_score),
            priority_source="fusion",
            priority_config_version=run.configuration_version,
        )
        case_repo.insert_event(
            db, case_id=case.id, event_type="CASE_CREATED", from_status=None,
            to_status="OPEN", actor_id=None,
            metadata={"fusion_run_id": run.id, "policy_version": config_row.version,
                      "reason": reason},
        )
        _audit_case_event(db, case, "CASE_CREATED", None, "create",
                          {"fusion_run_id": run.id})
        _emit_case_webhook(db, case, "CREATED", {"fusion_run_id": run.id})
        gen.status = "COMPLETED"
        gen.completed_at = utc_now()
        db.commit()
    except IntegrityError:
        # Lost a concurrent insert race on the partial-unique active-case
        # key: the winner is canonical — return it idempotently.
        db.rollback()
        winner = case_repo.active_system_case_for_run(db, run.id)
        if winner is not None:
            return winner, None, RESULT_EXISTS, "ACTIVE_CASE_FOR_RUN"
        raise
    except Exception as error:
        db.rollback()
        _fail_generation(
            db, run.id, config_row.id,
            {**snapshot, "eligibility_result": "FAILED"}, error,
        )
        logger.exception("case generation failed fusion_run_id=%s", run.id)
        raise
    db.refresh(case)
    db.refresh(gen)
    logger.info("review case created case_id=%s fusion_run_id=%s", case.id, run.id)
    return case, gen, RESULT_CREATED, reason


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_case(db: Session, case_id: str) -> ReviewCase:
    case_id = _require_uuid(case_id, "case_id")
    case = case_repo.get_case(db, case_id)
    if case is None:
        raise LookupError(f"Review case not found: {case_id}")
    return case


def list_cases(
    db: Session,
    *,
    project_id: str | None = None,
    status: str | None = None,
    priority_band: str | None = None,
    origin: str | None = None,
    assigned_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    project_ids: set[str] | None = None,
):
    """Deterministic paginated case listing with optional filters."""
    if status is not None and status not in STATUSES:
        raise ValueError(f"Unknown case status: {status!r}")
    if priority_band is not None and priority_band not in {"LOW", "NORMAL", "HIGH", "URGENT"}:
        raise ValueError(f"Unknown priority band: {priority_band!r}")
    if origin is not None and origin not in ORIGINS:
        raise ValueError(f"Unknown case origin: {origin!r}")
    if limit < 1 or offset < 0:
        raise ValueError("Invalid pagination")
    query = case_repo.list_query(
        db,
        project_id=_require_uuid(project_id, "project_id") if project_id else None,
        project_ids=project_ids,
        status=status,
        priority_band=priority_band,
        origin=origin,
        assigned_to=_require_uuid(assigned_to, "assigned_to") if assigned_to else None,
    )
    return query.offset(offset).limit(limit).all(), query.count()


def case_history(db: Session, case_id: str) -> list:
    case = get_case(db, case_id)
    return case_repo.events_for_case(db, case.id)


# ---------------------------------------------------------------------------
# Workflow actions (human-driven; automatic engine never calls these)
# ---------------------------------------------------------------------------


def _apply(
    db: Session,
    case: ReviewCase,
    to_status: str,
    event_type: str,
    actor_id: str | None,
    event_metadata: dict | None = None,
    **fields,
) -> ReviewCase:
    validate_transition(case.status, to_status)
    from_status = case.status
    for name, value in fields.items():
        setattr(case, name, value)
    case.status = to_status
    if to_status == "RESOLVED":
        case.resolved_at = utc_now()
    case_repo.insert_event(
        db, case_id=case.id, event_type=event_type, from_status=from_status,
        to_status=to_status, actor_id=actor_id, metadata=event_metadata or {},
    )
    _audit_case_event(
        db, case, event_type, actor_id,
        "transition" if to_status != "RESOLVED" else "resolve",
        {"from_status": from_status, "to_status": to_status},
    )
    _emit_case_notification(db, case, event_type, event_metadata)
    _emit_case_webhook(db, case, event_type, event_metadata)
    db.commit()
    db.refresh(case)
    return case


def _emit_case_notification(
    db: Session, case: ReviewCase, event_type: str, metadata: dict | None
) -> None:
    try:
        from backend.services import notification as notif_service

        meta = metadata or {}
        notif_type = None
        payload = {
            "case_id": str(case.id),
            "project_id": str(case.project_id) if case.project_id else None,
            "priority_band": getattr(case, "priority_band", "NORMAL"),
            "resource_type": "review_case",
            "resource_id": str(case.id),
        }
        if event_type == "ASSIGNED" and case.assigned_to:
            notif_type = "REVIEW_CASE_ASSIGNED"
            payload["assigned_to"] = str(case.assigned_to)
        elif event_type == "ESCALATED":
            notif_type = "REVIEW_CASE_ESCALATED"
            payload["escalation_reason"] = meta.get("reason", "Escalated for review")
            if meta.get("escalated_to"):
                payload["recipients"] = [str(meta["escalated_to"])]
        elif event_type == "DECISION_RECORDED":
            notif_type = "REVIEW_CASE_DECISION_PENDING"
            payload["decision"] = str(case.decision)
        elif event_type == "REOPENED":
            notif_type = "REVIEW_CASE_REOPENED"
            payload["reopen_reason"] = meta.get("reason", "Case reopened")
            if case.assigned_to:
                payload["assigned_to"] = str(case.assigned_to)

        if notif_type:
            notif_service.emit_notification_event(
                db,
                event_type=notif_type,
                aggregate_type="REVIEW_CASE",
                aggregate_id=str(case.id),
                payload=payload,
            )
    except Exception as exc:
        logger.warning(
            "Failed to emit notification for case %s event %s: %s", case.id, event_type, exc
        )


def _emit_case_webhook(
    db: Session, case: ReviewCase, event_type: str, metadata: dict | None = None
) -> None:
    try:
        from backend.services import webhook as webhook_service

        wh_type = None
        if event_type in ("CREATED", "CASE_CREATED"):
            wh_type = "review_case.created"
        elif event_type == "ASSIGNED":
            wh_type = "review_case.assigned"
        elif event_type == "ESCALATED":
            wh_type = "review_case.escalated"
        elif event_type == "RESOLVED":
            wh_type = "review_case.resolved"

        if wh_type:
            webhook_service.enqueue_webhook_event(
                db,
                event_type=wh_type,
                aggregate_type="REVIEW_CASE",
                aggregate_id=str(case.id),
                project_id=str(case.project_id) if case.project_id else None,
                data={
                    "case_id": str(case.id),
                    "status": case.status,
                    "priority_band": getattr(case, "priority_band", "NORMAL"),
                    "assigned_to": str(case.assigned_to) if case.assigned_to else None,
                },
            )
    except Exception as exc:
        logger.warning(
            "Failed to emit webhook for case %s event %s: %s", case.id, event_type, exc
        )



def assign_case(db: Session, case_id: str, assigned_to: str | None, actor_id: str | None = None):
    """Assign (OPEN/ESCALATED/ASSIGNED -> ASSIGNED) or unassign (-> OPEN)."""
    case = get_case(db, case_id)
    actor_id = _optional_uuid(actor_id, "actor_id")
    if assigned_to is None:
        if case.status != "ASSIGNED":
            raise ValueError("Only an ASSIGNED case can be unassigned")
        return _apply(db, case, "OPEN", "UNASSIGNED", actor_id, {},
                      assigned_to=None, assigned_at=None)
    assignee = _require_uuid(assigned_to, "assigned_to")
    if case.status not in ("OPEN", "ESCALATED", "ASSIGNED"):
        raise ValueError(f"Cannot assign a case in status {case.status}")
    return _apply(db, case, "ASSIGNED", "ASSIGNED", actor_id,
                  {"assigned_to": assignee}, assigned_to=assignee, assigned_at=utc_now())


def start_investigation(db: Session, case_id: str, actor_id: str | None = None):
    case = get_case(db, case_id)
    return _apply(db, case, "INVESTIGATING", "INVESTIGATION_STARTED",
                  _optional_uuid(actor_id, "actor_id"), {})


def record_decision(
    db: Session, case_id: str, decision: str, rationale: str,
    decided_by: str | None = None,
):
    """Record a human decision (allowed from INVESTIGATING/DECISION_PENDING)."""
    case = get_case(db, case_id)
    if case.status not in ("INVESTIGATING", "DECISION_PENDING"):
        raise ValueError(
            f"Decisions require INVESTIGATING or DECISION_PENDING status (current: {case.status})"
        )
    decision, rationale = validate_decision(decision, rationale)
    decider = _optional_uuid(decided_by, "decided_by")
    return _apply(
        db, case, "DECISION_PENDING", "DECISION_RECORDED", decider,
        {"decision": decision},
        decision=decision, decision_rationale=rationale,
        decided_by=decider, decided_at=utc_now(),
    )


def _decision_after_reopen(db: Session, case: ReviewCase) -> bool:
    events = case_repo.events_for_case(db, case.id)
    last_reopen = -1
    for index, event in enumerate(events):
        if event.event_type == "REOPENED":
            last_reopen = index
    return any(
        event.event_type == "DECISION_RECORDED" and index > last_reopen
        for index, event in enumerate(events)
    )


def resolve_case(db: Session, case_id: str, actor_id: str | None = None):
    """Resolve only from DECISION_PENDING with a recorded human decision."""
    case = get_case(db, case_id)
    if case.status != "DECISION_PENDING":
        raise ValueError(
            f"Resolution requires DECISION_PENDING status (current: {case.status})"
        )
    if case.decision is None or not _decision_after_reopen(db, case):
        raise ValueError("Resolution requires an existing human decision")
    return _apply(db, case, "RESOLVED", "RESOLVED",
                  _optional_uuid(actor_id, "actor_id"), {"decision": case.decision})


def reopen_case(db: Session, case_id: str, actor_id: str | None = None):
    """Reopen a resolved case; prior decision stays visible in history + row."""
    case = get_case(db, case_id)
    return _apply(db, case, "OPEN", "REOPENED",
                  _optional_uuid(actor_id, "actor_id"), {})


def escalate_case(
    db: Session, case_id: str, escalated_to: str, reason: str,
    actor_id: str | None = None,
):
    """Escalate; original assignment/decision history is preserved in events."""
    case = get_case(db, case_id)
    target = _require_uuid(escalated_to, "escalated_to")
    if reason is None or not str(reason).strip():
        raise ValueError("Escalation reason is required and must not be empty")
    return _apply(
        db, case, "ESCALATED", "ESCALATED", _optional_uuid(actor_id, "actor_id"),
        {"escalated_to": target},
        escalated_to=target, escalated_at=utc_now(),
        escalation_reason=str(reason).strip(),
    )
