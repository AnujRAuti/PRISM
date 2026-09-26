"""Explicit test-database resolution (BE-023 §2).

The PoA backend has exactly one database setting, ``settings.database_url``,
which the running application, Alembic and the test suite all share. That
sharing is what allowed a contaminated development database to be used as
the verification target: nothing forced the suite to say which database it
was talking to.

This module introduces a *separate*, explicit test target. Design rules,
in priority order:

1. ``TEST_DATABASE_URL`` is the ONLY supported way to select the database
   the test suite runs against.
2. If it is unset the suite must fail loudly with an actionable message.
   It must NEVER fall back to ``DATABASE_URL``/``pofa_dev``: a silent
   fallback is precisely the failure mode BE-023 exists to eliminate.
3. Refusing to run is correct behaviour, not an error to be worked around.

This module deliberately imports nothing from ``backend.db.session`` or
``backend.core.config``'s engine machinery, because it has to run *before*
``settings.database_url`` is ever used to build an engine. Importing
``settings`` here would defeat the isolation it exists to provide.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Environment variable naming the database the test suite may use.
TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"

#: Refusal to connect to these. ``pofa_dev`` is the documented development
#: database; running the suite against it is how historical audit
#: contamination happened, so it is blocked outright rather than warned
#: about.
_BLOCKED_DATABASE_NAMES = frozenset({"pofa_dev"})

_MISSING_MESSAGE = f"""
================================================================================
TEST DATABASE NOT CONFIGURED
================================================================================

The test suite will not run without an explicit test database.

Set the {TEST_DATABASE_URL_ENV} environment variable to a database that
integration tests may freely mutate:

    PowerShell:
        $env:{TEST_DATABASE_URL_ENV} = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"

    bash:
        export {TEST_DATABASE_URL_ENV}="postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"

Create it once, then build the schema:

    psql -U postgres -h localhost -c "CREATE DATABASE pofa_test;"
    psql -U postgres -h localhost -d pofa_test -c "CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS vector;"
    $env:{TEST_DATABASE_URL_ENV}="postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
    python -m alembic upgrade head

Why this is fatal rather than a warning
---------------------------------------
The suite deliberately refuses to fall back to DATABASE_URL. Integration
tests create and delete rows, and the audit ledger is append-only: a
suite run against the development database can permanently corrupt real
audit history. A passing test against an unintended database is not a
passing test (BE-023, "FINAL AGENT RULE").
================================================================================
"""


class TestDatabaseConfigurationError(RuntimeError):
    """Raised when the test database is unset, unsafe, or unusable."""

    # Pytest collects any imported class whose name starts with ``Test``.
    # This exception matches that pattern by accident, so pytest emitted a
    # PytestCollectionWarning about it in every module that imports it.
    # ``__test__ = False`` is the documented, purely declarative way to tell
    # pytest "this is not a test class". It changes no behaviour: the class
    # still raises exactly as before, and it is still caught by type in
    # tests/conftest.py and the unit tests.
    __test__ = False


@dataclass(frozen=True)
class TestDatabaseTarget:
    """The resolved, validated target for a test run."""

    url: str
    database_name: str
    source: str

    def describe(self) -> str:
        """Human-readable one-liner for logs and verification reports."""
        return f"{self.database_name} (from {self.source})"


def _database_name_from_url(url: str) -> str | None:
    """Best-effort database name extraction from a SQLAlchemy URL.

    Returns ``None`` when the name cannot be determined, so callers can
    treat an unparseable URL as a configuration error rather than
    silently accepting it.
    """
    if not url or "://" not in url:
        return None
    tail = url.split("://", 1)[1]
    # Strip any query/fragment, then take the path segment.
    for sep in ("?", "#"):
        if sep in tail:
            tail = tail.split(sep, 1)[0]
    if "/" not in tail:
        return None
    name = tail.rsplit("/", 1)[1]
    return name or None


def resolve_test_database_url(env: dict | None = None) -> TestDatabaseTarget:
    """Resolve and validate the test database target.

    Raises ``TestDatabaseConfigurationError`` with an actionable message
    when ``TEST_DATABASE_URL`` is absent, blank, unparseable, or points at
    a database reserved for development.
    """
    source = env if env is not None else os.environ
    raw = (source.get(TEST_DATABASE_URL_ENV) or "").strip()

    if not raw:
        raise TestDatabaseConfigurationError(_MISSING_MESSAGE.strip())

    if "://" not in raw:
        raise TestDatabaseConfigurationError(
            f"{TEST_DATABASE_URL_ENV} is not a valid database URL: {raw!r}\n"
            "Expected something like "
            '"postgresql+psycopg2://user:pass@localhost:5432/pofa_test".'
        )

    name = _database_name_from_url(raw)
    if not name:
        raise TestDatabaseConfigurationError(
            f"Could not determine a database name from {TEST_DATABASE_URL_ENV}={raw!r}.\n"
            "The URL must include the database name as its final path segment, "
            'e.g. "postgresql+psycopg2://user:pass@localhost:5432/pofa_test".'
        )

    if name in _BLOCKED_DATABASE_NAMES:
        raise TestDatabaseConfigurationError(
            f"{TEST_DATABASE_URL_ENV} points at {name!r}, which is reserved for "
            "development use.\n"
            "Integration tests mutate and delete data, and the audit ledger is "
            "append-only, so running them here risks permanently corrupting real "
            "audit history.\n"
            'Choose a dedicated test database, e.g. ".../pofa_test".'
        )

    return TestDatabaseTarget(url=raw, database_name=name, source=TEST_DATABASE_URL_ENV)


def apply_test_database_url(env: dict | None = None) -> TestDatabaseTarget:
    """Validate the test target and publish it as ``DATABASE_URL``.

    Called from ``tests/conftest.py`` *before* ``backend.db.session`` is
    imported, so the engine is constructed against the test database while
    leaving the developer's real ``DATABASE_URL`` untouched for every
    other process on the machine.

    The original ``DATABASE_URL`` is stashed under
    ``POA_ORIGINAL_DATABASE_URL`` for diagnostics and never used for
    connections during the test run.
    """
    target = resolve_test_database_url(env)
    source = env if env is not None else os.environ

    # Preserve the developer's real DATABASE_URL for diagnostics only. It is
    # never used for connections while the suite runs.
    original = source.get("DATABASE_URL")
    if original:
        source.setdefault("POA_ORIGINAL_DATABASE_URL", original)

    source["DATABASE_URL"] = target.url
    source["POA_TEST_DATABASE_URL"] = target.url
    return target
