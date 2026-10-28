"""BE-032 §7: read-only audit-chain verification via the shipped service controls.

Runs against the DATABASE_URL provided in the environment (target is resolved from
the server, never from the URL text). Performs NO writes: it puts the session in
read-only mode at the SET level, and verify_chain/anchored/checkpoint only SELECT.
`default_transaction_read_only = on` forces every later transaction read-only, so
even an accidental write raises rather than persists.
"""
import json
import os
import sys
sys.path.insert(0, os.getcwd())
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

EXPECTED = sys.argv[1] if len(sys.argv) > 1 else None
url = os.environ.get("DATABASE_URL", "")
engine = create_engine(url, future=True)
out = {}
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
    conn.exec_driver_sql("SET default_transaction_read_only = on")
    actual = conn.execute(text("SELECT current_database()")).scalar_one()
    out["current_database"] = actual
    out["read_only_mode"] = conn.execute(
        text("SHOW default_transaction_read_only")).scalar_one()
    if EXPECTED and actual != EXPECTED:
        print(json.dumps({"ERROR": f"target mismatch: connected {actual}, expected {EXPECTED}"}))
        sys.exit(3)
    out["server_version"] = conn.execute(text("SHOW server_version")).scalar_one()
    out["alembic_version"] = [r[0] for r in conn.execute(
        text("SELECT version_num FROM alembic_version"))]

from backend.services import audit_ledger as svc  # noqa: E402
sess = Session(engine)
try:
    bounded = svc.verify_chain(sess)
    out["verify_chain"] = {
        "valid": bounded["valid"],
        "checked_events": bounded["checked_events"],
        "first_sequence": bounded["first_sequence"],
        "last_sequence": bounded["last_sequence"],
        "failure_count": len(bounded["failures"]),
        "sample_failures": bounded["failures"][:12],
    }
    anchored = svc.verify_chain_anchored(sess)
    out["verify_chain_anchored"] = {
        "valid": anchored["valid"],
        "checked_events": anchored["checked_events"],
        "first_sequence": anchored["first_sequence"],
        "last_sequence": anchored["last_sequence"],
        "failure_count": len(anchored["failures"]),
    }
    out["checkpoint"] = svc.ledger_checkpoint(sess)
    sess.rollback()
except Exception as exc:  # surfaced verbatim, never suppressed
    out["ERROR"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(out, indent=1, default=str))
