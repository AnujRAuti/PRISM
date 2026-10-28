"""BE-030 feasibility: what does the writer do when its predecessor is already damaged?

``append_event`` (backend/services/audit_ledger.py:220-241) takes the advisory
lock, reads ``audit_repo.latest(db)`` and copies ``predecessor.event_hash`` into
the new row's ``previous_hash``. It never *recomputes* that hash, and it never
asks whether the chain is currently valid. So four questions, answered by doing
the operations rather than reasoning about them:

1. If the tail row is rewritten in place -- the shape BE-029 §14.6 measured the
   database to permit, leaving the stored ``event_hash`` stale -- does the next
   honest append inherit the stale hash as its ``previous_hash``? If yes, an
   attacker who edits one row silently re-bases every later event on the edited
   value, and writer-side "chain awareness" has to recompute the predecessor.
2. Where does ``verify_chain`` then report the break: at the rewritten row only,
   at every row after it, or nowhere?
3. Does the writer keep appending against history that is already invalid
   (a middle gap)? ``pofa_dev`` and every clone of it are in exactly this state,
   so a strict refuse-on-invalid policy would stop all audit writes on live data.
   This is the measurement behind BE-030's blocked decision D-2.
4. What does the tail segment look like afterwards -- i.e. could an operator
   reading only recent events conclude the ledger is healthy?

Disposable database only. The armed ``verification`` context refuses
``pofa_dev``/``pofa_test`` before connecting, and the script additionally
re-checks that ``current_database()`` equals the authorised name. Unlike the
enforcement probe, this one *commits* its damage: the property under test is what
a database with committed damage does. It therefore runs against
``pofa_be029_scratch``, a throwaway clone, and prints the sequences it wrote.

Usage:
    python ledger_tail_rewrite.py [url]
"""
import json
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.db import safety
from backend.db.session import build_guarded_engine
from backend.services.audit_ledger import append_event, verify_chain

OUT = "D:/CODING/Scratch/be029/ledger_tail_rewrite.json"
TABLE = "audit_ledger_events"
PROBE = "be030-tail-rewrite"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be029_scratch")
    authorized = safety.arm_verification(url)
    engine = build_guarded_engine(url)
    sessions = sessionmaker(bind=engine)

    with engine.connect() as conn:
        database = conn.execute(text("SELECT current_database()")).scalar_one()
    if database != authorized:
        raise SystemExit(f"refusing to run: armed for {authorized}, reached {database}")
    print(f"target: {database}")

    report = {"database": database}

    def scalar(sql, **params):
        with sessions() as s:
            return s.execute(text(sql), params).scalar_one()

    def append(note: str) -> int:
        with sessions() as s:
            row = append_event(s, event_type="ORGANIZATION_CREATED", action="create",
                               resource_type="organizations",
                               payload={"probe": PROBE, "note": note}, source=PROBE)
            s.commit()
            return int(row.sequence_number)

    def check(from_seq: int, to_seq: int) -> dict:
        with sessions() as s:
            result = verify_chain(s, from_sequence=from_seq, to_sequence=to_seq)
        return {"valid": result["valid"], "checked": result.get("checked"),
                "failures": result["failures"][:6],
                "failure_count": len(result["failures"])}

    tail_before = scalar(f"SELECT max(sequence_number) FROM {TABLE}")
    rows_before = scalar(f"SELECT count(*) FROM {TABLE}")
    report["before"] = {"rows": rows_before, "max_sequence": int(tail_before),
                        "tail_segment": check(int(tail_before) - 2, int(tail_before))}

    # --- Q1: rewrite the tail row in place, exactly the permitted shape.
    victim = append("victim-row")
    with sessions() as s:
        stored = s.execute(text(
            f"SELECT id, event_hash, previous_hash FROM {TABLE} "
            "WHERE sequence_number = CAST(:s AS bigint)"), {"s": victim}).one()
        victim_id, victim_hash = str(stored[0]), str(stored[1])
        # payload is JSON, not JSONB (measured: jsonb_set(json, unknown, unknown)
        # does not exist), so the edit has to round-trip through jsonb.
        s.execute(text(f"UPDATE {TABLE} SET payload = "
                       "CAST(CAST(payload AS jsonb) || CAST(:patch AS jsonb) AS json) "
                       "WHERE id = CAST(:id AS uuid)"),
                  {"id": victim_id, "patch": '{"tampered": true}'})
        s.commit()
    report["victim"] = {"sequence": victim, "stored_event_hash_prefix": victim_hash[:16]}

    # Q1: the next honest append -- what does it chain onto? The stored hash was
    # not rewritten along with the payload, so "equals the stale stored hash" is
    # the whole question; verify_victim_only below is what proves the stored
    # value no longer matches the row's contents.
    honest = append("honest-append-after-damage")
    chained_onto = scalar(
        f"SELECT previous_hash FROM {TABLE} WHERE sequence_number = CAST(:s AS bigint)",
        s=honest)
    report["honest_append"] = {
        "sequence": honest,
        "previous_hash": str(chained_onto)[:16],
        "equals_the_stale_stored_hash": str(chained_onto) == victim_hash,
    }

    # Q2: where does the verifier see it?
    report["verify_victim_only"] = check(victim, victim)
    report["verify_victim_through_honest"] = check(victim, honest)
    report["verify_honest_only"] = check(honest, honest)

    # --- Q3: append against history that is already invalid.
    gap_target = honest - 1  # the victim row's neighbour, this probe's own
    with sessions() as s:
        gone = s.execute(text(
            f"DELETE FROM {TABLE} WHERE sequence_number = CAST(:s AS bigint) "
            "RETURNING id"), {"s": gap_target}).scalar_one_or_none()
        s.commit()
    report["gap"] = {"deleted_sequence": gap_target, "deleted_id": str(gone) if gone else None}
    after_gap = append("append-against-invalid-history")
    report["gap"]["next_append_sequence"] = after_gap
    report["gap"]["writer_refused"] = False
    report["gap"]["note"] = (
        "The DELETE above is committed against a throwaway clone only. "
        "tests/audit_guard.py forbids this spelling in the repository test tree "
        "with no rollback exception, which is why the property is measured here "
        "instead of shipped as a test (BE-029 results §14.8).")

    # Q4: what can an operator reading only recent events conclude?
    report["verify_recent_window_after_damage"] = check(after_gap - 1, after_gap)
    tail_after = scalar(f"SELECT max(sequence_number) FROM {TABLE}")
    rows_after = scalar(f"SELECT count(*) FROM {TABLE}")
    report["after"] = {"rows": rows_after, "max_sequence": int(tail_after)}
    report["span_gap_now"] = int(tail_after) - int(tail_before) - (rows_after - rows_before)

    engine.dispose()
    safety.disarm()
    print(json.dumps(report, indent=2, default=str))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
