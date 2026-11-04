"""BE-029: unit tests for the database write guard (backend.db.safety).

These cover the *decision* logic with injected environments and a stub bind,
because a unit test cannot reach the databases the guard refuses. The server
half — a real ``SELECT current_database()`` against the real engine — is proven
in ``tests/integration/test_be029_database_safety_guard.py``.

The failure these tests exist to prevent is real, not hypothetical: a scratch
script built ``TestClient(app)`` without setting ``DATABASE_URL``, inherited
``.env``, resolved to ``pofa_dev``, and wrote rows there. Documentation said
"always set DATABASE_URL"; nothing enforced it.
"""

from __future__ import annotations

import pytest

from backend.db import safety
from backend.db.safety import (
    AUTHORIZED_NAME_ENV,
    CONTEXT_ENV,
    CONTEXT_PYTEST,
    CONTEXT_VERIFICATION,
    PROTECTED_DATABASE_NAMES,
    ProtectedDatabaseError,
    arm_pytest,
    arm_verification,
    authorized_database_name,
    current_context,
    disarm,
    guard_url,
)
from backend.db.test_target import (
    TEST_DATABASE_URL_ENV,
    TestDatabaseConfigurationError,
    apply_test_database_url,
)

DEV_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"
TEST_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
SCRATCH_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be029_scratch"


class _StubResult:
    def __init__(self, name: str):
        self._name = name

    def scalar_one(self):
        return self._name


class _StubConnection:
    def __init__(self, name: str):
        self._name = name

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _statement):
        return _StubResult(self._name)


class _StubBind:
    """Anything with ``connect()`` answering ``SELECT current_database()``."""

    def __init__(self, name: str):
        self._name = name
        self.connects = 0

    def connect(self):
        self.connects += 1
        return _StubConnection(self._name)


# ---------------------------------------------------------------------------
# The unarmed default must stay untouched
# ---------------------------------------------------------------------------


def test_no_context_means_normal_runtime_and_no_opinion():
    """Requirement: the guard must not break legitimate application startup.

    ``backend.db.session.get_engine`` calls the guard only when
    ``current_context()`` is non-``None``, so an empty environment has to
    resolve to "normal runtime" and skip both checks: the guard is a promise
    made by a test or probe run, not a global policy on database names.
    """
    assert current_context({}) is None
    assert authorized_database_name({}) is None


def test_blank_context_marker_is_not_a_context():
    assert current_context({CONTEXT_ENV: "   "}) is None


# ---------------------------------------------------------------------------
# pytest context: the URL must name the authorised database
# ---------------------------------------------------------------------------


def test_pytest_context_accepts_the_authorized_database():
    env = {AUTHORIZED_NAME_ENV: "pofa_test"}
    assert guard_url(TEST_URL, CONTEXT_PYTEST, env) == "pofa_test"


def test_pytest_context_refuses_a_url_naming_a_different_database():
    """The exact accident that happened: configuration pointed somewhere else."""
    env = {AUTHORIZED_NAME_ENV: "pofa_test"}
    with pytest.raises(ProtectedDatabaseError, match="refusing to write to the wrong database"):
        guard_url(DEV_URL, CONTEXT_PYTEST, env)


def test_pytest_context_refuses_an_unparseable_url():
    env = {AUTHORIZED_NAME_ENV: "pofa_test"}
    with pytest.raises(ProtectedDatabaseError, match="refusing to guess a write target"):
        guard_url("not-a-dsn", CONTEXT_PYTEST, env)
    with pytest.raises(ProtectedDatabaseError, match="refusing to guess a write target"):
        guard_url("", CONTEXT_PYTEST, env)


def test_pytest_context_without_an_authorized_name_still_resolves():
    # A missing expectation must not invent one; the server-side check is the
    # one that has teeth here.
    assert guard_url(TEST_URL, CONTEXT_PYTEST, {}) == "pofa_test"


# ---------------------------------------------------------------------------
# verification context: probes may only name a disposable database
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("protected_url", [DEV_URL, TEST_URL])
def test_verification_context_refuses_long_lived_databases(protected_url):
    name = protected_url.rsplit("/", 1)[1]
    assert name in PROTECTED_DATABASE_NAMES
    with pytest.raises(ProtectedDatabaseError, match="long-lived"):
        guard_url(protected_url, CONTEXT_VERIFICATION)


