"""Phase H: measure the drift-gate / ``alembic check`` divergence for real.

The custom gate says CLEAN; upstream ``alembic check`` says FAILED. Both are
reported here separately, and the difference is attributed to a specific layer
by reading the catalog, SQLAlchemy's reflection output and Alembic's own
comparison in the same session:

* ``pg_constraint`` says what the database actually enforces.
* ``sa.inspect().get_unique_constraints()`` says what SQLAlchemy hands to
  Alembic.
* ``compare_metadata()`` says what Alembic proposes.

Read-only: every connection sets ``readonly=True`` so a measurement can never
change a protected database. Targets are the isolated test database and the
disposable post-migration clone of dev data -- never live ``pofa_dev``.

Usage:
    python phase_h_drift.py <url> [<url> ...]
"""
import json
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from backend.db.models import Base
from backend.db.schema_drift_policy import include_object
from tests.schema_drift_baseline import compare, signature

OUT = "D:/CODING/Scratch/be029/phase_h_drift.json"

TABLE = "user_role_assignments"
CONSTRAINT = "uq_user_role_scoped"
COLUMNS = ["user_id", "role_id", "scope_type", "organization_id",
           "organizational_unit_id", "project_id"]

# The semantics the flag encodes, expressed as SQL so the *data* consequence is
# measured too: a group violates the constraint only when NULLs compare equal.
DUPLICATE_SQL = f"""
SELECT count(*) FROM (
    SELECT {", ".join("c." + c for c in COLUMNS)},
           count(*) AS n,
           bool_or(c.organization_id IS NULL
                   OR c.organizational_unit_id IS NULL
                   OR c.project_id IS NULL) AS has_null
    FROM {TABLE} AS c
    GROUP BY {", ".join("c." + c for c in COLUMNS)}
    HAVING count(*) > 1
) AS groups
WHERE has_null
"""

NULL_FREE_DUPLICATES_SQL = f"""
SELECT count(*) FROM (
    SELECT {", ".join("c." + c for c in COLUMNS)}, count(*) AS n
    FROM {TABLE} AS c
    GROUP BY {", ".join("c." + c for c in COLUMNS)}
    HAVING count(*) > 1
) AS groups
"""


def dsn(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://")


def measure(url: str) -> dict:
    engine = sa.create_engine(dsn(url))
    result: dict = {"url_table": url.rsplit("/", 1)[-1]}
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            result["current_database"] = conn.execute(
                sa.text("SELECT current_database()")).scalar()
            result["server_version"] = conn.execute(
                sa.text("SHOW server_version")).scalar()
            result["alembic_version"] = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalars().all()

            # PG 15 records nulls-not-distinct on the backing index, not on
            # pg_constraint, so read both sides: the rendered definition (what
            # the gate test asserts) and the catalog flag (what SQLAlchemy
            # would have to reflect).
            row = conn.execute(sa.text(
                "SELECT pg_get_constraintdef(k.oid) AS def, "
                "       k.contype AS contype, "
                "       i.indnullsnotdistinct AS index_flag "
                "FROM pg_constraint AS k "
                "JOIN pg_index AS i ON i.indexrelid = k.conindid "
                "WHERE k.conrelid = CAST(:t AS regclass) AND k.conname = :c"),
                {"t": TABLE, "c": CONSTRAINT}).mappings().one_or_none()
            result["catalog"] = dict(row) if row else None

            insp = sa.inspect(conn)
            uniques = [u for u in insp.get_unique_constraints(TABLE)
                       if u["name"] == CONSTRAINT]
            result["sqlalchemy_reflection"] = uniques
            result["flag_from_reflection"] = bool(
                uniques and uniques[0].get("dialect_options", {}).get(
                    "postgresql_nulls_not_distinct"))

            model_constraint = next(
                (c for c in Base.metadata.tables[TABLE].constraints
                 if c.name == CONSTRAINT), None)
            result["model_declares_flag"] = bool(
                model_constraint is not None
                and model_constraint.dialect_kwargs.get(
                    "postgresql_nulls_not_distinct"))

            ctx = MigrationContext.configure(
                conn, opts={"target_metadata": Base.metadata,
                            "include_object": include_object})
            entries = compare_metadata(ctx, Base.metadata)
            result["alembic_operations"] = [str(entry) for entry in entries]
            result["gate_signatures"] = sorted(signature(e) for e in entries)
            verdict = compare(result["gate_signatures"])
            result["gate_verdict"] = ("CLEAN" if verdict.clean
                                      else f"NEW={list(verdict.new)} "
                                           f"RESOLVED={list(verdict.resolved)}")

            result["rows"] = conn.execute(
                sa.text(f"SELECT count(*) FROM {TABLE}")).scalar()
            result["null_dependent_duplicate_groups"] = conn.execute(
                sa.text(DUPLICATE_SQL)).scalar()
            result["null_free_duplicate_groups"] = conn.execute(
                sa.text(NULL_FREE_DUPLICATES_SQL)).scalar()
    finally:
        engine.dispose()
    return result


def main() -> int:
    urls = sys.argv[1:] or [
        "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test",
    ]
    reports = [measure(url) for url in urls]
    for report in reports:
        print(json.dumps(report, indent=2, default=str))
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, indent=2, default=str)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
