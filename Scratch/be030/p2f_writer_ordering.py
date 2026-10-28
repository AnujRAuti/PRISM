"""BE-030 D-2, the ordering question p2e exposed.

p2e damaged the tail, ran the *shipped* writer first, and then found that the
predecessor-checking prototype happily appended. That is not a bug in the
prototype: the shipped append had already re-anchored onto the stale stored
hash, so the new tail was locally self-consistent and nothing downstream of it
could ever look wrong. Which is the whole of F-5/F-6, and it means the answer to
"validate only the immediate predecessor" depends on *who writes first*.

Measured here, on the disposable clone, in the order an incident would happen:

  1. damage the tail and commit it (trigger dropped for the damage, reinstated
     after, so the damage is pre-enforcement history);
  2. predecessor-checking writer is the first to run            -> refuse?
  3. shipped writer runs instead                                -> re-bases;
  4. predecessor-checking writer runs again on the new tail      -> ?
  5. an anchored check (recompute from the last known-good
     checkpoint, i.e. the D-2-C shape) against the same state    -> ?

    python p2f_writer_ordering.py <sqlalchemy-url>
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.db import safety  # noqa: E402
from backend.db.models import AUDIT_EVENT_TYPES, AuditLedgerEvent  # noqa: E402
from backend.db.session import build_guarded_engine  # noqa: E402
from backend.repositories import audit_ledger as audit_repo  # noqa: E402
from backend.services.audit_ledger import (  # noqa: E402
    APPEND_LOCK_KEY, append_event, verify_chain, verify_event)

from p2a_install_and_probe import INSTALL_FUNCTION, INSTALL_TRIGGER, TABLE, TRIGGER  # noqa: E402
from p2e_writer_prototype import PredecessorInvalid, chain_aware_append  # noqa: E402

results: dict = {}
probe_type = sorted(AUDIT_EVENT_TYPES)[0]


def main() -> int:
    url = sys.argv[1]
    authorized = safety.arm_verification(url)
    engine = build_guarded_engine(url)
    with engine.connect() as conn:
        if conn.execute(text("SELECT current_database()")).scalar_one() != authorized:
            raise SystemExit("target does not match the armed context")
        tail_before = int(conn.execute(
            text(f"SELECT max(sequence_number) FROM {TABLE}")).scalar_one())
    results["target"] = authorized
    results["tail_before"] = tail_before

    # 1. damage the tail and commit it.
    with engine.connect() as probe:
        victim_sequence = int(probe.execute(text(
            f"SELECT max(sequence_number) FROM {TABLE}")).scalar_one())
        victim_id = probe.execute(text(
            f"SELECT id FROM {TABLE} WHERE sequence_number = :s"),
            {"s": victim_sequence}).scalar_one()
    with engine.begin() as conn:
        conn.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE}"))
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {TABLE} SET payload = "
                          "CAST(CAST(payload AS jsonb) || '{\"tampered\": true}' AS json) "
                          "WHERE id = CAST(:id AS uuid)"), {"id": str(victim_id)})
    with engine.begin() as conn:
        conn.execute(text(INSTALL_FUNCTION))
        conn.execute(text(INSTALL_TRIGGER))
    results["damage"] = {"tampered_sequence": victim_sequence, "committed": True}

    with Session(engine) as db:
        # 2. the predecessor-checking writer is the FIRST writer after damage.
        try:
            row = chain_aware_append(db, event_type=probe_type,
                                     action="BE030-ORDER-PROTOTYPE-FIRST",
                                     resource_type="probe", payload={"n": 1},
                                     commit=True)
            results["step2_prototype_first"] = {"outcome": "appended",
                                                "sequence": int(row.sequence_number)}
            db.rollback()
        except PredecessorInvalid as exc:
            db.rollback()
            results["step2_prototype_first"] = {"outcome": "refused",
                                                "message": str(exc)[:220]}

        # 3. the shipped writer instead: it re-bases onto the stale hash.
        row = append_event(db, event_type=probe_type, action="BE030-ORDER-SHIPPED",
                           resource_type="probe", payload={"n": 2}, commit=True)
        new_tail = int(row.sequence_number)
        with Session(engine) as check:
            tampered_hash = str(check.query(AuditLedgerEvent).filter(
                AuditLedgerEvent.sequence_number == victim_sequence).one().event_hash)
        results["step3_shipped_writer_rebased"] = {
            "appended_sequence": new_tail,
            "previous_hash_equals_stale_tail_hash": str(row.previous_hash) == tampered_hash}

        # 4. the predecessor-checking writer, now that one honest event exists.
        try:
            row = chain_aware_append(db, event_type=probe_type,
                                     action="BE030-ORDER-PROTOTYPE-AGAIN",
                                     resource_type="probe", payload={"n": 3},
                                     commit=True)
            results["step4_prototype_after_rebase"] = {
                "outcome": "appended", "sequence": int(row.sequence_number),
                "meaning": "D-2-A is a one-shot control: it refuses the first "
                           "append onto a damaged tail, and nothing after a "
                           "successful re-basing looks damaged locally"}
        except PredecessorInvalid as exc:
            db.rollback()
            results["step4_prototype_after_rebase"] = {
                "outcome": "refused", "message": str(exc)[:220]}

        # 5. what only an anchored check can see.
        window = verify_chain(db, from_sequence=victim_sequence, to_sequence=new_tail)
        results["step5_window_from_damaged_row"] = {
            "valid": window["valid"], "checked": window["checked_events"],
            "failures": window["failures"][:4]}
        tail_only = verify_chain(db, from_sequence=new_tail)
        results["step5_tail_only_window"] = {"valid": tail_only["valid"],
                                            "checked": tail_only["checked_events"]}

        # D-2-C shape: a published checkpoint is the only thing that survives a
        # re-base. Simulate one captured before the damage by taking the hash of
        # the row *before* the tampered one and walking forward from it.
        anchor_row = db.query(AuditLedgerEvent).filter(
            AuditLedgerEvent.sequence_number == victim_sequence - 1).one()
        from_anchor = verify_chain(db, from_sequence=victim_sequence)
        results["step5_anchored_from_last_known_good"] = {
            "anchor_sequence": int(anchor_row.sequence_number),
            "anchor_verifies": verify_event(anchor_row)[0],
            "range_from_anchor_valid": from_anchor["valid"],
            "range_from_anchor_failures": from_anchor["failures"][:4]}

    # undo the marker so the clone is not left holding a fake field
    with engine.begin() as conn:
        conn.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE}"))
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {TABLE} SET payload = "
                          "CAST(CAST(payload AS jsonb) - 'tampered' AS json) "
                          "WHERE id = CAST(:id AS uuid)"), {"id": str(victim_id)})
    with engine.begin() as conn:
        conn.execute(text(INSTALL_FUNCTION))
        conn.execute(text(INSTALL_TRIGGER))
    with engine.connect() as conn:
        results["final_tail"] = int(conn.execute(
            text(f"SELECT max(sequence_number) FROM {TABLE}")).scalar_one())
        payload = conn.execute(text(
            f"SELECT payload::text FROM {TABLE} WHERE sequence_number = :s"),
            {"s": victim_sequence}).scalar_one()
    results["tamper_marker_removed"] = "tampered" not in json.loads(payload)
    engine.dispose()
    print(json.dumps(results, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
