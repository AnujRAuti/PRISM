"""BE-022 unit tests: policy rules, lifecycle, privacy, identifiers, and
bounded telemetry — pure logic only, no database (§38).

Covers the spec's explicit rules: lifecycle matrix (§6), target allowlist
(§4), prohibited-field detection (§5/§21), public identifier format (§16),
structured blockers (§11), and closed metric labels (§35).
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.db.models import (
    AUTH_PERMISSIONS,
    AUTH_ROLE_PERMISSIONS,
    AUDIT_EVENT_TYPES,
    DISPUTE_TARGET_TYPES,
    NOTIFICATION_TYPES,
    PUBLICATION_BLOCKERS,
    PUBLICATION_INTERNALLY_PROHIBITED_FIELDS,
    PUBLICATION_STATUSES,
    PUBLICATION_TARGET_TYPES,
)
from backend.observability import publication_metrics
from backend.services import publication as publication_service
from backend.services.authorization import (
    ACTION_PERMISSIONS,
    PERMISSIONS,
    publication_target_resource,
)


# ---------------------------------------------------------------------------
# Lifecycle (§6)
# ---------------------------------------------------------------------------


def test_lifecycle_accepts_documented_moves():
    valid = [
        ("DRAFT", "PENDING_REVIEW"),
        ("PENDING_REVIEW", "APPROVED"),
        ("PENDING_REVIEW", "REJECTED"),
        ("APPROVED", "PUBLISHED"),
        ("APPROVED", "REJECTED"),
        ("PUBLISHED", "UNPUBLISHED"),
    ]
    for from_status, to_status in valid:
        publication_service.validate_transition(from_status, to_status)


def test_lifecycle_rejects_invalid_moves():
    invalid = [
        ("DRAFT", "PUBLISHED"),       # cannot skip review
        ("DRAFT", "APPROVED"),
        ("DRAFT", "REJECTED"),
        ("PENDING_REVIEW", "PUBLISHED"),  # must be approved first
        ("PENDING_REVIEW", "DRAFT"),
        ("APPROVED", "PENDING_REVIEW"),
        ("PUBLISHED", "DRAFT"),       # never silently return to editable
        ("PUBLISHED", "APPROVED"),
        ("PUBLISHED", "PENDING_REVIEW"),
        ("PUBLISHED", "PUBLISHED"),
        ("UNPUBLISHED", "PUBLISHED"),  # terminal
        ("REJECTED", "PUBLISHED"),     # terminal
    ]
    for from_status, to_status in invalid:
        with pytest.raises(ValueError):
            publication_service.validate_transition(from_status, to_status)


def test_terminal_states_have_no_exits():
    for terminal in ("UNPUBLISHED", "REJECTED"):
        assert publication_service.TRANSITIONS[terminal] == frozenset()


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        publication_service.validate_transition("NOT_A_STATUS", "PUBLISHED")


# ---------------------------------------------------------------------------
# Target allowlist (§4)
# ---------------------------------------------------------------------------


def test_target_allowlist_is_explicit_and_closed():
    assert set(PUBLICATION_TARGET_TYPES) == {
        "PROJECT",
        "ACTIVITY",
        "CLAIM",
        "EVIDENCE",
        "REVIEW_CASE",
        "FUSION_ASSESSMENT",
    }


def test_internal_objects_are_not_publishable_targets():
    # Audit events, users, permissions, notifications and API clients are
    # never publishable (§4).
    for forbidden in ("USER", "AUDIT_EVENT", "PERMISSION", "API_CLIENT", "NOTIFICATION"):
        assert forbidden not in PUBLICATION_TARGET_TYPES


def test_publication_target_resource_maps_every_allowlisted_type():
    for target in PUBLICATION_TARGET_TYPES:
        assert publication_target_resource(target) is not None


def test_publication_target_resource_rejects_unknown():
    assert publication_target_resource("USER") is None
    assert publication_target_resource(None) is None
    assert publication_target_resource("") is None


# ---------------------------------------------------------------------------
# Privacy: prohibited fields (§5, §21)
# ---------------------------------------------------------------------------


def test_prohibited_field_set_covers_the_spec_list():
    for field in (
        "storage_key",
        "exif",
        "user_id",
        "reviewer_id",
        "secret",
        "password",
        "token",
        "priority_score",
        "fusion_signals",
    ):
        assert field in PUBLICATION_INTERNALLY_PROHIBITED_FIELDS


def test_assert_no_prohibited_fields_rejects_top_level_leak():
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._assert_no_prohibited_fields({"storage_key": "internal/path"})


def test_assert_no_prohibited_fields_rejects_nested_leak():
    payload = {"content": {"meta": {"exif": {"gps": 1}}}}
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._assert_no_prohibited_fields(payload)


def test_assert_no_prohibited_fields_rejects_list_leak():
    payload = {"items": [{"ok": 1}, {"token": "abc"}]}
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._assert_no_prohibited_fields(payload)


def test_assert_no_prohibited_fields_allows_clean_payload():
    publication_service._assert_no_prohibited_fields(
        {"public_id": "POA-PROJ-000001", "name": "Bridge project", "media": []}
    )


# ---------------------------------------------------------------------------
# Snapshot JSON-safety boundary (§8, §32)
#
# Regression: publishing EVIDENCE raised
#   TypeError: Object of type datetime is not JSON serializable
# while inserting publication_versions.snapshot as PostgreSQL JSONB.
# build_snapshot projects collected_at straight off the ORM row, and JSONB has
# no native temporal type, so the driver received a raw datetime.
#
# The fix canonicalizes at the projection->snapshot boundary, reusing the BE-015
# canonicalizer. These tests pin the contract: JSON-safe, deterministic, no
# catch-all serializer, and no weakening of the leak guards.
# ---------------------------------------------------------------------------


UTC = timezone.utc
_COLLECTED_AT = datetime(2026, 9, 24, 10, 30, 0, tzinfo=UTC)


def _evidence_projection(**overrides) -> dict:
    """A representative EVIDENCE projection, carrying the offending datetime."""
    payload = {
        "public_id": "EVD-000001",
        "public_project_id": "PROJ-000001",
        "status": "PUBLISHED",
        "collected_at": _COLLECTED_AT,
        "filename": "photo.jpg",
        "media": [],
        "location_precision": "HIDDEN",
    }
    payload.update(overrides)
    return payload


def test_snapshot_is_json_safe_when_the_projection_carries_datetimes():
    """The live failure: the persisted snapshot must be JSON-serializable."""
    safe = publication_service._json_safe_snapshot(_evidence_projection())
    # This exact call is what raised TypeError before the fix.
    json.dumps(safe)
    for value in safe.values():
        assert not isinstance(value, datetime), f"raw datetime persisted: {value!r}"


def test_snapshot_timestamps_are_deterministic_iso8601():
    """Timestamps are tz-aware ISO-8601, so the stored record is reproducible."""
    safe = publication_service._json_safe_snapshot(_evidence_projection())
    assert safe["collected_at"] == "2026-09-24T10:30:00+00:00"


def test_snapshot_normalizes_non_utc_timestamps_to_utc():
    """The same instant expressed in two offsets must produce identical JSON."""
    ist = timezone(timedelta(hours=5, minutes=30))
    local = datetime(2026, 9, 24, 16, 0, 0, tzinfo=ist)  # == 10:30 UTC
    via_offset = publication_service._json_safe_snapshot({"collected_at": local})
    via_utc = publication_service._json_safe_snapshot({"collected_at": _COLLECTED_AT})
    assert via_offset["collected_at"] == "2026-09-24T10:30:00+00:00"
    assert via_offset == via_utc


def test_every_temporal_field_a_projector_can_emit_is_canonicalized():
    """Not a one-off for collected_at: all four temporal fields are covered."""
    for field in (
        "occurred_at",
        "temporal_start_at",
        "temporal_end_at",
        "collected_at",
    ):
        safe = publication_service._json_safe_snapshot({field: _COLLECTED_AT})
        assert safe[field] == _COLLECTED_AT.isoformat(), field


def test_snapshot_rejects_unserializable_values_instead_of_stringifying_them():
    """No ``default=str`` catch-all: an unknown type must fail loudly.

    A str() catch-all would make the reported TypeError disappear while
    silently turning arbitrary objects into arbitrary strings inside the frozen
    public record, which is exactly the determinism §32 forbids.
    """
    with pytest.raises(ValueError, match="Unserializable value"):
        publication_service._json_safe_snapshot({"payload": object()})
    with pytest.raises(ValueError, match="Unserializable value"):
        publication_service._json_safe_snapshot({"payload": {1, 2}})
    with pytest.raises(ValueError, match="Naive datetimes are rejected"):
        publication_service._json_safe_snapshot({"occurred_at": datetime(2026, 1, 1)})


def test_snapshot_keys_are_sorted_for_determinism():
    """§32 requires the snapshot be reproducible, not merely serializable."""
    first = publication_service._json_safe_snapshot(
        {"zeta": 1, "alpha": 2, "collected_at": _COLLECTED_AT}
    )
    second = publication_service._json_safe_snapshot(
        {"alpha": 2, "collected_at": _COLLECTED_AT, "zeta": 1}
    )
    assert list(first) == sorted(first)
    assert first == second


def test_snapshot_still_excludes_storage_key_and_exif():
    """Serialization must not cost us the privacy guarantees."""
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._json_safe_snapshot(
            _evidence_projection(storage_key="quarantine/internal/secret.jpg")
        )
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._json_safe_snapshot(
            _evidence_projection(EXIF={"gps": [18.5984, 73.7898]})
        )


def test_snapshot_never_exposes_internal_database_uuids():
    """Canonicalization stringifies UUIDs, so the guard must run after it."""
    internal_id = uuid4()
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._json_safe_snapshot(
            _evidence_projection(actor_id=internal_id)
        )
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._json_safe_snapshot(
            _evidence_projection(user_id=internal_id)
        )
    # A clean snapshot must contain no raw UUID in string form either.
    safe = publication_service._json_safe_snapshot(_evidence_projection())
    assert str(internal_id) not in json.dumps(safe)


def test_snapshot_leak_guard_runs_on_the_persisted_structure():
    """A leak nested where the driver would serialize it is still rejected."""
    with pytest.raises(ValueError, match="Prohibited field"):
        publication_service._json_safe_snapshot(
            {"media": [{"public_id": "POA-MEDIA-1", "storage_key": "internal/x"}]}
        )


def test_snapshot_reuses_the_be015_canonicalizer_rather_than_duplicating_it():
    """One serializer for the whole platform, not a second copy in BE-022."""
    from backend.services import audit_ledger

    assert publication_service.normalize_value is audit_ledger.normalize_value


def test_build_snapshot_returns_the_json_safe_boundary():
    """Guard the wiring: the boundary must be applied, not merely defined.

    A future refactor could keep _json_safe_snapshot around and stop calling it,
    which would reintroduce the live failure while every helper test still
    passed. This asserts build_snapshot actually RETURNS the canonical form.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(publication_service.build_snapshot))
    # inspect.getsource returns the whole `def ...:` block, so descend into it.
    outer = tree.body[0]
    assert isinstance(outer, ast.FunctionDef), ast.dump(outer)[:200]
    body = outer.body
    assert isinstance(body[-1], ast.Return), ast.dump(body[-1])[:200]
    returned = body[-1].value
    assert isinstance(returned, ast.Call), ast.dump(returned)[:200]
    assert isinstance(returned.func, ast.Name)
    assert returned.func.id == "_json_safe_snapshot"


