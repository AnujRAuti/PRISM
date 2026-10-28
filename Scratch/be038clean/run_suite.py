"""Full-suite verification after the cleanup pass (safe deletes + OpenAPI refresh).

Same target derivation as verify_cleanup.py: TEST_DATABASE_URL is taken from the
configured DATABASE_URL with only the database name replaced, so the suite runs
on pofa_test and never on the dev database. No credential value is printed.
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
os.environ["TEST_DATABASE_URL"] = re.sub(r"/[^/]*$", "/pofa_test", database_url)
print("test target database name:", os.environ["TEST_DATABASE_URL"].rsplit("/", 1)[-1])

import pytest

raise SystemExit(pytest.main(["-q", "tests"]))
