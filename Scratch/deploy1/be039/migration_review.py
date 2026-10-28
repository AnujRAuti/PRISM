"""Read-only review of the BE-039 vocabulary rebuild.

Proves the migration only ADDS values: the live constraint on the un-migrated
database must equal AUDIT_EVENT_TYPES minus PROJECT_CREATED, and the migrated
one must equal AUDIT_EVENT_TYPES exactly.
"""
import re
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, "D:/CODING/Scratch/deploy1")

from backend.db.models import AUDIT_EVENT_TYPES  # noqa: E402
import armfull  # noqa: E402

STMT = ("select pg_get_constraintdef(oid) from pg_constraint "
        "where conname='ck_audit_ledger_event_type_domain'")
code = set(AUDIT_EVENT_TYPES)
print("AUDIT_EVENT_TYPES:", len(code), "| PROJECT_CREATED present:", "PROJECT_CREATED" in code)

for db in ("pofa_test", "poa_disp_suite"):
    raw = armfull.psql(db, STMT)
    live = set(re.findall(r"'([^']+)'", raw))
    print(f"\n{db}: live constraint values = {len(live)}")
    if live == code:
        print("  == code vocabulary exactly (nothing added, nothing dropped)")
    else:
        print("  only PROJECT_CREATED missing, nothing else:", (code - live) == {"PROJECT_CREATED"})
        print("  extra in live but not in code:", sorted(live - code) or "none")
        print("  missing from live:", sorted(code - live) or "none")
