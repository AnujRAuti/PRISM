"""BE-029 Phase C: the database write guard, proven against the live server.

The unit half (``tests/unit/test_database_safety.py``) checks the decision logic.
This half checks the thing a decision logic cannot fake: that the name comes
from ``SELECT current_database()`` on a real connection, that a mismatch raises
*before* an engine is handed to anything that could commit, and that Alembic
refuses a target its armed context forbids.

Requirement mapping from the master instruction:

* "A test must prove that the guard rejects an unsafe database target"
  -> the refusal tests below, one per layer: URL text, engine construction,
     session factory, live server name, and Alembic.
* "Another test must prove that normal isolated execution still works"
  -> ``test_armed_pytest_context_matches_the_live_connection`` and
  ``test_alembic_runs_and_states_the_authorized_database``.

Nothing here connects to ``pofa_dev``: refusal cases are expressed as URL text
that the guard rejects before opening a connection, or as a real connection to
this suite's own test database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.core.config import settings
from backend.db import safety
from backend.db.safety import (
    AUTHORIZED_NAME_ENV,
    CONTEXT_ENV,
    CONTEXT_PYTEST,
    CONTEXT_VERIFICATION,
    ProtectedDatabaseError,
    arm_pytest,
    authorized_database_name,
    current_context,
    server_database_name,
)
from backend.db.session import build_guarded_engine, get_engine
from backend.db import session as session_module
from backend.db.test_target import TEST_DATABASE_URL_ENV
from backend.observability.health import HealthStatus, PostgresHealthCheck
from sqlalchemy.exc import OperationalError

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent.parent

#: A URL naming the development database. The guard rejects it from the string,
#: so this test never dials it.
DEV_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"

#: A server that is not there. Used to prove the readiness probe really dials
#: the DSN it is given instead of reusing a pooled connection to somewhere else.
UNREACHABLE_URL = ("postgresql+psycopg2://postgres:postgres@127.0.0.1:1"
                   "/there_is_no_server")


def _authorized() -> str:
    name = authorized_database_name()
    assert name, "conftest must arm an authorised database name"
    return name


def test_the_suite_arms_the_pytest_context():
    assert current_context() == CONTEXT_PYTEST
    assert os.environ.get(CONTEXT_ENV) == CONTEXT_PYTEST
    assert os.environ.get(AUTHORIZED_NAME_ENV) == _authorized()


def test_armed_pytest_context_matches_the_live_connection():
    """Requirement 8: normal isolated execution still works, proved server-side."""
    engine = get_engine()
    actual = server_database_name(engine)
    assert actual == _authorized()
    assert safety.confirm_server_database(engine, CONTEXT_PYTEST) == actual
    # The published target and the URL the engine really used are the same
    # database; a settings fallback would show up as a mismatch here.
    configured = safety.database_name(os.environ[TEST_DATABASE_URL_ENV])
    assert configured == actual


def test_the_authorized_database_is_not_the_development_one():
    assert _authorized() != "pofa_dev"
    assert safety.database_name(os.environ["DATABASE_URL"]) == _authorized()


def test_guard_rejects_the_development_database_url_without_connecting():
    """Requirement 7: the exact URL that caused the accidental write."""
    env = {AUTHORIZED_NAME_ENV: _authorized()}
    with pytest.raises(ProtectedDatabaseError, match="refusing to write to the wrong database"):
        safety.guard_url(DEV_URL, CONTEXT_PYTEST, env)


def test_get_engine_refuses_a_url_that_names_another_database(monkeypatch):
    """The reachable accident, end to end: ``.env``/settings pointing at pofa_dev.

    ``guard_url`` rejects the name before ``create_engine`` is called, so this
    test proves the refusal without ever dialling the development database.
    """
    monkeypatch.setattr(session_module.settings, "database_url", DEV_URL)
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_SessionLocal", None)

    with pytest.raises(ProtectedDatabaseError, match="refusing to write to the wrong database"):
        session_module.get_engine()

    # A refused engine is not cached, so the next call cannot inherit a target
    # that was already rejected.
    assert session_module._engine is None
    assert session_module._SessionLocal is None


def test_no_session_exists_for_a_refused_target(monkeypatch):
    """Writes are impossible, not merely discouraged: the session factory raises first."""
    monkeypatch.setattr(session_module.settings, "database_url", DEV_URL)
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_SessionLocal", None)

    with pytest.raises(ProtectedDatabaseError):
        session_module.get_session()


def test_server_confirmation_refuses_when_the_live_name_contradicts_the_expectation():
    """Defence in depth, on a real connection.

    The URL layer can only judge the string it was given. This layer asks the
    server, which is what catches a URL that is technically the authorised name
    while the connection lands elsewhere (alias, pooler, redirect). The engine
    here really is on this suite's test database, and a planted expectation of
    ``pofa_dev`` is contradicted by the server's own answer.
    """
    env = {AUTHORIZED_NAME_ENV: "pofa_dev"}
    with pytest.raises(ProtectedDatabaseError, match=f"is connected to '{_authorized()}'"):
        safety.confirm_server_database(get_engine(), CONTEXT_PYTEST, env)


def test_verification_context_refuses_the_shared_test_database_over_a_real_connection():
    """A probe mislabelled as verification is stopped by the server's own answer."""
    with pytest.raises(ProtectedDatabaseError, match="protected database"):
        safety.confirm_server_database(get_engine(), CONTEXT_VERIFICATION)