def test_verification_context_accepts_a_disposable_database():
    assert guard_url(SCRATCH_URL, CONTEXT_VERIFICATION) == "pofa_be029_scratch"


def test_arm_verification_requires_an_explicit_url():
    """No default, no fallback: defaulting is how development databases get written to."""
    before = current_context()
    for bad in ("", "   ", None):
        with pytest.raises(ProtectedDatabaseError, match="requires an explicit database URL"):
            arm_verification(bad)
    assert current_context() == before, "a refused arm must not re-arm the process"


def test_arm_verification_publishes_the_context_and_refuses_protected_targets(monkeypatch):
    monkeypatch.delenv(CONTEXT_ENV, raising=False)
    monkeypatch.delenv(AUTHORIZED_NAME_ENV, raising=False)

    with pytest.raises(ProtectedDatabaseError, match="long-lived"):
        arm_verification(DEV_URL)
    assert current_context() is None, "a refused arm must leave no half-armed context"

    assert arm_verification(SCRATCH_URL) == "pofa_be029_scratch"
    assert current_context() == CONTEXT_VERIFICATION
    assert authorized_database_name() == "pofa_be029_scratch"

    disarm()
    assert current_context() is None
    assert authorized_database_name() is None


def test_arm_pytest_writes_both_markers_into_the_supplied_env():
    env: dict = {}
    assert arm_pytest("pofa_test", env) == "pofa_test"
    assert env[CONTEXT_ENV] == CONTEXT_PYTEST
    assert env[AUTHORIZED_NAME_ENV] == "pofa_test"


def test_apply_test_database_url_arms_the_guard():
    """The conftest path: resolving the target and arming the guard are one step."""
    env = {TEST_DATABASE_URL_ENV: TEST_URL}
    target = apply_test_database_url(env)
    assert target.database_name == "pofa_test"
    assert env[CONTEXT_ENV] == CONTEXT_PYTEST
    assert env[AUTHORIZED_NAME_ENV] == "pofa_test"
    assert guard_url(env["DATABASE_URL"], CONTEXT_PYTEST, env) == "pofa_test"


def test_apply_test_database_url_never_arms_for_the_development_database():
    with pytest.raises(TestDatabaseConfigurationError, match="pofa_dev"):
        apply_test_database_url({TEST_DATABASE_URL_ENV: DEV_URL})


# ---------------------------------------------------------------------------
# Server-side confirmation (unit half: the comparison, with a stub bind)
# ---------------------------------------------------------------------------


def test_confirm_accepts_the_matching_server_name():
    bind = _StubBind("pofa_test")
    env = {AUTHORIZED_NAME_ENV: "pofa_test"}
    assert safety.confirm_server_database(bind, CONTEXT_PYTEST, env) == "pofa_test"


def test_confirm_rejects_when_the_server_disagrees_with_the_armed_name():
    """A URL that lies (redirect, pool alias, overridden setting) is caught here."""
    bind = _StubBind("pofa_dev")
    env = {AUTHORIZED_NAME_ENV: "pofa_test"}
    with pytest.raises(ProtectedDatabaseError, match="connected to 'pofa_dev'"):
        safety.confirm_server_database(bind, CONTEXT_PYTEST, env)
    assert bind.connects == 1, "the proof must cost exactly one connection"


def test_confirm_rejects_a_protected_database_in_verification_context():
    for name in sorted(PROTECTED_DATABASE_NAMES):
        with pytest.raises(ProtectedDatabaseError, match="protected database"):
            safety.confirm_server_database(_StubBind(name), CONTEXT_VERIFICATION)


def test_confirm_passes_a_disposable_database_in_verification_context():
    bind = _StubBind("pofa_be029_scratch")
    assert safety.confirm_server_database(bind, CONTEXT_VERIFICATION) == "pofa_be029_scratch"


def test_protected_names_cover_both_long_lived_databases():
    assert {"pofa_dev", "pofa_test"} <= PROTECTED_DATABASE_NAMES


def test_error_type_is_not_collected_as_a_test():
    assert ProtectedDatabaseError.__test__ is False
