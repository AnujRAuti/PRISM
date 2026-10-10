"""BE-030 §13: append-only enforcement and chain-integrity, shipped tests.

These require the enforcement migration (``t0u1v2w3x030``) to be applied to the
test database — the refusing trigger and the event-type ``CHECK`` must exist.
They exercise the D-1-A hatch, the D-2-A write guard, the out-of-domain refusal
and the anchored-vs-windowed verification asymmetry.

Scope note on DELETE: BE-030 §13 also calls for a shipped "DELETE refused" test.
The audit guard (``tests/audit_guard.py``) treats any DELETE against the ledger
as an unconditional violation — even rolled back — because a rollback does not
license removing a row, and that is a deliberate safety property (see
``test_core_delete_has_no_rollback_exception``). So the DELETE-refusal proof is
carried on a disposable clone (BE-030 feasibility ``p2a`` / ``p2g``), exactly as
BE-029 carried DELETE detection there, rather than by narrowing the guard. UPDATE
is the mutating statement the guard *does* sanction inside a named,
rollback-guaranteed test, so the trigger refusal is pinned with a rolled-back
UPDATE here.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from backend.db.session import get_session
from backend.services import audit_ledger as audit_service
from backend.services.audit_ledger import (
    PredecessorInvalid,
    append_event,
    sanctioned_ledger_mutation,
)

pytestmark = pytest.mark.integration

PROBE = "be030-ledger-enforcement"


@pytest.fixture()
def db():
    session = get_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _sqlstate(exc) -> str | None:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(diag, "sqlstate", None) or getattr(orig, "pgcode", None)


def probe_append(db, note: str):
    """Append one committed probe event through the real writer."""
    row = append_event(
        db, event_type="ORGANIZATION_CREATED", action="create",
        resource_type="organizations", payload={"probe": PROBE, "note": note},
        source=PROBE,
    )
    db.commit()
    return row


def test_append_negative_control_with_enforcement_live(db):
    """§13.3: inserts are untouched — append still works with the trigger live."""
    before = int(db.execute(
        text("SELECT coalesce(max(sequence_number),0) FROM audit_ledger_events")
    ).scalar_one())
    row = probe_append(db, f"{PROBE}-append-works")
    assert int(row.sequence_number) == before + 1
    check = audit_service.verify_chain(
        db, from_sequence=max(before, 1), to_sequence=before + 1)
    assert check["valid"] is True, check["failures"]


def test_update_without_hatch_is_refused(db):
    """§13.1/§13.2: the trigger refuses UPDATE with SQLSTATE 42501, per operation."""
    row = probe_append(db, f"{PROBE}-refuse-update-target")
    try:
        with pytest.raises(ProgrammingError) as excinfo:
            db.execute(
                text("UPDATE audit_ledger_events SET action = :a WHERE id = :i"),
                {"a": "rewritten", "i": str(row.id)},
            )
        assert _sqlstate(excinfo.value) == "42501", _sqlstate(excinfo.value)
        assert "append-only enforcement refuses UPDATE" in str(excinfo.value.orig)
    finally:
        db.rollback()
    # The refused UPDATE never landed: the row is still valid.
    assert audit_service.verify_chain(
        db, from_sequence=row.sequence_number, to_sequence=row.sequence_number
    )["valid"] is True


def test_hatch_permits_and_records_sanctioned_update(db, caplog):
    """§13.4 + §13.5: SET LOCAL hatch allows the edit AND is observable; and the
    hatch is transaction-scoped (a fresh transaction is refused again)."""
    row = probe_append(db, f"{PROBE}-hatch-target")
    with caplog.at_level(logging.WARNING,
                         logger="backend.services.audit_ledger"):
        with sanctioned_ledger_mutation(db, "BE-030 §13.4 hatch proof"):
            db.execute(
                text("UPDATE audit_ledger_events SET action = :a WHERE id = :i"),
                {"a": "sanctioned", "i": str(row.id)},
            )
            db.flush()
        assert "AUDIT_LEDGER_HATCH_OPEN" in caplog.text
        assert "BE-030 §13.4 hatch proof" in caplog.text
    # The sanctioned edit is visible within the (still open) transaction.
    db.expire_all()
    seen = db.execute(
        text("SELECT action FROM audit_ledger_events WHERE id = :i"),
        {"i": str(row.id)},
    ).scalar_one()
    assert seen == "sanctioned"
    # Roll it back; the SET LOCAL hatch does not survive the transaction.
    db.rollback()
    with pytest.raises(ProgrammingError) as excinfo:
        db.execute(
            text("UPDATE audit_ledger_events SET action = :a WHERE id = :i"),
            {"a": "should-fail", "i": str(row.id)},
        )
    assert _sqlstate(excinfo.value) == "42501"
    db.rollback()


def test_out_of_domain_insert_is_refused(db):
    """§13.13: after the CHECK, a raw out-of-domain event_type insert is refused."""
    from uuid import uuid4
    bad_type = "NOT_A_REAL_EVENT_TYPE_BE030"
    with pytest.raises(IntegrityError) as excinfo:
        db.execute(
            text("INSERT INTO audit_ledger_events (id, sequence_number, event_type,"
                 " action, resource_type, payload, metadata, previous_hash,"
                 " event_hash, hash_algorithm, ledger_version, created_at)"
                 " VALUES (:id, (SELECT coalesce(max(sequence_number),0)+1"
                 " FROM audit_ledger_events), :t, 'x', 'y', '{}'::jsonb,"
                 " '{}'::jsonb, 'g', 'h', 'sha256', 'v1', now())"),
            {"id": str(uuid4()), "t": bad_type},
        )
    assert _sqlstate(excinfo.value) == "23514", _sqlstate(excinfo.value)
    db.rollback()


def test_enforcement_objects_are_present_in_the_catalog(db):
    """§13.6: the drift gate cannot see the enforcement (feasibility §2a), so the
    catalog itself is pinned — trigger, function and CHECK all exist."""
    trigger = db.execute(text(
        "SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid"
        " JOIN pg_namespace n ON n.oid=c.relnamespace"
        " WHERE t.tgname='trg_audit_ledger_append_only' AND c.relname="
        "'audit_ledger_events' AND n.nspname='public' AND NOT t.tgisinternal"
    )).fetchone()
    assert trigger, "append-only trigger is not installed on this database"
    function = db.execute(text(
        "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace"
        " WHERE p.proname='audit_ledger_refuse_mutation' AND n.nspname='public'"
    )).fetchone()
    assert function, "refusal trigger function is not installed"
    check = db.execute(text(
        "SELECT 1 FROM pg_constraint WHERE conname="
        "'ck_audit_ledger_event_type_domain' AND conrelid="
        "'public.audit_ledger_events'::regclass"
    )).fetchone()
    assert check, "event-type domain CHECK is not installed"


def test_append_refused_after_tail_tampering(db):
    """§13.8 D-2-A: the writer recomputes the immediate predecessor and refuses to
    append onto a damaged tail."""
    probe_append(db, f"{PROBE}-d2a-first")
    tail = probe_append(db, f"{PROBE}-d2a-tail")
    try:
        with sanctioned_ledger_mutation(db, "BE-030 D-2-A tail tamper"):
            db.execute(
                text("UPDATE audit_ledger_events SET payload = :p WHERE id = :i"),
                {"p": '{"tampered": true}', "i": str(tail.id)},
            )
            db.flush()
        # The raw UPDATE bypasses the ORM identity map; expire so the writer's
        # next read loads the tampered payload from the database, exactly as it
        # would in production when the damage was committed by another session.
        db.expire_all()
        with pytest.raises(PredecessorInvalid):
            append_event(db, event_type="ORGANIZATION_CREATED", action="create",
                         resource_type="organizations",
                         payload={"probe": PROBE, "note": f"{PROBE}-should-refuse"},
                         source=PROBE)
    finally:
        db.rollback()


def test_anchored_verification_catches_mid_chain_tampering(db):
    """§13.9: a tampered middle row is invisible to a downstream window but is
    caught by a walk that includes it — the asymmetry D-2-A relies on §9 for."""
    first = probe_append(db, f"{PROBE}-mid-first")
    middle = probe_append(db, f"{PROBE}-mid-target")
    last = probe_append(db, f"{PROBE}-mid-last")
    try:
        with sanctioned_ledger_mutation(db, "BE-030 §13.9 middle tamper"):
            db.execute(
                text("UPDATE audit_ledger_events SET payload = :p WHERE id = :i"),
                {"p": '{"tampered": true}', "i": str(middle.id)},
            )
            db.flush()
        db.expire_all()
        # A window strictly after the tampered row is locally valid.
        downstream = audit_service.verify_chain(
            db, from_sequence=int(last.sequence_number),
            to_sequence=int(last.sequence_number))
        assert downstream["valid"] is True, downstream["failures"]
        # Including the tampered row flags it.
        covering = audit_service.verify_chain(
            db, from_sequence=int(first.sequence_number),
            to_sequence=int(last.sequence_number))
        assert covering["valid"] is False
        assert any("event_hash mismatch" in f for f in covering["failures"])
    finally:
        db.rollback()
