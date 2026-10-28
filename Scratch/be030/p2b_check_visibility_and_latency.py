"""BE-030 §11.2 / §9.3 micro-probes on the same disposable clone.

Two claims that p2a left unresolved, each measured by removing the thing and
counting what the comparison reports:

1. §11.2 asserts "a named CHECK on a mapped table is visible [to the drift
   machinery], and omitting it from the model would make the gate report real
   drift". p2a installed the CHECK and the diff still mentioned neither it nor
   the table. This decides whether the containment gate can protect the domain
   constraint at all, or whether only the §13.6 catalog test can.
2. The write-path cost of the enforcement trigger. Measured as the same 20
   appends with the trigger dropped and then reinstalled, on the same data.

Enforcement is reinstalled before exiting so the shipped tests can run against
this shape next (p2c).
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

from p2a_install_and_probe import (  # noqa: E402
    CHECK, FUNC, INSTALL_FUNCTION, INSTALL_TRIGGER, TABLE, TRIGGER)

results: dict = {}


def drift(engine) -> dict:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from backend.db.models import Base
    from backend.db.schema_drift_policy import include_object

    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"target_metadata": Base.metadata,
                        "include_object": include_object})
        entries = [str(e) for e in compare_metadata(ctx, Base.metadata)]
    return {"operations": len(entries),
            "signatures": [e[:80] for e in entries],
            "mentions_ledger": any(TABLE in e for e in entries),
            "mentions_check": any(CHECK in e for e in entries)}


def appends(engine, n: int) -> float:
    from backend.services.audit_ledger import append_event
    from sqlalchemy.orm import Session

    probe_type = sorted(AUDIT_EVENT_TYPES)[0]
    started = time.perf_counter()
    for i in range(n):
        with Session(engine) as db:
            append_event(db, event_type=probe_type, actor_id=None,
                         action="BE030-LATENCY", resource_type="probe",
                         resource_id=None, payload={"i": i}, commit=True)
    return round((time.perf_counter() - started) * 1000 / n, 2)


def main() -> int:
    url = sys.argv[1]
    authorized = safety.arm_verification(url)
    engine = build_guarded_engine(url)
    with engine.connect() as conn:
        database = conn.execute(text("SELECT current_database()")).scalar_one()
        if database != authorized:
            raise SystemExit(f"armed {authorized}, reached {database}")
        results["target"] = database

        # 1. CHECK visibility: drop it and see whether the diff changes at all.
        results["drift_with_check"] = drift(engine)
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CHECK}"))
        results["drift_without_check"] = drift(engine)

        # 2. trigger + CHECK absent: the write path's own cost baseline.
        with engine.begin() as conn:
            conn.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER} ON {TABLE}"))
        results["append_ms_without_trigger"] = appends(engine, 20)

        # 3. reinstall both, measure again on identical data.
        with engine.begin() as conn:
            conn.execute(text(INSTALL_FUNCTION))
            conn.execute(text(INSTALL_TRIGGER))
            values = ",".join("'" + v.replace("'", "''") + "'"
                              for v in sorted(AUDIT_EVENT_TYPES))
            conn.execute(text(f"ALTER TABLE {TABLE} "
                              f"ADD CONSTRAINT {CHECK} CHECK (event_type IN ({values}))"))
        results["append_ms_with_trigger"] = appends(engine, 20)
        results["drift_after_reinstall"] = drift(engine)

        with engine.connect() as conn:
            results["catalog_now"] = {
                "triggers": [r[0] for r in conn.execute(text(
                    "SELECT tgname FROM pg_trigger WHERE tgrelid = CAST(:t AS regclass) "
                    "AND NOT tgisinternal"), {"t": TABLE}).all()],
                "constraints": [r[0] for r in conn.execute(text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
                    "ORDER BY 1"), {"t": TABLE}).all()],
            }
            tail = conn.execute(
                text(f"SELECT count(*), max(sequence_number) FROM {TABLE}")).one()
            results["rows"] = int(tail[0])
            results["max_sequence"] = int(tail[1])
    engine.dispose()
    print(json.dumps(results, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
