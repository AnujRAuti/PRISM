"""BE-030: does the refusal trigger cover TRUNCATE? (It cannot, and §7.7 forbids
solving it with a trigger, so this measures the size of the hole.)

Runs on a second disposable database created as a TEMPLATE copy of the enforced
scratch, so destroying it costs nothing.

    python p2g_truncate_hole.py <sqlalchemy-url-for-the-throwaway>
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.db import safety  # noqa: E402
from backend.db.models import AUDIT_EVENT_TYPES  # noqa: E402
from backend.db.session import build_guarded_engine  # noqa: E402
from backend.services.audit_ledger import append_event, verify_chain  # noqa: E402

from p2a_install_and_probe import TABLE, TRIGGER  # noqa: E402

results: dict = {}


def main() -> int:
    url = sys.argv[1]
    authorized = safety.arm_verification(url)
    engine = build_guarded_engine(url)
    with engine.connect() as conn:
        database = conn.execute(text("SELECT current_database()")).scalar_one()
        if database != authorized:
            raise SystemExit(f"armed {authorized}, reached {database}")
        trigger_present = conn.execute(text(
            "SELECT count(*) FROM pg_trigger WHERE tgrelid = CAST(:t AS regclass) "
            "AND NOT tgisinternal"), {"t": TABLE}).scalar_one()
        tail = conn.execute(
            text(f"SELECT count(*), coalesce(max(sequence_number), 0) FROM {TABLE}")).one()
    results["target"] = database
    results["enforcement_present_at_start"] = {"triggers": int(trigger_present),
                                              "rows": int(tail[0]),
                                              "max_sequence": int(tail[1])}

    # 1. TRUNCATE through the application's own engine, with enforcement live.
    try:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {TABLE}"))
        results["truncate"] = {"outcome": "executed",
                               "note": "the BEFORE ROW trigger never fires: "
                                       "TRUNCATE is not a row-level operation"}
    except Exception as exc:  # noqa: BLE001
        results["truncate"] = {"outcome": "refused",
                               "message": str(exc).splitlines()[0][:200]}

    with engine.connect() as conn:
        after = conn.execute(
            text(f"SELECT count(*), coalesce(max(sequence_number), 0) FROM {TABLE}")).one()
        trigger_after = conn.execute(text(
            "SELECT count(*) FROM pg_trigger WHERE tgrelid = CAST(:t AS regclass) "
            "AND NOT tgisinternal"), {"t": TABLE}).scalar_one()
    results["after_truncate"] = {"rows": int(after[0]),
                                 "max_sequence": int(after[1]),
                                 "trigger_survived": int(trigger_after) > 0}

    # 2. the consequence: a rebuilt chain verifies perfectly.
    probe_type = sorted(AUDIT_EVENT_TYPES)[0]
    with Session(engine) as db:
        for i in range(3):
            append_event(db, event_type=probe_type, action="BE030-REBUILT",
                         resource_type="probe", payload={"i": i}, commit=True)
        verdict = verify_chain(db)
    results["chain_after_rebuild"] = {
        "valid": verdict["valid"], "checked": verdict["checked_events"],
        "first_sequence": verdict["first_sequence"],
        "last_sequence": verdict["last_sequence"],
        "meaning": "total-loss tamper followed by a fresh chain is reported as "
                   "intact: link verification cannot distinguish a rebuilt history "
                   "from a continuous one without an external checkpoint"}

    # 3. is the hole closable by privileges? measured against the owner role.
    with engine.connect() as conn:
        results["privileges"] = dict(conn.execute(text("""
            SELECT current_user AS role,
                   pg_get_userbyid((SELECT relowner FROM pg_class
                                     WHERE oid = CAST(:t AS regclass))) AS table_owner,
                   has_table_privilege(current_user, CAST(:t AS regclass), 'TRUNCATE')
                       AS truncate_priv
        """), {"t": TABLE}).mappings().one())

    engine.dispose()
    print(json.dumps(results, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