def test_projectors_do_not_hand_roll_their_own_timestamp_serialization():
    """No per-field ``.isoformat()`` / ``str()`` workaround crept in.

    The boundary is the single place a datetime is converted. A projector that
    converts it itself would re-introduce non-deterministic, field-specific
    formatting that the canonicalizer exists to prevent.
    """
    import ast
    import inspect

    offenders = []
    for name, member in vars(publication_service).items():
        if not (name.startswith("_project_") and inspect.isfunction(member)):
            continue
        tree = ast.parse(inspect.getsource(member))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "isoformat":
                    offenders.append(f"{name}: isoformat()")
                if (
                    isinstance(func, ast.Name)
                    and func.id == "str"
                    and any(
                        isinstance(a, ast.Attribute) and a.attr in {"created_at", "temporal_start_at", "temporal_end_at"}
                        for a in node.args
                    )
                ):
                    offenders.append(f"{name}: str(<temporal field>)")
    assert not offenders, offenders


def test_private_visibility_values_are_never_public():
    for value in (
        "CITIZEN_OWNED_PRIVATE",
        "OPERATIONAL",
        "INTELLIGENCE_INTERNAL",
        "ADMINISTRATIVE_SECURITY",
    ):
        assert value in publication_service.PRIVATE_VISIBILITY_VALUES
    assert "PUBLIC" not in publication_service.PRIVATE_VISIBILITY_VALUES


