"""BE-030 D-2 prototype: what does a chain-aware writer actually cost, and does
the recommended policy (A: validate only the immediate predecessor) keep a
gapped database writable?

Run against the disposable clone p2a/p2b left with enforcement installed.

    python p2e_writer_prototype.py <sqlalchemy-url>

Damage is created on purpose, because the clone is the only place that is
allowed to hold it:
  * shape 1 -- the tail row's payload rewritten and *committed* (results §14.11,
    the re-basing attack), to see whether the shipped writer notices and whether
    a predecessor-checking writer does;
  * shape 2 -- a row deleted from the middle of the chain, to see the gap case
    D-2-A has to survive.
The enforcement trigger is dropped for the damage and reinstated afterwards, so
the damage is provably *pre-enforcement* history, which is the state `pofa_dev`
is actually in.
"""

from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.db import safety  # noqa: E402
from backend.db.models import AUDIT_EVENT_TYPES  # noqa: E402
from backend.db.session import build_guarded_engine  # noqa: E402
from backend.repositories import audit_ledger as audit_repo  # noqa: E402
from backend.services.audit_ledger import (  # noqa: E402
    APPEND_LOCK_KEY, append_event, verify_chain, verify_event)

from p2a_install_and_probe import (  # noqa: E402
    CHECK, FUNC, INSTALL_FUNCTION, INSTALL_TRIGGER, TABLE, TRIGGER)

results: dict = {}
probe_type = sorted(AUDIT_EVENT_TYPES)[0]


class PredecessorInvalid(RuntimeError):
    """The proposed §8 typed refusal: refuse, name the row, never re-anchor."""


