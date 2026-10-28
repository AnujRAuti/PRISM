"""BE-030 D-1 feasibility: install the refusal trigger on a disposable clone and
measure what it enforces, what it costs, and whether the exception path holds.

Target must be a disposable database; ``safety.arm_verification`` refuses
``pofa_dev`` / ``pofa_test`` outright, so the armed context is the proof of intent.

    python p2a_install_and_probe.py <sqlalchemy-url>

Every claim below is a *behaviour* observed by running the statement, not a
reading of the DDL. Mutating probes that would leave damage behind run inside a
transaction that is rolled back; only the appends through ``append_event`` and
the ``CHECK`` constraint persist, both of which are part of the design.
"""

from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

from sqlalchemy import text  # noqa: E402

from backend.db import safety  # noqa: E402
from backend.db.models import AUDIT_EVENT_TYPES  # noqa: E402
from backend.db.session import build_guarded_engine  # noqa: E402

TABLE = "audit_ledger_events"
FUNC = "public.audit_ledger_refuse_mutation"
TRIGGER = "trg_audit_ledger_append_only"
EXCEPTION_GUC = "poa.ledger_mutation_exception"
CHECK = "ck_audit_ledger_event_type_domain"

#: §7 exactly: BEFORE ROW on UPDATE OR DELETE only (insert stays free), TG_OP
#: rather than TG_TAG, an explicit ERRCODE, and **no `%` in the RAISE format
#: string at all** -- measured: SQLAlchemy's psycopg2 dialect doubles a literal
#: `%` in DDL text on the way to the server, so a `%`-placeholder message arrives
#: as `%%` and the function fails to compile. Naming the operation per branch
#: keeps the message stable for tests (§7.3) without the hazard (§7.4).
INSTALL_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {FUNC}() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF lower(coalesce(current_setting('{EXCEPTION_GUC}', true), ''))
       IN ('true', 'on', '1') THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'append-only enforcement refuses UPDATE on the audit ledger'
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'SET LOCAL {EXCEPTION_GUC} to use the sanctioned path';
    ELSE
        RAISE EXCEPTION 'append-only enforcement refuses DELETE on the audit ledger'
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'SET LOCAL {EXCEPTION_GUC} to use the sanctioned path';
    END IF;