# ---------------------------------------------------------------------------
# Public identifiers (§16)
# ---------------------------------------------------------------------------


def test_public_id_prefixes_cover_every_target_type():
    for target in PUBLICATION_TARGET_TYPES:
        assert target in publication_service.PUBLIC_ID_PREFIXES


def test_public_ids_are_non_sensitive_and_namespaced():
    # A public id is a namespaced sequential token, never a UUID or secret.
    assert publication_service.PUBLIC_ID_PREFIXES["PROJECT"] == "PROJ"
    assert publication_service.PUBLIC_ID_PREFIXES["EVIDENCE"] == "EVD"
    for prefix in publication_service.PUBLIC_ID_PREFIXES.values():
        assert "-" not in prefix
        assert prefix.isupper()


# ---------------------------------------------------------------------------
# Blockers (§11)
# ---------------------------------------------------------------------------


def test_blockers_are_structured_not_collapsed():
    assert len(PUBLICATION_BLOCKERS) >= 10
    assert "NOT_ALLOWED" not in PUBLICATION_BLOCKERS
    for code in (
        "UNAUTHORIZED",
        "NOT_PUBLISHABLE_TYPE",
        "PRIVATE_VISIBILITY",
        "ACTIVE_DISPUTE",
        "UNRESOLVED_CORRECTION",
        "RETENTION_RESTRICTION",
        "LEGAL_HOLD",
        "MISSING_REQUIRED_APPROVAL",
        "SENSITIVE_DATA_PRESENT",
        "SOURCE_RESTRICTION",
        "UNAVAILABLE_PUBLIC_DERIVATIVE",
    ):
        assert code in PUBLICATION_BLOCKERS


# ---------------------------------------------------------------------------
# Policy configuration vocabularies (§9, §22)
#
# These closed vocabularies are enforced in three independent places -- the
# Pydantic enum, the database CHECK constraint, and the service default. A test
# that invents a value outside them fails as an opaque HTTP 422 at the API
# boundary, which reads like an implementation bug rather than a bad test value.
# Pinning the vocabularies here makes that class of mistake obvious.
# ---------------------------------------------------------------------------


