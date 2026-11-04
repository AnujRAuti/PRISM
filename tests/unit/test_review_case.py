"""BE-013 unit tests: policy, transitions, decisions (no database)."""

import pytest

from backend.schemas import review_case as case_schemas
from backend.services import review_case as case_service
from backend.services.review_case import DEFAULT_POLICY_V1


def policy(**overrides):
    base = {
        "generate_bands": ["URGENT", "HIGH"],
        "include_normal": False,
        "dedupe_open_cases_per_target": True,
    }
    base.update(overrides)
    return base


def test_policy_eligibility_exact():
    assert case_service.evaluate_policy("MIXED", "URGENT", policy()) == (True, "BAND_ELIGIBLE")
    assert case_service.evaluate_policy("SUPPORTED", "HIGH", policy()) == (True, "BAND_ELIGIBLE")
    assert case_service.evaluate_policy("SUPPORTED", "NORMAL", policy()) == (False, "BAND_NOT_INCLUDED")
    assert case_service.evaluate_policy("UNKNOWN", "LOW", policy()) == (False, "BAND_NOT_INCLUDED")
    assert case_service.evaluate_policy("SUPPORTED", "NORMAL", policy(include_normal=True)) == (
        True, "NORMAL_INCLUDED",
    )
    # Assessment value never gates by documented V1 design.
    assert case_service.evaluate_policy(None, "HIGH", policy())[0] is True
    assert case_service.evaluate_policy("CONTRADICTED", "LOW", policy())[0] is False


def test_policy_validation():
    assert case_service.validate_policy(policy()) == policy()
    assert case_service.validate_policy(DEFAULT_POLICY_V1) == DEFAULT_POLICY_V1
    with pytest.raises(ValueError):
        case_service.validate_policy({"generate_bands": []})
    with pytest.raises(ValueError):
        case_service.validate_policy({"generate_bands": ["CRITICAL"]})
    with pytest.raises(ValueError):
        case_service.validate_policy({"generate_bands": ["HIGH"], "include_normal": "yes"})
    with pytest.raises(ValueError):
        case_service.validate_policy("not-a-mapping")


def test_default_policy_shape():
    assert DEFAULT_POLICY_V1["generate_bands"] == ["URGENT", "HIGH"]
    assert DEFAULT_POLICY_V1["include_normal"] is False
    assert DEFAULT_POLICY_V1["dedupe_open_cases_per_target"] is True


def test_lifecycle_matrix_accepts_documented_moves():
    valid = [
        ("OPEN", "ASSIGNED"), ("OPEN", "ESCALATED"),
        ("ASSIGNED", "OPEN"), ("ASSIGNED", "INVESTIGATING"), ("ASSIGNED", "ESCALATED"),
        ("INVESTIGATING", "DECISION_PENDING"), ("INVESTIGATING", "ESCALATED"),
        ("DECISION_PENDING", "RESOLVED"), ("DECISION_PENDING", "ESCALATED"),
        ("ESCALATED", "ASSIGNED"), ("ESCALATED", "INVESTIGATING"),
        ("RESOLVED", "OPEN"),
    ]
    for from_status, to_status in valid:
        case_service.validate_transition(from_status, to_status)


def test_lifecycle_matrix_rejects_everything_else():
    invalid = [
        ("OPEN", "INVESTIGATING"), ("OPEN", "RESOLVED"), ("OPEN", "DECISION_PENDING"),
        ("OPEN", "OPEN"), ("ASSIGNED", "ASSIGNED"), ("ASSIGNED", "RESOLVED"),
        ("ASSIGNED", "DECISION_PENDING"), ("INVESTIGATING", "OPEN"),
        ("INVESTIGATING", "ASSIGNED"), ("INVESTIGATING", "RESOLVED"),
        ("DECISION_PENDING", "OPEN"), ("DECISION_PENDING", "INVESTIGATING"),
        ("DECISION_PENDING", "ASSIGNED"), ("ESCALATED", "OPEN"),
        ("ESCALATED", "RESOLVED"), ("ESCALATED", "DECISION_PENDING"),
        ("ESCALATED", "ESCALATED"), ("RESOLVED", "ASSIGNED"),
        ("RESOLVED", "RESOLVED"), ("RESOLVED", "ESCALATED"),
        ("RESOLVED", "INVESTIGATING"), ("RESOLVED", "DECISION_PENDING"),
    ]
    for from_status, to_status in invalid:
        with pytest.raises(ValueError):
            case_service.validate_transition(from_status, to_status)
    with pytest.raises(ValueError):
        case_service.validate_transition("OPEN", "BOGUS")
    with pytest.raises(ValueError):
        case_service.validate_transition("BOGUS", "OPEN")


def test_decision_validation():
    assert case_service.validate_decision("SUPPORTED", "looks consistent") == (
        "SUPPORTED", "looks consistent",
    )
    assert case_service.validate_decision("INCONCLUSIVE", "  padded  ") == (
        "INCONCLUSIVE", "padded",
    )
    with pytest.raises(ValueError):
        case_service.validate_decision("FRAUD", "reason")
    with pytest.raises(ValueError):
        case_service.validate_decision("SUPPORTED", "")
    with pytest.raises(ValueError):
        case_service.validate_decision("SUPPORTED", "   ")
    with pytest.raises(ValueError):
        case_service.validate_decision(None, "reason")


def test_decision_vocab_excludes_automation_outcomes():
    # Human decisions never include fusion-only values like MIXED/UNKNOWN.
    assert "MIXED" not in case_service.DECISIONS
    assert "UNKNOWN" not in case_service.DECISIONS
    assert case_service.DECISIONS == {
        "SUPPORTED", "CONTRADICTED", "INCONCLUSIVE", "INSUFFICIENT_EVIDENCE",
    }


def test_uuid_helpers():
    from uuid import uuid4

    value = str(uuid4())
    assert case_service._require_uuid(value, "x") == value
    assert case_service._optional_uuid(None, "x") is None
    assert case_service._optional_uuid(value, "x") == value
    with pytest.raises(ValueError):
        case_service._require_uuid("not-a-uuid", "x")
    with pytest.raises(ValueError):
        case_service._optional_uuid("not-a-uuid", "x")


def test_result_state_constants():
    assert case_service.RESULT_CREATED == "CASE_CREATED"
    assert case_service.RESULT_EXISTS == "CASE_ALREADY_EXISTS"
    assert case_service.RESULT_NOT_ELIGIBLE == "NOT_ELIGIBLE"
    assert case_service.RESULT_UNAVAILABLE == "UNAVAILABLE"


def test_response_schemas_have_no_forbidden_fields():
    for model in (case_schemas.ReviewCaseResponse, case_schemas.CaseGenerationResponse,
                  case_schemas.ReviewCaseHistoryResponse):
        fields = set(model.model_fields)
        assert not (fields & {"fraud_score", "authenticity_score", "truth_score",
                              "risk_score", "probability", "verdict"})
    assert "decision" in case_schemas.ReviewCaseResponse.model_fields
