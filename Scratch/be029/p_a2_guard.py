"""BE-029 A2: evaluate the residue guard predicate (READ-ONLY) and print the exact
candidate deletion set. Nothing here writes; the session is readonly."""
import json
import psycopg2
from psycopg2.extras import RealDictCursor

URLS = {
    "pofa_test": "postgresql://postgres:postgres@localhost:5432/pofa_test",
    "pofa_dev": "postgresql://postgres:postgres@localhost:5432/pofa_dev",
}
RULE = {"a": "NO ACTION", "r": "CASCADE", "p": "RESTRICT", "n": "SET NULL", "d": "SET DEFAULT"}

FK_TO = """
SELECT cl.relname AS tbl, a.attname AS col,
       CASE c.confdeltype WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'CASCADE'
            WHEN 'p' THEN 'RESTRICT' WHEN 'n' THEN 'SET NULL'
            WHEN 'd' THEN 'SET DEFAULT' END AS rule
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f' AND c.confrelid = %s::regclass
ORDER BY tbl, col
"""
MEMBERS = """
SELECT id, created_at::text, status, is_active, identity_provider,
       external_subject IS NULL AS subj_null, display_name IS NULL AS disp_null
FROM users WHERE username = 'testuser' AND email = 'test@example.com'
ORDER BY created_at, id
"""

report = {}
for label, url in URLS.items():
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    rows = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(FK_TO, ("users",))
        user_fks = [r for r in cur.fetchall() if not (r["tbl"] == "projects" and r["col"] == "owner_id")]
        cur.execute(FK_TO, ("evidence",))
        ev_fks = cur.fetchall()

        cur.execute(MEMBERS)
        members = cur.fetchall()
        for m in members:
            checks = {}
            # 1. owns exactly one project, named 'testproj'
            cur.execute("SELECT id, name FROM projects WHERE owner_id = %s", (m["id"],))
            prows = cur.fetchall()
            checks["one_project_named_testproj"] = (
                len(prows) == 1 and prows[0]["name"] == "testproj")
            # 2. that project's only children are evidence rows with filename 'foo.jpg'
            ev_rows = []
            if prows:
                cur.execute("SELECT id, filename FROM evidence WHERE project_id = %s",
                            (prows[0]["id"],))
                ev_rows = cur.fetchall()
                checks["children_are_foo_jpg"] = bool(ev_rows) and all(
                    e["filename"] == "foo.jpg" for e in ev_rows)
            else:
                checks["children_are_foo_jpg"] = False
            # 3. zero rows in every other FK column pointing at the user id
            other_refs = 0
            offenders = []
            for r in user_fks:
                cur.execute(f'SELECT count(*) AS c FROM "{r["tbl"]}" WHERE "{r["col"]}" = %s',
                            (m["id"],))
                c = cur.fetchone()["c"]
                other_refs += c
                if c:
                    offenders.append(f'{r["tbl"]}.{r["col"]}={c}({r["rule"]})')
            checks["no_other_user_refs"] = other_refs == 0
            # 4. zero audit ledger involvement
            cur.execute("""
                SELECT count(*) AS c FROM audit_ledger_events
                WHERE actor_id = %s
                   OR (resource_type = 'users' AND resource_id::text = %s)
            """, (m["id"], m["id"]))
            checks["no_ledger_rows"] = cur.fetchone()["c"] == 0
            # 5. the evidence rows are leaves
            ev_refs = 0
            ev_offenders = []
            if ev_rows:
                ids = [e["id"] for e in ev_rows]
                for r in ev_fks:
                    cur.execute(f'SELECT count(*) AS c FROM "{r["tbl"]}" WHERE "{r["col"]}"'
                                ' = ANY(%s::uuid[])', (ids,))
                    c = cur.fetchone()["c"]
                    ev_refs += c
                    if c:
                        ev_offenders.append(f'{r["tbl"]}.{r["col"]}={c}({r["rule"]})')
            checks["evidence_are_leaves"] = ev_refs == 0

            passed = all(checks.values())
            rows.append({
                "user_id": m["id"], "created_at": m["created_at"],
                "status": m["status"], "subj_null": m["subj_null"],
                "disp_null": m["disp_null"],
                "project_id": prows[0]["id"] if prows else None,
                "evidence_ids": [e["id"] for e in ev_rows],
                "checks": checks, "passed": passed,
                "other_user_refs": other_refs, "evidence_refs": ev_refs,
                "offenders": offenders + ev_offenders,
            })
    report[label] = rows
    conn.close()

for label, rows in report.items():
    ok = sum(1 for r in rows if r["passed"])
    print(f"\n================ {label} ================")
    print(f"members: {len(rows)}   predicate PASS: {ok}   FAIL: {len(rows) - ok}")
    print(f"candidate deletion set: users={len(rows)} "
          f"projects={sum(1 for r in rows if r['passed'])} "
          f"evidence={sum(len(r['evidence_ids']) for r in rows if r['passed'])}")
    print(f"non-residue references that would block deletion: "
          f"{sum(r['other_user_refs'] + r['evidence_refs'] for r in rows)}")
    print(f"ledger rows that would lose their actor/resource: "
          f"{sum(0 if r['checks']['no_ledger_rows'] else 1 for r in rows)}")
    print()
    print(f'  {"created_at":26} {"user_id":38} {"project_id":38} ev  P S')
    for r in rows:
        print(f'  {r["created_at"]:26} {r["user_id"]:38} '
              f'{(r["project_id"] or "-"):38} {len(r["evidence_ids"]):<3} '
              f'{"PASS" if r["passed"] else "FAIL":>2} '
              f'{"subj=NULL" if r["subj_null"] else "subj=id"}'
              f'{" disp=NULL" if r["disp_null"] else ""}')
        if not r["passed"]:
            print("        failed checks:", [k for k, v in r["checks"].items() if not v],
                  "offenders:", r["offenders"])

with open("D:/CODING/Scratch/be029/a2_guard_report.json", "w") as fh:
    json.dump(report, fh, indent=1)
print("\nfull detail -> D:/CODING/Scratch/be029/a2_guard_report.json")