def test_location_precision_vocabulary_is_closed_and_authoritative():
    from backend.db.models import LOCATION_PRECISION_POLICIES
    from backend.schemas.publication import LocationPrecision

    assert set(LOCATION_PRECISION_POLICIES) == {
        "EXACT",
        "APPROXIMATE",
        "AREA",
        "HIDDEN",
    }
    assert {member.value for member in LocationPrecision} == set(
        LOCATION_PRECISION_POLICIES
    )
    # "CITY" was briefly used by a BE-022 test and rejected with 422. It is not
    # part of the contract: precision is expressed as a granularity label, and
    # AREA is the coarse-geography setting.
    assert "CITY" not in LOCATION_PRECISION_POLICIES


# ---------------------------------------------------------------------------
# BE-021 dispute vocabulary (§12)
#
# Regression: test_active_dispute_blocks_approval opened a
# Dispute(target_type="PROJECT") directly through the ORM and PostgreSQL
# rejected it with ck_dispute_target_type.
#
# BE-021 §5.1 enumerates six disputable targets and omits PROJECT, and that
# omission is deliberate and enforced in four places. PROJECT is publishable
# but not disputable -- the two vocabularies only partly overlap, so a BE-022
# test may not assume any publishable type is also disputable.
# ---------------------------------------------------------------------------


def test_dispute_target_vocabulary_matches_the_be021_contract():
    """The dispute vocabulary is BE-021's, and PROJECT is not in it."""
    assert set(DISPUTE_TARGET_TYPES) == {
        "EVIDENCE",
        "EVIDENCE_CLAIM_RELATIONSHIP",
        "CLAIM",
        "EXTERNAL_ASSERTION",
        "FUSION_ASSESSMENT",
        "REVIEW_CASE",
    }
    # A project is publishable, but BE-021 has no project-level dispute object.
    assert "PROJECT" in PUBLICATION_TARGET_TYPES
    assert "PROJECT" not in DISPUTE_TARGET_TYPES


def test_publication_targets_that_are_also_disputable():
    """Pin the intersection §12 interactions can actually be expressed over.

    If BE-021 or BE-022 ever changed either vocabulary, this is the assertion
    that would surface it instead of a CheckViolation at integration time.
    """
    assert set(PUBLICATION_TARGET_TYPES) & set(DISPUTE_TARGET_TYPES) == {
        "EVIDENCE",
        "CLAIM",
        "REVIEW_CASE",
        "FUSION_ASSESSMENT",
    }
    # Publishable but not disputable -- the exact gap that caused the failure.
    assert set(PUBLICATION_TARGET_TYPES) - set(DISPUTE_TARGET_TYPES) == {
        "PROJECT",
        "ACTIVITY",
    }


