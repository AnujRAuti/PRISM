"""BE-037 WS-E2: the owner-side tamper transcript, on this run's own cluster.

The pytest module (``tests/integration/test_be037e2_ledger_identity_matrix.py``)
proves the *privilege* facts for three identities. Two things it deliberately
does not do, this script does:

1. It performs the destructive attempts, so the transcript quotes PostgreSQL's
   own words. The repository's ``tests/audit_guard.py`` makes any UPDATE /
   DELETE / TRUNCATE text against the ledger an unconditional violation inside
   the test tree - the enforcement must not be reachable from CI - so the live
   refusal evidence has to be captured outside it.
2. It runs as the *privileged owner*, the only identity where the two protection
   layers disagree: grants refuse nothing, so a row trigger is what stops
   UPDATE/DELETE, and TRUNCATE is statement-level, so that trigger never sees it.

Target is ``be037fin7c1f1_app2``: this run's second-boot disposable cluster
(127.0.0.1:15433), whose WS-D evidence is already on disk and which exists only
to be torn down. Nothing here touches pofa_dev or pofa_test.

Sequence, all as the cluster owner (``postgres``, a superuser of THIS cluster):
  a. publish the checkpoint digest - the anchor an operator keeps out-of-band
  b. UPDATE the tail row            -> refused by the enforcement trigger
  c. DELETE the tail row            -> refused by the enforcement trigger
  d. UPDATE through the sanctioned ``SET LOCAL`` hatch -> lands, and the app's
     own verification reports the chain invalid (so a permitted edit is still
     detectable, it is only *permitted*, not *invisible*)
  e. TRUNCATE the ledger            -> SUCCEEDS, and verification then reports
     ``valid=True`` over zero rows: indistinguishable from a fresh database from
     inside it. The published digest from (a) is what disagrees.

(e) is the documented hole and the reason the digest is published outside the
database; the report states the threat-model distinction rather than claiming an
application-level trigger defeats a database owner.

Lock discipline: a TRUNCATE needs ACCESS EXCLUSIVE, and an app session still
holding its read transaction pins ACCESS SHARE on the same table - the first run
of this script stalled exactly there and lost its evidence. So every application
read goes through ``app_read()``, which always ends the transaction, every raw
connection sets ``lock_timeout``, and the evidence file is rewritten after each
step.
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, str(REPO))
EVIDENCE = HERE / "evidence"
RUN_ID = "be037fin7c1f1"

OWNER_URL = (
    f"postgresql+psycopg2://postgres:{RUN_ID}pw2@127.0.0.1:15433/{RUN_ID}_app2"
)
TABLE = "audit_ledger_events"
HATCH_GUC = "poa.ledger_mutation_exception"
EVIDENCE_FILE = EVIDENCE / "wse2_owner_transcript.json"


def _parts(url: str) -> dict:
    """Connection kwargs instead of a DSN.

    psycopg2 rejects SQLAlchemy's ``postgresql+psycopg2`` scheme and prints the
    whole string back in the error, so building a DSN here would risk putting this
    run's disposable password into a traceback. Parts never get echoed.
    """
    from urllib.parse import unquote, urlsplit

    u = urlsplit(url)
    return {
        "host": u.hostname,
        "port": u.port,
        "user": u.username,
        "password": unquote(u.password or ""),
        "dbname": unquote(u.path.lstrip("/") or ""),
    }


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def save(out: dict) -> None:
    """Persist after every step, so a later stall cannot lose what was measured."""
    EVIDENCE_FILE.write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8")


def raw(autocommit: bool = False):
    """A psycopg2 connection that reports a lock wait instead of hanging on it."""
    import psycopg2

    parts = _parts(OWNER_URL)
    parts["options"] = (
        "-c lock_timeout=5000 "
        "-c idle_in_transaction_session_timeout=30000 "
        "-c statement_timeout=60000"
    )
    conn = psycopg2.connect(**parts)
    conn.autocommit = autocommit
    return conn


def attempt(conn, label: str, statements: list[str]) -> dict:
    """Run one transaction; the refusal text IS the evidence, so keep it verbatim."""
    import psycopg2

    started = time.monotonic()
    try:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        conn.commit()
        result = {"label": label, "ok": True, "statements": statements}
    except psycopg2.Error as exc:
        conn.rollback()
        result = {
            "label": label,
            "ok": False,
            "sqlstate": exc.pgcode,
            "error": str(exc).strip().splitlines()[0],
            "statements": statements,
        }
    result["elapsed_s"] = round(time.monotonic() - started, 2)
    return result


def main() -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.services import audit_ledger

    out: dict = {"target": f"{RUN_ID}_app2 on 127.0.0.1:15433 (this run's cluster)"}
    engine = create_engine(OWNER_URL)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def app_read():
        """One app session whose transaction ALWAYS ends before leaving the block."""
        session = Session()
        try:
            yield session
        finally:
            session.commit()
            session.close()

    # A chain to attack, built by the app's own append path on this disposable DB.
    with app_read() as session:
        rows = audit_ledger.ledger_checkpoint(session)
    if rows["rows"] < 3:
        from backend.db.models import AUDIT_EVENT_TYPES

        append_session = Session()
        try:
            for i in range(3):
                audit_ledger.append_event(
                    append_session,
                    event_type="ORGANIZATION_CREATED",
                    action="create",
                    resource_type="organizations",
                    payload={"probe": f"wse2-owner-{i}"},
                    source="be037final_wse2_owner_transcript",
                    commit=True,
                )
        finally:
            append_session.commit()
            append_session.close()
        out["appends_made"] = 3
        out["event_type_is_in_domain"] = "ORGANIZATION_CREATED" in AUDIT_EVENT_TYPES
        with app_read() as session:
            rows = audit_ledger.ledger_checkpoint(session)

    # a. The digest an operator would have published before the attack.
    with app_read() as session:
        out["before_verify"] = audit_ledger.verify_chain(session)
    out["before_checkpoint"] = rows
    tail = rows["max_sequence"]
    save(out)
    log(f"before: rows={rows['rows']} tail={tail} "
        f"valid={out['before_verify']['valid']}")

    conn = raw()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_user, rolsuper, "
                "has_table_privilege(current_user, %s::regclass, 'UPDATE'), "
                "has_table_privilege(current_user, %s::regclass, 'DELETE'), "
                "has_table_privilege(current_user, %s::regclass, 'TRUNCATE') "
                "FROM pg_roles WHERE rolname = current_user",
                (TABLE, TABLE, TABLE),
            )
            r = cur.fetchone()
            out["identity"] = {
                "current_user": r[0],
                "is_superuser": bool(r[1]),
                "grants_update": bool(r[2]),
                "grants_delete": bool(r[3]),
                "grants_truncate": bool(r[4]),
            }
            cur.execute(
                "SELECT t.tgname, t.tgtype, (t.tgtype & 1) <> 0 AS row_level, "
                "(t.tgtype & 16) <> 0 AS fires_on_update, "
                "(t.tgtype & 8) <> 0 AS fires_on_delete, "
                "(t.tgtype & 32) <> 0 AS fires_on_truncate "
                "FROM pg_trigger t WHERE t.tgrelid = %s::regclass "
                "AND NOT t.tgisinternal",
                (TABLE,),
            )
            cols = [d.name for d in cur.description]
            out["triggers_on_ledger"] = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.commit()

        # b/c. The trigger's own words, as the owner.
        out["owner_update"] = attempt(conn, "update tail row", [
            f'UPDATE {TABLE} SET payload = \'{{"tampered": true}}\'::jsonb '
            f"WHERE sequence_number = {tail}"
        ])
        out["owner_delete"] = attempt(conn, "delete tail row", [
            f"DELETE FROM {TABLE} WHERE sequence_number = {tail}"
        ])

        # d. The sanctioned hatch: proof the refusal came from the trigger, and
        # that a permitted edit is still detectable afterwards.
        out["owner_update_via_hatch"] = attempt(conn, "update through SET LOCAL hatch", [
            f"SET LOCAL {HATCH_GUC} = 'true'",
            f'UPDATE {TABLE} SET payload = \'{{"tampered": true}}\'::jsonb '
            f"WHERE sequence_number = {tail}",
        ])
    finally:
        conn.close()
    save(out)
    log(f"update refused={not out['owner_update']['ok']} "
        f"delete refused={not out['owner_delete']['ok']} "
        f"hatch landed={out['owner_update_via_hatch']['ok']}")

    with app_read() as session:
        out["after_hatch_verify"] = audit_ledger.verify_chain(session)
    save(out)
    log(f"after hatch: valid={out['after_hatch_verify']['valid']} "
        f"failures={len(out['after_hatch_verify']['failures'])}")

    # e. The documented hole. No app session may be open here.
    conn = raw(autocommit=True)
    try:
        out["owner_truncate"] = attempt(conn, "truncate the ledger", [
            f"TRUNCATE {TABLE}"
        ])
    finally:
        conn.close()
    save(out)

    with app_read() as session:
        out["after_truncate_checkpoint"] = audit_ledger.ledger_checkpoint(session)
        out["after_truncate_verify"] = audit_ledger.verify_chain(session)
        out["after_truncate_verify_anchored"] = audit_ledger.verify_chain_anchored(session)

    out["conclusion"] = {
        "trigger_refused_owner_update": not out["owner_update"]["ok"],
        "trigger_refused_owner_delete": not out["owner_delete"]["ok"],
        "hatch_update_landed": out["owner_update_via_hatch"]["ok"],
        "tampering_detected_by_verification": not out["after_hatch_verify"]["valid"],
        "truncate_allowed_for_owner": out["owner_truncate"]["ok"],
        "in_database_verdict_after_wipe": out["after_truncate_verify"]["valid"],
        "checked_events_after_wipe": out["after_truncate_verify"]["checked_events"],
        "external_digest_disagrees": (
            out["after_truncate_checkpoint"] != out["before_checkpoint"]
        ),
    }
    log(f"conclusion: {out['conclusion']}")

    engine.dispose()
    save(out)
    log(f"wrote {EVIDENCE_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
