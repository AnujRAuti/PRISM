"""Proof that the BE-030 §15 filter does NOT reach the drift gate.

Reproduces tests/integration/test_schema_drift_gate.py::collect_drift exactly
(compare_metadata with only target_metadata + include_object in opts -- no
process_revision_directives), against pofa_dev read-only, and runs the result
through the untouched baseline comparator.
"""

import sys

sys.path.insert(0, r"D:/CODING/Projects/Proof-Of-Action-Final")

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from backend.db.models import Base
from backend.db.schema_drift_policy import include_object
from backend.db.session import get_engine
from tests.schema_drift_baseline import ACCEPTED_SIGNATURES, compare, signature

engine = get_engine()
with engine.connect() as conn:
    ctx = MigrationContext.configure(
        conn,
        opts={"target_metadata": Base.metadata, "include_object": include_object},
    )
    entries = compare_metadata(ctx, Base.metadata)
    print("database:", conn.exec_driver_sql("select current_database()").scalar())
    print("at alembic revision:", conn.exec_driver_sql(
        "select version_num from alembic_version"
    ).scalars().all())

sigs = [signature(e) for e in entries]
print("\ncompare_metadata() signatures the GATE would collect (%d):" % len(sigs))
for s in sigs:
    print("   ", s)

verdict = compare(sigs)
print("\nbaseline ACCEPTED_SIGNATURES:")
for s in sorted(ACCEPTED_SIGNATURES):
    print("   ", s)
print("\ngate verdict -> new=%s resolved=%s clean=%s"
      % (verdict.new, verdict.resolved, verdict.clean))

assert "remove_constraint|user_role_assignments|uq_user_role_scoped" in sigs
assert "add_constraint|user_role_assignments|uq_user_role_scoped" in sigs
assert verdict.clean, "the gate must still see the pair as documented baseline drift"
print(
    "\nPASS: the drift gate path still emits AND still records both halves of the "
    "pair;\n      process_revision_directives is not consulted by compare_metadata()."
)