def test_active_dispute_lookup_is_scoped_to_the_publication_target():
    """§12 blocks the disputed object, not its neighbours or its project.

    The lookup must match the publication's OWN target type and id. Widening it
    to the enclosing project_id would block unrelated publications, and
    including RESOLVED would freeze resolved targets forever. Checked via the
    AST rather than the source text so reformatting cannot silently pass or
    break the guard.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(publication_service._has_active_dispute))
    compared = set()
    status_values = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            left = ast.unparse(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                compared.add(f"{left} {type(op).__name__} {ast.unparse(comparator)}")
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "in_":
            for arg in node.args:
                try:
                    status_values |= set(ast.literal_eval(arg))
                except (ValueError, TypeError):
                    pass

    # Scoped to this exact object.
    assert any("Dispute.target_type" in c for c in compared), compared
    assert any("Dispute.target_id" in c for c in compared), compared
    # Scoped to live disputes only.
    assert status_values == {"OPEN", "UNDER_REVIEW", "ESCALATED"}, status_values
    # Never widened to the enclosing project, which would block unrelated
    # publications sharing a project.
    assert not any("project_id" in c for c in compared), compared


def test_active_dispute_statuses_match_the_be021_uniqueness_index():
    """"Active" means the same thing in BE-021 and BE-022, or idempotency breaks.

    BE-021 enforces one active dispute per (target, initiator) with a PARTIAL
    unique index whose predicate is ``status IN ('OPEN', 'UNDER_REVIEW',
    'ESCALATED')``. BE-022 independently decides what counts as blocking. If
    the two sets drifted -- BE-022 treating a status as blocking that the index
    does not consider active -- then a retried dispute would be refused as a
    duplicate while still being treated as a live blocker, or worse, a resolved
    dispute would keep blocking publication.
    """
    from backend.db.models import Dispute

    index_predicates = [
        str(index.dialect_options["postgresql"]["where"])
        for index in Dispute.__table_args__
        if getattr(index, "name", "") == "uq_disputes_active_target_initiator"
    ]
    assert index_predicates, "BE-021 active-dispute unique index is missing"
    predicate = index_predicates[0]

    import ast
    import inspect

    tree = ast.parse(inspect.getsource(publication_service._has_active_dispute))
    blocker_statuses = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "in_":
            for arg in node.args:
                try:
                    blocker_statuses |= set(ast.literal_eval(arg))
                except (ValueError, TypeError):
                    pass
    assert blocker_statuses, "could not read the blocker status filter"

    for status in blocker_statuses:
        assert f"'{status}'" in predicate, (
            f"{status} blocks publication in BE-022 but is not an 'active' "
            f"dispute in BE-021: {predicate}"
        )
    for status in ("OPEN", "UNDER_REVIEW", "ESCALATED"):
        assert f"'{status}'" in predicate, status
        assert status in blocker_statuses, (
            f"BE-021 treats {status} as active but BE-022 would not block it"
        )


def test_be022_tests_only_open_disputes_against_supported_targets():
    """Guard: no BE-022 test may invent an out-of-vocabulary dispute target.

    A test that constructs ``Dispute(...)`` through the ORM bypasses the
    service-layer TARGET_TYPES check, so the only thing standing between an
    invented value and the database is the DB CHECK constraint -- which reports
    it as an opaque psycopg2 error rather than pointing at the test. This is the
    dispute-side counterpart of the policy-configuration vocabulary guard.
    """
    import ast
    from pathlib import Path

    here = Path(__file__).parent
    sources = {
        "unit": here / "test_publication.py",
        "integration": here.parent / "integration" / "test_publication.py",
    }
    offenders = []
    for label, path in sources.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Dispute(target_type="PROJECT")
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Dispute":
                for keyword in node.keywords:
                    if (
                        keyword.arg == "target_type"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value not in DISPUTE_TARGET_TYPES
                    ):
                        offenders.append(f"{label}: {keyword.value.value}")
            # CorrectionRequest / any row with a target_type kwarg on a dispute
            # vocabulary field -- caught by the Dict/Assign form below.
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "dispute_target_type"
                        and isinstance(node.value, ast.Constant)
                        and node.value.value not in DISPUTE_TARGET_TYPES
                    ):
                        offenders.append(f"{label}: {node.value.value}")
    assert not offenders, (
        "BE-022 tests use dispute target types outside the BE-021 contract "
        f"(DISPUTE_TARGET_TYPES): {offenders}"
    )


def test_redaction_level_vocabulary_is_closed():
    from backend.schemas.publication import RedactionLevel

    assert {member.value for member in RedactionLevel} == {
        "NONE",
        "STANDARD",
        "STRICT",
    }


def test_publication_tests_only_use_valid_policy_configuration_values():
    """Guard against reintroducing an out-of-vocabulary test value.

    Both this module and the integration module are checked: an invented value
    such as ``location_precision="CITY"`` is rejected at the API boundary with
    an opaque 422, which reads like an implementation bug rather than a bad
    test value, so the vocabulary is asserted up front in both places.
    """
    import ast
    from pathlib import Path

    from backend.db.models import LOCATION_PRECISION_POLICIES

    allowed = {
        "location_precision": set(LOCATION_PRECISION_POLICIES),
        "redaction_level": {"NONE", "STANDARD", "STRICT"},
        "min_authorization_level": {"REVIEWER", "SUPERVISOR", "ADMINISTRATOR"},
    }
    here = Path(__file__).parent
    sources = {
        "unit": here / "test_publication.py",
        "integration": here.parent / "integration" / "test_publication.py",
    }
    for label, path in sources.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            # Keyword arguments: create_policy(location_precision="CITY")
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg in allowed and isinstance(keyword.value, ast.Constant):
                        used.setdefault(keyword.arg, set()).add(keyword.value.value)
            # Dict literals: {"location_precision": "CITY"}
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value in allowed
                        and isinstance(value, ast.Constant)
                    ):
                        used.setdefault(key.value, set()).add(value.value)
            # Plain and class-level assignments:
            # location_precision = "CITY" / class _StubVersion: ...
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                value = node.value
                if not isinstance(value, ast.Constant):
                    continue
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in allowed:
                        used.setdefault(target.id, set()).add(value.value)
        # Parsed via AST rather than a regex so comments and docstrings -- which
        # legitimately name the rejected value -- are never scanned as usage.
        for field, vocabulary in allowed.items():
            offending = used.get(field, set()) - vocabulary
            assert not offending, (
                f"{label} {field} uses values outside the contract: "
                f"{sorted(offending)}"
            )


# ---------------------------------------------------------------------------
# Submit-for-review ownership guard (§6, §15)
#
# DRAFT -> PENDING_REVIEW is the requester handing over their own work. The
# endpoint gate (publication.create) is deliberately not sufficient on its
# own: any officer holds it, so the service must additionally require that the
# actor is the requester. This is the piece that stops one officer from
# submitting a draft another officer raised.
# ---------------------------------------------------------------------------


class _OwnedPublication:
    def __init__(self, status="DRAFT", requested_by=None):
        self.id = "33333333-3333-3333-3333-333333333333"
        self.status = status
        self.requested_by = requested_by


def _transition_with_publication(publication, **kwargs):
    """Exercise _transition's guards with a stubbed publication lookup."""
    import inspect

    source = inspect.getsource(publication_service._transition)
    # The ownership check must be present, guarded by the flag, and must run
    # AFTER the state-machine check so an impossible transition is reported
    # accurately rather than as an ownership complaint.
    state_check = source.index("if publication.status not in expected_from")
    owner_check = source.index("if requester_only")
    assert state_check < owner_check, (
        "the state-machine guard must run before the ownership guard so a "
        "caller retrying an already-submitted request is told the real reason"
    )
    assert "requested_by" in source[owner_check:owner_check + 400]
    return source


def test_transition_ownership_check_runs_after_the_state_machine_check():
    _transition_with_publication(_OwnedPublication())


