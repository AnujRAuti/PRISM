"""BE-029 Phase G: can the audit ledger actually be falsified, and is it caught?

Runs on the explicitly named disposable database through the Phase C guard
(``arm_verification`` + ``build_guarded_engine``), never on ``pofa_dev`` or
``pofa_test``. The question it answers with a real write, not a reading:

  * does the writer ever skip a sequence number?          (contiguity)
  * does a rolled-back append burn a number?              (the gap hypothesis)
  * does the DATABASE refuse UPDATE/DELETE on the ledger? (enforcement)
  * if it does not, does the verifier notice?             (detection)

This matters because ``pofa_dev``'s chain is invalid in a very specific shape:
36 rows missing across 7 ranges and *no* hash recomputation failure anywhere.
The writer derives every number from the current maximum, so an application
append cannot produce that shape -- only removing rows afterwards can. Which
leaves the question of whether anything stops someone from doing exactly that.

Results go to ledger_append_only.json for the results document.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend.db import safety  # noqa: E402
from backend.db.models import AuditLedgerEvent  # noqa: E402
from backend.db.session import build_guarded_engine  # noqa: E402
from backend.services.audit_ledger import append_event, verify_chain  # noqa: E402

URL = ("postgresql+psycopg2://postgres:postgres@localhost:5432"
       "/pofa_be029_assumptions")
OUT = Path("D:/CODING/Scratch/be029/ledger_append_only.json")
KEY = "be029-phase-g"


def snapshot(db) -> dict:
    rows = db.execute(
        select(AuditLedgerEvent.sequence_number, AuditLedgerEvent.event_hash)
        .order_by(AuditLedgerEvent.sequence_number)).all()
    return {"count": len(rows),
            "sequences": [r[0] for r in rows],
            "tail_hash": rows[-1][1] if rows else None,
            "verify": verify_chain(db)}


def append(db, note: str):
    return append_event(db, event_type="ORGANIZATION_CREATED", action="create",
                        resource_type="organizations", resource_id=None,
                        payload={"probe": KEY, "note": note}, source=KEY)


def main() -> int:
    name = safety.arm_verification(URL)
    print(f"armed verification context for {name!r}")
    engine = build_guarded_engine(URL)
    Session = sessionmaker(bind=engine)
    report: dict = {"database": name}

    with Session() as db:
        db.execute(text("DELETE FROM audit_ledger_events"))
        db.commit()

    # 1. Contiguity of ordinary appends.
    with Session() as db:
        seqs = [append(db, f"append-{i}").sequence_number for i in range(3)]
        db.commit()
        report["appends"] = {"sequence_numbers": seqs, "snapshot": snapshot(db)}
        contiguous = seqs == sorted(seqs) and seqs == list(range(seqs[0], seqs[0] + 3))
        report["appends"]["contiguous"] = contiguous

    # 2. A rolled-back append: does it burn a sequence number? If it did, normal
    # application traffic alone could open gaps, and pofa_dev's shape would need
    # no other explanation.
    with Session() as db:
        before = db.execute(text(
            "SELECT max(sequence_number) FROM audit_ledger_events")).scalar_one()
        probe = append(db, "will-rollback")
        db.rollback()
        after_rollback = db.execute(text(
            "SELECT count(*) FROM audit_ledger_events")).scalar_one()
        next_row = append(db, "after-rollback")
        db.commit()
        report["rollback"] = {
            "max_before": int(before),
            "rows_after_rollback": int(after_rollback),
            "rolled_back_sequence": int(probe.sequence_number),
            "next_sequence": int(next_row.sequence_number),
            "burned_a_number": int(next_row.sequence_number) != int(before) + 1,
            "snapshot": snapshot(db),
        }

    # 3. Is UPDATE blocked by the database? Attempt it inside a transaction and
    # roll it back either way, so a permissive server leaves no trace.
    with Session() as db:
        target = db.execute(select(AuditLedgerEvent)
                            .order_by(AuditLedgerEvent.sequence_number).limit(1)
                            ).scalar_one()
        try:
            db.execute(text("UPDATE audit_ledger_events SET payload = '{\"tampered\": 1}'"
                            " WHERE id = :id"), {"id": target.id})
            db.flush()
            report["update"] = {"refused_by_database": False,
                                "error": None}
        except Exception as error:  # a trigger, policy or rule would land here
            report["update"] = {"refused_by_database": True,
                                "error": type(error).__name__ + ": "
                                         + str(error).splitlines()[0][:200]}
        db.rollback()
        report["update"]["state_after_rollback"] = snapshot(db)["verify"]["valid"]

    # 4. Is DELETE blocked? And if not, does the shipped verifier notice the hole?
    # This one is allowed to commit -- on a disposable database -- because the
    # point is what the ledger looks like *after* a deletion, which a rollback
    # cannot show.
    with Session() as db:
        middle = db.execute(select(AuditLedgerEvent)
                            .order_by(AuditLedgerEvent.sequence_number)
                            .offset(1).limit(1)).scalar_one()
        deleted_sequence = int(middle.sequence_number)
        try:
            db.execute(delete(AuditLedgerEvent)
                       .where(AuditLedgerEvent.id == middle.id))
            db.commit()
            refused_delete = False
        except Exception as error:
            db.rollback()
            refused_delete = True
            report["delete"] = {"refused_by_database": True,
                                "error": type(error).__name__ + ": "
                                         + str(error).splitlines()[0][:200]}
        if not refused_delete:
            with Session() as check:
                verification = snapshot(check)
                report["delete"] = {
                    "refused_by_database": False,
                    "deleted_sequence": deleted_sequence,
                    "verifier_notice": not verification["verify"]["valid"],
                    "failures": verification["verify"]["failures"][:4],
                    "count": verification["count"],
                }

    # 5. After a committed deletion, what does the *writer* do? pofa_dev's chain
    # has to keep extending somehow, so this is the mechanism that turns one
    # deletion into a permanent discontinuity.
    if not report["delete"]["refused_by_database"]:
        with Session() as db:
            row = append(db, "after-deletion")
            db.commit()
            report["writer_after_deletion"] = {
                "new_sequence": int(row.sequence_number),
                "deleted_sequence": deleted_sequence,
                "verifier_valid": snapshot(db)["verify"]["valid"],
                "failures": snapshot(db)["verify"]["failures"][:4],
            }

    engine.dispose()
    safety.disarm()
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
