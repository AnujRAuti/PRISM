"""BE-030 #99: prove the enforcement MIGRATION on a disposable clone.

This is the migration-level proof, not the shipped test suite. It runs the real
alembic revision ``t0u1v2w3x030`` (upgrade / downgrade / re-upgrade) against
``pofa_be030_proof`` and exercises the behaviours the shipped tests CANNOT show
because ``tests/audit_guard.py`` forbids them in test code:

  * DELETE against the ledger is refused by the trigger (42501);
  * TRUNCATE is NOT refused by a FOR EACH ROW trigger (the D-1-A documented hole).

Everything else mirrors the shipped tests so the clone evidence and the suite
agree: UPDATE refusal, the SET LOCAL hatch, the out-of-domain CHECK on INSERT,
the D-2-A immediate-predecessor write guard, and the anchored-vs-windowed
verification asymmetry.

Safety: the clone is reached only through ``safety.arm_verification``, which
refuses the protected names outright; the target database is re-confirmed from
the server before and after. pofa_dev is never connected to here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

from sqlalchemy import text  # noqa: E402

from backend.core.config import settings  # noqa: E402
from backend.db import safety  # noqa: E402
from backend.db.session import build_guarded_engine  # noqa: E402
from backend.db.models import AUDIT_EVENT_TYPES  # noqa: E402
from backend.services.audit_ledger import (  # noqa: E402
    PredecessorInvalid, append_event, ledger_checkpoint, verify_chain,
)

REPO = "D:/CODING/Projects/Proof-Of-Action-Final"
PY = REPO + "/backend/.venv312_repro/Scripts/python.exe"
CLONE = "pofa_be030_proof"
TABLE = "audit_ledger_events"
HEAD = "t0u1v2w3x030"
PREV = "s9t0u1v2w029"
VICTIM_COLS = ["NOT_A_REAL_EVENT_TYPE_BE030"]

_r = urlsplit(settings.database_url)
CLONE_URL = urlunsplit((_r.scheme, _r.netloc, f"/{CLONE}", _r.query, ""))

results: dict = {}


def db_name(session) -> str:
    return session.execute(text("SELECT current_database()")).scalar_one()


def sqlstate(exc) -> str | None:
    orig = getattr(exc, "orig", exc)
    return (getattr(getattr(orig, "diag", None), "sqlstate", None)
            or getattr(orig, "pgcode", None))


def run_alembic(args: list[str]) -> dict:
    """Invoke the real alembic command against the clone, armed for verification."""
    import os
    env = dict(os.environ)
    env["DATABASE_URL"] = CLONE_URL
    env["POA_DATABASE_CONTEXT"] = "verification"
    env["POA_AUTHORIZED_DATABASE_NAME"] = CLONE
    proc = subprocess.run(
        [PY, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=REPO, env=env, capture_output=True, text=True,
    )
    return {"args": args, "returncode": proc.returncode,
            "stdout_tail": proc.stdout.strip().splitlines()[-6:],
            "stderr_tail": proc.stderr.strip().splitlines()[-8:]}


def revision_and_catalog(engine) -> dict:
    with engine.connect() as c:
        rev = c.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        trigger = bool(c.execute(text(
            "SELECT 1 FROM pg_trigger t JOIN pg_class k ON k.oid=t.tgrelid"
            " JOIN pg_namespace n ON n.oid=k.relnamespace"
            " WHERE t.tgname='trg_audit_ledger_append_only' AND k.relname='audit_ledger_events'"
            " AND n.nspname='public' AND NOT t.tgisinternal")).fetchone())
        function = bool(c.execute(text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace"
            " WHERE p.proname='audit_ledger_refuse_mutation' AND n.nspname='public'")).fetchone())
        check = bool(c.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname='ck_audit_ledger_event_type_domain'"
            " AND conrelid='public.audit_ledger_events'::regclass")).fetchone())
    return {"revision": rev, "trigger": trigger, "function": function, "check": check}


def refuse(engine, sql: str, **params) -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text(sql), params)
            conn.rollback()
        return {"outcome": "executed"}
    except Exception as exc:  # noqa: BLE001
        return {"outcome": "refused", "error_class": type(exc).__name__,
                "sqlstate": sqlstate(exc),
                "message": str(getattr(exc, "orig", exc)).splitlines()[0][:200]}


def max_seq(engine) -> int:
    with engine.connect() as c:
        return int(c.execute(
            text(f"SELECT coalesce(max(sequence_number),0) FROM {TABLE}")).scalar_one())


def append_committed(engine, note: str) -> int:
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        row = append_event(s, event_type="ORGANIZATION_CREATED", action="create",
                           resource_type="organizations",
                           payload={"probe": "p99", "note": note}, source="p99")
        s.commit()
        return int(row.sequence_number)


def hatch_update(engine, seq: int, payload: dict) -> None:
    """Commit an authorized UPDATE of one row's payload via the SET LOCAL hatch."""
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        s.execute(text("SET LOCAL poa.ledger_mutation_exception = 'true'"))
        s.execute(
            text(f"UPDATE {TABLE} SET payload = CAST(:p AS jsonb) WHERE sequence_number = :i"),
            {"p": json.dumps(payload), "i": seq})
        s.commit()