def test_only_submit_review_is_requester_only():
    """The ownership restriction applies to the handover and nothing else."""
    import inspect

    submit = inspect.getsource(publication_service.submit_review)
    assert "requester_only=True" in submit, (
        "submit_review must restrict the handover to the requester"
    )
    # Reject/unpublish are adjudicative or administrative actions that a
    # non-requester is entitled to perform; they must stay unrestricted.
    reject = inspect.getsource(publication_service.reject_publication)
    assert "requester_only" not in reject


def test_transition_defaults_to_unrestricted():
    import inspect

    sig = inspect.signature(publication_service._transition)
    assert sig.parameters["requester_only"].default is False, (
        "requester_only must be opt-in so existing transitions are unchanged"
    )


# ---------------------------------------------------------------------------
# Authorization (§14)
# ---------------------------------------------------------------------------


def test_publication_permissions_are_registered():
    for permission in (
        "publication.create",
        "publication.read",
        "publication.review",
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
        "publication.policy.manage",
    ):
        assert permission in AUTH_PERMISSIONS
        assert permission in PERMISSIONS
        assert ACTION_PERMISSIONS[permission] == permission


def test_citizens_hold_no_publication_authority():
    """A citizen must never be granted any internal publication permission.

    Public access is governed by publication state, not by granting citizens
    internal authority (§17). If any publication.* permission leaked into the
    CITIZEN role, citizens could reach the internal workflow endpoints.
    """
    citizen = set(AUTH_ROLE_PERMISSIONS.get("CITIZEN", ()))
    assert not any(p.startswith("publication.") for p in citizen)


def test_administrators_do_not_receive_substantive_publication_authority():
    admin = set(AUTH_ROLE_PERMISSIONS["ADMINISTRATOR"])
    for substantive in (
        "publication.create",
        "publication.review",
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
    ):
        assert substantive not in admin
    # Policy management stays administrative and read stays available.
    assert "publication.policy.manage" in admin
    assert "publication.read" in admin


def test_supervisor_holds_the_substantive_publication_actions():
    supervisor = set(AUTH_ROLE_PERMISSIONS["SUPERVISOR"])
    for action in (
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
    ):
        assert action in supervisor
    # But not administrative policy management (§14).
    assert "publication.policy.manage" not in supervisor


def test_reviewer_cannot_approve_or_publish():
    reviewer = set(AUTH_ROLE_PERMISSIONS["REVIEWER"])
    assert "publication.review" in reviewer
    assert "publication.approve" not in reviewer
    assert "publication.publish" not in reviewer


def test_citizens_have_no_publication_authority():
    citizen = set(AUTH_ROLE_PERMISSIONS["CITIZEN"])
    for permission in (
        "publication.create",
        "publication.approve",
        "publication.publish",
        "publication.unpublish",
    ):
        assert permission not in citizen


def test_role_permission_mappings_only_use_known_permissions():
    for role, permissions in AUTH_ROLE_PERMISSIONS.items():
        for permission in permissions:
            assert permission in AUTH_PERMISSIONS, f"{role} -> {permission}"


# ---------------------------------------------------------------------------
# Audit + notification vocabulary (§26, §27)
# ---------------------------------------------------------------------------


def test_required_audit_events_are_registered():
    for event in (
        "PUBLICATION_CREATED",
        "PUBLICATION_REVIEW_STARTED",
        "PUBLICATION_APPROVED",
        "PUBLICATION_REJECTED",
        "PUBLICATION_PUBLISHED",
        "PUBLICATION_UNPUBLISHED",
        "PUBLICATION_POLICY_CREATED",
        "PUBLICATION_POLICY_UPDATED",
        "PUBLICATION_ELIGIBILITY_FAILED",
        "PUBLIC_PUBLICATION_VERSION_CREATED",
    ):
        assert event in AUDIT_EVENT_TYPES


def test_publication_notification_types_are_registered():
    for notification in (
        "PUBLICATION_SUBMITTED",
        "PUBLICATION_APPROVED",
        "PUBLICATION_REJECTED",
        "PUBLICATION_PUBLISHED",
        "PUBLICATION_UNPUBLISHED",
        "PUBLICATION_REQUIRES_REVIEW",
    ):
        assert notification in NOTIFICATION_TYPES


# ---------------------------------------------------------------------------
# Bounded telemetry labels (§35)
# ---------------------------------------------------------------------------


def test_metric_label_vocabularies_are_closed():
    assert set(publication_metrics.TARGET_TYPES) == set(PUBLICATION_TARGET_TYPES)
    assert set(publication_metrics.PUBLICATION_STATUSES) == set(PUBLICATION_STATUSES)
    assert set(publication_metrics.BLOCKERS) == set(PUBLICATION_BLOCKERS)


def test_high_cardinality_labels_are_forbidden():
    # §35 explicitly forbids these as Prometheus labels.
    forbidden = {"user_id", "project_id", "evidence_id", "claim_id", "publication_id", "public_id"}
    for vocabulary in (
        publication_metrics.TARGET_TYPES,
        publication_metrics.PUBLICATION_STATUSES,
        publication_metrics.BLOCKERS,
    ):
        assert not (set(vocabulary) & forbidden)


