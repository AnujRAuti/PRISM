"""Phase 4/5: diff two rb_state.py snapshots and say what actually changed.

Usage: python rb_diff.py <before.json> <after.json> [options]
  --allow-tables a,b,c    tables allowed to differ in content (others are failures)
  --added-table x         a table expected to appear (e.g. the archive on re-upgrade)
  --removed-table x       a table expected to disappear
  --rows users:+40,...    expected row-image change per table: +N added, -N removed,
                          =0 unchanged. Any *modified* row is a failure regardless.

Row-level truth is compared, not counts: for users, projects and evidence the
whole row image (every column) is diffed by primary key.
"""
import argparse
import json
import sys

parser = argparse.ArgumentParser()
parser.add_argument("before")
parser.add_argument("after")
parser.add_argument("--allow-tables", default="")
parser.add_argument("--added-table", action="append", default=[])
parser.add_argument("--removed-table", action="append", default=[])
parser.add_argument("--rows", default="")
args = parser.parse_args()

before = json.load(open(args.before))
after = json.load(open(args.after))
allow = {t for t in args.allow_tables.split(",") if t}
problems, notes = [], []

print(f"before: {before['current_database']} @ {before['alembic_version']}")
print(f"after : {after['current_database']} @ {after['alembic_version']}")
if before["current_database"] != after["current_database"]:
    problems.append("the two snapshots are of different databases")

b_tabs, a_tabs = set(before["table_fingerprints"]), set(after["table_fingerprints"])
for t in sorted(a_tabs - b_tabs):
    line = f"table added: {t} ({after['table_fingerprints'][t]['rows']} rows)"
    (notes if t in args.added_table else problems).append(line)
for t in sorted(b_tabs - a_tabs):
    line = f"table removed: {t} (was {before['table_fingerprints'][t]['rows']} rows)"
    (notes if t in args.removed_table else problems).append(line)

changed = []
for t in sorted(b_tabs & a_tabs):
    b, a = before["table_fingerprints"][t], after["table_fingerprints"][t]
    if b["fingerprint"] != a["fingerprint"] or b["rows"] != a["rows"]:
        changed.append(t)
        if t not in allow and t not in ("users", "projects", "evidence"):
            problems.append(f"unexpected content change in {t}: "
                            f"{b['rows']} -> {a['rows']} rows, fingerprint differs")
print(f"\ntables whose content changed: {changed or 'none'}")
print(f"tables unchanged: {len(b_tabs & a_tabs) - len(changed)}")

expect = {}
for item in (x for x in args.rows.split(",") if x):
    table, spec = item.split(":")
    expect[table] = (int(spec[1:]) if spec[0] in "+-" else 0, spec[0])

for t in ("users", "projects", "evidence"):
    b, a = before["row_images"][t], after["row_images"][t]
    removed = sorted(set(b) - set(a))
    added = sorted(set(a) - set(b))
    modified = sorted(k for k in set(b) & set(a) if b[k] != a[k])
    print(f"\n{t}: {len(b)} -> {len(a)} rows | removed={len(removed)} "
          f"added={len(added)} surviving-rows-modified={len(modified)}")
    if modified:
        problems.append(f"{t}: {len(modified)} surviving row(s) changed value: "
                        + ", ".join(str(m) for m in modified[:5]))
    want = expect.get(t)
    if want:
        signed_add = len(added) if want[1] == "+" else 0
        signed_rm = len(removed) if want[1] == "-" else 0
        if want[0] not in (signed_add, signed_rm) or (want[0] == 0 and (added or removed)):
            problems.append(f"{t}: expected {want[1]}{want[0]} row change, got "
                            f"+{len(added)} -{len(removed)}")

print("\nusers indexes:")
for name in sorted(set(before["index_definitions"]) | set(after["index_definitions"])):
    b = before["index_definitions"].get(name, "(absent)")
    a = after["index_definitions"].get(name, "(absent)")
    flag = "SAME" if b == a else "CHANGED"
    print(f"  [{flag}] {name}\n        before: {b}\n        after : {a}")
    if flag == "CHANGED" and name not in ("ix_users_username", "ix_users_email"):
        problems.append(f"unexpected change to index {name}")

print("\nusers constraints:")
for name in sorted(set(before["constraint_definitions"]) | set(after["constraint_definitions"])):
    b = before["constraint_definitions"].get(name, "(absent)")
    a = after["constraint_definitions"].get(name, "(absent)")
    if b != a:
        problems.append(f"constraint {name} changed: {b!r} -> {a!r}")
    else:
        print(f"  [SAME] {name}: {a}")

def arch(state):
    return {} if state["archive"] is None else {
        r: sum(1 for x in state["archive"] if x["source_table"] == r)
        for r in ("users", "projects", "evidence")}

print(f"\narchive: before={arch(before) or 'table absent'} after={arch(after) or 'table absent'}")
print(f"residue users: {before['residue_users']} -> {after['residue_users']}")
for col in ("username", "email"):
    b, a = before["duplicate_groups"][col], after["duplicate_groups"][col]
    print(f"duplicate {col} groups: {b} -> {a}")

b_l, a_l = before["ledger"], after["ledger"]
b_f = before["table_fingerprints"].get("audit_ledger_events", {})
a_f = after["table_fingerprints"].get("audit_ledger_events", {})
print(f"\naudit ledger: {b_l['n']} -> {a_l['n']} rows, "
      f"span {b_l['lo']}..{b_l['hi']} -> {a_l['lo']}..{a_l['hi']}, "
      f"fingerprint {'IDENTICAL' if b_f.get('fingerprint') == a_f.get('fingerprint') else 'DIFFERENT'}")
if b_f.get("fingerprint") != a_f.get("fingerprint"):
    problems.append("audit_ledger_events content changed")

print()
if problems:
    print(f"VERDICT: {len(problems)} PROBLEM(S)")
    for p in problems:
        print(f"  - {p}")
else:
    print("VERDICT: only the expected objects changed; every other table is"
          " byte-identical and no surviving row was modified")
for n in notes:
    print(f"  note: {n}")
sys.exit(1 if problems else 0)
