"""BE-030 §5 Phase 1 -- re-measure the ledger before writing any migration.

Read-only. Targets one database, named explicitly on the command line, and the
script refuses to continue unless the *server* reports that name (§14: never
trust .env, a shell variable, or a printed URL).

    python p1_remeasure.py <sqlalchemy-url> <expected-current_database>

Nothing here mutates: every psycopg2 statement runs under
``set_session(readonly=True)`` and the SQLAlchemy session is only ever used for
the shipped verifier's own SELECTs. The refusal-shaped facts (F-1/F-2) are
therefore *not* probed by attempting an UPDATE -- that belongs on a disposable
clone (§12.5). Here they are established from the catalog: which enforcement
objects exist.
"""

from __future__ import annotations

import json
import sys
import time

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

TABLE = "audit_ledger_events"


def missing_ranges(cur) -> list[dict]:
    """Every absent sequence number, collapsed into contiguous ranges.

    A gap can only mean a row was removed after the fact: the writer holds an
    advisory lock and computes sequence = latest + 1, so it cannot skip a
    number, and a rolled-back append does not burn one (BE-029 F-3).
    """
    cur.execute(
        f"""
        WITH bounds AS (SELECT min(sequence_number) AS lo,
                                  max(sequence_number) AS hi
                           FROM {TABLE}),
        present AS (SELECT sequence_number AS s FROM {TABLE}),
        gaps AS (
            SELECT gs AS missing,
                   (gs - row_number() OVER (ORDER BY gs)) AS grp
              FROM generate_series((SELECT lo FROM bounds),
                                   (SELECT hi FROM bounds)) AS gs
             WHERE gs NOT IN (SELECT s FROM present))
        SELECT min(missing) AS from_sequence,
               max(missing) AS to_sequence,
               count(*) AS count
          FROM gaps GROUP BY grp ORDER BY min(missing)
        """)
    rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        # The surviving neighbours bracket when the removal happened.
        cur.execute(
            f"""
            SELECT (SELECT created_at FROM {TABLE}
                     WHERE sequence_number = %(lo)s) AS before_at,
                   (SELECT created_at FROM {TABLE}
                     WHERE sequence_number = %(hi)s) AS after_at
            """, {"lo": row["from_sequence"] - 1, "hi": row["to_sequence"] + 1})
        neighbours = cur.fetchone() or {}
        row["survivor_before_created_at"] = str(neighbours.get("before_at"))
        row["survivor_after_created_at"] = str(neighbours.get("after_at"))
    return rows


def classify(failures: list[str]) -> dict:
    """Count the three symptom classes separately (F-7): they mean different
    incidents, so an operator reading a verdict must be able to tell them."""
    buckets = {"event_hash mismatch": 0, "missing predecessor": 0, "sequence gap": 0}
    for failure in failures:
        for key in buckets:
            if failure.startswith(key):
                buckets[key] += 1
                break
    return {k: v for k, v in buckets.items() if v}


