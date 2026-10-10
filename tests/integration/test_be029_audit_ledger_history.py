"""BE-029 Phase G: the audit ledger's append-only history, pinned by tests.

Why these tests exist
---------------------
``pofa_dev``'s chain verifies as invalid in one specific shape: 36 sequence
numbers missing across 7 ranges, and *no* hash recomputation failure anywhere in
6,023 events. Reading the writer explains the shape: ``append_event`` derives
every number from the row that currently has the maximum, under an advisory
transaction lock, so an application append — even one that rolls back — cannot
skip a number. A discontinuity can therefore only mean rows were removed after
the fact.

What this file proves, and what it deliberately does not
-------------------------------------------------------
* the writer stays contiguous and keeps the chain valid;
* a rolled-back append burns no sequence number, so failed traffic cannot open a
  gap;
* rewriting an event in place is caught by ``verify_chain`` — the test that
  demonstrates that never commits: it edits a row this file created, inside a
  transaction that is rolled back, then re-reads it from a fresh session.

Detection of *removal* is deliberately not tested here. ``tests/audit_guard.py``
makes any DELETE against the ledger a violation, with no rollback exception —
"there is no legitimate reason for a test to remove a ledger row" — so that half
of the property is proven on a disposable clone instead (BE-029 results §14.6),
and the guard itself is regression-tested against the DELETE spellings in
``tests/unit/test_audit_guard.py``.

Nothing here repairs, renumbers or deletes committed history. The events these
tests append stay in the ledger: that is what append-only means, and a test that
tidied up by deleting its own audit rows would be demonstrating the exact
violation it is supposed to detect.

The tampering attempts are confined to rows created in this file, identified by
primary key. They never touch an event that predates the test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from backend.db.models import AuditLedgerEvent
from backend.db.session import get_session
from backend.services.audit_ledger import (
    append_event,
    sanctioned_ledger_mutation,
    verify_chain,
)

pytestmark = pytest.mark.integration

#: Marks every event this file writes, so its rows are always findable and
#: always its own — never a historical event.
PROBE = "be029-phase-g-history"


@pytest.fixture()
def db():
    session = get_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def probe_event(db, note: str) -> AuditLedgerEvent:
    """Append one event through the real writer, marked as this file's."""
    row = append_event(db, event_type="ORGANIZATION_CREATED", action="create",
                       resource_type="organizations",
                       payload={"probe": PROBE, "note": note}, source=PROBE)
    db.commit()
    return row


def max_sequence(db) -> int:
    return int(db.execute(
        text("SELECT coalesce(max(sequence_number), 0) FROM audit_ledger_events")
    ).scalar_one())


def count_events(db) -> int:
    return int(db.execute(
        text("SELECT count(*) FROM audit_ledger_events")).scalar_one())


def test_appends_are_contiguous_and_keep_the_chain_valid(db):
    """The writer never skips: each number is the previous maximum plus one.

    This is the invariant that makes ``pofa_dev``'s gaps a *deletion* finding
    rather than a writer bug. It is checked on the live chain, not an empty one,
    so it cannot pass by accident on a fresh database.
    """
    start = max_sequence(db)
    first = probe_event(db, f"{PROBE}-contiguous-1")
    second = probe_event(db, f"{PROBE}-contiguous-2")
    assert (int(first.sequence_number), int(second.sequence_number)) == (
        start + 1, start + 2)

    check = verify_chain(db, from_sequence=max(start, 1), to_sequence=start + 2)
    assert check["valid"] is True, check["failures"]
    assert check["first_sequence"] == max(start, 1)
    assert check["last_sequence"] == start + 2


def test_a_rolled_back_append_does_not_burn_a_sequence_number(db):
    """A failed transaction must not leave a hole in the chain.

    If it did, ordinary application errors would be enough to explain the 36
    missing rows on ``pofa_dev`` and the ledger's gaps would be a symptom rather
    than evidence of removal.
    """
    start = max_sequence(db)
    rows_before = count_events(db)
    attempted = append_event(db, event_type="ORGANIZATION_CREATED", action="create",
                             resource_type="organizations",
                             payload={"probe": PROBE, "note": f"{PROBE}-rollback"},
                             source=PROBE)
    assert int(attempted.sequence_number) == start + 1
    db.rollback()

    assert count_events(db) == rows_before, "the rolled-back append was persisted"
    revived = probe_event(db, f"{PROBE}-after-rollback")
    assert int(revived.sequence_number) == start + 1, (
        "a number was burned: the ledger would now show a permanent gap")
    assert verify_chain(db, from_sequence=max(start, 1),
                        to_sequence=start + 1)["valid"] is True


def test_rewriting_an_event_is_detected_by_hash_recomputation(db):
    """Editing history in place is caught even though no row disappears.

    The ledger's protection is a hash recomputed from the persisted fields, so a
    payload rewrite breaks the event's own hash. As above: this file's row,
    inside a transaction that is rolled back.
    """
    event = probe_event(db, f"{PROBE}-tamper-target")
    sequence = int(event.sequence_number)

    # BE-030 D-1-A: the refusing trigger permits this sanctioned, rolled-back
    # rewrite only through the audited SET LOCAL hatch. The edit is still undone
    # by the fixture's rollback, and the hash recompute still detects it.
    with sanctioned_ledger_mutation(
        db, "BE-030 D-1-A sanctioned hash-recompute proof"
    ):
        db.execute(text("UPDATE audit_ledger_events SET payload = '{\"probe\":"
                        " \"be029-phase-g-history\", \"tampered\": true}'::jsonb"
                        " WHERE id = :id"), {"id": event.id})
        db.flush()
    db.expire_all()  # the UPDATE went around the ORM; verify against the database
    detected = verify_chain(db, from_sequence=sequence, to_sequence=sequence)
    assert detected["valid"] is False, detected
    assert any("event_hash mismatch" in failure for failure in detected["failures"]), (
        detected["failures"])

    db.rollback()
    restored = get_session()
    try:
        row = restored.get(AuditLedgerEvent, event.id)
        assert row is not None and "tampered" not in (row.payload or {}), row.payload
        assert verify_chain(restored, from_sequence=sequence,
                            to_sequence=sequence)["valid"] is True
    finally:
        restored.close()


def test_probe_events_from_this_file_are_findable_and_stay(db):
    """Every event this file writes is marked, and none of them is cleaned up.

    That is what makes the claim checkable: "the suite deleted audit history"
    can be answered by querying the marker. A teardown that removed these rows
    to leave the database tidy would be committing the violation this file
    exists to detect.
    """
    marked = db.execute(
        text("SELECT sequence_number FROM audit_ledger_events"
             " WHERE payload->>'probe' = :probe ORDER BY sequence_number"),
        {"probe": PROBE}).all()
    assert marked, "this file's own events must be findable by marker"
    sequences = [row[0] for row in marked]
    assert sequences == sorted(sequences)
