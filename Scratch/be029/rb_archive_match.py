"""Phase 5: compare two identity_retirement_archive snapshots, payload-for-payload.

Usage: python rb_archive_match.py <before.json> <after.json>

Proves a re-upgrade re-archives exactly the expected records: same (source_table,
source_id) set and byte-identical row_json for every row. retired_at is a real
wall-clock written by the migration, so it is reported but never treated as a
mismatch -- everything else must match exactly.
"""
import json
import sys

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
for label, s in (("before", a), ("after", b)):
    if s["archive"] is None:
        sys.exit(f"{label} snapshot has no identity_retirement_archive table")

key = lambda r: (r["source_table"], r["source_id"])
ra, rb = {key(r): r for r in a["archive"]}, {key(r): r for r in b["archive"]}
print(f"before: {a['current_database']} @ {a['alembic_version']}: {len(ra)} archive rows")
print(f"after : {b['current_database']} @ {b['alembic_version']}: {len(rb)} archive rows")

only_a = sorted(set(ra) - set(rb))
only_b = sorted(set(rb) - set(ra))
payload_diff = [k for k in sorted(set(ra) & set(rb)) if ra[k]["row_json"] != rb[k]["row_json"]]
moved = [k for k in sorted(set(ra) & set(rb)) if ra[k]["retired_at"] != rb[k]["retired_at"]]

for k in only_a[:10]:
    print(f"  only in before: {k}")
for k in only_b[:10]:
    print(f"  only in after : {k}")
for k in payload_diff[:10]:
    print(f"  payload differs: {k}")

by_table = {}
for (t, _), r in rb.items():
    by_table[t] = by_table.get(t, 0) + 1
print(f"\nafter per source table: {by_table}")
print(f"retired_at changed on {len(moved)} of {len(set(ra) & set(rb))} shared rows "
      f"(expected: the migration writes a new timestamp)")

problems = []
if only_a:
    problems.append(f"{len(only_a)} record(s) archived before but not after")
if only_b:
    problems.append(f"{len(only_b)} record(s) archived after but not before")
if payload_diff:
    problems.append(f"{len(payload_diff)} archived row_json payload(s) differ")
print("\nVERDICT: " + ("FAIL" if problems else
      "identical record set and identical payloads -- only retired_at moved"))
for p in problems:
    print(f"  - {p}")
sys.exit(1 if problems else 0)
