"""Isolate the uq_user_role_scoped drift pair: toggle ONLY the flag, keep
everything else identical (the real Base.metadata against the real schema)."""
import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, UniqueConstraint

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")
from backend.db.models import Base
from backend.db.schema_drift_policy import include_object

URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be028_scratch"
engine = create_engine(URL)

TABLE = "user_role_assignments"
NAME = "uq_user_role_scoped"


def ops_for(table_name):
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"include_object": include_object, "target_metadata": Base.metadata}
        )
        diffs = compare_metadata(ctx, Base.metadata)
    out = []
    for d in diffs:
        if not isinstance(d, (tuple, list)):
            continue
        kind = d[0]
        obj = d[1] if len(d) > 1 else None
        tname = getattr(obj, "table", None)
        tname = getattr(tname, "name", None) if tname is not None else None
        if tname == table_name:
            flag = None
            if obj is not None:
                flag = getattr(getattr(obj, "dialect_kwargs", {}), "get", lambda *_: None)(
                    "postgresql_nulls_not_distinct"
                )
            out.append((kind, getattr(obj, "name", None), flag))
    return out


print("A) model as committed (postgresql_nulls_not_distinct=True):")
for row in ops_for(TABLE):
    print("   ", row)

uc = next(
    c for c in Base.metadata.tables[TABLE].constraints
    if isinstance(c, UniqueConstraint) and c.name == NAME
)
saved = dict(uc.dialect_kwargs)
uc.dialect_kwargs.pop("postgresql_nulls_not_distinct", None)

print("B) same metadata with the flag removed (plain UNIQUE):")
for row in ops_for(TABLE):
    print("   ", row)

uc.dialect_kwargs.update(saved)
print("C) flag restored:")
for row in ops_for(TABLE):
    print("   ", row)
engine.dispose()
