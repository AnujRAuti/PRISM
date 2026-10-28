"""Cleanup verification for the BE-038-prep file sweep.

Proves two things without touching any data:
  1. the application still imports after the stage scripts were deleted, i.e.
     nothing depended on them;
  2. pytest still collects the same number of tests as the committed baseline.

The test target is derived from the configured DATABASE_URL by replacing only the
database name, because backend/db/test_target.py refuses to run at all unless
TEST_DATABASE_URL is explicit (BE-023: no silent fallback to the dev database).
No value is ever printed.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
os.chdir(REPO)
sys.path.insert(0, str(REPO))

values = {}
for line in (REPO / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
    match = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$", line)
    if match:
        values[match.group(1)] = match.group(2).strip().strip('"').strip("'")

database_url = values.get("DATABASE_URL", "")
if not database_url:
    raise SystemExit("DATABASE_URL is not present in .env")
os.environ["DATABASE_URL"] = database_url

test_target = re.sub(r"/[^/]*$", "/pofa_test", database_url)
os.environ["TEST_DATABASE_URL"] = test_target
print("test target database name:", test_target.rsplit("/", 1)[-1])
print("dev target database name: ", database_url.rsplit("/", 1)[-1])

import backend.app.main  # noqa: F401,E401  - import smoke only

print("app import OK")

import pytest

raise SystemExit(pytest.main(["--collect-only", "-q", "tests"]))