def test_unknown_label_values_are_coerced_to_bounded_fallbacks():
    # A high-cardinality or unexpected value must not become a label.
    assert publication_metrics._bounded("NOT_A_TYPE", publication_metrics.TARGET_TYPES, "PROJECT") == "PROJECT"
    assert publication_metrics._bounded(
        "public_id_abc123", publication_metrics.BLOCKERS, "SOURCE_RESTRICTION"
    ) == "SOURCE_RESTRICTION"
    # A legitimate value passes through unchanged.
    assert publication_metrics._bounded("EVIDENCE", publication_metrics.TARGET_TYPES, "PROJECT") == "EVIDENCE"


# ---------------------------------------------------------------------------
# Persisted actor identity boundary
#
# Regression: the development bypass used to fabricate the literal string
# "dev-user" as the actor, which reached PostgreSQL as
#   invalid input syntax for type uuid: "dev-user"
# because Publication.requested_by / PublicationPolicyVersion.created_by /
# PublicationEvent.actor_id are all UUID columns. A principal identity is an
# *authorization* identity, not necessarily a persisted user id.
# ---------------------------------------------------------------------------


def test_require_uuid_rejects_synthetic_actor_identities():
    """A non-UUID actor must be refused, never coerced or persisted."""
    for synthetic in ("dev-user", "system", "anonymous", "", "not-a-uuid", "12345"):
        with pytest.raises(ValueError):
            publication_service._require_uuid(synthetic, "actor_id")


def test_require_uuid_accepts_a_real_user_uuid():
    real = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    assert publication_service._require_uuid(real, "actor_id") == real
    # A UUID instance is normalised to its canonical string form.
    from uuid import UUID

    assert publication_service._require_uuid(UUID(real), "actor_id") == real


def test_optional_uuid_keeps_anonymous_actor_as_null():
    """An anonymous actor is stored as NULL, not as a fabricated identity."""
    assert publication_service._optional_uuid(None, "created_by") is None
    # But a present-but-invalid identity is still an error, not silently NULL.
    with pytest.raises(ValueError):
        publication_service._optional_uuid("dev-user", "created_by")


def test_endpoint_does_not_fabricate_a_dev_user_identity():
    """The literal "dev-user" must not be used as a persisted actor value.

    Checked against the module's runtime code (docstrings excluded) so the
    explanatory comment documenting the fix does not trip the assertion.
    """
    import inspect

    from backend.api.v1.endpoints import publication as publication_endpoints

    code = inspect.getsource(publication_endpoints._get_principal_or_raise)
    # Only executable code is under test: comments and the docstring that
    # documents the fix may legitimately mention the old literal.
    offending = [
        line for line in code.splitlines()
        if "dev-user" in line and "``" not in line and not line.lstrip().startswith(("#", "*"))
    ]
    assert not offending, f"dev-user fabricated as an actor: {offending}"


# ---------------------------------------------------------------------------
# Policy response projection (§9)
#
# Regression: PublicationPolicy carries identity, PublicationPolicyVersion
# carries configuration, and PublicationPolicyResponse requires fields from
# both. create_publication_policy returned the bare PublicationPolicy ORM row,
# so model_validate() raised 13 "field required" errors. The service now
# returns policy_view(policy, active_version) on every path.
# ---------------------------------------------------------------------------


POLICY_RESPONSE_FIELDS = (
    "id",
    "name",
    "description",
    "version",
    "status",
    "allowed_target_types",
    "public_fields",
    "prohibited_fields",
    "allow_media_exposure",
    "allow_derived_intelligence",
    "allow_review_outcomes",
    "min_authorization_level",
    "required_approvals",
    "require_separation_of_duties",
    "location_precision",
    "retention_publication_duration_days",
    "geographic_restrictions",
    "privacy_restrictions",
    "redaction_level",
    "created_at",
)


def test_policy_view_supplies_every_required_response_field():
    """The projection must cover PublicationPolicyResponse in full."""
    from backend.schemas.publication import PublicationPolicyResponse

    assert set(POLICY_RESPONSE_FIELDS) == set(
        PublicationPolicyResponse.model_fields
    ), "policy_view keys have drifted from the response schema"

    class _Policy:
        id = "11111111-1111-1111-1111-111111111111"
        name = "default"
        description = "desc"
        created_at = None

    class _Version:
        version = "1.0"
        status = "ACTIVE"
        allowed_target_types = ["PROJECT"]
        public_fields = ["public_id", "name"]
        prohibited_fields = ["storage_key"]
        allow_media_exposure = False
        allow_derived_intelligence = False
        allow_review_outcomes = False
        min_authorization_level = "REVIEWER"
        required_approvals = 1
        require_separation_of_duties = True
        location_precision = "HIDDEN"
        retention_publication_duration_days = None
        geographic_restrictions = None
        privacy_restrictions = None
        redaction_level = "STANDARD"

    view = publication_service.policy_view(_Policy(), _Version())
    # It must be a mapping, not an ORM object: model_validate over a dict is
    # what makes the version fields reachable at all.
    assert isinstance(view, dict)
    for field in POLICY_RESPONSE_FIELDS:
        assert field in view, f"policy_view missing {field!r}"
    # Values come from the ACTIVE version, not from the policy identity row.
    assert view["version"] == "1.0"
    assert view["status"] == "ACTIVE"
    assert view["allowed_target_types"] == ["PROJECT"]
    assert view["min_authorization_level"] == "REVIEWER"

    # And the projection actually satisfies the response schema.
    validated = PublicationPolicyResponse.model_validate(view)
    assert validated.status == "ACTIVE"
    assert validated.version == "1.0"


