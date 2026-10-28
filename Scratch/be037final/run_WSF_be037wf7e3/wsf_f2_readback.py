"""Read-only follow-up on the F2 cases' database side effects.

F2 measures the worker from outside (logs, list lengths, exit codes). This asks
the questions those observations cannot answer, and only ever SELECTs:

  * did C3's duplicate delivery leave duplicate rows (results, audit events)?
  * are the jobs each case created in exactly one terminal state?
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import psycopg2

RUN_ID = "be037wf7e3"
DB_HOST, DB_PORT = "127.0.0.1", 15442
DB, OWNER, PW = f"{RUN_ID}_app", "postgres", f"{RUN_ID}pw"
EVIDENCE = Path(__file__).resolve().parent / "evidence"


def q(sql: str, params: tuple = ()) -> list:
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=OWNER, password=PW,
                            dbname=DB, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []
    finally:
        conn.close()


def main() -> int:
    f2 = json.loads((EVIDENCE / "wsf-03-f2.json").read_text(encoding="utf-8"))
    out: dict = {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                 "statement_kinds": "SELECT only"}

    job_ids: list[tuple[str, str]] = []
    for key in ("f2_c1", "f2_c2", "f2_c3", "f2_c8", "f2_c9"):
        case = f2.get(key) or {}
        fx = case.get("fixture")
        if isinstance(fx, dict) and fx.get("job_id"):
            job_ids.append((key, fx["job_id"]))
        jobs = case.get("jobs_final")
        if isinstance(jobs, dict):
            job_ids.extend((key, jid) for jid in jobs)

    per_case: dict = {}
    for key, job_id in job_ids:
        rows = q("""
            select j.status, j.attempt_count,
                   (select count(*) from analysis_results r where r.job_id = j.id),
                   (select count(*) from audit_ledger_events e where e.resource_id = j.id)
            from analysis_jobs j where j.id = %s""", (job_id,))
        per_case.setdefault(key, []).append({
            "job_id": job_id,
            "status/attempt/results/ledger_events": rows[0] if rows else None,
            "ledger_event_types": [list(r) for r in q(
                "select event_type, action, count(*) from audit_ledger_events "
                "where resource_id = %s group by 1,2 order by 1", (job_id,))],
        })
    out["jobs"] = per_case

    out["ledger_total"] = q("select count(*) from audit_ledger_events")[0][0]
    out["ledger_sequence_range"] = q(
        "select min(sequence_number), max(sequence_number) from audit_ledger_events")[0]
    out["ledger_analysis_event_types"] = [list(r) for r in q(
        "select event_type, count(*) from audit_ledger_events "
        "where resource_id in (select id from analysis_jobs) group by 1 order by 1")]
    out["analysis_result_shape"] = {
        "results": q("select count(*) from analysis_results")[0][0],
        "distinct_jobs": q("select count(distinct job_id) from analysis_results")[0][0],
        "jobs_total": q("select count(*) from analysis_jobs")[0][0],
        "jobs_by_status": [list(r) for r in q(
            "select status, count(*) from analysis_jobs group by 1 order by 1")],
    }

    text = json.dumps(out, indent=2, default=str)
    (EVIDENCE / "wsf-03b-f2-db-readback.json").write_text(text, encoding="utf-8")
    print(text.replace(PW, "***REDACTED***"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
