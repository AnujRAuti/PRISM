"""BE-029 follow-up: prove which database a test or verification run is writing to.

The backend has exactly one database setting, and its default is the development
database. That default is correct for the application and dangerous for anything
that mutates: a scratch script that built ``TestClient(app)`` without setting
``DATABASE_URL`` inherited ``.env``, resolved to ``pofa_dev``, and wrote real rows
there. The rows were deleted afterwards; the append-only audit-ledger events they
emitted are permanent. A documented rule ("always set DATABASE_URL") did not
prevent that, because the rule had no enforcement point.

This module supplies the enforcement point. A process declares its context:

* unset                       -> normal application / worker / Alembic runtime.
                                 No guard, no behaviour change.
* ``pytest``                  -> the suite, armed by ``tests/conftest.py`` through
                                 ``backend.db.test_target``. The database name the
                                 server reports must equal the name the suite was
                                 given. A mismatch means the URL was ignored,
                                 overridden, or fell back to a default: writes stop.
* ``verification``            -> ad-hoc probes against a disposable database. The
                                 name must not be one of the long-lived databases.
                                 The target has to be passed explicitly; there is
                                 no default and no fallback.

Checking ``settings.database_url``'s text would not be enough: the point of the
guard is that the string you configured may not be the database you reach, so the
name is read from the server with ``SELECT current_database()`` at engine creation,
before any session exists to write with.
"""

from __future__ import annotations

import os
from sqlalchemy import text

from backend.db.test_target import _database_name_from_url

#: Environment variable naming the armed context. Absent means normal runtime.
CONTEXT_ENV = "POA_DATABASE_CONTEXT"

#: Environment variable naming the single database the armed context may use.
AUTHORIZED_NAME_ENV = "POA_AUTHORIZED_DATABASE_NAME"

CONTEXT_PYTEST = "pytest"
CONTEXT_VERIFICATION = "verification"

#: Long-lived databases. ``pofa_dev`` holds accumulated development state; ``pofa_test``
#: is the shared suite target, which ad-hoc probes must not mutate out from under a run.
PROTECTED_DATABASE_NAMES = frozenset({"pofa_dev", "pofa_test"})


class ProtectedDatabaseError(RuntimeError):
    """Raised when a write-capable run is not aimed at its authorised database."""

    __test__ = False


def _source(env: dict | None) -> dict:
    return os.environ if env is None else env


def current_context(env: dict | None = None) -> str | None:
    """The armed context name, or ``None`` for normal application runtime."""
    value = (_source(env).get(CONTEXT_ENV) or "").strip()
    return value or None


def authorized_database_name(env: dict | None = None) -> str | None:
    value = (_source(env).get(AUTHORIZED_NAME_ENV) or "").strip()
    return value or None


def database_name(database_url: str) -> str | None:
    """The database a URL names, or ``None`` when it does not name one.

    Public because ``alembic/env.py`` needs it in offline mode, where there is
    no connection to ask the server.
    """
    return _database_name_from_url(database_url or "")


def guard_url(database_url: str, context: str, env: dict | None = None) -> str:
    """Return the URL's database name, or refuse it for this context.

    Pure string logic: the server-side proof is ``confirm_server_database``. This
    exists so a wrong name is rejected before a connection is even attempted.
    """
    name = database_name(database_url)
    if name is None:
        raise ProtectedDatabaseError(
            f"Cannot determine a database name from the supplied URL in "
            f"{context!r} context; refusing to guess a write target."
        )
    if context == CONTEXT_VERIFICATION and name in PROTECTED_DATABASE_NAMES:
        raise ProtectedDatabaseError(
            f"Verification runs may not target {name!r}: it is a long-lived "
            f"database ({sorted(PROTECTED_DATABASE_NAMES)}). Create or reuse a "
            "disposable database and pass its URL explicitly."
        )
    if context == CONTEXT_PYTEST:
        expected = authorized_database_name(env)
        if expected and name != expected:
            raise ProtectedDatabaseError(
                f"Test context was armed for {expected!r} but the URL names "
                f"{name!r}; refusing to write to the wrong database."
            )
    return name


def server_database_name(bind) -> str:
    """Ask the server which database this engine is connected to."""
    with bind.connect() as conn:
        return conn.execute(text("SELECT current_database()")).scalar_one()


def confirm_server_database(bind, context: str, env: dict | None = None) -> str:
    """Prove the live connection matches the armed expectation, or fail closed."""
    actual = server_database_name(bind)
    if context == CONTEXT_PYTEST:
        expected = authorized_database_name(env)
        if expected and actual != expected:
            raise ProtectedDatabaseError(
                f"The suite was armed for database {expected!r} but the engine "
                f"is connected to {actual!r}. A settings fallback, an overriding "
                "environment variable, or a redirected URL is in play; refusing "
                "to run tests that would write there."
            )
    elif context == CONTEXT_VERIFICATION:
        if actual in PROTECTED_DATABASE_NAMES:
            raise ProtectedDatabaseError(
                f"Verification context resolved to protected database {actual!r}; "
                "refusing to run."
            )
    return actual


def arm_pytest(database_name: str, env: dict | None = None) -> str:
    """Declare this process a pytest run whose only write target is ``database_name``.

    Called from ``backend.db.test_target.apply_test_database_url``, which runs
    before any engine exists, so every later connection is checked against the
    name the suite was actually given rather than against whatever URL happened
    to be configured.
    """
    source = env if env is not None else os.environ
    source[CONTEXT_ENV] = CONTEXT_PYTEST
    source[AUTHORIZED_NAME_ENV] = database_name
    return database_name


def arm_verification(database_url: str) -> str:
    """Declare this process an ad-hoc verification run against one disposable database.

    Scratches, probes and one-off ``TestClient`` scripts call this before touching
    the application, and it takes the target as a required argument: an unset or
    unparseable URL is a refusal, not a fallback.
    """
    if not (database_url or "").strip():
        raise ProtectedDatabaseError(
            "arm_verification() requires an explicit database URL; there is no "
            "default, because defaulting is how development databases get written to."
        )
    name = guard_url(database_url, CONTEXT_VERIFICATION)
    os.environ[CONTEXT_ENV] = CONTEXT_VERIFICATION
    os.environ[AUTHORIZED_NAME_ENV] = name
    return name


def disarm() -> None:
    os.environ.pop(CONTEXT_ENV, None)
    os.environ.pop(AUTHORIZED_NAME_ENV, None)
