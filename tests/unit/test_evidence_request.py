"""BE-014 unit tests: lifecycle, fulfillment, scope, due dates (no database)."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.schemas import evidence_request as request_schemas
from backend.services import evidence_request as request_service


def item(required=True, status="REQUESTED"):
    from types import SimpleNamespace

    return SimpleNamespace(required=required, item_status=status)


def aware(year=2030, month=1, day=1):
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_lifecycle_matrix_accepts_documented_moves():
    valid = [
        ("DRAFT", "OPEN"), ("DRAFT", "CANCELLED"),
        ("OPEN", "ACKNOWLEDGED"), ("OPEN", "DECLINED"), ("OPEN", "EXPIRED"),
        ("OPEN", "CANCELLED"), ("OPEN", "FULFILLED"), ("OPEN", "PARTIALLY_FULFILLED"),
        ("ACKNOWLEDGED", "DECLINED"), ("ACKNOWLEDGED", "EXPIRED"),
        ("ACKNOWLEDGED", "CANCELLED"), ("ACKNOWLEDGED", "FULFILLED"),
        ("ACKNOWLEDGED", "PARTIALLY_FULFILLED"),
        ("PARTIALLY_FULFILLED", "FULFILLED"), ("PARTIALLY_FULFILLED", "CANCELLED"),
    ]
    for from_status, to_status in valid:
        request_service.validate_transition(from_status, to_status)


def test_lifecycle_matrix_rejects_everything_else():
    invalid = [
        ("DRAFT", "ACKNOWLEDGED"), ("DRAFT", "FULFILLED"), ("DRAFT", "DECLINED"),
        ("OPEN", "DRAFT"), ("OPEN", "OPEN"),
        ("ACKNOWLEDGED", "DRAFT"), ("ACKNOWLEDGED", "OPEN"),
        ("ACKNOWLEDGED", "ACKNOWLEDGED"), ("FULFILLED", "OPEN"),
        ("FULFILLED", "CANCELLED"), ("FULFILLED", "PARTIALLY_FULFILLED"),
        ("DECLINED", "OPEN"), ("EXPIRED", "OPEN"), ("CANCELLED", "OPEN"),
        ("PARTIALLY_FULFILLED", "OPEN"), ("PARTIALLY_FULFILLED", "DECLINED"),
        ("PARTIALLY_FULFILLED", "EXPIRED"), ("PARTIALLY_FULFILLED", "PARTIALLY_FULFILLED"),
    ]
    for from_status, to_status in invalid:
        with pytest.raises(ValueError):
            request_service.validate_transition(from_status, to_status)
    with pytest.raises(ValueError):
        request_service.validate_transition("OPEN", "BOGUS")


def test_item_transitions():
    request_service.validate_item_transition("REQUESTED", "RECEIVED")
    request_service.validate_item_transition("RECEIVED", "ACCEPTED_FOR_REQUEST")
    request_service.validate_item_transition("RECEIVED", "REJECTED_FOR_REQUEST")
    for bad in [("REQUESTED", "ACCEPTED_FOR_REQUEST"), ("REQUESTED", "REJECTED_FOR_REQUEST"),
                ("ACCEPTED_FOR_REQUEST", "RECEIVED"), ("REJECTED_FOR_REQUEST", "RECEIVED"),
                ("RECEIVED", "RECEIVED"), ("ACCEPTED_FOR_REQUEST", "FULFILLED")]:
        with pytest.raises(ValueError):
            request_service.validate_item_transition(*bad)


def test_fulfillment_calculation():
    accepted = lambda required=True: item(required, "ACCEPTED_FOR_REQUEST")  # noqa: E731
    received = lambda required=True: item(required, "RECEIVED")  # noqa: E731
    assert request_service.fulfillment_state([]) is None
    assert request_service.fulfillment_state([item(True, "REQUESTED")]) is None
    assert request_service.fulfillment_state([received()]) is None
    assert request_service.fulfillment_state([accepted()]) == "FULFILLED"
    assert request_service.fulfillment_state([accepted(), accepted()]) == "FULFILLED"
    assert request_service.fulfillment_state([accepted(), item(True, "REQUESTED")]) == "PARTIALLY_FULFILLED"
    assert request_service.fulfillment_state([accepted(), received()]) == "PARTIALLY_FULFILLED"
    # Rejected items never count as fulfilled.
    assert request_service.fulfillment_state([item(True, "REJECTED_FOR_REQUEST")]) is None
    assert request_service.fulfillment_state(
        [accepted(), item(True, "REJECTED_FOR_REQUEST")]) == "PARTIALLY_FULFILLED"
    # Optional items never block fulfillment.
    assert request_service.fulfillment_state(
        [accepted(), item(False, "REQUESTED")]) == "FULFILLED"
    assert request_service.fulfillment_state([item(False, "REQUESTED")]) is None


def test_expiration_eligibility():
    now = aware(2026, 6, 1)
    assert request_service.expiration_eligible("OPEN", aware(2026, 1, 1), now) is True
    assert request_service.expiration_eligible("ACKNOWLEDGED", aware(2026, 1, 1), now) is True
    assert request_service.expiration_eligible("OPEN", aware(2027, 1, 1), now) is False
    assert request_service.expiration_eligible("OPEN", None, now) is False
    assert request_service.expiration_eligible("DRAFT", aware(2026, 1, 1), now) is False
    assert request_service.expiration_eligible("FULFILLED", aware(2026, 1, 1), now) is False
    assert request_service.expiration_eligible("DECLINED", aware(2026, 1, 1), now) is False
    # Naive "now" is treated as UTC rather than crashing.
    assert request_service.expiration_eligible(
        "OPEN", aware(2026, 1, 1), datetime(2026, 6, 1)) is True


def test_due_date_validation():
    assert request_service.normalize_due_at(None) is None
    converted = request_service.normalize_due_at(
        datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    )
    assert converted == datetime(2030, 1, 1, 6, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        request_service.normalize_due_at(datetime(2030, 1, 1, 12, 0, 0))
    with pytest.raises(ValueError):
        request_service.normalize_due_at("2030-01-01")


def test_scope_consistency():
    request_service.check_scope_consistency(
        {"project": "p1", "claim": "p1", "case": "p1", "evidence": None, "activity": None}
    )
    request_service.check_scope_consistency(
        {"project": None, "claim": None, "case": None, "evidence": None, "activity": None}
    )
    with pytest.raises(ValueError):
        request_service.check_scope_consistency(
            {"project": "p1", "claim": "p2", "case": None, "evidence": None, "activity": None}
        )
    with pytest.raises(ValueError):
        request_service.check_scope_consistency(
            {"project": "p1", "claim": None, "case": "p2", "evidence": None, "activity": None}
        )


def test_uuid_helpers():
    from uuid import uuid4

    value = str(uuid4())
    assert request_service._require_uuid(value, "x") == value
    assert request_service._optional_uuid(None, "x") is None
    with pytest.raises(ValueError):
        request_service._require_uuid("nope", "x")


def test_priority_vocab_is_operational_only():
    assert request_service.PRIORITIES == {"LOW", "NORMAL", "HIGH", "URGENT"}
    assert "CRITICAL" not in request_service.PRIORITIES


def test_response_schemas_have_no_forbidden_fields():
    for model in (request_schemas.EvidenceRequestResponse,
                  request_schemas.EvidenceRequestItemResponse,
                  request_schemas.EvidenceRequestLinkResponse):
        fields = set(model.model_fields)
        assert not (fields & {"fraud_score", "authenticity_score", "truth_score",
                              "risk_score", "verdict", "decision"})