def capture_payload(engine, seq: int):
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        return s.execute(text(
            f"SELECT payload FROM {TABLE} WHERE sequence_number = :i"), {"i": seq}).scalar_one()


def main() -> int:
    authorized = safety.arm_verification(CLONE_URL)
    results["armed_for"] = authorized
    engine = build_guarded_engine(CLONE_URL)

    # ---- baseline: clone is at the pre-030 head, no enforcement objects ----
    results["before_upgrade"] = revision_and_catalog(engine)
    with engine.connect() as c:
        results["confirmed_database_before"] = db_name(c)
    assert results["confirmed_database_before"] == CLONE, results["confirmed_database_before"]

    # ---- 1. real alembic upgrade head ----
    results["alembic_upgrade"] = run_alembic(["upgrade", HEAD])
    assert results["alembic_upgrade"]["returncode"] == 0, results["alembic_upgrade"]
    after = results["after_upgrade"] = revision_and_catalog(engine)
    assert HEAD in after["revision"], after
    assert after["trigger"] and after["function"] and after["check"], after

    # ---- 2. UPDATE refused (no hatch) ----
    victim = max_seq(engine)
    results["update_refused"] = refuse(
        engine, f"UPDATE {TABLE} SET action='x' WHERE sequence_number=:i", i=victim)

    # ---- 3. DELETE refused -- the proof the shipped suite cannot carry ----
    results["delete_refused"] = refuse(
        engine, f"DELETE FROM {TABLE} WHERE sequence_number=:i", i=victim)

    # ---- 4. TRUNCATE is NOT refused (D-1-A documented hole); rolled back ----
    try:
        with engine.connect() as conn:
            conn.execute(text(f"TRUNCATE {TABLE}"))
            inside_count = int(conn.execute(
                text(f"SELECT count(*) FROM {TABLE}")).scalar_one())
            conn.rollback()
        after_rb = int(engine.connect().execute(
            text(f"SELECT count(*) FROM {TABLE}")).scalar_one())
        results["truncate_hole"] = {
            "outcome": "executed",
            "rows_during_truncate": inside_count,
            "rows_after_rollback": after_rb,
            "note": "FOR EACH ROW trigger does not fire on TRUNCATE; "
                    "rollback restored the clone, so no damage persisted"}
    except Exception as exc:  # noqa: BLE001
        results["truncate_hole"] = {"outcome": "refused",
                                     "message": str(getattr(exc, "orig", exc))[:200]}

    # ---- 5. SET LOCAL hatch permits the UPDATE, then expires ----
    from sqlalchemy.orm import Session
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL poa.ledger_mutation_exception = 'true'"))
        conn.execute(text(f"UPDATE {TABLE} SET action='hatch-ok' WHERE sequence_number=:i"),
                     {"i": victim})
        conn.rollback()
    results["hatch_update_in_transaction"] = {"outcome": "executed (rolled back)"}
    results["hatch_does_not_survive"] = refuse(
        engine, f"UPDATE {TABLE} SET action='x' WHERE sequence_number=:i", i=victim)

    # ---- 6. CHECK refuses an out-of-domain INSERT, accepts an in-domain one ----
    domain = sorted(AUDIT_EVENT_TYPES)[0]
    off = results["out_of_domain_insert"] = refuse(
        engine,
        f"INSERT INTO {TABLE} (id, sequence_number, event_type, action, resource_type,"
        " payload, metadata, previous_hash, event_hash, hash_algorithm, ledger_version,"
        " created_at) VALUES (gen_random_uuid(),"
        " (SELECT coalesce(max(sequence_number),0)+1 FROM audit_ledger_events),"
        " :t, 'x','y','{}'::jsonb,'{}'::jsonb,'g','h','sha256','v1',now())",
        t="NOT_A_REAL_EVENT_TYPE_BE030")
    on = results["in_domain_insert"] = refuse(
        engine,
        f"INSERT INTO {TABLE} (id, sequence_number, event_type, action, resource_type,"
        " payload, metadata, previous_hash, event_hash, hash_algorithm, ledger_version,"
        " created_at) VALUES (gen_random_uuid(),"
        " (SELECT coalesce(max(sequence_number),0)+1 FROM audit_ledger_events),"
        " :t, 'x','y','{}'::jsonb,'{}'::jsonb,'g','h','sha256','v1',now())",
        t=domain)
    results["check_latency_note"] = "both inserts rolled back; no out-of-domain row persists"

    # ---- 7. writer stays contiguous + chain valid under the trigger ----
    start = max_seq(engine)
    a = append_committed(engine, "chain-a")
    b = append_committed(engine, "chain-b")
    c = append_committed(engine, "chain-c")
    results["writer_contiguous"] = {"start": start, "seqs": [a, b, c],
                                    "contiguous": (a, b, c) == (start + 1, start + 2, start + 3)}

    # ---- 8. anchored vs windowed asymmetry on a tampered MIDDLE row ----
    b_original = capture_payload(engine, b)
    hatch_update(engine, b, {"tampered": True})
    downstream = verify(engine, from_sequence=c, to_sequence=c)
    covering = verify(engine, from_sequence=a, to_sequence=c)
    results["midchain_asymmetry"] = {
        "downstream_window_valid": downstream["valid"],
        "covering_range_valid": covering["valid"],
        "covering_failures": covering["failures"][:3],
        "expected": "downstream window valid; covering range invalid with event_hash mismatch",
    }
    hatch_update(engine, b, b_original)   # restore; clone keeps a valid chain
    results["midchain_restored_valid"] = verify(
        engine, from_sequence=a, to_sequence=c)["valid"]

    # ---- 9. D-2-A: append refuses onto a damaged tail, works once restored ----
    c_original = capture_payload(engine, c)
    hatch_update(engine, c, {"tampered": "tail"})
    with Session(engine) as s:
        try:
            append_event(s, event_type="ORGANIZATION_CREATED", action="create",
                         resource_type="organizations", payload={"note": "should-refuse"},
                         source="p99")
            results["d2a_tail_refusal"] = {"outcome": "NOT refused (BUG)"}
        except PredecessorInvalid as exc:
            results["d2a_tail_refusal"] = {"outcome": "PredecessorInvalid",
                                           "message": str(exc)[:200]}
        finally:
            s.rollback()
    hatch_update(engine, c, c_original)   # restore the tail
    try:
        d = append_committed(engine, "d2a-after-restore")
        results["d2a_after_restore_append"] = {"outcome": "executed", "seq": d}
    except Exception as exc:  # noqa: BLE001
        results["d2a_after_restore_append"] = {"outcome": "refused",
                                                "message": str(exc)[:200]}

    # ---- 10. durable read-path control: full anchored verify is valid ----
    results["anchored_full_chain"] = {
        k: v for k, v in verify(engine).items()
        if k in ("valid", "checked_events", "first_sequence", "last_sequence")}
    results["checkpoint"] = checkpoint(engine)

    # ---- 11. downgrade removes every object ----
    # Release every pooled connection: the parent engine holds sessions that would
    # block the subprocess's DROP TRIGGER / DROP CONSTRAINT (ACCESS EXCLUSIVE).
    engine.dispose()
    results["alembic_downgrade"] = run_alembic(["downgrade", PREV])
    assert results["alembic_downgrade"]["returncode"] == 0, results["alembic_downgrade"]
    down = results["after_downgrade"] = revision_and_catalog(engine)
    assert PREV in down["revision"], down
    assert not down["trigger"] and not down["function"] and not down["check"], down

    # ---- 12. re-upgrade restores them (idempotence guards let it recreate) ----
    results["alembic_reupgrade"] = run_alembic(["upgrade", "head"])
    assert results["alembic_reupgrade"]["returncode"] == 0, results["alembic_reupgrade"]
    reup = results["after_reupgrade"] = revision_and_catalog(engine)
    assert HEAD in reup["revision"] and reup["trigger"] and reup["function"] and reup["check"], reup

    # ---- final: chain still valid after the whole round trip ----
    results["final_full_chain_valid"] = verify(engine)["valid"]
    with engine.connect() as conn:
        results["confirmed_database_end"] = db_name(conn)
    engine.dispose()

    print(json.dumps(results, indent=1, default=str))
    return 0


def verify(engine, **kw):
    """Run verify_chain on a short-lived, properly closed ORM Session."""
    from sqlalchemy.orm import Session
    s = Session(engine)
    try:
        return verify_chain(s, **kw)
    finally:
        s.close()


def checkpoint(engine):
    from sqlalchemy.orm import Session
    s = Session(engine)
    try:
        return ledger_checkpoint(s)
    finally:
        s.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - dump evidence, then re-raise
        results["CRASH"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps(results, indent=1, default=str))
        raise