def test_a_real_write_then_read_still_works_after_the_guard_is_active():
    """The guard must not cost the suite its normal database behaviour."""
    name = server_database_name(get_engine())
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT current_database()")).scalar_one() == name
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
        conn.execute(text("CREATE TEMP TABLE be029_guard_probe (x int) ON COMMIT DROP"))
        conn.execute(text("INSERT INTO be029_guard_probe VALUES (1)"))
        assert conn.execute(text("SELECT count(*) FROM be029_guard_probe")).scalar_one() == 1
        conn.rollback()


def _alembic(args: list[str], env_overrides: dict[str, str]):
    env = {**os.environ, **env_overrides}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_alembic_runs_and_states_the_authorized_database():
    """Requirement 5, positive half: migrations run against the named target and say so."""
    result = _alembic(["current"], {CONTEXT_ENV: CONTEXT_PYTEST,
                                    AUTHORIZED_NAME_ENV: _authorized()})
    assert result.returncode == 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert f"Alembic target database: {_authorized()}" in combined, combined


def test_alembic_refuses_a_target_its_armed_context_forbids():
    """Requirement 5, negative half: an armed Alembic cannot migrate any other database.

    ``pofa_wrong_target`` is not a database that exists; the point is that the
    armed expectation, not the URL in ``.env``, decides what Alembic may touch.
    """
    result = _alembic(["current"], {CONTEXT_ENV: CONTEXT_PYTEST,
                                    AUTHORIZED_NAME_ENV: "pofa_wrong_target"})
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "ProtectedDatabaseError" in combined, combined
    # Measured: env.py refuses on the configured name, so no connection is
    # opened and no DDL is emitted.
    assert "refusing to write to the wrong database" in combined, combined


def test_alembic_without_a_context_is_untouched():
    """Legitimate developer/production migration stays exactly as it was."""
    result = _alembic(["current"], {CONTEXT_ENV: "", AUTHORIZED_NAME_ENV: ""})
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Alembic target database: {_authorized()}" in result.stdout + result.stderr


def test_arm_pytest_is_the_only_writer_of_the_context_markers():
    """A probe cannot half-arm itself: both markers or neither."""
    env: dict = {}
    arm_pytest("pofa_be029_clone", env)
    assert env == {CONTEXT_ENV: CONTEXT_PYTEST, AUTHORIZED_NAME_ENV: "pofa_be029_clone"}


# -- the readiness probe goes through the same factory (defect found in Phase C)


def test_readiness_probes_the_configured_dsn_not_the_cached_engine(monkeypatch):
    """FOUND while arming the guard: the probe must observe live configuration.

    Routing ``PostgresHealthCheck`` through the cached ``get_engine()`` made it
    report HEALTHY whatever ``settings.database_url`` said, because the pool was
    already open to this suite's own database. That passed in isolation and only
    failed inside a full run, which is the worst shape a regression can have.

    Inside this armed suite the refusal then comes from the guard, not from
    psycopg2; ``test_unarmed_readiness_reaches_a_real_connection_refusal`` covers
    the genuine socket failure.
    """
    get_engine()  # open and cache the application engine first, as a real run does
    assert session_module._engine is not None

    monkeypatch.setattr(settings, "database_url", UNREACHABLE_URL)
    status, details = PostgresHealthCheck().check()
    assert status is HealthStatus.UNHEALTHY
    assert details["message"] == "PostgreSQL connection failed"


def test_armed_readiness_refuses_a_foreign_database_before_connecting():
    """The guard also covers the probe: an armed run cannot dial arbitrary hosts.

    Under an armed context the foreign DSN never reaches psycopg2 -- the
    configured name is rejected first. The client-visible answer is the same
    UNHEALTHY either way, so readiness cannot be used to probe around the guard.
    """
    assert current_context() == CONTEXT_PYTEST
    with pytest.raises(ProtectedDatabaseError, match="refusing to write"):
        build_guarded_engine(UNREACHABLE_URL)


def test_unarmed_readiness_reaches_a_real_connection_refusal(monkeypatch):
    """The production shape is unchanged: an unreachable DSN is a genuine failure.

    Unarming the context is what a deployed process does, so this is the case
    BE-027's shipped test describes ("psycopg2 must really fail to connect").
    ``build_guarded_engine`` is lazy -- it only connects when asked to confirm an
    armed context -- so the refusal is observed where a real caller would meet
    it: on the first connection.
    """
    monkeypatch.setenv(CONTEXT_ENV, "")
    monkeypatch.setenv(AUTHORIZED_NAME_ENV, "")
    assert current_context() is None

    engine = build_guarded_engine(UNREACHABLE_URL)
    try:
        with pytest.raises(OperationalError) as refused:
            engine.connect()
    finally:
        engine.dispose()
    assert "connection refused" in str(refused.value).lower(), str(refused.value)

    monkeypatch.setattr(settings, "database_url", UNREACHABLE_URL)
    status, details = PostgresHealthCheck().check()
    assert status is HealthStatus.UNHEALTHY
    assert details["message"] == "PostgreSQL connection failed"
