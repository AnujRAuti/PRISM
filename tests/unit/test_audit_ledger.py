"""BE-015 unit tests: canonicalization, hashing, verification (no database)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.schemas import audit_ledger as audit_schemas
from backend.services import audit_ledger as audit_service


def aware(year=2026, month=1, day=1, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_canonical_serialization_is_deterministic():
    first = audit_service.canonical_json({"b": 1, "a": {"y": [3, 2], "x": None}})
    second = audit_service.canonical_json({"a": {"x": None, "y": [3, 2]}, "b": 1})
    assert first == second == '{"a":{"x":null,"y":[3,2]},"b":1}'


def test_canonical_normalization_types():
    moment = aware(2026, 3, 4, 5, 6, 7)
    assert audit_service.normalize_value(moment) == "2026-03-04T05:06:07+00:00"
    uid = uuid4()
    assert audit_service.normalize_value(uid) == str(uid)
    assert audit_service.normalize_value(b"\x00\xff") == "00ff"
    assert audit_service.normalize_value(True) is True
    assert audit_service.canonical_json({"e": "caf\u00e9", "c": 1}) == '{"c":1,"e":"caf\u00e9"}'
    with pytest.raises(ValueError):
        audit_service.normalize_value(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        audit_service.normalize_value(float("nan"))
    with pytest.raises(ValueError):
        audit_service.normalize_value(object())


def test_hash_deterministic_and_sensitive_to_protected_fields():
    base = {
        "event_id": str(uuid4()), "sequence_number": 7, "event_type": "EVIDENCE_UPLOADED",
        "action": "upload", "actor_id": None, "resource_type": "evidence",
        "resource_id": str(uuid4()), "payload": {"a": 1},
        "created_at": aware(), "previous_hash": "GENESIS",
    }
    first = audit_service.compute_event_hash(**base)
    assert first == audit_service.compute_event_hash(**base)
    assert len(first) == 64
    for field in ("event_id", "sequence_number", "event_type", "action", "resource_type",
                  "resource_id", "payload", "created_at", "previous_hash"):
        altered = dict(base)
        altered[field] = "CHANGED" if field != "sequence_number" else 999
        if field == "payload":
            altered[field] = {"a": 2}
        if field == "created_at":
            altered[field] = aware(2027, 1, 1)
        assert audit_service.compute_event_hash(**altered) != first, field
    # Actor participates too.
    altered = dict(base, actor_id=str(uuid4()))
    assert audit_service.compute_event_hash(**altered) != first


def test_previous_hash_links_chain():
    first_hash = audit_service.compute_event_hash(
        event_id=str(uuid4()), sequence_number=1, event_type="A", action="x",
        actor_id=None, resource_type="r", resource_id=None, payload={},
        created_at=aware(), previous_hash=audit_service.GENESIS_HASH)
    second_hash = audit_service.compute_event_hash(
        event_id=str(uuid4()), sequence_number=2, event_type="B", action="y",
        actor_id=None, resource_type="r", resource_id=None, payload={},
        created_at=aware(), previous_hash=first_hash)
    assert first_hash != second_hash


def make_row(sequence_number, event_hash, previous_hash, event_type="EVIDENCE_UPLOADED"):
    return SimpleNamespace(
        id=str(uuid4()), sequence_number=sequence_number, event_type=event_type,
        action="upload", actor_id=None, resource_type="evidence",
        resource_id=str(uuid4()), payload={"k": "v"}, created_at=aware(),
        previous_hash=previous_hash, event_hash=event_hash,
    )


def test_verify_event_detects_tampering():
    event_id, resource_id = str(uuid4()), str(uuid4())
    created = aware()
    good_hash = audit_service.compute_event_hash(
        event_id=event_id, sequence_number=3, event_type="EVIDENCE_UPLOADED",
        action="upload", actor_id=None, resource_type="evidence", resource_id=resource_id,
        payload={"k": "v"}, created_at=created, previous_hash="abc")
    row = SimpleNamespace(
        id=event_id, sequence_number=3, event_type="EVIDENCE_UPLOADED", action="upload",
        actor_id=None, resource_type="evidence", resource_id=resource_id,
        payload={"k": "v"}, created_at=created, previous_hash="abc", event_hash=good_hash)
    assert audit_service.verify_event(row, "abc") == (True, None)
    assert audit_service.verify_event(row, "wrong")[0] is False
    tampered = SimpleNamespace(**{**row.__dict__, "payload": {"k": "EVIL"}})
    assert audit_service.verify_event(tampered, "abc")[0] is False
    assert "mismatch" in audit_service.verify_event(tampered, "abc")[1]


def test_append_rejects_unknown_types_and_bad_fields():
    import unittest.mock as mock

    db = mock.MagicMock()
    with pytest.raises(ValueError):
        audit_service.append_event(db, event_type="BOGUS", action="x", resource_type="r")
    with pytest.raises(ValueError):
        audit_service.append_event(db, event_type="EVIDENCE_UPLOADED", action="  ",
                                   resource_type="r")
    with pytest.raises(ValueError):
        audit_service.append_event(db, event_type="EVIDENCE_UPLOADED", action="x",
                                   resource_type="  ")
    with pytest.raises(ValueError):
        audit_service.append_event(db, event_type="EVIDENCE_UPLOADED", action="x",
                                   resource_type="r", actor_id="nope")
    assert db.execute.call_count == 0


def test_sensitive_field_filtering():
    cleaned = audit_service.scrub_sensitive({
        "evidence_id": "abc", "password": "x", "Token": "y", "FILENAME": "f.jpg",
        "presigned_url": "z", "nested": {"keep": 1},
    })
    assert cleaned == {"evidence_id": "abc", "FILENAME": "f.jpg", "nested": {"keep": 1}}


def test_event_vocabulary_is_explicit():
    assert "EVIDENCE_UPLOADED" in audit_service.EVENT_TYPES
    assert "REVIEW_CASE_DECISION_RECORDED" in audit_service.EVENT_TYPES
    assert "GRAPH_RELATIONSHIP_CREATED" in audit_service.EVENT_TYPES
    assert len(audit_service.EVENT_TYPES) >= 20


def test_verify_chain_rejects_bad_ranges():
    import unittest.mock as mock

    db = mock.MagicMock()
    with pytest.raises(ValueError):
        audit_service.verify_chain(db, 0, 5)
    with pytest.raises(ValueError):
        audit_service.verify_chain(db, 5, 2)


def test_response_schemas_have_no_forbidden_fields():
    for model in (audit_schemas.AuditEventResponse, audit_schemas.AuditEventListResponse,
                  audit_schemas.AuditVerificationResponse):
        fields = set(model.model_fields)
        assert not (fields & {"password", "token", "secret", "fraud_score", "verdict"})
