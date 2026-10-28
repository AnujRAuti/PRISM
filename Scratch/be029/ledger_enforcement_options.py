"""BE-030 feasibility: what actually enforces append-only in this database?

BE-029 Phase G measured the hole: PostgreSQL refuses neither UPDATE nor DELETE
on ``audit_ledger_events`` (no trigger, rule or policy exists), ``event_type`` is
constrained only in Python, and after a committed deletion ``append_event`` kept
appending onto a permanently invalid chain. So today the ledger is append-only by
convention plus a verifier that has to be called by someone.

This measures the *enforcement* options against a disposable database so BE-030
can be planned on evidence instead of on assumptions about PostgreSQL. For each
variant, three questions, all answered by attempting the statement rather than by
reasoning about it:

* is a mutation **refused** (raises), **swallowed** (succeeds, row unchanged), or
  **allowed** (succeeds, row changed)? A guard that swallows silently is worse
  than one that raises: the writer believes it wrote.
* does the real writer (``append_event``) still work?
* does the pattern BE-023 §4 *sanctions* -- a single-row UPDATE inside a
  transaction that is rolled back, which is how tamper detection is tested --
  still work? If an enforcement breaks it, three shipped tests stop being
  runnable, and that is a design consequence BE-030 must decide about now.
* does the repository's drift machinery notice the object exists at all? An
  object ``alembic check`` cannot see is an object the drift gate will never
  protect.

Nothing here is proposed for ``pofa_dev`` or ``pofa_test``: the armed
``verification`` context refuses both before connecting. Every mutation attempt
is rolled back, so the scratch database's committed history is not altered.

Usage:
    python ledger_enforcement_options.py [url]
"""
import json
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from backend.db import safety
from backend.db.models import AUDIT_EVENT_TYPES, AuditLedgerEvent, Base
from backend.db.schema_drift_policy import include_object
from backend.db.session import build_guarded_engine
from backend.services.audit_ledger import append_event

OUT = "D:/CODING/Scratch/be029/ledger_enforcement_options.json"
TABLE = "audit_ledger_events"

# TG_OP, not TG_TAG: TG_TAG only exists in *event* trigger functions. The first
# run of this probe used TG_TAG and every mutation failed with
# "column \"tg_tag\" does not exist" -- a refusal, but for the wrong reason, and
# a deploy script copy-pasted from it would abort the transaction with a
# confusing error rather than the intended policy message.
TRIGGER_SQL = f"""
CREATE OR REPLACE FUNCTION {TABLE}_refuse_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only: % on the audit ledger is not permitted', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql
"""

INSTALL_TRIGGER = [
    "DROP TRIGGER IF EXISTS audit_ledger_events_no_mutation ON audit_ledger_events",
    "DROP FUNCTION IF EXISTS audit_ledger_events_refuse_mutation()",
    TRIGGER_SQL,
    f"""CREATE TRIGGER {TABLE}_no_mutation
        BEFORE UPDATE OR DELETE ON {TABLE}
        FOR EACH ROW EXECUTE FUNCTION {TABLE}_refuse_mutation()""",
]

UNINSTALL_TRIGGER = [
    f"DROP TRIGGER IF EXISTS {TABLE}_no_mutation ON {TABLE}",
    f"DROP FUNCTION IF EXISTS {TABLE}_refuse_mutation()",
]


def _rule_sql(action: str) -> list[str]:
    """Rules suppressing one mutation kind.

    The keyword is the whole design question, so both spellings are measured:

    * ``DO NOTHING`` -- a rule that fires and does nothing, while the *default*
      action still runs. The first run of this probe used it and the ledger
      stayed fully mutable: UPDATE changed the row and DELETE deleted it.
    * ``DO INSTEAD NOTHING`` -- suppresses the default action.
    """
    return [
        f"DROP RULE IF EXISTS {TABLE}_refuse_update ON {TABLE}",
        f"DROP RULE IF EXISTS {TABLE}_refuse_delete ON {TABLE}",
        f"CREATE RULE {TABLE}_refuse_update AS ON UPDATE TO {TABLE} "
        f"DO {action} NOTHING",
        f"CREATE RULE {TABLE}_refuse_delete AS ON DELETE TO {TABLE} "
        f"DO {action} NOTHING",
    ]


