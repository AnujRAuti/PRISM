"""BE-037 Phase B remediation, Stage 3 classification (READ-ONLY).

Explains tests/integration/test_be029_database_safety_guard.py::
test_verification_context_refuses_the_shared_test_database_over_a_real_connection,
which failed on this run's disposable target with "DID NOT RAISE".

The guard is a name check (backend/db/safety.py:128-134): the verification
context raises only when the connected database is one of
PROTECTED_DATABASE_NAMES. The test is written against the documented shared
target, whose name is protected; a uniquely named disposable database is, by
design, not. This probe calls the guard itself on both targets and prints the
outcome plus the unit-test surface that covers the same rule, so the
classification rests on the guard's actual behaviour rather than on reading it.

SELECT current_database() is the only statement issued.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

from backend.db import safety

print(f"PROTECTED_DATABASE_NAMES = {sorted(safety.PROTECTED_DATABASE_NAMES)}")
print(f"CONTEXT_VERIFICATION = {safety.CONTEXT_VERIFICATION!r}")

for label, url in (
    ("disposable target (this run)", os.environ["DISPOSABLE_URL"]),
    ("documented shared test database", os.environ["SHARED_TEST_URL"]),
):
    engine = create_engine(url)
    try:
        returned = safety.confirm_server_database(engine, safety.CONTEXT_VERIFICATION)
        print(f"\n{label}: guard returned {returned!r} (no refusal)")
    except safety.ProtectedDatabaseError as error:
        print(f"\n{label}: guard raised ProtectedDatabaseError -> {error}")
    finally:
        engine.dispose()
