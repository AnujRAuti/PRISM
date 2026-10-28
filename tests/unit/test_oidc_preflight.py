"""PRISM-3 — the release gate that proves the identity provider is the intended one.

A configuration can satisfy every startup check and still be wrong in two ways
this suite pins down: it can point at a *real* provider project that is not the
project under review, and it can name an algorithm the provider does not sign
with. Both boot cleanly, and both then refuse or mis-attribute every reviewer at
runtime, so the questions have to be answered before a release — against the live
key set, not against the shape of a URL.

Nothing here reaches the network: :func:`backend.security.oidc._fetch_key_set` is
the single outbound seam and every test replaces it, as the stage 02 verification
suite does.
"""

import json
import time
import uuid
from dataclasses import dataclass

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from backend.security import oidc
from backend.security import oidc_preflight as gate
from backend.security.oidc_preflight import CheckStatus

ISSUER = "https://poa-gate.supabase.co/auth/v1"
JWKS = "https://poa-gate.supabase.co/auth/v1/.well-known/jwks.json"
PROJECT_REF = "poa-gate"
AUDIENCE = "authenticated"
KID = "gate-key-1"


@dataclass(frozen=True)
class Fixture:
    private_key: object
    jwk: dict
    calls: list


def rsa_entry(kid: str = KID, alg: str = "RS256"):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    entry = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    entry.update({"kid": kid, "alg": alg, "use": "sig"})
    return private_key, entry


def signed_token(private_key, **overrides):
    now = int(time.time())
    claims = {"sub": str(uuid.uuid4()), "iss": ISSUER, "aud": AUDIENCE,
              "iat": now, "exp": now + 300}
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def provider(monkeypatch):
    """OIDC enabled against a local key set; the gate never goes out."""
    private_key, entry = rsa_entry()
    for name, value in {
        "auth_oidc_enabled": True,
        "auth_oidc_issuer": ISSUER,
        "auth_oidc_jwks_uri": JWKS,
        "auth_oidc_audience": AUDIENCE,
        "auth_oidc_identity_provider": "supabase",
        "auth_oidc_algorithms": "RS256",
        "auth_oidc_jwks_ttl_seconds": 300,
    }.items():
        monkeypatch.setattr(oidc.settings, name, value)
    calls: list[str] = []
    monkeypatch.setattr(oidc, "_fetch_key_set",
                        lambda uri: calls.append(uri) or {"keys": [entry]})
    oidc.reset_key_cache()
    yield Fixture(private_key=private_key, jwk=entry, calls=calls)
    oidc.reset_key_cache()


def check_map(checks) -> dict[str, tuple[CheckStatus, str]]:
    return {check.name: (check.status, check.detail) for check in checks}


