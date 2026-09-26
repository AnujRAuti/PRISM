"""Pytest bootstrap: pin the suite to an explicit test database (BE-023 §2/§3).

This module is imported by pytest before any test module. That ordering is
load-bearing and must not be "tidied up": ``backend.db.session`` builds its
engine from ``settings.database_url`` at first use, and ``settings`` is a
module-level singleton created on first import. To make the suite run
against the test database, ``TEST_DATABASE_URL`` has to be published as
``DATABASE_URL`` *before* anything imports ``backend.core.config``.

If ``TEST_DATABASE_URL`` is absent, the suite refuses to run. It never
falls back to the development database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the repository root importable so `backend` and `tests` resolve
# without a manually-set PYTHONPATH. Mirrors `pythonpath = .` in pytest.ini.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.test_target import (  # noqa: E402
    TestDatabaseConfigurationError,
    apply_test_database_url,
)

# Resolve and publish the test target before any engine is constructed.
# A configuration error here is raised during collection and reported as a
# hard error, which is the intended outcome: better a loud refusal than a
# suite that silently verifies the wrong database.
try:
    _TEST_TARGET = apply_test_database_url(os.environ)
except TestDatabaseConfigurationError as exc:  # pragma: no cover
    raise TestDatabaseConfigurationError(str(exc)) from exc


def pytest_report_header(config) -> list[str]:
    """State the exact database and dependency state under test.

    BE-023 §3/§8/§9/§13: a verification run must never leave the operator
    guessing what was actually exercised. The ML state in particular is
    reported explicitly so a green run cannot be mistaken for "ML was
    verified" when it was in fact unavailable.
    """
    from tests.preflight import classify_ml

    lines = [
        f"PoA test database: {_TEST_TARGET.database_name}",
        f"PoA test database source: {_TEST_TARGET.source}",
    ]
    # Detection uses find_spec, so this is cheap and does not import torch.
    lines.append(classify_ml().describe())
    return lines


def pytest_configure(config) -> None:
    """Register BE-023 markers so ``-m`` selection works and never errors."""
    config.addinivalue_line(
        "markers",
        "be023: BE-023 verification-hardening tests",
    )
    config.addinivalue_line(
        "markers",
        "integration: requires the explicit test database and live dependencies",
    )