def main() -> int:
    url = sys.argv[1]
    expected = sys.argv[2]
    dsn = url.replace("postgresql+psycopg2", "postgresql", 1)

    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    report: dict = {"requested_database": expected}

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT current_database() AS db, version() AS v")
        server = cur.fetchone()
        report["server_database"] = server["db"]
        report["postgres_version"] = server["v"].split(",")[0]
        if server["db"] != expected:
            conn.close()
            raise SystemExit(
                f"refusing to measure: URL was expected to reach {expected!r} "
                f"but the server reports {server['db']!r}")

        cur.execute("SELECT version_num FROM alembic_version ORDER BY 1")
        report["alembic_version_num"] = [r["version_num"] for r in cur.fetchall()]

        cur.execute(
            f"""
            SELECT count(*) AS rows,
                   coalesce(min(sequence_number), 0) AS min_sequence,
                   coalesce(max(sequence_number), 0) AS max_sequence,
                   count(DISTINCT sequence_number) AS distinct_sequences
              FROM {TABLE}
            """)
        ledger = cur.fetchone()
        span = ledger["max_sequence"] - ledger["min_sequence"] + 1
        report["ledger"] = {**ledger, "span": span,
                            "span_minus_count": span - ledger["distinct_sequences"]}

        # F-8 / F-9: is the event_type domain enforced anywhere but Python, and
        # is the data clean enough for a CHECK to be addable at all?
        cur.execute(f"""
            SELECT count(*) FILTER (WHERE event_type IS NULL) AS null_event_type,
                   count(DISTINCT event_type) AS distinct_event_types,
                   count(*) AS rows
              FROM {TABLE}
        """)
        report["event_type_counts"] = dict(cur.fetchone())
        cur.execute(f"""
            SELECT DISTINCT event_type FROM {TABLE}
             WHERE event_type <> ALL(%(types)s) ORDER BY 1
        """, {"types": list(_audit_event_types())})
        report["out_of_domain_event_types"] = [r["event_type"] for r in cur.fetchall()]

        # F-12: the json-vs-jsonb trap.
        cur.execute("""
            SELECT column_name, data_type FROM information_schema.columns
             WHERE table_schema='public' AND table_name=%(t)s
               AND column_name IN ('payload','metadata','event_type','event_hash',
                                   'previous_hash','sequence_number')
             ORDER BY column_name
        """, {"t": TABLE})
        report["column_types"] = {r["column_name"]: r["data_type"] for r in cur.fetchall()}

        # F-1 / F-2 / F-14 baseline: what enforcement exists *right now*, read
        # from the catalog rather than by attempting a destructive statement.
        cur.execute("""
            SELECT tgname AS name, pg_get_triggerdef(oid) AS definition
              FROM pg_trigger WHERE tgrelid = CAST(%(t)s AS regclass)
               AND NOT tgisinternal ORDER BY 1
        """, {"t": TABLE})
        report["triggers"] = [dict(r) for r in cur.fetchall()]
        cur.execute("""
            SELECT rulename AS name, definition FROM pg_rules
             WHERE schemaname = 'public' AND tablename = %(t)s ORDER BY 1
        """, {"t": TABLE})
        report["rules"] = [dict(r) for r in cur.fetchall()]
        cur.execute("""
            SELECT polname AS name FROM pg_policy WHERE polrelid = CAST(%(t)s AS regclass)
        """, {"t": TABLE})
        report["policies"] = [dict(r) for r in cur.fetchall()]
        cur.execute("""
            SELECT conname AS name, pg_get_constraintdef(oid) AS definition
              FROM pg_constraint WHERE conrelid = CAST(%(t)s AS regclass) ORDER BY 1
        """, {"t": TABLE})
        report["constraints"] = [dict(r) for r in cur.fetchall()]
        cur.execute("""
            SELECT relrowsecurity, relforcerowsecurity FROM pg_class
             WHERE oid = CAST(%(t)s AS regclass)
        """, {"t": TABLE})
        report["row_security"] = dict(cur.fetchone())
        cur.execute("""
            SELECT current_user AS role,
                   has_table_privilege(current_user, CAST(%(t)s AS regclass), 'UPDATE') AS update_priv,
                   has_table_privilege(current_user, CAST(%(t)s AS regclass), 'DELETE') AS delete_priv,
                   pg_get_userbyid((SELECT relowner FROM pg_class
                                     WHERE oid = CAST(%(t)s AS regclass))) AS table_owner
        """, {"t": TABLE})
        report["privileges"] = dict(cur.fetchone())

        # The §10 register source.
        report["missing_ranges"] = missing_ranges(cur)
        report["missing_total"] = sum(r["count"] for r in report["missing_ranges"])
    conn.close()

    # The shipped verifier, over the full range and over a recent window. Full
    # range is O(rows) Python hash recomputes, so both durations get recorded
    # (§9.3 wants the cost stated, not assumed).
    engine = create_engine(url, pool_pre_ping=True)
    with Session(engine) as db:
        from backend.services.audit_ledger import verify_chain

        max_sequence = report["ledger"]["max_sequence"]
        for label, kwargs in (
            ("full_range", {}),
            ("window_last_500", {"from_sequence": max(1, max_sequence - 499)}),
            ("window_last_1", {"from_sequence": max_sequence}),
        ):
            started = time.perf_counter()
            verdict = verify_chain(db, **kwargs)
            report.setdefault("verify_chain", {})[label] = {
                "valid": verdict["valid"],
                "checked_events": verdict["checked_events"],
                "first_sequence": verdict["first_sequence"],
                "last_sequence": verdict["last_sequence"],
                "failure_count": len(verdict["failures"]),
                "failures_by_class": classify(verdict["failures"]),
                "first_failures": verdict["failures"][:8],
                "duration_seconds": round(time.perf_counter() - started, 3),
            }

        # F-14: enforcement objects are invisible to autogenerate, so the drift
        # comparison cannot protect them. Measure the current diff shape.
        from alembic.migration import MigrationContext
        from alembic.autogenerate import compare_metadata
        from backend.db.models import Base
        from backend.db.schema_drift_policy import include_object

        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"target_metadata": Base.metadata,
                            "include_object": include_object})
            entries = [str(e) for e in compare_metadata(ctx, Base.metadata)]
        report["drift"] = {"operations": len(entries),
                           "mentions_ledger": any(TABLE in e for e in entries),
                           "operation_details": [e[:160] for e in entries]}
    engine.dispose()

    print(json.dumps(report, indent=1, default=str))
    return 0


_DOMAIN_CACHE: dict | None = None


def _audit_event_types():
    global _DOMAIN_CACHE
    if _DOMAIN_CACHE is None:
        from backend.db.models import AUDIT_EVENT_TYPES
        _DOMAIN_CACHE = AUDIT_EVENT_TYPES
    return _DOMAIN_CACHE


if __name__ == "__main__":
    sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")
    raise SystemExit(main())