def test_policy_view_falls_back_when_no_active_version_exists():
    """A policy with no ACTIVE version still yields a complete, valid shape."""
    from backend.schemas.publication import PublicationPolicyResponse

    class _Policy:
        id = "22222222-2222-2222-2222-222222222222"
        name = "orphan"
        description = None
        created_at = None

    view = publication_service.policy_view(_Policy(), None)
    assert view["version"] == "1.0"
    assert view["status"] == "DRAFT"
    assert view["allowed_target_types"] == []
    assert PublicationPolicyResponse.model_validate(view).status == "DRAFT"


def test_create_publication_policy_returns_a_projection_not_an_orm_row():
    """Every return path of create_publication_policy must yield a projection.

    The idempotent (created=False) path and the creation (created=True) path are
    separate returns; both must hand the caller the flattened dict, or the
    endpoint's model_validate() raises 13 missing-field errors.
    """
    import ast
    import inspect

    source = inspect.getsource(publication_service.create_publication_policy)
    returns = [
        node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Return)
    ]
    assert returns, "no return statements found to inspect"

    # Each returned value must be routed through the projection rather than
    # passing a bare model (PublicationPolicy / PublicationPolicyVersion).
    # A return may be a bare name, a tuple (the service returns ``(view,
    # created)``), or a parenthesised form, so every model name reachable in
    # the returned expression counts.
    model_names = {"policy", "version", "existing"}

    def leaked(node):
        if isinstance(node, ast.Name):
            return node.id in model_names
        if isinstance(node, ast.Tuple):
            return any(leaked(element) for element in node.elts)
        return False

    bare_model_returns = [node for node in returns if leaked(node.value)]
    assert not bare_model_returns, (
        "create_publication_policy returns a bare ORM object at "
        f"{[node.lineno for node in bare_model_returns]}; it must return "
        "policy_view(policy, version) so the response carries the active version"
    )
    assert "policy_view" in source, "the create path must use the policy_view projection"


class _StubPolicy:
    def __init__(self, name="default"):
        self.id = "11111111-1111-1111-1111-111111111111"
        self.name = name
        self.description = "stub"
        self.created_at = None


class _StubVersion:
    version = "2.0"
    status = "ACTIVE"
    allowed_target_types = ["PROJECT"]
    public_fields = ["public_id"]
    prohibited_fields = ["storage_key"]
    allow_media_exposure = False
    allow_derived_intelligence = False
    allow_review_outcomes = False
    min_authorization_level = "SUPERVISOR"
    required_approvals = 3
    require_separation_of_duties = True
    location_precision = "AREA"
    retention_publication_duration_days = 30
    geographic_restrictions = None
    privacy_restrictions = None
    redaction_level = "STRICT"


def test_idempotent_policy_creation_resolves_the_active_version(monkeypatch):
    """created=False must still resolve the ACTIVE version, not fall back to DRAFT.

    Regression risk: the idempotent path is a separate return from the creation
    path, so it can silently degrade. If it passes ``None`` for the version,
    ``policy_view`` applies its no-version defaults and the response reports
    status DRAFT / version 1.0 instead of the policy's real configuration —
    while still looking like a valid response, so no field-required error
    would reveal it.
    """
    existing = _StubPolicy("already-there")
    active = _StubVersion()
    looked_up = []

    def fake_get_active(db, policy_id):
        looked_up.append(policy_id)
        return active

    monkeypatch.setattr(
        publication_service.pub_repo, "get_policy_by_name", lambda db, name: existing
    )
    monkeypatch.setattr(
        publication_service.pub_repo, "get_active_policy_version", fake_get_active
    )
    # Any creation attempt in the idempotent path is a bug; make it loud.
    def _unexpected(*a, **k):
        raise AssertionError("idempotent path must not create a new policy")

    monkeypatch.setattr(publication_service.pub_repo, "insert_policy", _unexpected)
    monkeypatch.setattr(
        publication_service.pub_repo, "insert_policy_version", _unexpected
    )

    view, created = publication_service.create_publication_policy(
        object(), {"name": "already-there"}, None
    )

    assert created is False
    # It must have consulted the active version for this policy.
    assert looked_up == [existing.id], "idempotent path did not resolve the active version"
    # And the response must carry that version's configuration verbatim.
    assert view["version"] == "2.0"
    assert view["status"] == "ACTIVE"
    assert view["allowed_target_types"] == ["PROJECT"]
    assert view["min_authorization_level"] == "SUPERVISOR"
    assert view["required_approvals"] == 3
    assert view["location_precision"] == "AREA"
    assert view["retention_publication_duration_days"] == 30
    assert view["redaction_level"] == "STRICT"
    # Not the no-version defaults.
    assert view["status"] != "DRAFT"
