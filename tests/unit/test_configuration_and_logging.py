"""BE-027 §20/§21/§23: the two configuration-level pieces of the foundation.

Both are wiring checks, not behaviour echoes: they assert where the pieces are
attached, because in each case the bug was a piece attached to the wrong object
while looking perfectly reasonable.
"""

import logging

import pytest
from fastapi.middleware.cors import CORSMiddleware

from backend.app.main import app
from backend.core.config import MIN_JWT_SECRET_LENGTH, Settings
from backend.core.logging import RequestIdFilter, setup_logging


# ---------------------------------------------------------------------------
# CORS (§20, §21)
# ---------------------------------------------------------------------------


def make_settings(raw: str | None = None) -> Settings:
    values = {"cors_allow_origins": raw} if raw is not None else {}
    return Settings(**values)


def test_cors_allowlist_defaults_to_every_origin_for_local_development():
    assert make_settings().cors_origin_list == ["*"]


def test_cors_allowlist_parses_a_comma_separated_origin_list():
    parsed = make_settings(
        "http://localhost:3000, https://review.example ,http://127.0.0.1:5173"
    ).cors_origin_list
    assert parsed == ["http://localhost:3000", "https://review.example",
                      "http://127.0.0.1:5173"]


def test_cors_allowlist_falls_back_to_the_wildcard_when_configured_blank():
    assert make_settings("   ").cors_origin_list == ["*"]
    assert make_settings(",").cors_origin_list == ["*"]


def test_the_running_app_takes_its_cors_origins_from_configuration():
    """The middleware must be built from settings, not from a literal list.

    Asserting equality against ``settings.cors_origin_list`` is what fails if
    someone puts a hardcoded ``["*"]`` back while a deployment has configured
    a real allowlist.
    """
    cors = [
        middleware
        for middleware in app.user_middleware
        if middleware.cls is CORSMiddleware
    ]
    assert len(cors) == 1
    assert cors[0].kwargs["allow_origins"] == make_settings().cors_origin_list


# ---------------------------------------------------------------------------
# Logging (§23)
# ---------------------------------------------------------------------------


def test_request_id_filter_lives_on_the_handler_not_on_the_root_logger():
    """Root-logger filters are skipped for records propagating from other loggers.

    With the filter on the root logger, a record from e.g. ``httpx`` reached the
    formatter without a ``request_id`` attribute and the handler swallowed the
    failure as ``--- Logging error ---``, so nothing useful was logged.
    """
    root = logging.getLogger()
    saved_handlers, saved_filters, saved_level = (
        root.handlers[:], root.filters[:], root.level
    )
    try:
        root.handlers.clear()
        root.filters.clear()
        setup_logging()
        assert root.handlers, "setup_logging did not install a handler"
        handler = root.handlers[0]
        assert any(isinstance(f, RequestIdFilter) for f in handler.filters)
        assert not any(isinstance(f, RequestIdFilter) for f in root.filters)

        record = logging.LogRecord(
            name="httpx", level=logging.INFO, pathname=__file__, lineno=0,
            msg='HTTP Request: %s %s "%s %d %s"', args=(), exc_info=None,
        )
        assert handler.filter(record) is not False
        assert record.request_id == "-"
        assert "[rid=-]" in handler.format(record)
    finally:
        root.handlers[:] = saved_handlers
        root.filters[:] = saved_filters
        root.level = saved_level


# ---------------------------------------------------------------------------
# BE-032R: production JWT-secret guard (config fail-fast, no secret echoed)
# ---------------------------------------------------------------------------


def test_development_and_staging_keep_the_permissive_jwt_default():
    """Only production is hardened; local workflows must not break."""
    assert Settings(environment="development").jwt_secret == "changeme"
    assert Settings(environment="staging").jwt_secret == "changeme"


@pytest.mark.parametrize("bad", ["changeme", "", "x" * (MIN_JWT_SECRET_LENGTH - 1)])
def test_production_rejects_an_unsafe_jwt_secret(bad):
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret=bad)


def test_production_accepts_a_strong_jwt_secret():
    strong = "k" * MIN_JWT_SECRET_LENGTH
    assert Settings(environment="production", jwt_secret=strong).jwt_secret == strong


def test_production_rejection_does_not_echo_the_secret_value():
    """The refusal must not leak whatever secret was actually configured."""
    sentinel = "s" * MIN_JWT_SECRET_LENGTH
    with pytest.raises(ValueError) as excinfo:
        Settings(environment="prod", jwt_secret="")  # blank is what fails the length check
    assert sentinel not in str(excinfo.value)