INSTALL_RULES_DO_NOTHING = _rule_sql("")
INSTALL_RULES_DO_INSTEAD = _rule_sql("INSTEAD")

UNINSTALL_RULES = [
    f"DROP RULE IF EXISTS {TABLE}_refuse_update ON {TABLE}",
    f"DROP RULE IF EXISTS {TABLE}_refuse_delete ON {TABLE}",
]

# The application connects as the table owner here, so this is the harder case,
# not the easier one: an owner's privileges are implicit.
INSTALL_REVOKES = [
    f"REVOKE UPDATE, DELETE ON {TABLE} FROM PUBLIC",
    f"REVOKE UPDATE, DELETE ON {TABLE} FROM CURRENT_USER",
]

UNINSTALL_REVOKES = [f"GRANT ALL ON {TABLE} TO CURRENT_USER"]

VARIANTS = [
    ("none (current shipped schema)", [], []),
    ("BEFORE ROW trigger that RAISEs EXCEPTION", INSTALL_TRIGGER, UNINSTALL_TRIGGER),
    ("rules spelled DO NOTHING", INSTALL_RULES_DO_NOTHING, UNINSTALL_RULES),
    ("rules spelled DO INSTEAD NOTHING", INSTALL_RULES_DO_INSTEAD, UNINSTALL_RULES),
    ("REVOKE UPDATE, DELETE from the connected role", INSTALL_REVOKES,
     UNINSTALL_REVOKES),
]


def append_one(engine, marker: str) -> tuple[str, int]:
    """Commit one event through the real writer; return (id, sequence)."""
    session = sessionmaker(bind=engine)()
    try:
        row = append_event(session, event_type="ORGANIZATION_CREATED",
                           action="create", resource_type="organizations",
                           payload={"probe": "be030-enforcement", "note": marker},
                           source="be030-enforcement")
        session.commit()
        return str(row.id), int(row.sequence_number)
    finally:
        session.close()


def attempt(engine, sql: str, target_id: str) -> dict:
    """Run a mutation in its own transaction, inspect, then roll it back.

    Three outcomes are distinguished because they mean different things for a
    safety design: an exception is a refusal, a no-op is a swallow, and a
    visible change means nothing is enforcing anything.
    """
    conn = engine.connect()
    try:
        conn.execute(text("SET lock_timeout = '10s'"))
        try:
            conn.execute(text(sql), {"id": target_id})
            outcome = "statement succeeded"
        except Exception as exc:  # noqa: BLE001 - the refusal is the answer
            orig = getattr(exc, "orig", exc)
            conn.rollback()
            return {"refused": True, "swallowed": False, "changed": False,
                    "error": f"{type(orig).__name__}: "
                             f"{' '.join(str(orig).split())[:160]}"}
        # Still inside the transaction: did the row actually change?
        probe = conn.execute(text(
            f"SELECT action FROM {TABLE} WHERE id = CAST(:id AS uuid)"),
            {"id": target_id}).scalar_one_or_none()
        changed = probe == "marked-by-probe"
        absent = probe is None
        conn.rollback()
        return {"refused": False,
                "swallowed": not changed and not absent,
                "changed": changed, "gone": absent,
                "error": None, "note": outcome}
    finally:
        conn.close()


UPDATE_SQL = (f"UPDATE {TABLE} SET action = 'marked-by-probe' "
              "WHERE id = CAST(:id AS uuid)")
DELETE_SQL = f"DELETE FROM {TABLE} WHERE id = CAST(:id AS uuid)"