def token_file(tmp_path, token: str) -> str:
    path = tmp_path / "probe-token"
    path.write_text(token, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# what a passing gate has to have actually reached
# ---------------------------------------------------------------------------


def test_a_matching_project_with_a_usable_key_set_passes_end_to_end(provider):
    checks = gate.run(expected_project_ref=PROJECT_REF,
                      probe_token=signed_token(provider.private_key))
    statuses = check_map(checks)
    assert gate.verdict(checks) is CheckStatus.PASS, statuses
    # Non-vacuity: every assertion the gate makes had to be reached and answered.
    assert set(statuses) == {"oidc_enabled", "auth_oidc_issuer", "auth_oidc_jwks_uri",
                             "same_authority", "issuer_shape", "project_identity",
                             "configured_algorithms", "key_set_reachable", "usable_keys",
                             "key_types", "probe_token"}
    assert set(provider.calls) == {JWKS}


def test_no_expected_project_ref_leaves_the_identity_unverified(provider):
    """A syntactically perfect endpoint can still belong to the wrong tenant."""
    checks = gate.run()
    statuses = check_map(checks)
    assert statuses["project_identity"][0] is CheckStatus.BLOCKED
    assert "not tied to a project" in statuses["project_identity"][1]
    assert gate.verdict(checks) is CheckStatus.BLOCKED


def test_a_real_provider_project_that_is_not_this_one_is_refused(provider):
    checks = gate.run(expected_project_ref="some-other-project")
    status, detail = check_map(checks)["project_identity"]
    assert status is CheckStatus.FAIL
    assert "some-other-project" in detail and PROJECT_REF in detail
    assert gate.verdict(checks) is CheckStatus.FAIL


# ---------------------------------------------------------------------------
# the two ways a valid-looking configuration locks everyone out
# ---------------------------------------------------------------------------


def test_an_algorithm_the_provider_does_not_use_refuses_every_reviewer(provider, monkeypatch):
    """RS256 configured against a provider whose published key is ES256.

    This is the discrepancy PRISM-1's investigation closed: both endpoints are
    real, the host is right, and every token is nevertheless refused.
    """
    ec_entry = {"kty": "EC", "crv": "P-256", "kid": "es-key-1", "alg": "ES256",
                "x": "AAAA", "y": "AAAA"}
    monkeypatch.setattr(oidc, "_fetch_key_set", lambda uri: {"keys": [ec_entry]})
    checks = gate.run(expected_project_ref=PROJECT_REF)
    status, detail = check_map(checks)["usable_keys"]
    assert status is CheckStatus.FAIL
    assert "RS256" in detail and "EC/ES256" in detail
    assert gate.verdict(checks) is CheckStatus.FAIL


def test_a_disabled_verifier_fails_the_gate(monkeypatch):
    monkeypatch.setattr(oidc.settings, "auth_oidc_enabled", False)
    checks = gate.run(expected_project_ref=PROJECT_REF)
    assert [check.name for check in checks] == ["oidc_enabled"]
    assert checks[0].status is CheckStatus.FAIL
    assert "service client" in checks[0].detail


@pytest.mark.parametrize("field,value,fragment", [
    ("auth_oidc_issuer", "", "is not set"),
    ("auth_oidc_jwks_uri", "", "is not set"),
    ("auth_oidc_issuer", "http://poa-gate.supabase.co/auth/v1", "https://"),
    ("auth_oidc_algorithms", "", "accepts nothing"),
])
def test_a_half_configured_provider_is_named_field_by_field(provider, monkeypatch,
                                                            field, value, fragment):
    monkeypatch.setattr(oidc.settings, field, value)
    checks = gate.run(expected_project_ref=PROJECT_REF)
    refusals = [detail for _name, (status, detail) in check_map(checks).items()
                if status is CheckStatus.FAIL]
    assert any(fragment in detail for detail in refusals), check_map(checks)


def test_an_issuer_on_the_right_host_but_the_wrong_path_is_refused(provider, monkeypatch):
    monkeypatch.setattr(oidc.settings, "auth_oidc_issuer",
                        "https://poa-gate.supabase.co/auth/v1/tenants/other")
    status, detail = check_map(gate.run(expected_project_ref=PROJECT_REF))["issuer_shape"]
    assert status is CheckStatus.FAIL
    assert "/auth/v1" in detail


def test_an_unreachable_key_set_fails_the_gate_instead_of_crashing(provider, monkeypatch):
    def refuse(uri):
        raise httpx.ConnectError("provider is unreachable")

    monkeypatch.setattr(oidc, "_fetch_key_set", refuse)
    checks = gate.run(expected_project_ref=PROJECT_REF)
    statuses = check_map(checks)
    assert statuses["key_set_reachable"][0] is CheckStatus.FAIL
    assert "ConnectError" in statuses["key_set_reachable"][1]
    assert gate.verdict(checks) is CheckStatus.FAIL
    assert not any("Traceback" in detail for detail in statuses.values())


# ---------------------------------------------------------------------------
# what the report is allowed to contain
# ---------------------------------------------------------------------------


def test_a_planted_symmetric_key_is_neither_used_nor_leaked(provider, monkeypatch):
    planted = {"kty": "oct", "kid": "planted-shared", "alg": "HS256",
               "k": "shared-secret-material-not-for-reporting"}
    monkeypatch.setattr(oidc, "_fetch_key_set",
                        lambda uri: {"keys": [provider.jwk, planted]})
    checks = gate.run(expected_project_ref=PROJECT_REF,
                      probe_token=signed_token(provider.private_key))
    statuses = check_map(checks)
    assert statuses["usable_keys"][0] is CheckStatus.PASS
    assert KID in statuses["usable_keys"][1]
    rendered = json.dumps([check.detail for check in checks])
    assert "planted-shared" not in rendered and "shared-secret-material" not in rendered
    assert gate.verdict(checks) is CheckStatus.PASS


def test_the_report_never_carries_the_probe_token_or_the_private_key(provider):
    token = signed_token(provider.private_key)
    pem = provider.private_key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).hex()
    checks = gate.run(expected_project_ref=PROJECT_REF, probe_token=token)
    rendered = json.dumps([{"name": check.name, "detail": check.detail} for check in checks])
    assert token not in rendered
    assert token.split(".")[1] not in rendered
    assert pem not in rendered


def test_a_token_signed_by_a_key_the_provider_no_longer_publishes_is_refused(
        provider, monkeypatch):
    _other_private, other_entry = rsa_entry(kid="rotated-key-2")
    monkeypatch.setattr(oidc, "_fetch_key_set", lambda uri: {"keys": [other_entry]})
    checks = gate.run(expected_project_ref=PROJECT_REF,
                      probe_token=signed_token(provider.private_key))
    status, detail = check_map(checks)["probe_token"]
    assert status is CheckStatus.FAIL
    assert "UNKNOWN_KEY_ID" in detail
    assert gate.verdict(checks) is CheckStatus.FAIL


def test_a_refresh_token_never_passes_the_probe(provider):
    checks = gate.run(expected_project_ref=PROJECT_REF,
                      probe_token=signed_token(provider.private_key, use="refresh"))
    status, detail = check_map(checks)["probe_token"]
    assert status is CheckStatus.FAIL
    assert "REFRESH_TOKEN" in detail


# ---------------------------------------------------------------------------
# the operator command itself
# ---------------------------------------------------------------------------


def test_the_command_reports_and_exits_zero_only_when_everything_passed(provider, tmp_path,
                                                                        capsys):
    token = signed_token(provider.private_key)
    code = gate.main(["--expected-project-ref", PROJECT_REF,
                      "--token-file", token_file(tmp_path, token)])
    printed = capsys.readouterr().out
    assert code == 0
    assert "verdict: PASS" in printed
    segments = token.split(".")
    for line in printed.splitlines():
        assert not any(segment in line for segment in segments)


def test_the_command_exits_one_and_names_the_failing_check(provider, capsys):
    code = gate.main(["--expected-project-ref", "not-this-project"])
    printed = capsys.readouterr().out
    assert code == 1
    assert any(line.startswith("FAIL") and "project_identity" in line
               for line in printed.splitlines())


def test_the_command_exits_two_when_something_is_unverified(provider, capsys):
    assert gate.main(["--expected-project-ref", PROJECT_REF]) == 2
    assert "verdict: BLOCKED" in capsys.readouterr().out


def test_the_json_output_is_machine_readable_evidence(provider, tmp_path, capsys):
    code = gate.main(["--expected-project-ref", PROJECT_REF,
                      "--token-file", token_file(tmp_path, signed_token(provider.private_key)),
                      "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["verdict"] == "PASS"
    assert {entry["name"] for entry in payload["checks"]} >= {
        "project_identity", "usable_keys", "probe_token"}
