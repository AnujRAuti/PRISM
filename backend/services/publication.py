"""BE-022 publication, transparency & public evidence governance service.

Publication is a CONTROLLED PROJECTION of authorized information, never a
statement that the underlying evidence is true (§2). The internal intelligence
system is never serialized directly into a public response: every public
payload is assembled here from an explicit allowlist and then checked against
the prohibited-field set before it can be returned.

Governance interactions reuse the existing systems rather than forking them:
BE-015 audit, BE-016 authorization, BE-017 retention, BE-018 notifications,
BE-021 disputes/corrections, and BE-020 telemetry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    PUBLICATION_INTERNALLY_PROHIBITED_FIELDS,
    PUBLICATION_TARGET_TYPES,
    Activity,
    Claim,
    CorrectionRequest,
    Dispute,
    Evidence,
    EvidenceMetadata,
    IntegrityAssessment,
    Project,
    Publication,
    PublicationEvent,
    PublicationPolicy,
    PublicationPolicyVersion,
    ReviewCase,
)
from backend.observability import publication_metrics as metrics
from backend.repositories import publication as pub_repo

logger = logging.getLogger(__name__)


# Public-id prefix per target type (§16). Deliberately decoupled from the
# internal UUID and from any secret.
PUBLIC_ID_PREFIXES = {
    "PROJECT": "PROJ",
    "ACTIVITY": "ACT",
    "CLAIM": "CLAIM",
    "EVIDENCE": "EVD",
    "REVIEW_CASE": "CASE",
    "FUSION_ASSESSMENT": "ASMT",
}

# Visibility that a publication inherits from its source. Anything that is not
# PUBLIC is never served publicly (§10).
PRIVATE_VISIBILITY_VALUES = frozenset(
    {
        "CITIZEN_OWNED_PRIVATE",
        "OPERATIONAL",
        "INTELLIGENCE_INTERNAL",
        "ADMINISTRATIVE_SECURITY",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Audit helper (BE-015) — single audit store, bounded payload only (§26)
# ---------------------------------------------------------------------------


def _audit(
    db: Session,
    event_type: str,
    action: str,
    publication_id: str,
    actor_id: str | None,
    payload: dict,
) -> None:
    from backend.services import audit_ledger as audit_service

    audit_service.append_event(
        db,
        event_type=event_type,
        action=action,
        resource_type="publication",
        resource_id=publication_id,
        actor_id=actor_id,
        payload=payload,
        source="publication_service",
    )


def _record_event(
    db: Session,
    publication: Publication,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    actor_id: str | None,
    reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    pub_repo.insert_event(
        db,
        publication_id=publication.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_id=actor_id,
        reason=reason,
        event_metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Publication policies (§9)
# ---------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    """Normalize an Enum to its string value.

    Endpoint payloads arrive as Pydantic enums; the model columns are plain
    strings. Normalizing here keeps the service callable from both the API
    and direct service-level tests.
    """
    return value.value if hasattr(value, "value") else value


def create_publication_policy(db: Session, payload: dict, actor_id: str | None) -> tuple:
    """Create a policy (idempotent on name) with its first ACTIVE version.

    Returns ``(policy, created)``. Re-submitting an existing policy name is
    a no-op that returns the existing policy rather than raising, so a
    retried admin request cannot create a duplicate.
    """
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Policy name is required")

    existing = pub_repo.get_policy_by_name(db, name)
    if existing is not None:
        return existing, False

    allowed = [_plain(t) for t in (payload.get("allowed_target_types") or [])]
    unknown = [t for t in allowed if t not in PUBLICATION_TARGET_TYPES]
    if unknown:
        raise ValueError(f"Unknown publication target types: {unknown}")

    policy = pub_repo.insert_policy(
        db,
        name=name,
        description=payload.get("description"),
    )
    version = pub_repo.insert_policy_version(
        db,
        policy_id=policy.id,
        version=payload.get("version") or "1.0",
        status="ACTIVE",
        allowed_target_types=allowed,
        public_fields=list(payload.get("public_fields") or []),
        prohibited_fields=list(payload.get("prohibited_fields") or []),
        allow_media_exposure=bool(payload.get("allow_media_exposure", False)),
        allow_derived_intelligence=bool(payload.get("allow_derived_intelligence", False)),
        allow_review_outcomes=bool(payload.get("allow_review_outcomes", False)),
        min_authorization_level=_plain(payload.get("min_authorization_level")) or "REVIEWER",
        required_approvals=int(payload.get("required_approvals") or 1),
        require_separation_of_duties=bool(payload.get("require_separation_of_duties", True)),
        location_precision=_plain(payload.get("location_precision")) or "HIDDEN",
        retention_publication_duration_days=payload.get(
            "retention_publication_duration_days"
        ),
        geographic_restrictions=payload.get("geographic_restrictions"),
        privacy_restrictions=payload.get("privacy_restrictions"),
        redaction_level=_plain(payload.get("redaction_level")) or "STANDARD",
        created_by=actor_id,
    )
    _audit(
        db,
        "PUBLICATION_POLICY_CREATED",
        "create",
        policy.id,
        actor_id,
        {"policy_id": policy.id, "name": name, "version": version.version},
    )
    db.commit()
    db.refresh(policy)
    return policy, True


def policy_view(policy: PublicationPolicy, version: PublicationPolicyVersion | None) -> dict:
    """Flatten policy + active version into the response shape."""
    return {
        "id": policy.id,
        "name": policy.name,
        "description": policy.description,
        "version": version.version if version else "1.0",
        "status": version.status if version else "DRAFT",
        "allowed_target_types": list(version.allowed_target_types or []) if version else [],
        "public_fields": list(version.public_fields or []) if version else [],
        "prohibited_fields": list(version.prohibited_fields or []) if version else [],
        "allow_media_exposure": bool(version.allow_media_exposure) if version else False,
        "allow_derived_intelligence": bool(version.allow_derived_intelligence) if version else False,
        "allow_review_outcomes": bool(version.allow_review_outcomes) if version else False,
        "min_authorization_level": version.min_authorization_level if version else "REVIEWER",
        "required_approvals": int(version.required_approvals) if version else 1,
        "require_separation_of_duties": bool(version.require_separation_of_duties)
        if version
        else True,
        "location_precision": version.location_precision if version else "HIDDEN",
        "retention_publication_duration_days": version.retention_publication_duration_days
        if version
        else None,
        "geographic_restrictions": version.geographic_restrictions if version else None,
        "privacy_restrictions": version.privacy_restrictions if version else None,
        "redaction_level": version.redaction_level if version else "STANDARD",
        "created_at": policy.created_at,
    }


def get_publication_policy(db: Session, policy_id: str) -> dict:
    policy = pub_repo.get_policy(db, policy_id)
    if policy is None:
        raise LookupError(f"Publication policy not found: {policy_id}")
    return policy_view(policy, pub_repo.get_active_policy_version(db, policy.id))


def list_publication_policies(db: Session) -> tuple[list[dict], int]:
    rows, total = pub_repo.list_policies(db, limit=1000, offset=0)
    return [policy_view(p, pub_repo.get_active_policy_version(db, p.id)) for p in rows], total


# ---------------------------------------------------------------------------
# Public identifiers (§16)
# ---------------------------------------------------------------------------


def ensure_public_identifier(db: Session, target_type: str, target_id: str) -> str:
    """Return the stable public id for a target, minting one if absent.

    Minted once per target and reused by every subsequent version, which is
    what makes it stable across versions (§16).
    """
    existing = pub_repo.get_identifier_for_target(db, target_type, target_id)
    if existing is not None:
        return existing.public_id
    prefix = PUBLIC_ID_PREFIXES.get(target_type, "OBJ")
    public_id = pub_repo.next_public_id(db, "POA", prefix)
    try:
        row = pub_repo.insert_identifier(
            db,
            target_type=target_type,
            target_id=target_id,
            public_id=public_id,
            namespace="POA",
            identifier_type="SEQUENTIAL",
        )
    except IntegrityError:
        # Concurrent mint for the same target: the other transaction won.
        db.rollback()
        existing = pub_repo.get_identifier_for_target(db, target_type, target_id)
        if existing is not None:
            return existing.public_id
        raise
    return row.public_id


# ---------------------------------------------------------------------------
# Releasability evaluation (§11)
# ---------------------------------------------------------------------------


def _target_row(db: Session, target_type: str, target_id: str):
    models = {
        "PROJECT": Project,
        "ACTIVITY": Activity,
        "CLAIM": Claim,
        "EVIDENCE": Evidence,
        "REVIEW_CASE": ReviewCase,
        "FUSION_ASSESSMENT": IntegrityAssessment,
    }
    model = models.get(target_type)
    if model is None:
        return None
    return db.query(model).filter(model.id == target_id).one_or_none()


def _has_active_dispute(db: Session, target_type: str, target_id: str) -> bool:
    return (
        db.query(Dispute)
        .filter(
            Dispute.target_type == target_type,
            Dispute.target_id == target_id,
            Dispute.status.in_(("OPEN", "UNDER_REVIEW", "ESCALATED")),
        )
        .first()
        is not None
    )


def _has_unresolved_correction(db: Session, target_type: str, target_id: str) -> bool:
    if target_type != "EVIDENCE":
        return False
    return (
        db.query(CorrectionRequest)
        .filter(
            CorrectionRequest.target_type == "EVIDENCE",
            CorrectionRequest.target_id == target_id,
            CorrectionRequest.status.in_(("REQUESTED", "UNDER_REVIEW", "APPROVED")),
        )
        .first()
        is not None
    )


def _retention_blockers(db: Session, target_type: str, target_id: str) -> list[str]:
    """Retention interaction (§13): publication never bypasses BE-017.

    Consulted opportunistically — if the retention tables are unavailable the
    check degrades to "no restriction" rather than blocking all publication.
    """
    from backend.db.models import RetentionHold, RetentionState

    blockers: list[str] = []
    model = {
        "PROJECT": Project,
        "ACTIVITY": Activity,
        "CLAIM": Claim,
        "EVIDENCE": Evidence,
        "REVIEW_CASE": ReviewCase,
        "FUSION_ASSESSMENT": IntegrityAssessment,
    }.get(target_type)
    if model is None:
        return blockers
    try:
        state = (
            db.query(RetentionState)
            .filter(
                RetentionState.resource_type == target_type,
                RetentionState.resource_id == target_id,
            )
            .one_or_none()
        )
        if state is not None and state.state in (
            "ELIGIBLE_FOR_DELETION",
            "DELETION_PENDING",
            "DELETED",
        ):
            blockers.append("RETENTION_RESTRICTION")
        hold = (
            db.query(RetentionHold)
            .filter(
                RetentionHold.scope == "RESOURCE",
                RetentionHold.resource_type == target_type,
                RetentionHold.resource_id == target_id,
                RetentionHold.status == "ACTIVE",
            )
            .first()
        )
        if hold is not None:
            blockers.append("LEGAL_HOLD")
    except Exception:  # pragma: no cover - retention tables absent in some setups
        logger.debug("retention check skipped", exc_info=True)
    return blockers


def check_eligibility(db: Session, publication_id: str) -> dict:
    """Deterministic releasability evaluation returning structured reasons.

    Deliberately does NOT treat low integrity or high review priority as a
    blocker (§11): publication governance is separate from truth
    determination.
    """
    publication = pub_repo.get_publication(db, publication_id)
    if publication is None:
        raise LookupError(f"Publication not found: {publication_id}")

    version = pub_repo.get_active_policy_version(db, publication.policy_id)
    blockers: list[dict] = []

    def add(code: str, detail: str | None = None) -> None:
        blockers.append({"code": code, "detail": detail})

    # 1. Target type must be on the explicit allowlist (§4).
    if publication.target_type not in PUBLICATION_TARGET_TYPES:
        add("NOT_PUBLISHABLE_TYPE", publication.target_type)
    elif version is not None and publication.target_type not in (
        version.allowed_target_types or []
    ):
        add("NOT_PUBLISHABLE_TYPE", "not in policy allowlist")

    target = _target_row(db, publication.target_type, publication.target_id)
    if target is None:
        add("SOURCE_RESTRICTION", "source object not found")

    # 2. Only PUBLIC visibility may ever be served (§10).
    if target is not None:
        visibility = getattr(target, "visibility", None)
        if visibility and visibility in PRIVATE_VISIBILITY_VALUES:
            add("PRIVATE_VISIBILITY", visibility)
        elif publication.target_type == "EVIDENCE" and getattr(
            target, "status", None
        ) in ("private", "restricted", "quarantined", "uploaded_quarantine"):
            add("PRIVATE_VISIBILITY", target.status)

    # 3. BE-021 interaction: a live dispute or unresolved correction must not
    #    silently produce a new public version (§12).
    if _has_active_dispute(db, publication.target_type, publication.target_id):
        add("ACTIVE_DISPUTE", "active dispute against target")
    if _has_unresolved_correction(db, publication.target_type, publication.target_id):
        add("UNRESOLVED_CORRECTION", "correction pending against target")

    # 4. BE-017 interaction (§13).
    for code in _retention_blockers(db, publication.target_type, publication.target_id):
        add(code, "retention governance applies to source")

    # 5. Approval separation and required approvals (§15).
    if version is not None:
        if version.require_separation_of_duties and publication.requested_by is not None:
            if str(publication.requested_by) == str(publication.approver_id):
                add("MISSING_REQUIRED_APPROVAL", "requester cannot approve own request")
        if publication.status not in ("APPROVED", "PUBLISHED"):
            if int(version.required_approvals or 1) > 1 and not publication.approver_id:
                add("MISSING_REQUIRED_APPROVAL", "additional approval required")

    # 6. Media exposure requires an approved derivative (§19/§20).
    if version is not None and version.allow_media_exposure:
        if publication.target_type == "EVIDENCE":
            from backend.db.models import PublicMediaDerivative

            derivative = (
                db.query(PublicMediaDerivative)
                .filter(PublicMediaDerivative.publication_id == publication.id)
                .first()
            )
            if derivative is None:
                add("UNAVAILABLE_PUBLIC_DERIVATIVE", "no approved public derivative")

    for blocker in blockers:
        metrics.record_eligibility_failure(blocker["code"])

    return {
        "publication_id": publication.id,
        "eligible": not blockers,
        "blockers": blockers,
        "evaluated_at": utc_now(),
        "policy_version": version.version if version else None,
    }


# ---------------------------------------------------------------------------
# Snapshot projection (§5, §8, §21, §22)
# ---------------------------------------------------------------------------


def _assert_no_prohibited_fields(payload: dict) -> None:
    """Defensive last line of defense against a leak (§5/§21).

    The builders below already avoid these fields; this raises rather than
    letting a future change publish a storage key or reviewer identity.
    """
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if str(key).lower() in PUBLICATION_INTERNALLY_PROHIBITED_FIELDS:
                    raise ValueError(f"Prohibited field in public payload: {key}")
                stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)


def _project_project(db: Session, row: Project, policy: PublicationPolicyVersion | None) -> dict:
    # Description is an operator-authored summary, not internal metadata.
    return {
        "public_id": None,  # filled by caller
        "name": row.name,
        "description": None,
        "status": "PUBLISHED",
    }


def _project_activity(db: Session, row: Activity) -> dict:
    # actor_id is deliberately absent: internal user identity never leaks (§21).
    return {
        "public_id": None,
        "verb": row.verb,
        "occurred_at": row.created_at,
    }


def _project_claim(db: Session, row: Claim, public_project_id: str | None) -> dict:
    return {
        "public_id": None,
        "public_project_id": public_project_id,
        "title": row.title,
        "description": row.description,
        "temporal_start_at": row.temporal_start_at,
        "temporal_end_at": row.temporal_end_at,
        "status": "PUBLISHED",
    }


def _project_evidence(
    db: Session, row: Evidence, public_project_id: str | None, policy: PublicationPolicyVersion | None
) -> dict:
    payload = {
        "public_id": None,
        "public_project_id": public_project_id,
        "status": "PUBLISHED",
        "collected_at": row.created_at,
        "filename": row.filename,
        "media": [],
    }
    # §22: never a raw private coordinate pair unless policy says EXACT.
    if policy is not None and policy.location_precision == "EXACT":
        payload["location_precision"] = "EXACT"
        loc = getattr(row, "location", None)
        if loc is not None:
            payload["location"] = str(loc)
    else:
        payload["location_precision"] = policy.location_precision if policy else "HIDDEN"
    # §19: media only when the policy allows it, and only as public-safe
    # derivatives served by public id — never the original storage key.
    if policy is not None and policy.allow_media_exposure:
        for derivative in pub_repo.list_derivatives_for_evidence(db, row.id):
            payload["media"].append(
                {
                    "public_id": f"POA-MEDIA-{derivative.id}",
                    "derivative_type": derivative.derivative_type,
                }
            )
    return payload


def _project_review_case(db: Session, row: ReviewCase, policy: PublicationPolicyVersion | None) -> dict:
    payload = {
        "public_id": None,
        "status": row.status,
        "decision": None,
    }
    # §24: only approved public vocabulary, and only when policy allows.
    if policy is not None and policy.allow_review_outcomes and row.decision:
        payload["decision"] = row.decision
        payload["source_category"] = "HUMAN_DECISION"
    return payload


def build_snapshot(
    db: Session,
    publication: Publication,
    policy: PublicationPolicyVersion | None,
) -> dict:
    """Assemble the deterministic public snapshot for a target (§8).

    The output is derived only from explicit allowlisted fields, so it cannot
    contain storage keys, EXIF, internal graph edges, reviewer notes, or
    internal signal values.
    """
    public_id = ensure_public_identifier(db, publication.target_type, publication.target_id)
    target_type = publication.target_type
    target_id = publication.target_id

    # Public project id, when the target hangs off a project.
    public_project_id: str | None = None
    project_id: str | None = None
    if target_type == "PROJECT":
        project_id = target_id
    else:
        row = _target_row(db, target_type, target_id)
        project_id = str(getattr(row, "project_id")) if row is not None and getattr(
            row, "project_id", None
        ) else None
    if project_id:
        public_project_id = ensure_public_identifier(db, "PROJECT", project_id)

    if target_type == "PROJECT":
        row = _target_row(db, target_type, target_id)
        payload = _project_project(db, row, policy) if row is not None else {}
    elif target_type == "ACTIVITY":
        row = _target_row(db, target_type, target_id)
        payload = _project_activity(db, row) if row is not None else {}
    elif target_type == "CLAIM":
        row = _target_row(db, target_type, target_id)
        payload = _project_claim(db, row, public_project_id) if row is not None else {}
    elif target_type == "EVIDENCE":
        row = _target_row(db, target_type, target_id)
        payload = (
            _project_evidence(db, row, public_project_id, policy) if row is not None else {}
        )
    elif target_type == "REVIEW_CASE":
        row = _target_row(db, target_type, target_id)
        payload = (
            _project_review_case(db, row, policy) if row is not None else {}
        )
    elif target_type == "FUSION_ASSESSMENT":
        row = _target_row(db, target_type, target_id)
        # §24: automated signal is labelled as such and never presented as a
        # final government determination; internal weights stay internal.
        payload = {
            "public_id": None,
            "assessment_value": row.assessment_value if row is not None else None,
            "source_category": "AUTOMATED_SIGNAL",
        } if row is not None else {}
    else:
        payload = {}

    payload["public_id"] = public_id
    _assert_no_prohibited_fields(payload)
    return payload


# ---------------------------------------------------------------------------
# Publication lifecycle (§6, §7)
# ---------------------------------------------------------------------------


def create_publication(db: Session, payload: dict, actor_id: str) -> tuple:
    """Create a publication request in DRAFT. Idempotent per target.

    Returns ``(publication, created)``. A second request for the same target
    returns the existing publication rather than creating a duplicate row
    (the unique target constraint backs this up at the database level).
    """
    target_type = _plain(payload["target_type"])
    target_id = str(payload["target_id"])
    policy_id = str(payload["policy_id"])
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise ValueError("A publication reason is required")

    if target_type not in PUBLICATION_TARGET_TYPES:
        raise ValueError(f"Not a publishable target type: {target_type}")

    policy = pub_repo.get_policy(db, policy_id)
    if policy is None:
        raise LookupError(f"Publication policy not found: {policy_id}")

    existing = pub_repo.get_publication_for_target(db, target_type, target_id)
    if existing is not None:
        return existing, False

    version = pub_repo.get_active_policy_version(db, policy_id)
    if version is not None and target_type not in (version.allowed_target_types or []):
        raise ValueError(f"Target type {target_type} is not allowed by this policy")

    public_id = ensure_public_identifier(db, target_type, target_id)

    publication = pub_repo.insert_publication(
        db,
        target_type=target_type,
        target_id=target_id,
        policy_id=policy_id,
        policy_version_id=version.id if version else None,
        public_id=public_id,
        current_version_number=0,
        status="DRAFT",
        requested_by=actor_id,
        reason=reason,
    )
    _record_event(
        db, publication, "CREATED", None, "DRAFT", actor_id, reason=reason
    )
    _audit(
        db,
        "PUBLICATION_CREATED",
        "create",
        publication.id,
        actor_id,
        {
            "target_type": target_type,
            "policy_id": policy_id,
            "public_id": public_id,
        },
    )
    metrics.record_publication_created(target_type)
    db.commit()
    db.refresh(publication)
    return publication, True


def get_publication(db: Session, publication_id: str) -> Publication:
    publication = pub_repo.get_publication(db, publication_id)
    if publication is None:
        raise LookupError(f"Publication not found: {publication_id}")
    return publication


def list_publications(db: Session, **filters) -> tuple[list, int]:
    limit = int(filters.pop("limit", 50))
    offset = int(filters.pop("offset", 0))
    return pub_repo.list_publications(db, limit=limit, offset=offset, **filters)


# §6 Lifecycle transition matrix. A PUBLISHED item never returns to an
# editable published state: republishing a material change creates the next
# version instead (handled by publish_publication's version increment).
TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PENDING_REVIEW"}),
    "PENDING_REVIEW": frozenset({"APPROVED", "REJECTED"}),
    "APPROVED": frozenset({"PUBLISHED", "REJECTED"}),
    "PUBLISHED": frozenset({"UNPUBLISHED"}),
    "UNPUBLISHED": frozenset(),
    "REJECTED": frozenset(),
}


def validate_transition(from_status: str, to_status: str) -> None:
    """Raise if a publication lifecycle transition is not permitted (§6)."""
    allowed = TRANSITIONS.get(from_status)
    if allowed is None:
        raise ValueError(f"Unknown publication status: {from_status}")
    if to_status not in allowed:
        raise ValueError(
            f"Invalid publication transition: {from_status} -> {to_status}"
        )


def _transition(
    db: Session,
    publication_id: str,
    *,
    expected_from: tuple[str, ...],
    to_status: str,
    event_type: str,
    actor_id: str,
    audit_event: str,
    reason: str | None = None,
) -> Publication:
    """Apply one guarded lifecycle transition under a row lock.

    The row lock plus the expected-state check makes concurrent publish
    attempts serialize: the loser sees a state that no longer matches and
    raises rather than double-publishing.
    """
    publication = pub_repo.get_publication_for_update(db, publication_id)
    if publication is None:
        raise LookupError(f"Publication not found: {publication_id}")
    if publication.status not in expected_from:
        raise ValueError(
            f"Invalid transition: {publication.status} -> {to_status} "
            f"(expected one of {expected_from})"
        )
    validate_transition(publication.status, to_status)
    previous = publication.status
    publication.status = to_status
    _record_event(
        db, publication, event_type, previous, to_status, actor_id, reason=reason
    )
    _audit(
        db,
        audit_event,
        event_type.lower(),
        publication.id,
        actor_id,
        {"from_status": previous, "to_status": to_status, "target_type": publication.target_type},
    )
    db.commit()
    db.refresh(publication)
    return publication


def submit_review(db: Session, publication_id: str, actor_id: str) -> Publication:
    return _transition(
        db,
        publication_id,
        expected_from=("DRAFT",),
        to_status="PENDING_REVIEW",
        event_type="REVIEW_STARTED",
        actor_id=actor_id,
        audit_event="PUBLICATION_REVIEW_STARTED",
    )


def approve_publication(db: Session, publication_id: str, actor_id: str) -> Publication:
    """Approve a request. Enforces releasability and separation of duties (§15)."""
    publication = pub_repo.get_publication_for_update(db, publication_id)
    if publication is None:
        raise LookupError(f"Publication not found: {publication_id}")
    if publication.status != "PENDING_REVIEW":
        raise ValueError(
            f"Invalid transition: {publication.status} -> APPROVED "
            "(expected PENDING_REVIEW)"
        )

    version = pub_repo.get_active_policy_version(db, publication.policy_id)
    if version is not None and version.require_separation_of_duties:
        if str(publication.requested_by) == str(actor_id):
            raise ValueError(
                "Separation of duties: the requester cannot approve their own request"
            )

    # Approval must not succeed on a target that is no longer releasable.
    result = check_eligibility(db, publication.id)
    if not result["eligible"]:
        codes = ", ".join(b["code"] for b in result["blockers"])
        _audit(
            db,
            "PUBLICATION_ELIGIBILITY_FAILED",
            "eligibility",
            publication.id,
            actor_id,
            {"blockers": [b["code"] for b in result["blockers"]]},
        )
        db.commit()
        raise ValueError(f"Target is not releasable: {codes}")

    previous = publication.status
    publication.status = "APPROVED"
    publication.approver_id = actor_id
    publication.approved_at = utc_now()
    _record_event(db, publication, "APPROVED", previous, "APPROVED", actor_id)
    _audit(
        db,
        "PUBLICATION_APPROVED",
        "approve",
        publication.id,
        actor_id,
        {"target_type": publication.target_type},
    )
    metrics.record_publication_approved(publication.target_type)
    db.commit()
    db.refresh(publication)
    return publication


def reject_publication(
    db: Session, publication_id: str, actor_id: str, reason: str | None = None
) -> Publication:
    return _transition(
        db,
        publication_id,
        expected_from=("PENDING_REVIEW", "APPROVED"),
        to_status="REJECTED",
        event_type="REJECTED",
        actor_id=actor_id,
        audit_event="PUBLICATION_REJECTED",
        reason=reason,
    )


def publish_publication(db: Session, publication_id: str, actor_id: str) -> Publication:
    """Publish: freeze a new immutable snapshot version and make it current.

    A published item never returns to an editable published state; republishing
    after a material change creates the next version number (§6, §7).
    """
    publication = pub_repo.get_publication_for_update(db, publication_id)
    if publication is None:
        raise LookupError(f"Publication not found: {publication_id}")
    if publication.status != "APPROVED":
        raise ValueError(
            f"Invalid transition: {publication.status} -> PUBLISHED (expected APPROVED)"
        )

    policy = pub_repo.get_active_policy_version(db, publication.policy_id)
    result = check_eligibility(db, publication.id)
    if not result["eligible"]:
        codes = ", ".join(b["code"] for b in result["blockers"])
        _audit(
            db,
            "PUBLICATION_ELIGIBILITY_FAILED",
            "eligibility",
            publication.id,
            actor_id,
            {"blockers": [b["code"] for b in result["blockers"]]},
        )
        db.commit()
        raise ValueError(f"Target is not releasable: {codes}")

    snapshot = build_snapshot(db, publication, policy)
    next_number = int(publication.current_version_number or 0) + 1
    now = utc_now()

    version_row = pub_repo.insert_version(
        db,
        publication_id=publication.id,
        version_number=next_number,
        snapshot=snapshot,
        public_id=publication.public_id,
        target_type=publication.target_type,
        target_id=publication.target_id,
        status="PUBLISHED",
        policy_version_id=policy.id if policy else None,
        source_version_references={"previous_version": int(publication.current_version_number or 0)},
        requested_by=publication.requested_by,
        approved_by=publication.approver_id,
        published_by=actor_id,
        approved_at=publication.approved_at,
        published_at=now,
    )

    previous_status = publication.status
    publication.status = "PUBLISHED"
    publication.current_version_number = next_number
    publication.publisher_id = actor_id
    publication.published_at = now
    publication.unpublished_at = None
    _record_event(
        db,
        publication,
        "PUBLISHED",
        previous_status,
        "PUBLISHED",
        actor_id,
        metadata={"version_number": next_number},
    )
    _audit(
        db,
        "PUBLICATION_PUBLISHED",
        "publish",
        publication.id,
        actor_id,
        {"version_number": next_number, "target_type": publication.target_type},
    )
    _audit(
        db,
        "PUBLIC_PUBLICATION_VERSION_CREATED",
        "version",
        publication.id,
        actor_id,
        {"version_number": next_number, "version_id": version_row.id},
    )
    metrics.record_publication_published(publication.target_type)
    db.commit()
    db.refresh(publication)
    return publication


def unpublish_publication(
    db: Session, publication_id: str, actor_id: str, reason: str | None = None
) -> Publication:
    """Withdraw a publication. The historical version row is preserved (§7)."""
    publication = pub_repo.get_publication_for_update(db, publication_id)
    if publication is None:
        raise LookupError(f"Publication not found: {publication_id}")
    if publication.status != "PUBLISHED":
        raise ValueError(
            f"Invalid transition: {publication.status} -> UNPUBLISHED (expected PUBLISHED)"
        )
    previous = publication.status
    now = utc_now()
    publication.status = "UNPUBLISHED"
    publication.unpublished_at = now

    current = pub_repo.get_current_version(db, publication.id)
    if current is not None:
        current.status = "UNPUBLISHED"
        current.unpublished_at = now

    _record_event(
        db, publication, "UNPUBLISHED", previous, "UNPUBLISHED", actor_id, reason=reason
    )
    _audit(
        db,
        "PUBLICATION_UNPUBLISHED",
        "unpublish",
        publication.id,
        actor_id,
        {"target_type": publication.target_type},
    )
    metrics.record_publication_unpublished(publication.target_type)
    db.commit()
    db.refresh(publication)
    return publication


def get_history(db: Session, publication_id: str, *, limit: int = 100, offset: int = 0) -> dict:
    get_publication(db, publication_id)
    events, total = pub_repo.list_events(db, publication_id, limit=limit, offset=offset)
    return {"publication_id": publication_id, "events": events, "total": total}


def list_versions(db: Session, publication_id: str) -> list:
    get_publication(db, publication_id)
    return pub_repo.list_versions(db, publication_id)


# ---------------------------------------------------------------------------
# Public read surface (§17)
# ---------------------------------------------------------------------------
# Only PUBLISHED publications are ever readable here, and only through their
# immutable version snapshot. A DRAFT, REJECTED, or UNPUBLISHED publication
# resolves to nothing.


def _published_snapshot(db: Session, public_id: str) -> dict:
    version = pub_repo.get_published_version_for_public_id(db, public_id)
    if version is None:
        raise LookupError(f"No published content for public id: {public_id}")
    return {
        "public_id": version.public_id,
        "target_type": version.target_type,
        "version_number": version.version_number,
        "status": version.status,
        "published_at": version.published_at,
        "provenance": {
            "publication_version": version.version_number,
            "source_category": (version.snapshot or {}).get("source_category"),
            "published_at": version.published_at,
            "human_approval_status": "APPROVED" if version.approved_by else None,
        },
        "content": version.snapshot or {},
    }


def list_public_projects(db: Session, *, limit: int = 50, offset: int = 0) -> list[dict]:
    rows, _total = pub_repo.list_published_publications(
        db, target_type="PROJECT", limit=limit, offset=offset
    )
    out = []
    for publication in rows:
        try:
            out.append(_published_snapshot(db, publication.public_id))
        except LookupError:
            continue
    return out


def get_public_project(db: Session, public_id: str) -> dict:
    return _published_snapshot(db, public_id)


def list_public_activities(db: Session, public_id: str, *, limit: int = 50, offset: int = 0) -> list[dict]:
    """Published activities belonging to a published project."""
    parent = pub_repo.get_published_version_for_public_id(db, public_id)
    if parent is None or parent.target_type != "PROJECT":
        raise LookupError(f"No published project for public id: {public_id}")
    project_identifier = pub_repo.get_identifier_for_target(db, "PROJECT", str(parent.target_id))
    if project_identifier is None:
        return []
    rows, _total = pub_repo.list_published_publications(
        db, target_type="ACTIVITY", limit=limit, offset=offset
    )
    out = []
    for publication in rows:
        activity = _target_row(db, "ACTIVITY", publication.target_id)
        if activity is None or str(activity.project_id) != str(parent.target_id):
            continue
        try:
            out.append(_published_snapshot(db, publication.public_id))
        except LookupError:
            continue
    return out


def list_public_claims(db: Session, public_id: str, *, limit: int = 50, offset: int = 0) -> list[dict]:
    parent = pub_repo.get_published_version_for_public_id(db, public_id)
    if parent is None or parent.target_type != "PROJECT":
        raise LookupError(f"No published project for public id: {public_id}")
    rows, _total = pub_repo.list_published_publications(
        db, target_type="CLAIM", limit=limit, offset=offset
    )
    out = []
    for publication in rows:
        claim = _target_row(db, "CLAIM", publication.target_id)
        if claim is None or str(claim.project_id) != str(parent.target_id):
            continue
        try:
            out.append(_published_snapshot(db, publication.public_id))
        except LookupError:
            continue
    return out


def list_public_evidence(db: Session, public_id: str, *, limit: int = 50, offset: int = 0) -> list[dict]:
    parent = pub_repo.get_published_version_for_public_id(db, public_id)
    if parent is None or parent.target_type != "PROJECT":
        raise LookupError(f"No published project for public id: {public_id}")
    rows, _total = pub_repo.list_published_publications(
        db, target_type="EVIDENCE", limit=limit, offset=offset
    )
    out = []
    for publication in rows:
        evidence = _target_row(db, "EVIDENCE", publication.target_id)
        if evidence is None or str(evidence.project_id) != str(parent.target_id):
            continue
        try:
            out.append(_published_snapshot(db, publication.public_id))
        except LookupError:
            continue
    return out


def get_public_evidence(db: Session, public_id: str) -> dict:
    version = pub_repo.get_published_version_for_public_id(db, public_id)
    if version is None or version.target_type != "EVIDENCE":
        raise LookupError(f"No published evidence for public id: {public_id}")
    return _published_snapshot(db, public_id)


def get_public_publication(db: Session, public_id: str) -> dict:
    return _published_snapshot(db, public_id)