def sanctioned_pattern(engine) -> dict:
    """BE-023 §4's tamper-test shape: rewrite a row, then roll it back.

    Returns whether the test could still do its job -- which requires the UPDATE
    to actually change the row *inside* the transaction, so that ``verify_chain``
    can observe the damage before the rollback undoes it.
    """
    conn = engine.connect()
    session = sessionmaker(bind=conn)()
    try:
        row = append_event(session, event_type="ORGANIZATION_CREATED",
                           action="create", resource_type="organizations",
                           payload={"probe": "be030-sanctioned"},
                           source="be030-sanctioned")
        session.commit()
        target = str(row.id)
    finally:
        session.close()
        conn.close()
    result = attempt(engine, UPDATE_SQL, target)
    result["target"] = target
    return result


def drift_visibility(engine) -> dict:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"target_metadata": Base.metadata,
                        "include_object": include_object})
        entries = [str(e) for e in compare_metadata(ctx, Base.metadata)]
    return {"operations": len(entries),
            "operation_details": [e[:150] for e in entries],
            "mentions_ledger": any(TABLE in e for e in entries)}


def existing_event_types(engine) -> list[str]:
    """Can a database CHECK on event_type be added to *this* data at all?"""
    with engine.connect() as conn:
        return conn.execute(text(
            f"SELECT DISTINCT event_type FROM {TABLE} "
            "WHERE event_type <> ALL(CAST(:types AS text[])) ORDER BY 1"),
            {"types": list(AUDIT_EVENT_TYPES)}).scalars().all()


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be029_assumptions")
    authorized = safety.arm_verification(url)
    engine = build_guarded_engine(url)
    with engine.connect() as conn:
        database = conn.execute(text("SELECT current_database()")).scalar_one()
        revision = conn.execute(
            text("SELECT version_num FROM alembic_version")).scalars().all()
        ledger_rows = conn.execute(
            text(f"SELECT count(*), coalesce(max(sequence_number), 0) FROM {TABLE}")
        ).one()
    if database != authorized:
        raise SystemExit(f"refusing to run: armed for {authorized}, reached {database}")
    print(f"target: {database} (authorised {authorized}), revision {revision}, "
          f"ledger rows/max = {ledger_rows}")

    report = {
        "database": database,
        "revision": revision,
        "ledger_before": {"rows": int(ledger_rows[0]), "max_sequence": int(ledger_rows[1])},
        "event_type_values_outside_the_python_domain": existing_event_types(engine),
        "variants": [],
    }

    for label, install, uninstall in VARIANTS:
        record: dict = {"variant": label}
        with engine.connect() as conn:
            for statement in install:
                conn.execute(text(statement))
            conn.commit()
        try:
            marker = f"{label[:12]}".replace(" ", "-")
            target_id, sequence = append_one(engine, marker)
            record["writer_appends"] = True
            record["appended_sequence"] = sequence
            record["update"] = attempt(engine, UPDATE_SQL, target_id)
            record["delete"] = attempt(engine, DELETE_SQL, target_id)
            record["sanctioned_tamper_pattern"] = sanctioned_pattern(engine)
            record["drift_gate_sees_it"] = drift_visibility(engine)
        except Exception as exc:  # noqa: BLE001
            orig = getattr(exc, "orig", exc)
            record["writer_appends"] = False
            record["writer_error"] = f"{type(orig).__name__}: " \
                f"{' '.join(str(orig).split())[:200]}"
        finally:
            with engine.connect() as conn:
                for statement in uninstall:
                    conn.execute(text(statement))
                conn.commit()
        report["variants"].append(record)
        print(json.dumps(record, indent=2))

    with engine.connect() as conn:
        after = conn.execute(
            text(f"SELECT count(*), coalesce(max(sequence_number), 0) FROM {TABLE}")
        ).one()
    report["ledger_after"] = {"rows": int(after[0]), "max_sequence": int(after[1])}
    # Every mutation attempt rolled back, so the only growth is the appends the
    # writer legitimately made. Contiguity is what proves nothing was removed.
    report["appends_only_growth"] = (
        int(after[0]) - int(ledger_rows[0]) == int(after[1]) - int(ledger_rows[1]))
    engine.dispose()
    safety.disarm()
    print(json.dumps({k: report[k] for k in
                      ("database", "ledger_after", "appends_only_growth",
                       "event_type_values_outside_the_python_domain")}, indent=2))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
