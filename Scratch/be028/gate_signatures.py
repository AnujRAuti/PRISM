"""Print the exact signature strings the BE-028 gate compares, for one database.

Same code path as tests/integration/test_schema_drift_gate.py:compare_drift, so
the output is directly comparable with tests/schema_drift_baseline.py.
Read-only.
"""
import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

REPO = r"D:\CODING\Projects\Proof-Of-Action-Final"
sys.path.insert(0, REPO)

from backend.db.models import Base                          # noqa: E402
from backend.db.schema_drift_policy import include_object    # noqa: E402
from tests.schema_drift_baseline import signature            # noqa: E402

URL = sys.argv[1]
engine = create_engine(URL)
with engine.connect() as conn:
    version = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().one_or_none()
    ctx = MigrationContext.configure(
        conn, opts={"target_metadata": Base.metadata, "include_object": include_object})
    entries = compare_metadata(ctx, Base.metadata)
print(f"DATABASE   {URL.rsplit('/', 1)[-1]}")
print(f"SCHEMA     at {version}")
print(f"ENTRIES    {len(entries)}")
for s in sorted(signature(e) for e in entries):
    print(f"  {s}")
engine.dispose()