END
$fn$
"""

INSTALL_TRIGGER = (
    f"CREATE TRIGGER {TRIGGER} BEFORE UPDATE OR DELETE ON {TABLE} "
    f"FOR EACH ROW EXECUTE FUNCTION {FUNC}()"
)

results: dict = {}


def sqlstate_of(exc) -> str | None:
    orig = getattr(exc, "orig", exc)
    return getattr(getattr(orig, "diag", None), "sqlstate", None)


def refusal(engine, sql: str, **params) -> dict:
    """Run one mutating statement and classify what the database did."""
    try:
        with engine.connect() as conn:
            conn.execute(text(sql), params)
            conn.rollback()
        return {"outcome": "executed"}
    except Exception as exc:  # noqa: BLE001 - the classification is the result
        return {"outcome": "refused", "error_class": type(exc).__name__,
                "sqlstate": sqlstate_of(exc),
                "message": str(exc).splitlines()[0][:220]}


def main() -> int:
    url = sys.argv[1]
    authorized = safety.arm_verification(url)
    engine = build_guarded_engine(url)
    results["armed_for"] = authorized

    with engine.connect() as conn:
        database = conn.execute(text("SELECT current_database()")).scalar_one()
        revision = conn.execute(
            text("SELECT version_num FROM alembic_version")).scalars().all()
        tail = conn.execute(
            text(f"SELECT count(*), max(sequence_number) FROM {TABLE}")).one()
        victim = conn.execute(
            text(f"SELECT id FROM {TABLE} ORDER BY sequence_number DESC LIMIT 1")
        ).scalar_one()
        columns = [r[0] for r in conn.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position
        """), {"t": TABLE}).all()]
    results["target"] = {"database": database, "revision": revision,
                         "rows": int(tail[0]), "max_sequence": int(tail[1]),
                         "columns": columns}
    if database != authorized:
        raise SystemExit(
            f"refusing to run: armed for {authorized}, reached {database}")

    tamper_sql = (
        f"UPDATE {TABLE} SET payload = "
        "CAST(CAST(payload AS jsonb) || '{\"probe\": true}' AS json) "
        "WHERE id = CAST(:id AS uuid)")
    touch_sql = f"UPDATE {TABLE} SET metadata = metadata WHERE id = CAST(:id AS uuid)"
    delete_sql = f"DELETE FROM {TABLE} WHERE id = CAST(:id AS uuid)"

    # 1. baseline, before any enforcement: the same statement is accepted.
    results["baseline_touch_without_trigger"] = {"outcome": "executed"}
    with engine.connect() as conn:
        results["baseline_touch_without_trigger"]["rowcount"] = conn.execute(
            text(touch_sql), {"id": victim}).rowcount
        conn.rollback()

    # 2a. isolation control for the `%` finding: the same plpgsql body, sent
    # straight through psycopg2 with no bound parameters. If this compiles, the
    # `%%` that reached the server above was SQLAlchemy's doing, and the
    # migration must avoid `%` in DDL text rather than blame plpgsql.
    import psycopg2 as _psycopg2

    control_sql = f"""
CREATE OR REPLACE FUNCTION {FUNC}_percent_control() RETURNS trigger
LANGUAGE plpgsql AS $cfn$
BEGIN
    RAISE EXCEPTION 'append-only: % on the audit ledger is not permitted', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END
$cfn$
"""
    dsn = url.replace("postgresql+psycopg2", "postgresql", 1)
    control_conn = _psycopg2.connect(dsn)
    control_conn.autocommit = True
    with control_conn.cursor() as control_cur:
        try:
            control_cur.execute(control_sql)
            results["percent_placeholder_via_psycopg2_directly"] = {"outcome": "compiled"}
        except Exception as exc:  # noqa: BLE001
            results["percent_placeholder_via_psycopg2_directly"] = {
                "outcome": "failed",
                "message": str(exc).splitlines()[0][:200]}
        control_cur.execute(f"DROP FUNCTION IF EXISTS {FUNC}_percent_control(trigger)")
    control_conn.close()

    # 2. install the enforcement.
    with engine.begin() as conn:
        conn.execute(text(INSTALL_FUNCTION))
        conn.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE}"))
        conn.execute(text(INSTALL_TRIGGER))

    # 3. F-14 re-measured with the objects *present*.
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from backend.db.models import Base
    from backend.db.schema_drift_policy import include_object
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"target_metadata": Base.metadata,
                        "include_object": include_object})
        entries = [str(e) for e in compare_metadata(ctx, Base.metadata)]
    results["drift_with_enforcement_installed"] = {
        "operations": len(entries),
        "mentions_ledger_table": any(TABLE in e for e in entries),
        "mentions_trigger": any(TRIGGER in e for e in entries),
        "mentions_check": any(CHECK in e for e in entries)}

    # 4/5/6. the three refusals, including the shape BE-023 §4 sanctions.
    results["update_refused"] = refusal(engine, touch_sql, id=victim)
    results["delete_refused"] = refusal(engine, delete_sql, id=victim)
    results["rollback_guarded_tamper_update_refused"] = refusal(engine, tamper_sql,
                                                                id=victim)

    # 7. the exception path. SET LOCAL inside the transaction that SQLAlchemy 2.0
    # opens, then rolled back so the clone keeps its real contents.
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL {EXCEPTION_GUC} = 'true'"))
            rowcount = conn.execute(text(tamper_sql), {"id": victim}).rowcount
            conn.rollback()
        results["update_with_set_local_in_transaction"] = {
            "outcome": "executed", "rowcount": rowcount}
    except Exception as exc:  # noqa: BLE001
        results["update_with_set_local_in_transaction"] = {
            "outcome": "refused", "message": str(exc).splitlines()[0][:200]}

    # ...and it must not outlive that transaction.
    results["update_after_the_transaction_ended"] = refusal(engine, touch_sql, id=victim)

    # 8. Why the exception must be SET LOCAL and not SET: a plain session-level
    # SET survives the transaction, and with a connection pool that means the
    # next borrower of the same connection inherits an open escape hatch.
    import psycopg2

    dsn = url.replace("postgresql+psycopg2", "postgresql", 1)
    leak = psycopg2.connect(dsn)
    leak.autocommit = True
    with leak.cursor() as cur:
        cur.execute(f"SET {EXCEPTION_GUC} = 'true'")
        try:
            cur.execute(touch_sql.replace(":id", "%s"), (victim,))
            session_level = {"outcome": "executed",
                             "rowcount": cur.rowcount}
        except Exception as exc:  # noqa: BLE001
            session_level = {"outcome": "refused",
                             "message": str(exc).splitlines()[0][:160]}
        cur.execute(f"RESET {EXCEPTION_GUC}")
        try:
            cur.execute(touch_sql.replace(":id", "%s"), (victim,))
            after_reset = {"outcome": "executed"}
        except Exception as exc:  # noqa: BLE001
            after_reset = {"outcome": "refused",
                           "message": str(exc).splitlines()[0][:160]}
    leak.close()
    results["session_level_set_leaks_past_the_transaction"] = {
        "with_plain_set": session_level, "after_reset": after_reset,
        "conclusion": "SET (session scope) opens the hatch for the whole pooled "
                      "connection; only SET LOCAL is transaction-bounded"}

    # 9. the writer is unaffected, and each append costs one extra trigger check.
    from backend.services.audit_ledger import append_event
    from sqlalchemy.orm import Session

    probe_type = sorted(AUDIT_EVENT_TYPES)[0]
    sequences = []
    started = time.perf_counter()
    for i in range(20):
        with Session(engine) as db:
            row = append_event(db, event_type=probe_type, actor_id=None,
                               action="BE030-PROBE", resource_type="probe",
                               resource_id=None, payload={"i": i}, commit=True)
            sequences.append(int(row.sequence_number))
    results["append_event_with_trigger"] = {
        "first_sequence": sequences[0], "last_sequence": sequences[-1],
        "count": len(sequences),
        "ms_per_append": round((time.perf_counter() - started) * 1000 / len(sequences), 2)}

    # 10. §11: the event_type CHECK, generated from the Python enum.
    values = ",".join("'" + v.replace("'", "''") + "'" for v in sorted(AUDIT_EVENT_TYPES))
    started = time.perf_counter()
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {TABLE} "
                          f"ADD CONSTRAINT {CHECK} CHECK (event_type IN ({values}))"))
    results["event_type_check_added"] = {
        "members": len(AUDIT_EVENT_TYPES),
        "validate_seconds_on_this_data": round(time.perf_counter() - started, 3)}

    # Raw SQL, bypassing every Python guard: refused by the database now. Each
    # attempt is rolled back so no out-of-domain row can exist afterwards.
    def raw_insert(event_type: str) -> dict:
        cols = [c for c in results["target"]["columns"] if c not in
                ("id", "sequence_number", "event_type")]
        select_list = ", ".join(["gen_random_uuid()", "999999999",
                                 "'" + event_type.replace("'", "''") + "'"]
                                + cols)
        sql = (f"INSERT INTO {TABLE} (id, sequence_number, event_type, {', '.join(cols)}) "
               f"SELECT {select_list} FROM {TABLE} WHERE id = CAST(:id AS uuid)")
        return refusal(engine, sql, id=victim)

    results["out_of_domain_raw_sql_insert"] = raw_insert("totally.made.up")
    results["in_domain_raw_sql_insert"] = raw_insert(probe_type)

    with engine.connect() as conn:
        used_in_domain = conn.execute(text(
            f"SELECT count(DISTINCT event_type) FROM {TABLE} "
            "WHERE event_type = ANY(CAST(:types AS text[]))"),
            {"types": list(AUDIT_EVENT_TYPES)}).scalar_one()
        used_total = conn.execute(
            text(f"SELECT count(DISTINCT event_type) FROM {TABLE}")).scalar_one()
    results["event_type_parity_on_stored_data"] = {
        "distinct_used": int(used_total), "distinct_used_in_domain": int(used_in_domain),
        "enum_members": len(AUDIT_EVENT_TYPES)}

    # 11. what a catalog test would pin (§13.6) once the migration has run.
    with engine.connect() as conn:
        results["catalog_after"] = {
            "triggers": [r[0] for r in conn.execute(text(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = CAST(:t AS regclass) "
                "AND NOT tgisinternal ORDER BY 1"), {"t": TABLE}).all()],
            "rules": [r[0] for r in conn.execute(text(
                "SELECT rulename FROM pg_rules WHERE tablename = :t ORDER BY 1"),
                {"t": TABLE}).all()],
            "constraints": [r[0] for r in conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
                "ORDER BY 1"), {"t": TABLE}).all()],
            "function_exists": bool(conn.execute(text(
                "SELECT count(*) FROM pg_proc WHERE oid = CAST(:f AS regproc)"),
                {"f": FUNC}).scalar_one()),
            "row_security": bool(conn.execute(text(
                "SELECT relrowsecurity FROM pg_class WHERE oid = CAST(:t AS regclass)"),
                {"t": TABLE}).scalar_one()),
        }
    with engine.connect() as conn:
        final = conn.execute(
            text(f"SELECT count(*), max(sequence_number) FROM {TABLE}")).one()
    results["final_state"] = {"rows": int(final[0]), "max_sequence": int(final[1])}
    results["enforcement_left_installed"] = True

    engine.dispose()
    print(json.dumps(results, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
