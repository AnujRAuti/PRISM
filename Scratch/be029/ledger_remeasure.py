"""BE-029 Phase G: remeasure the append-only audit ledger, using the product's own verifier.

Read-only by construction: the only statement issued through the ORM session is
``verify_chain``, which selects. The psycopg2 connection is additionally set to
``READ ONLY``. Nothing here writes, deletes, renumbers or backfills -- history
is reported, never edited.

Two questions it answers:

1. What is the chain's actual state on this database right now (count, span,
   gaps, verifier verdict)?
2. Which events did this session's own mistake add, and are they still
   distinguishable? A scratch TestClient wrote into ``pofa_dev`` before the
   database guard existed; the domain rows were deleted but the ledger is
   append-only, so those events remain and must be named, not quietly ignored.

No context is armed, so ``backend.db.safety`` stays inert -- this is a developer
diagnostic against a database the operator chose to point at.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path("D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, str(ROOT))

from backend.services.audit_ledger import verify_chain  # noqa: E402

DEV_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"
OUT = Path("D:/CODING/Scratch/be029/ledger_remeasure.json")


def dsn(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://", 1)


def q(cur, sql, params=()):
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEV_URL
    since = sys.argv[2] if len(sys.argv) > 2 else "2026-10-09 00:00:00"
    report: dict = {}

    raw = psycopg2.connect(dsn(url), cursor_factory=psycopg2.extras.RealDictCursor)
    raw.set_session(readonly=True, autocommit=False)
    with raw.cursor() as cur:
        report["database"] = q(cur, "SELECT current_database() AS d")[0]["d"]
        head = q(cur, "SELECT version_num FROM alembic_version")[0]
        report["revision"] = head["version_num"]
        span = q(cur, "SELECT count(*) AS n, min(sequence_number) AS lo,"
                      " max(sequence_number) AS hi FROM audit_ledger_events")[0]
        report["count"], report["min_seq"], report["max_seq"] = (
            span["n"], span["lo"], span["hi"])
        report["missing_by_span"] = (span["hi"] - span["lo"] + 1) - span["n"]
        report["gaps"] = q(
            cur,
            "SELECT lo, hi, hi - lo + 1 AS rows_missing FROM ("
            "  SELECT sequence_number + 1 AS lo,"
            "         lead(sequence_number) OVER (ORDER BY sequence_number) - 1 AS hi"
            "  FROM audit_ledger_events"
            ") g WHERE lo <= hi ORDER BY lo")
        report["gap_count"] = len(report["gaps"])
        report["gap_rows"] = sum(g["rows_missing"] for g in report["gaps"])
        # The writer derives every sequence number from the current maximum, so a
        # normal append cannot skip a number: gaps can only mean rows were
        # removed after the fact.
        report["distinct_sequence_numbers"] = q(
            cur, "SELECT count(DISTINCT sequence_number) AS d FROM"
                 " audit_ledger_events")[0]["d"]

        report["events_since"] = q(
            cur,
            "SELECT sequence_number, event_type, action, resource_type, resource_id,"
            "       actor_id, project_id, created_at"
            " FROM audit_ledger_events WHERE created_at >= %s"
            " ORDER BY sequence_number", (since,))
        resource_ids = [r["resource_id"] for r in report["events_since"]
                        if r["resource_type"] == "users" and r["resource_id"]]
        report["events_since_resource_rows_still_present"] = (
            q(cur, "SELECT id, username, email FROM users WHERE id = ANY(%s::uuid[])",
              (resource_ids,)) if resource_ids else [])
        report["events_since_actor_rows_still_present"] = q(
            cur,
            "SELECT id, username, email FROM users WHERE id = ANY("
            "  SELECT DISTINCT actor_id FROM audit_ledger_events"
            "  WHERE created_at >= %s AND actor_id IS NOT NULL)", (since,))
    raw.close()

    # The application's own verdict, computed by the shipped verifier rather than
    # by a reimplementation here.
    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    try:
        report["verify_chain_full"] = verify_chain(session)
        tail = int(report["max_seq"]) - 20
        report["verify_chain_tail"] = verify_chain(session, from_sequence=max(tail, 1))
    finally:
        session.close()
        engine.dispose()

    for key in ("verify_chain_full", "verify_chain_tail"):
        entry = report[key]
        entry["failures"] = list(entry.get("failures", []))[:12]

    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
