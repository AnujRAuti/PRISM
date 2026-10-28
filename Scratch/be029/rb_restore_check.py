"""Phase 4/5: prove the archive<->live-table restore is exact, column by column.

Usage: python rb_restore_check.py <archived-snapshot.json> <restored-snapshot.json>

The first snapshot must contain identity_retirement_archive rows (the state where
the residue is archived); the second is the state where those rows live in
users/projects/evidence again. For every archived (source_table, source_id) the
check compares the archived JSONB image against the live row image key by key,
and reports any id that is absent, any extra restored row, and every column whose
textified value differs -- so a silent format/coercion change cannot pass.
"""
import json
import sys

archived = json.load(open(sys.argv[1]))
restored = json.load(open(sys.argv[2]))

rows = archived["archive"]
if rows is None:
    sys.exit(f"{sys.argv[1]} has no archive rows to restore from")
print(f"archived rows in snapshot: {len(rows)} "
      f"({archived['current_database']} @ {archived['alembic_version']})")
print(f"restored live state: {restored['current_database']} @ {restored['alembic_version']}")

live = restored["row_images"]
problems = []
by_table = {}
for r in rows:
    by_table.setdefault(r["source_table"], {})[r["source_id"]] = r["row_json"]

for table, wanted in sorted(by_table.items()):
    got = live[table]
    missing = sorted(set(wanted) - set(got))
    extra = sorted(set(got) - set(wanted) -
                   {k for k, v in archived["row_images"].get(table, {}).items()})
    cols_compared = 0
    value_diffs = []
    for rid, img in sorted(wanted.items()):
        if rid in missing:
            continue
        live_img = got[rid]
        keys = set(img) | set(live_img)
        for key in sorted(keys):
            a, b = img.get(key, "<absent>"), live_img.get(key, "<absent>")
            cols_compared += 1
            if str(a) != str(b):
                value_diffs.append((rid, key, str(a)[:80], str(b)[:80]))
    print(f"\n{table}: {len(wanted)} archived -> restored={len(wanted) - len(missing)}"
          f" missing={len(missing)} extra_restored={len(extra)}"
          f" columns_compared={cols_compared} value_mismatches={len(value_diffs)}")
    for m in missing[:5]:
        print(f"  MISSING {m}")
    for e in extra[:5]:
        print(f"  EXTRA {e}")
    for d in value_diffs[:8]:
        print(f"  DIFF id={d[0]} col={d[1]}\n       archived={d[2]!r}\n       restored={d[3]!r}")
    if missing:
        problems.append(f"{table}: {len(missing)} archived row(s) not restored")
    if value_diffs:
        problems.append(f"{table}: {len(value_diffs)} column value mismatch(es)")
    if extra:
        problems.append(f"{table}: {len(extra)} restored row(s) that were not archived")

print()
if problems:
    print(f"VERDICT: {len(problems)} PROBLEM(S)")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("VERDICT: every archived row was restored with its original primary key"
      " and identical column values")