def chain_aware_append(db: Session, **kwargs):
    """Prototype of the D-2-A write path, using only shipped internals.

    Same advisory lock the writer already holds, so check and link are atomic.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
               {"key": APPEND_LOCK_KEY})
    predecessor = audit_repo.latest(db)
    if predecessor is not None:
        ok, failure = verify_event(predecessor)
        if not ok:
            raise PredecessorInvalid(
                f"refusing to append: predecessor sequence "
                f"{int(predecessor.sequence_number)} does not verify ({failure})")
    return append_event(db, **kwargs)


def drop_enforcement(engine):
    with engine.begin() as conn:
        conn.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE}"))


def install_enforcement(engine):
    with engine.begin() as conn:
        conn.execute(text(INSTALL_FUNCTION))
        conn.execute(text(INSTALL_TRIGGER))


def tail_state(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text(
            f"SELECT count(*), max(sequence_number) FROM {TABLE}")).one()
    return {"rows": int(row[0]), "max_sequence": int(row[1])}


def main() -> int:
    url = sys.argv[1]
    authorized = safety.arm_verification(url)
    engine = build_guarded_engine(url)
    with engine.connect() as conn:
        database = conn.execute(text("SELECT current_database()")).scalar_one()
    if database != authorized:
        raise SystemExit(f"armed {authorized}, reached {database}")
    results["target"] = database
    results["state_at_start"] = tail_state(engine)

    # ---- shape 1: committed tail tamper, i.e. the re-basing attack (F-5)
    with engine.connect() as victim_conn:
        victim_sequence = int(victim_conn.execute(text(
            f"SELECT max(sequence_number) FROM {TABLE}")).scalar_one())
        victim_id = victim_conn.execute(text(
            f"SELECT id FROM {TABLE} WHERE sequence_number = :s"),
            {"s": victim_sequence}).scalar_one()

    drop_enforcement(engine)
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {TABLE} SET payload = CAST(CAST(payload AS jsonb) "
            "|| '{\"tampered\": true}' AS json) WHERE id = CAST(:id AS uuid)"),
            {"id": str(victim_id)})
    install_enforcement(engine)
    results["damage_1"] = {"tampered_sequence": victim_sequence,
                           "committed": True,
                           "trigger_reinstalled_after": True}

    # Full-chain and tail-window verdicts on that state, before touching it again.
    with Session(engine) as db:
        full = verify_chain(db)
        tail = verify_chain(db, from_sequence=victim_sequence + 1)
        results["verify_after_damage_full"] = {
            "valid": full["valid"], "checked": full["checked_events"],
            "failures": full["failures"][:5]}
        results["verify_after_damage_tail_window"] = {
            "note": "a window starting after the tampered row cannot see it",
            "valid": tail["valid"], "checked": tail["checked_events"],
            "first_sequence": tail["first_sequence"]}

        # The shipped writer, unchanged: does it notice? (control)
        control_before = tail_state(engine)
        row = append_event(db, event_type=probe_type, action="BE030-CONTROL",
                           resource_type="probe", payload={"control": True},
                           commit=True)
        results["shipped_writer_after_damage"] = {
            "appended_sequence": int(row.sequence_number),
            "previous_hash_equals_stale_tail": str(row.previous_hash) ==
            str(db.execute(text(f"SELECT event_hash FROM {TABLE} "
                               f"WHERE sequence_number = :s"),
                          {"s": victim_sequence}).scalar_one())}
        control_after = tail_state(engine)
        results["shipped_writer_after_damage"]["state"] = {
            "before": control_before, "after": control_after}

        # The prototype: refuse, and leave the damaged row alone.
        refused = None
        try:
            chain_aware_append(db, event_type=probe_type,
                               action="BE030-PROTOTYPE", resource_type="probe",
                               payload={"should_refuse": True}, commit=True)
            results["prototype_after_damage"] = {"outcome": "executed"}
        except PredecessorInvalid as exc:
            db.rollback()
            refused = str(exc)
            results["prototype_after_damage"] = {"outcome": "refused",
                                                 "message": refused[:220]}
        with Session(engine) as check_db:
            still_tampered = check_db.execute(text(
                f"SELECT payload::text FROM {TABLE} WHERE sequence_number = :s"),
                {"s": victim_sequence}).scalar_one()
        results["prototype_left_damaged_row_untouched"] = (
            "tampered" in json.loads(still_tampered))

    # ---- cost of the extra recompute, measured on the same data
    with Session(engine) as db:
        started = time.perf_counter()
        for i in range(20):
            append_event(db, event_type=probe_type, action="BE030-TIMING-SHIPPED",
                         resource_type="probe", payload={"i": i}, commit=True)
        shipped_ms = round((time.perf_counter() - started) * 1000 / 20, 2)
    results["timing_note"] = (
        "the shipped writer currently refuses nothing on this database shape, "
        "so its 20 appends are the control; the prototype refuses at the first "
        "damaged predecessor and cannot be timed on a healthy chain until it is "
        "installed as code -- measured instead as the cost of one verify_event "
        "recompute per append:")
    with engine.connect() as conn:
        latest = conn.execute(text(
            f"SELECT * FROM {TABLE} ORDER BY sequence_number DESC LIMIT 1")).mappings().one()
    from backend.db.models import AuditLedgerEvent
    with Session(engine) as db:
        row = db.query(AuditLedgerEvent).filter(
            AuditLedgerEvent.sequence_number == int(latest["sequence_number"])).one()
        started = time.perf_counter()
        for _ in range(200):
            verify_event(row)
        recompute_ms = round((time.perf_counter() - started) * 1000 / 200, 3)
    results["one_predecessor_recompute_ms"] = recompute_ms
    results["shipped_append_ms_on_this_shape"] = shipped_ms

    # ---- shape 2: a row deleted from the middle (how pofa_dev's gaps happened)
    middle = victim_sequence - 5
    drop_enforcement(engine)
    with engine.begin() as conn:
        deleted = conn.execute(text(
            f"DELETE FROM {TABLE} WHERE sequence_number = :s"),
            {"s": middle}).rowcount
    install_enforcement(engine)
    results["damage_2"] = {"deleted_sequence": middle, "rowcount": deleted}

    with Session(engine) as db:
        full = verify_chain(db)
        results["verify_after_mid_delete"] = {
            "valid": full["valid"], "failures_by_class": {},
            "first_failures": full["failures"][:6]}
        classes: dict[str, int] = {}
        for failure in full["failures"]:
            key = failure.split(" ")[0] + " " + failure.split(" ")[1]
            classes[key] = classes.get(key, 0) + 1
        results["verify_after_mid_delete"]["failures_by_class"] = classes

        # D-2-A claims a gapped database stays writable. The prototype only
        # validates the immediate predecessor, so a *middle* gap must not
        # refuse -- measured, not assumed.
        try:
            row = chain_aware_append(db, event_type=probe_type,
                                     action="BE030-GAP-WRITABLE",
                                     resource_type="probe", payload={"gap": True},
                                     commit=True)
            results["prototype_with_mid_chain_gap"] = {
                "outcome": "appended", "sequence": int(row.sequence_number)}
        except PredecessorInvalid as exc:
            db.rollback()
            results["prototype_with_mid_chain_gap"] = {
                "outcome": "refused", "message": str(exc)[:200]}

    # ---- restore: undo the tamper marker, drop the extra CHECK-only state
    drop_enforcement(engine)
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {TABLE} SET payload = CAST(CAST(payload AS jsonb) "
            "- 'tampered' AS json) WHERE id = CAST(:id AS uuid)"),
            {"id": str(victim_id)})
    install_enforcement(engine)
    with engine.connect() as conn:
        payload_now = conn.execute(text(
            f"SELECT payload::text FROM {TABLE} WHERE sequence_number = :s"),
            {"s": victim_sequence}).scalar_one()
    results["tamper_marker_removed_after_prototype"] = "tampered" not in json.loads(payload_now)
    results["state_at_end"] = tail_state(engine)
    results["enforcement_left_installed"] = True
    results["check_still_installed"] = CHECK

    engine.dispose()
    print(json.dumps(results, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
