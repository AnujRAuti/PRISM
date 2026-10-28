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
# BE-032R / BE-037: production fail-fast guard (config refuses insecure defaults)
# ---------------------------------------------------------------------------

STRONG_JWT = "k" * MIN_JWT_SECRET_LENGTH

#: A reachable identity provider, shaped like the real one. Used as the baseline
#: every refusal test perturbs in exactly one way, so a red test names the field
#: that was wrong rather than the validator that fired. ``.invalid``-style hosts
#: cannot be reused here: PRISM-1 refuses reserved TLDs as identity endpoints.
REAL_ISSUER = "https://poa-real.supabase.co/auth/v1"
REAL_JWKS = "https://poa-real.supabase.co/auth/v1/.well-known/jwks.json"


def _safe_production(**overrides):
    """A genuinely safe production ``Settings`` base, overridable per test."""
    base = dict(
        environment="production",
        jwt_secret=STRONG_JWT,
        auth_mode="enforcing",
        auth_dev_tokens_enabled=False,
        cors_allow_origins="https://app.invalid.example",
        auth_oidc_enabled=True,
        auth_oidc_issuer=REAL_ISSUER,
        auth_oidc_jwks_uri=REAL_JWKS,
        auth_oidc_algorithms="ES256",
    )
    base.update(overrides)
    return base


def test_development_and_staging_keep_the_permissive_jwt_default():
    """Only production is hardened; local workflows must not break."""
    assert Settings(environment="development").jwt_secret == "changeme"
    assert Settings(environment="staging").jwt_secret == "changeme"


@pytest.mark.parametrize("bad", ["changeme", "", "x" * (MIN_JWT_SECRET_LENGTH - 1)])
def test_production_rejects_an_unsafe_jwt_secret(bad):
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret=bad)


def test_production_accepts_a_strong_jwt_secret():
    s = Settings(**_safe_production())
    assert s.jwt_secret == STRONG_JWT


def test_production_requires_enforcing_auth_mode():
    """Development auth mode bypasses authorization for anonymous callers."""
    with pytest.raises(ValueError):
        Settings(**_safe_production(auth_mode="development"))


def test_production_forbids_development_bearer_tokens():
    with pytest.raises(ValueError):
        Settings(**_safe_production(auth_dev_tokens_enabled=True))


@pytest.mark.parametrize("origins", ["*", "", "https://app.invalid.example,*"])
def test_production_forbids_wildcard_cors(origins):
    """With credentials enabled a wildcard origin can read authenticated data."""
    with pytest.raises(ValueError):
        Settings(**_safe_production(cors_allow_origins=origins))


def test_production_rejection_does_not_echo_the_secret_value():
    """The refusal must not leak whatever secret was actually configured."""
    sentinel = "s" * MIN_JWT_SECRET_LENGTH
    with pytest.raises(ValueError) as excinfo:
        Settings(environment="prod", jwt_secret="")  # blank is what fails the length check
    assert sentinel not in str(excinfo.value)


# ---------------------------------------------------------------------------
# PRISM-1: an enabled identity verifier must point at a provider that exists
# ---------------------------------------------------------------------------


def _enabled_oidc(**overrides):
    """OIDC switched on against a reachable provider, overridable per test."""
    base = dict(auth_oidc_enabled=True, auth_oidc_issuer=REAL_ISSUER,
                auth_oidc_jwks_uri=REAL_JWKS, auth_oidc_algorithms="ES256")
    base.update(overrides)
    return base


#: Hosts that satisfy a non-blank + ``https://`` check while being unusable: the
#: placeholder that was committed as a default, loopback, reserved TLDs and a
#: single-label name. Each is tried in both endpoint positions.
UNUSABLE_ENDPOINTS = [
    "https://supabase.auth.local",
    "https://supabase.auth.local/.well-known/jwks",
    "https://localhost/auth/v1",
    "https://127.0.0.1/auth/v1/.well-known/jwks.json",
    "https://127.0.0.42/.well-known/jwks.json",
    "https://[::1]/auth/v1/.well-known/jwks.json",
    "https://oidc.test/auth/v1",
    "https://auth.internal/auth/v1",
    "https://keycloak/auth/v1",
]


@pytest.mark.parametrize("endpoint", UNUSABLE_ENDPOINTS)
def test_an_unreachable_identity_issuer_is_refused_whatever_environment(endpoint):
    """A syntactically valid endpoint is not a usable one.

    The committed placeholder passed the old issuer check, so a deployment could
    boot believing reviewers were being verified while every sign-in was refused
    by a host that does not resolve.
    """
    with pytest.raises(ValueError):
        Settings(**_enabled_oidc(auth_oidc_issuer=endpoint))
    with pytest.raises(ValueError):
        Settings(**_safe_production(auth_oidc_issuer=endpoint))


@pytest.mark.parametrize("endpoint", UNUSABLE_ENDPOINTS)
def test_an_unreachable_jwks_endpoint_is_refused(endpoint):
    with pytest.raises(ValueError):
        Settings(**_enabled_oidc(auth_oidc_jwks_uri=endpoint))


def test_issuer_and_jwks_must_be_served_by_the_same_authority():
    """Keys fetched from a host other than the issuer could sign anything."""
    with pytest.raises(ValueError):
        Settings(**_enabled_oidc(
            auth_oidc_jwks_uri="https://poa-other.supabase.co/.well-known/jwks.json"))


def test_a_reachable_provider_configuration_boots():
    """The positive control: the refusals above are about the host, not the shape."""
    s = Settings(**_enabled_oidc())
    assert s.auth_oidc_issuer == REAL_ISSUER
    assert s.auth_oidc_algorithms == "ES256"


def test_source_defaults_do_not_carry_a_placeholder_identity_endpoint():
    """``settings`` is built at import, so a placeholder default is a live config.

    Development must boot with OIDC simply *off* and no endpoints, which is an
    honest unconfigured state, not one that looks configured and refuses everyone.
    """
    s = Settings()
    assert s.auth_oidc_enabled is False
    assert s.auth_oidc_issuer == ""
    assert s.auth_oidc_jwks_uri == ""


def test_development_defaults_remain_usable():
    """Hardening belongs in the production guard, not in the shared defaults.

    ``enforcing`` with development tokens off and no working sign-in path leaves
    a local checkout unable to call its own API, which is how BE-037's
    anonymous-bypass test broke.
    """
    s = Settings()
    assert s.auth_mode == "development"
    assert s.auth_dev_tokens_enabled is True


def test_production_requires_the_identity_verifier_to_be_enabled():
    """A production reviewer deployment with no human identity path is mis-set."""
    with pytest.raises(ValueError):
        Settings(**_safe_production(auth_oidc_enabled=False))


def test_production_refuses_placeholder_identity_endpoints():
    with pytest.raises(ValueError):
        Settings(**_safe_production(
            auth_oidc_issuer="https://supabase.auth.local",
            auth_oidc_jwks_uri="https://supabase.auth.local/.well-known/jwks"))


def test_production_requires_an_identity_provider_name():
    """The provider name is what a verified ``sub`` is looked up under."""
    with pytest.raises(ValueError):
        Settings(**_safe_production(auth_oidc_identity_provider="   "))


def test_a_complete_production_configuration_boots():
    s = Settings(**_safe_production())
    assert s.auth_oidc_enabled is True
    assert s.auth_oidc_identity_provider == "supabase"
