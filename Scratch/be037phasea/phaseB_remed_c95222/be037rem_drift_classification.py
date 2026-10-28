"""BE-037 Phase B remediation, Stage 3 classification (READ-ONLY).

The full integration suite on the disposable target reported three failures in
two files that measure the *environment*, not the analysis paths:

  * tests/integration/test_be029_database_safety_guard.py::
    test_verification_context_refuses_the_shared_test_database_over_a_real_connection
  * tests/integration/test_schema_drift_gate.py::
    test_drift_is_exactly_the_documented_baseline
    test_extension_owned_objects_are_excluded_not_suppressed

This probe answers, without writing anywhere:

  1. which database each target is actually on, and which extensions it has;
  2. what the safety guard's verification context really refuses;
  3. whether the drift gate's unexplained operations are the same set on the
     documented shared test database (pofa_test) as on this run's disposable
     database -- i.e. whether the diff is an image/extension artifact.

Only reflection and SELECTs are issued. No engine comes from
backend.db.session, so nothing can be armed as a write context.
"""

from __future__ import annotations

import os
import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

from backend.db.models import Base
from backend.db.schema_drift_policy import EXTENSION_OWNED_TABLES, include_object
from tests.schema_drift_baseline import ACCEPTED_SIGNATURES, compare, signature

DISPOSABLE = os.environ["DISPOSABLE_URL"]
SHARED = os.environ["SHARED_TEST_URL"]


def drift_signatures(connection) -> list[str]:
    ctx = MigrationContext.configure(
        connection,
        opts={"target_metadata": Base.metadata, "include_object": include_object},
    )
    return [signature(entry) for entry in compare_metadata(ctx, Base.metadata)]


def probe(label: str, url: str) -> None:
    engine = create_engine(url)
    print(f"\n=== {label} ===")
    with engine.connect() as connection:
        name = connection.execute(text("SELECT current_database()")).scalar()
        user = connection.execute(text("SELECT current_user")).scalar()
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().one_or_none()
        extensions = sorted(
            connection.execute(
                text("SELECT extname FROM pg_extension ORDER BY extname")
            ).scalars()
        )
        print(f"current_database={name} current_user={user}")
        print(f"alembic_version={version}")
        print(f"pg_extension={extensions}")
        print(f"spatial_ref_sys rows="
              f"{connection.execute(text('SELECT count(*) FROM spatial_ref_sys')).scalar()}")

        signatures = drift_signatures(connection)

    verdict = compare(signatures)
    print(f"total diff operations={len(signatures)}")
    print(f"unexplained (verdict.new)={len(verdict.new)}")
    for item in sorted(verdict.new):
        print(f"  NEW {item}")
    print(f"baseline entries no longer observed (verdict.resolved)="
          f"{len(verdict.resolved)}")
    for item in sorted(verdict.resolved):
        print(f"  RESOLVED {item}")
    print(f"remove_table entries="
          f"{[s for s in signatures if s.startswith('remove_table|')][:5]}"
          f" ... total={len([s for s in signatures if s.startswith('remove_table|')])}")
    engine.dispose()


print(f"EXTENSION_OWNED_TABLES (repo exclusion list) = {sorted(EXTENSION_OWNED_TABLES)}")
probe("disposable target (this run)", DISPOSABLE)
probe("documented shared test database", SHARED)
