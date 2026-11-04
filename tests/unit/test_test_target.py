"""Unit tests for the explicit test-database resolver (BE-023 §2).

These tests are deliberately free of any database connection: they verify
the *configuration contract*, which is what prevents the suite from
silently running against the wrong database.
"""

from __future__ import annotations

import pytest

from backend.db.test_target import (
    TEST_DATABASE_URL_ENV,
    TestDatabaseConfigurationError,
    apply_test_database_url,
    resolve_test_database_url,
)

GOOD = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"

# BE-023 §2: selectable with `-m be023`. Module level so no individual test
# signature or behaviour is altered.
pytestmark = pytest.mark.be023


def test_missing_test_database_url_fails_loudly():
    """Unset TEST_DATABASE_URL must raise, never fall back to DATABASE_URL."""
    env = {"DATABASE_URL": "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"}
    with pytest.raises(TestDatabaseConfigurationError) as excinfo:
        resolve_test_database_url(env)
    message = str(excinfo.value)
    # The message must be actionable: name the variable and show the shape.
    assert TEST_DATABASE_URL_ENV in message
    assert "pofa_test" in message


def test_blank_test_database_url_fails_loudly():
    for blank in ("", "   ", "\t"):
        with pytest.raises(TestDatabaseConfigurationError):
            resolve_test_database_url({TEST_DATABASE_URL_ENV: blank})


def test_development_database_is_refused():
    """pofa_dev is reserved; running the suite there risks corrupting history."""
    env = {TEST_DATABASE_URL_ENV: "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"}
    with pytest.raises(TestDatabaseConfigurationError) as excinfo:
        resolve_test_database_url(env)
    assert "pofa_dev" in str(excinfo.value)


def test_malformed_url_fails_loudly():
    with pytest.raises(TestDatabaseConfigurationError):
        resolve_test_database_url({TEST_DATABASE_URL_ENV: "not-a-url"})


def test_url_without_database_name_fails_loudly():
    with pytest.raises(TestDatabaseConfigurationError) as excinfo:
        resolve_test_database_url({TEST_DATABASE_URL_ENV: "postgresql+psycopg2://host:5432"})
    assert "database name" in str(excinfo.value).lower()


def test_valid_url_resolves_with_database_name():
    target = resolve_test_database_url({TEST_DATABASE_URL_ENV: GOOD})
    assert target.database_name == "pofa_test"
    assert target.url == GOOD
    assert target.source == TEST_DATABASE_URL_ENV
    assert "pofa_test" in target.describe()


def test_database_name_parsing_handles_query_and_fragment():
    url = "postgresql+psycopg2://u:p@host:5432/pofa_test?sslmode=require"
    assert resolve_test_database_url({TEST_DATABASE_URL_ENV: url}).database_name == "pofa_test"


def test_apply_publishes_test_url_and_preserves_original():
    """The developer's DATABASE_URL is stashed, not destroyed, and never used."""
    env = {
        TEST_DATABASE_URL_ENV: GOOD,
        "DATABASE_URL": "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev",
    }
    target = apply_test_database_url(env)

    assert env["DATABASE_URL"] == GOOD, "engine must bind to the test database"
    assert env["POA_TEST_DATABASE_URL"] == GOOD
    assert env["POA_ORIGINAL_DATABASE_URL"].endswith("/pofa_dev")


def test_apply_refuses_when_unset():
    with pytest.raises(TestDatabaseConfigurationError):
        apply_test_database_url({"DATABASE_URL": "postgresql+psycopg2://u:p@h:5432/pofa_dev"})
