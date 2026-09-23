"""BE-017 unit tests: policy rules, precedence, expiry, holds (no database)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.schemas import retention as retention_schemas
from backend.services import retention as retention_service


def aware(year=2026, month=1, day=1):
    return datetime(year, month, day, tzinfo=timezone.utc)


def rules(**overrides):
    base = {"retention_days": 365, "archive_after_days": 90,
            "anchor": "INGESTED_AT", "allow_derived_cleanup": False}
    base.update(overrides)
    return base


def test_policy_rules_validation():
    assert retention_service.validate_policy_rules(rules()) == rules()
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules("nope")
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(retention_days=0))
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(retention_days=-5))
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(retention_days=1.5))
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(archive_after_days=365))
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(archive_after_days=0))
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(anchor="VIBES"))
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(allow_derived_cleanup="yes"))
    # Archive later than retention is rejected, never clamped.
    with pytest.raises(ValueError):
        retention_service.validate_policy_rules(rules(retention_days=30, archive_after_days=30))
    assert retention_service.validate_policy_rules(
        rules(archive_after_days=None))["archive_after_days"] is None


def test_expiry_arithmetic_exact():
    anchor = aware(2026, 1, 1)
    assert retention_service.compute_expiry(anchor, 365) == aware(2027, 1, 1)
    assert retention_service.compute_expiry(anchor, 1) == aware(2026, 1, 2)


def candidate(policy_id, specificity):
    return {"policy": SimpleNamespace(id=policy_id), "version": SimpleNamespace(version=1),
            "scope_specificity": specificity}


def test_scope_precedence_deterministic():
    assert retention_service.select_policy([]) is None
    only = candidate("p1", 0)
    assert retention_service.select_policy([only]) is only
    project = candidate("pp", 3)
    unit = candidate("pu", 2)
    org = candidate("po", 1)
    glob = candidate("pg", 0)
    assert retention_service.select_policy([glob, org, unit, project]) is project
    assert retention_service.select_policy([glob, unit]) is unit
    assert retention_service.select_policy([org, glob]) is org
    # Same-level duplicates fail closed with an explicit conflict marker.
    assert retention_service.select_policy([candidate("a", 1), candidate("b", 1)]) == "POLICY_CONFLICT"
    assert retention_service.select_policy([candidate("a", 0), candidate("b", 0)]) == "POLICY_CONFLICT"


def hold(status="ACTIVE", expires_at=None, **fields):
    payload = {"id": "h1", "status": status, "expires_at": expires_at,
               "scope": "RESOURCE", "resource_type": "EVIDENCE", "resource_id": "e1",
               "project_id": None, "claim_id": None, "case_id": None,
               "organization_id": None, "created_at": aware()}
    payload.update(fields)
    return SimpleNamespace(**payload)


def test_hold_liveness():
    now = aware(2026, 6, 1)
    assert retention_service._hold_is_live(hold(), now) is True
    assert retention_service._hold_is_live(hold(status="RELEASED"), now) is False
    assert retention_service._hold_is_live(hold(status="CANCELLED"), now) is False
    assert retention_service._hold_is_live(hold(expires_at=aware(2027, 1, 1)), now) is True
    assert retention_service._hold_is_live(hold(expires_at=aware(2026, 1, 1)), now) is False
    # Expired-by-time holds behave as expired without any mutation.
    assert retention_service._hold_is_live(hold(expires_at=now), now) is False
    # Naive expiry is interpreted as UTC rather than crashing.
    assert retention_service._hold_is_live(
        hold(expires_at=datetime(2027, 1, 1)), now) is True


def test_scope_match_levels():
    policy = lambda scope, **ids: SimpleNamespace(scope_type=scope, **{
        "project_id": ids.get("project_id"), "organization_id": ids.get("organization_id"),
        "organizational_unit_id": ids.get("organizational_unit_id")})
    scope = {"project_id": "p", "organization_id": "o", "organizational_unit_id": "u"}
    assert retention_service._scope_match(policy("GLOBAL"), scope) == 0
    assert retention_service._scope_match(
        policy("PROJECT", project_id="p"), scope) == 3
    assert retention_service._scope_match(
        policy("PROJECT", project_id="other"), scope) is None
    assert retention_service._scope_match(
        policy("ORGANIZATION", organization_id="o"), scope) == 1
    assert retention_service._scope_match(
        policy("ORGANIZATIONAL_UNIT", organizational_unit_id="u"), scope) == 2
    assert retention_service._scope_match(policy("BOGUS"), scope) is None
    assert retention_service._scope_match(
        policy("PROJECT", project_id="p"), {"project_id": None,
                                            "organization_id": None,
                                            "organizational_unit_id": None}) is None


def test_uuid_helpers():
    from uuid import uuid4

    value = str(uuid4())
    assert retention_service._require_uuid(value, "x") == value
    assert retention_service._optional_uuid(None, "x") is None
    with pytest.raises(ValueError):
        retention_service._require_uuid("nope", "x")


def test_archive_prefix_and_hash_helpers():
    assert retention_service.ARCHIVE_PREFIX == "archive"
    assert retention_service._sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


def test_evaluation_shape_contract():
    evaluation = retention_service._evaluation(
        aware(), state="ACTIVE", anchor="INGESTED_AT", anchor_ts=aware(),
        expiry=aware(2027, 1, 1), policy=None, version=None,
        reasons=["NO_APPLICABLE_POLICY"], details={})
    assert evaluation["eligible"] is False
    assert evaluation["deletion_eligible"] is False
    assert evaluation["archive_eligible"] is False
    assert evaluation["state"] == "ACTIVE"
    assert evaluation["blocking_reasons"] == ["NO_APPLICABLE_POLICY"]
    assert evaluation["anchor_timestamp"] == "2026-01-01T00:00:00+00:00"


def test_response_schemas_have_no_forbidden_fields():
    for model in (retention_schemas.PolicyResponse, retention_schemas.HoldResponse,
                  retention_schemas.OperationResponse,
                  retention_schemas.RetentionEvaluationResponse):
        fields = set(model.model_fields)
        assert not (fields & {"fraud_score", "authenticity_score", "truth_score",
                              "risk_score", "probability", "verdict", "decision"})


def test_naive_datetimes_rejected_for_hold_bounds():
    import unittest.mock as mock

    db = mock.MagicMock()
    with pytest.raises(ValueError):
        retention_service.create_hold(
            db, scope="PROJECT", reason="r", project_id="00000000-0000-0000-0000-000000000000",
            expires_at=datetime(2030, 1, 1))
