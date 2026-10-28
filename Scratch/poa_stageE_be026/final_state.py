"""BE-026 Stage E, final environment and hygiene proof.

Run after every fault injection has been undone. Each claim in the Stage E
results document is backed by one line of this output, measured rather than
asserted:

* the injections are gone (no function, no trigger, by name);
* the test database accepts connections again and the containers are running;
* the audit ledger is contiguous, append-only and still verifies;
* nothing disposable was left behind by the probes;
* pofa_dev was never written to (the standing isolation rule).
"""

import json
import os
import subprocess
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.environ["PYTHONPATH"])
from sqlalchemy.orm import sessionmaker  # noqa: E402
from backend.services.audit_ledger import verify_chain  # noqa: E402

URL = os.environ["DATABASE_URL"]
DEV_URL = URL.rsplit("/", 1)[0] + "/pofa_dev"
engine = create_engine(URL)
dev = create_engine(DEV_URL)

with engine.connect() as c:
    print("current_db    ", c.execute(text("select current_database()")).scalar())
    print("postgres      ", c.execute(text("select version()")).scalar().split(" on")[0])
    print("datallowconn  ", {
        r[0]: r[1] for r in c.execute(text(
            "select datname, datallowconn from pg_database"
            " where datname in ('pofa_test','pofa_dev') order by datname"))
    })
    print("leftover_fns  ", c.execute(text(
        "select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace"
        " where n.nspname = 'public' and p.proname like 'be026\\_stage\\_e%' escape '\\'"
    )).scalar())
    print("leftover_trg  ", c.execute(text(
        "select count(*) from pg_trigger where tgname like 'be026\\_stage\\_e%' escape '\\'"
    )).scalar())
    print("field_rows    ", {
        t: c.execute(text(f"select count(*) from {t}")).scalar()
        for t in ("field_assignments", "field_sessions", "field_capture_operations")
    })
    print("ledger        ", c.execute(text(
        "select count(*), min(sequence_number), max(sequence_number)"
        " from audit_ledger_events")).one())
with sessionmaker(bind=engine)() as session:
    print("chain         ", json.dumps(verify_chain(session)))

with dev.connect() as c:
    existing = {r[0] for r in c.execute(text(
        "select tablename from pg_tables where schemaname = 'public'")).all()}
    print("dev_field_tables", sorted(t for t in
                                     ("field_assignments", "field_sessions",
                                      "field_capture_operations") if t in existing) or "absent")
    print("dev_alembic     ", (
        [r[0] for r in c.execute(text("select version_num from alembic_version")).all()]
        if "alembic_version" in existing else "absent"))
    print("dev_evidence    ", (c.execute(text("select count(*) from evidence")).scalar()
                               if "evidence" in existing else "absent"))

print("containers    ", subprocess.run(
    ["docker", "ps", "--format", "{{.Names}} {{.Status}}"],
    capture_output=True, text=True).stdout.strip().replace("\n", " | "))
