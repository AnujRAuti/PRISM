"""Read-only: would the BE-028 drift gate accept pofa_dev's post-migration state?

Uses the gate test's own machinery (include_object hook, signature(), compare())
so the answer is the same one pytest would give, just pointed at pofa_dev
instead of the test database.
"""
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from backend.db.models import Base
from backend.db.schema_drift_policy import include_object
from tests.schema_drift_baseline import compare, signature

URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"

engine = sa.create_engine(URL)
with engine.connect() as conn:
    print("current_database():", conn.execute(sa.text("SELECT current_database()")).scalar())
    print("alembic_version  :", conn.execute(
        sa.text("SELECT version_num FROM alembic_version")).scalars().all())
    ctx = MigrationContext.configure(
        conn, opts={"target_metadata": Base.metadata, "include_object": include_object})
    drift = [signature(entry) for entry in compare_metadata(ctx, Base.metadata)]

print(f"\noperations reported: {len(drift)}")
for sig in sorted(drift):
    print(f"  {sig}")

verdict = compare(drift)
print("\ngate verdict:", "CLEAN (all ops accepted)" if verdict.clean
      else f"NEW={verdict.new} RESOLVED={verdict.resolved}")
engine.dispose()
