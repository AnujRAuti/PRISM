"""BE-028 §12-§14: structured drift inventory (read-only, writes nothing).

Uses Alembic's own comparison engine but keeps the *typed* operations rather
than the flattened repr string, so every entry can be classified by the actual
object it touches (kind, table, name, columns, uniqueness, WHERE clause,
NULLS NOT DISTINCT). That signature is what the containment gate will compare
against its documented baseline.
"""
import sys

from alembic.autogenerate import produce_migrations
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")
from backend.db.models import Base
from backend.db.schema_drift_policy import include_object

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be028_scratch"
)

engine = create_engine(URL)


def signature(op):
    """Stable, comparable identity for one autogenerate operation."""
    kind = type(op).__name__
    parts = [kind]
    table = getattr(op, "table_name", None)
    if table:
        parts.append(f"table={table}")
    name = (
        getattr(op, "index_name", None)
        or getattr(op, "constraint_name", None)
        or getattr(op, "name", None)
    )
    if name:
        parts.append(f"name={name}")
    cols = getattr(op, "columns", None)
    if cols:
        parts.append("cols=[" + ",".join(getattr(c, "name", str(c)) for c in cols) + "]")
    if hasattr(op, "unique"):
        parts.append(f"unique={op.unique}")
    dialect_kwargs = getattr(op, "dialect_kwargs", {}) or {}
    pg = dialect_kwargs.get("postgresql", {}) or {}
    for key in ("postgresql_where", "where"):
        if pg.get(key) is not None:
            parts.append(f"where={pg[key]}")
            break
    if pg.get("postgresql_nulls_not_distinct") or getattr(op, "kw", {}).get(
        "postgresql_nulls_not_distinct"
    ):
        parts.append("nulls_not_distinct=True")
    if kind == "RemoveTable":
        parts.append(f"schema={getattr(op, 'schema', None)}")
    return " ".join(parts)


def flatten(step, table=None):
    """Yield leaf operations, carrying the table name from ModifyTableOps groups."""
    for op in getattr(step, "ops", []):
        if type(op).__name__ == "ModifyTableOps":
            yield from flatten(op, table=getattr(op, "table_name", table))
        else:
            yield op, getattr(op, "table_name", table)


with engine.connect() as conn:
    ctx = MigrationContext.configure(conn, opts={"include_object": include_object})
    migration = produce_migrations(ctx, Base.metadata)
    ops = list(flatten(migration.upgrade_ops))
    print(f"DATABASE {URL.rsplit('/',1)[-1]}")
    print(f"leaf operations produced by Alembic's comparison: {len(ops)}\n")
    for i, (op, table) in enumerate(ops, 1):
        sig = signature(op)
        if table and "table=" not in sig:
            sig += f" table={table}"
        print(f"{i:>2}. {sig}")

# The flattened view alembic check itself prints, for cross-reference.
from alembic.autogenerate import compare_metadata  # noqa: E402

with engine.connect() as conn:
    ctx = MigrationContext.configure(conn, opts={"include_object": include_object})
    flat = compare_metadata(ctx, Base.metadata)
    print(f"\nalembic-check-level entries: {len(flat)}")
engine.dispose()
