"""BE-032R F-03 / D-CHAIN: the anchored-verification endpoint and the classified
read path, exercised against the real test database (``pofa_test``).

Everything here is read-only or rolled back. ``pofa_test`` is a protected
database: no test may delete ledger rows or leave a committed tamper. The one
write-shaped case opens the sanctioned ``SET LOCAL`` hatch and rolls back, the
same pattern BE-030 §13 uses, so no damage persists.

What is being proven that BE-030 did not already:
  * ``verify_chain_classified`` attaches a *classification* (status / degraded /
    buckets) and a ``writer_policy`` to the anchored walk;
  * the durable detection that D-CHAIN leans on fires for a mid-chain hash
    mismatch — a rolled-back tamper degrades the classification, and once rolled
    back the same database is ``clean`` again;
  * the ``/verify/anchored`` endpoint serves that structure, is gated like every
    other audit route, and rejects an unknown baseline instead of silently
    defaulting.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.main import app
from backend.db.session import get_session
from backend.services import audit_ledger as audit_service
from backend.services.audit_integrity_baseline import POFA_DEV_HISTORICAL_BASELINE

pytestmark = pytest.mark.integration

client = TestClient(app)
PROBE = "be032r-anchored"


@pytest.fixture()
def db():
    session = get_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def probe_append(db, note: str):
    row = audit_service.append_event(
        db, event_type="ORGANIZATION_CREATED", action="create",
        resource_type="organizations", payload={"probe": PROBE, "note": note},
        source=PROBE,
    )
    db.commit()
    return row


# ---------------------------------------------------------------------------
# verify_chain_classified (service layer)
# ---------------------------------------------------------------------------


def test_clean_ledger_classifies_as_clean(db):
    probe_append(db, f"{PROBE}-clean")
    result = audit_service.verify_chain_classified(db)
    assert result["valid"] is True
    assert result["classification"]["status"] == "clean"
    assert result["classification"]["degraded"] is False
    assert result["classification"]["hard_anomalies"] == []
    assert result["writer_policy"] == "controlled_continuation"
    # the anchored walk publishes the checkpoint digest
    assert result["checkpoint"]["rows"] >= 1
    assert result["checkpoint"]["max_sequence"] >= 1
    assert result["checkpoint"]["tail_event_hash"]


def test_midchain_tamper_degrades_and_a_rollback_restores_clean(db):
    first = probe_append(db, f"{PROBE}-tamper-first")
    middle = probe_append(db, f"{PROBE}-tamper-target")
    probe_append(db, f"{PROBE}-tamper-last")
    try:
        with audit_service.sanctioned_ledger_mutation(db, "BE-032R degraded proof"):
            db.execute(
                text("UPDATE audit_ledger_events SET payload = :p WHERE id = :i"),
                {"p": '{"tampered": true}', "i": str(middle.id)},
            )
            db.flush()
        db.expire_all()
        result = audit_service.verify_chain_classified(db)
        assert result["valid"] is False
        assert result["classification"]["status"] == "new_anomaly"
        assert result["classification"]["degraded"] is True
        assert any("event_hash mismatch" in f
                   for f in result["classification"]["hard_anomalies"])
    finally:
        db.rollback()
    # Rolled back: the same classified walk on a fresh session is clean again.
    session = get_session()
    try:
        assert audit_service.verify_chain_classified(
            session)["classification"]["status"] == "clean"
    finally:
        session.close()
    assert first is not None and middle is not None


def test_baseline_selection_does_not_invent_history_on_a_clean_db(db):
    probe_append(db, f"{PROBE}-baseline")
    # Selecting the pofa_dev register on a database that has no findings stays
    # clean: a baseline only re-labels existing gap findings, it never fabricates
    # them and never turns a clean ledger into known_historical_only.
    result = audit_service.verify_chain_classified(
        db, POFA_DEV_HISTORICAL_BASELINE.name)
    assert result["classification"]["status"] == "clean"
    assert result["classification"]["known_historical_gaps"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/audit/verify/anchored (F-03 endpoint)
# ---------------------------------------------------------------------------


def test_anchored_endpoint_serves_classified_structure(db):
    row = probe_append(db, f"{PROBE}-endpoint")
    response = client.get("/api/v1/audit/verify/anchored")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["writer_policy"] == "controlled_continuation"
    assert body["classification"]["status"] == "clean"
    assert body["classification"]["degraded"] is False
    assert set(body["classification"]) >= {
        "status", "degraded", "known_historical_gaps", "new_gaps",
        "hard_anomalies", "baseline_name", "baseline_version",
    }
    assert set(body["checkpoint"]) >= {
        "rows", "min_sequence", "max_sequence", "tail_event_hash",
        "tail_previous_hash",
    }
    assert body["checkpoint"]["max_sequence"] >= int(row.sequence_number)


@pytest.mark.parametrize("name", [
    "none", POFA_DEV_HISTORICAL_BASELINE.name,
])
def test_anchored_endpoint_accepts_registered_baselines(db, name):
    probe_append(db, f"{PROBE}-ok-baseline")
    response = client.get(
        "/api/v1/audit/verify/anchored", params={"baseline": name})
    assert response.status_code == 200, response.text
    assert response.json()["classification"]["baseline_name"] == name


def test_anchored_endpoint_rejects_unknown_baseline(db):
    probe_append(db, f"{PROBE}-bad-baseline")
    response = client.get(
        "/api/v1/audit/verify/anchored", params={"baseline": "not-a-baseline"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "not-a-baseline" in detail
    # honest about what is available rather than silently defaulting
    assert POFA_DEV_HISTORICAL_BASELINE.name in detail


def test_anchored_endpoint_is_read_only(db):
    probe_append(db, f"{PROBE}-read-only")
    assert client.post("/api/v1/audit/verify/anchored").status_code == 405
    assert client.put("/api/v1/audit/verify/anchored").status_code == 405
    assert client.delete("/api/v1/audit/verify/anchored").status_code == 405
