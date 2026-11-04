"""Stage 02-2: a reviewer's own token is verified here, and only these ways.

Audit register rows 1.2/1.3 measured that no human identity path existed: the
only credential an ``enforcing`` deployment accepted was a service
``client_id:secret``, which a browser may never hold. This module pins the
verifier that replaces it — signature, algorithm, issuer, audience, lifetime,
key rotation and refusal hygiene — with a locally generated key set, so not one
test touches the network.

The refusals are the point. Each one is checked against a token that *would* be
accepted by a naive decoder: an unsigned ``alg: none`` token, an HMAC token
signed with the provider's own public material, an expired token, a token for a
different audience or issuer, and a token naming a key the provider never
published. A verifier that only ever says yes to the happy path proves nothing.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from backend.core.config import Settings
from backend.security import oidc


ISSUER = "https://poa-test.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "key-abc"


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = KID
    public_jwk["alg"] = "RS256"
    return private_key, public_jwk


@pytest.fixture
def rotation_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk["kid"] = "key-rot"
    public_jwk["alg"] = "RS256"
    return private_key, public_jwk


@pytest.fixture(autouse=True)
def configured(keypair, monkeypatch):
    """OIDC switched on against a local key set; no outbound request ever happens."""
    private_key, public_jwk = keypair
    settings = {
        "auth_oidc_enabled": True,
        "auth_oidc_issuer": ISSUER,
        "auth_oidc_jwks_uri": "https://poa-test.supabase.co/auth/v1/.well-known/jwks.json",
        "auth_oidc_audience": AUDIENCE,
        "auth_oidc_identity_provider": "supabase",
        "auth_oidc_algorithms": "RS256",
        "auth_oidc_jwks_ttl_seconds": 300,
    }
    for name, value in settings.items():
        monkeypatch.setattr(oidc.settings, name, value)
    oidc.reset_key_cache()
    calls = []

    def fake_fetch(uri):
        calls.append(uri)
        return {"keys": [public_jwk]}

    monkeypatch.setattr(oidc, "_fetch_key_set", fake_fetch)
    yield {"private_key": private_key, "jwk": public_jwk, "calls": calls}
    oidc.reset_key_cache()


def _b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def token(private_key, **overrides):
    now = int(time.time())
    claims = {
        "sub": str(uuid4()),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "email": "reviewer@example.test",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


# ---------------------------------------------------------------------------
# the happy path, and the caching it must not break
# ---------------------------------------------------------------------------


def test_a_validly_signed_token_yields_its_claims(configured):
    claims = oidc.verify_token(token(configured["private_key"], sub="reviewer-1"))
    assert claims["sub"] == "reviewer-1"
    assert claims["aud"] == AUDIENCE


def test_the_key_set_is_fetched_once_not_per_request(configured):
    signed = token(configured["private_key"])
    for _ in range(5):
        oidc.verify_token(signed)
    assert configured["calls"] == [oidc.settings.auth_oidc_jwks_uri]


def test_no_token_material_reaches_the_log(configured, caplog):
    signed = token(configured["private_key"])
    with caplog.at_level(logging.WARNING):
        for bad in (signed + "x", "not.a.jwt", "a.b.c"):
            with pytest.raises(oidc.OIDCError):
                oidc.verify_token(bad)
    assert signed not in caplog.text
    assert "reviewer@example.test" not in caplog.text


# ---------------------------------------------------------------------------
# every refusal a naive decoder would have accepted
# ---------------------------------------------------------------------------


def test_a_tampered_signature_is_refused(configured):
    signed = token(configured["private_key"])
    header, payload, signature = signed.split(".")
    forged = ".".join([header, payload, "A" * len(signature)])
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(forged)
    assert error.value.reason == "TOKEN_REJECTED"


def test_an_unsigned_alg_none_token_is_refused(configured):
    now = int(time.time())
    unsigned = jwt.encode(
        {"sub": "attacker", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300},
        key=None, algorithm="none")
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(unsigned)
    assert error.value.reason == "ALGORITHM_REFUSED"


def test_a_token_forged_with_the_public_key_as_an_hmac_secret_is_refused(configured):
    """The classic confusion: sign HS256 using the published RSA material.

    PyJWT's own encoder refuses PEM material as an HMAC secret, so the attack
    token is assembled by hand — a real attacker is not bound by that
    convenience, and the verifier must still refuse what it receives.
    """
    now = int(time.time())
    public_pem = configured["private_key"].public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = _b64(json.dumps({
        "sub": "attacker", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300,
    }).encode())
    signing_input = header + b"." + payload
    signature = _b64(hmac.new(public_pem, signing_input, hashlib.sha256).digest())
    forged = (signing_input + b"." + signature).decode()
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(forged)
    assert error.value.reason == "ALGORITHM_REFUSED"


def test_a_token_signed_by_an_unpublished_key_is_refused(configured, rotation_keypair):
    other_private, _ = rotation_keypair
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(jwt.encode(
            {"sub": "x", "iss": ISSUER, "aud": AUDIENCE,
             "iat": int(time.time()), "exp": int(time.time()) + 300},
            other_private, algorithm="RS256", headers={"kid": "not-published"}))
    assert error.value.reason == "UNKNOWN_KEY_ID"
    # An unknown kid costs exactly one refetch, so a flood of bad tokens cannot
    # become a flood of outbound requests.
    assert len(configured["calls"]) == 2


def test_an_expired_token_is_refused(configured):
    now = int(time.time())
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(token(configured["private_key"], iat=now - 7200, exp=now - 3600))
    assert error.value.reason == "TOKEN_REJECTED"


def test_a_token_from_another_audience_is_refused(configured):
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(token(configured["private_key"], aud="service-role"))
    assert error.value.reason == "TOKEN_REJECTED"


def test_a_token_from_another_issuer_is_refused(configured):
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(token(configured["private_key"], iss="https://evil.example/auth"))
    assert error.value.reason == "TOKEN_REJECTED"


def test_a_refresh_token_is_refused(configured):
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(token(configured["private_key"], use="refresh"))
    assert error.value.reason == "REFRESH_TOKEN"


def test_a_malformed_authorization_value_is_refused_without_a_fetch(configured):
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token("dev-user-11111111-1111-1111-1111-111111111111")
    assert error.value.reason == "MALFORMED_TOKEN"
    assert configured["calls"] == []


def test_a_symmetric_entry_in_the_key_set_is_never_used_as_a_verification_key(
        configured, monkeypatch):
    planted = {"kty": "oct", "kid": "key-oct", "alg": "HS256",
               "k": "c2VjcmV0LW1hdGVyaWFsLXBsYWNlaG9sZGVy"}

    def with_planted(uri):
        configured["calls"].append(uri)
        return {"keys": [configured["jwk"], planted]}

    monkeypatch.setattr(oidc, "_fetch_key_set", with_planted)
    oidc.reset_key_cache()
    assert "key-oct" not in oidc.signing_keys()


# ---------------------------------------------------------------------------
# key rotation and provider availability
# ---------------------------------------------------------------------------


def test_a_rotated_key_is_picked_up_on_the_first_unknown_kid(
        configured, rotation_keypair, monkeypatch):
    other_private, other_jwk = rotation_keypair
    stages = [{"keys": [configured["jwk"]]},
              {"keys": [configured["jwk"], other_jwk]}]

    def rotating_fetch(uri):
        configured["calls"].append(uri)
        return stages[min(len(configured["calls"]) - 1, len(stages) - 1)]

    monkeypatch.setattr(oidc, "_fetch_key_set", rotating_fetch)
    oidc.reset_key_cache()
    now = int(time.time())
    claims = oidc.verify_token(jwt.encode(
        {"sub": "rotated", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300},
        other_private, algorithm="RS256", headers={"kid": "key-rot"}))
    assert claims["sub"] == "rotated"
    assert len(configured["calls"]) == 2


def test_an_unreachable_provider_fails_closed(configured, monkeypatch):
    import httpx

    def down(uri):
        configured["calls"].append(uri)
        raise httpx.ConnectError("provider down")

    oidc.reset_key_cache()
    monkeypatch.setattr(oidc, "_fetch_key_set", down)
    with pytest.raises(oidc.OIDCError) as error:
        oidc.verify_token(token(configured["private_key"]))
    assert error.value.reason == "KEY_SET_UNAVAILABLE"


def test_a_still_fresh_key_set_carries_a_request_through_a_provider_hiccup(
        configured, monkeypatch):
    import httpx

    oidc.verify_token(token(configured["private_key"]))  # fills the cache

    def down(uri):
        raise httpx.ConnectError("provider down")

    monkeypatch.setattr(oidc, "_fetch_key_set", down)
    claims = oidc.verify_token(token(configured["private_key"]))
    assert claims["aud"] == AUDIENCE


# ---------------------------------------------------------------------------
# configuration: a half-configured verifier must refuse to start
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("overrides", [
    {"auth_oidc_issuer": ""},
    {"auth_oidc_jwks_uri": ""},
    {"auth_oidc_issuer": "http://insecure.example/auth"},
    {"auth_oidc_jwks_uri": "http://insecure.example/jwks.json"},
    {"auth_oidc_audience": "  "},
    {"auth_oidc_algorithms": "none"},
    {"auth_oidc_algorithms": "HS256"},
    {"auth_oidc_algorithms": "RS256,HS256"},
    {"auth_oidc_algorithms": ""},
])
def test_enabling_oidc_without_usable_settings_is_refused_at_startup(overrides):
    base = dict(auth_oidc_enabled=True, auth_oidc_issuer=ISSUER,
                auth_oidc_jwks_uri="https://poa-test.supabase.co/auth/v1/.well-known/jwks.json",
                auth_oidc_audience=AUDIENCE, auth_oidc_algorithms="RS256")
    base.update(overrides)
    with pytest.raises(ValueError):
        Settings(**base)


def test_oidc_stays_opt_in_and_unconfigured_settings_are_accepted():
    """An integration-only deployment must keep starting with no OIDC config."""
    quiet = Settings(auth_oidc_enabled=False, auth_oidc_issuer="", auth_oidc_jwks_uri="",
                     auth_oidc_algorithms="none")
    assert quiet.auth_oidc_enabled is False


def test_asymmetric_families_are_all_acceptable_configuration():
    configured = Settings(auth_oidc_enabled=True, auth_oidc_issuer=ISSUER,
                          auth_oidc_jwks_uri="https://poa-test.supabase.co/jwks.json",
                          auth_oidc_algorithms="RS256, ES256, PS256")
    assert configured.auth_oidc_algorithms == "RS256, ES256, PS256"
