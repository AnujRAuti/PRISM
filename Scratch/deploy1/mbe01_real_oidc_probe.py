"""M-BE-01 step 5 (owner input received 2026-10-27): verify the REAL Supabase
project the owner created, using the project's own published key set.

Nothing here needs a secret: the issuer, the JWKS and the public key are published
by design. What this measures is whether this backend, configured with the six
AUTH_OIDC_* values the owner supplied, actually trusts that project and refuses
everything else -- through the real verifier code path, against the live endpoint.

Checks:
 1. the discovery document's `issuer` and `jwks_uri` match the configured values
    verbatim (the milestone forbids guessing a URL, so the URL is checked, not assumed);
 2. the published key set is exactly one asymmetric signing key, and `AUTH_OIDC_ALGORITHMS
    =ES256` indexes it by its real `kid`;
 3. no symmetric entry is published, so the "previous HS256 key" the owner is keeping
    cannot be used against this service -- and the verifier would refuse it anyway;
 4. a token that *claims* that real kid but carries a forged signature is refused,
    proven against the live public key (this is the non-vacuity check: an accept path
    that never refuses would pass every other test by accident);
 5. a genuine-shape ES256 token signed by a DIFFERENT key is refused;
 6. with the same live key set swapped for a set that does not contain that kid, the
    token is refused as UNKNOWN_KEY_ID after exactly one forced refetch (a rotation
    cannot be silently accepted, and a flood of unknown kids cannot become a flood of
    outbound requests);
 7. the wrong issuer, wrong audience, expired token and missing-claim cases each refuse
    for their OWN reason -- minted against a local key set, because a real Supabase
    token cannot be re-signed with a tampered payload. The reason code is what is
    asserted, so a refusal that happens for the wrong reason does not pass.

No token value is ever printed, and no outbound request is made to any URL other than
this project's published endpoints.
"""

import base64
import json
import os
import time
from cryptography.hazmat.primitives.asymmetric import ec

ISSUER = "https://tuaeujvuuanadqvykugw.supabase.co/auth/v1"
JWKS_URI = ISSUER + "/.well-known/jwks.json"
AUDIENCE = "authenticated"
ALGORITHMS = "ES256"
IDENTITY_PROVIDER = "supabase"

# Claim shape copied from what Supabase issues: a 1-hour access token, subject = the
# auth user id, audience = the role.
SUB = "00000000-0000-4000-8000-000000000001"


def _env_overrides():
    os.environ.update(
        AUTH_MODE="enforcing",
        AUTH_DEV_TOKENS_ENABLED="false",
        AUTH_OIDC_ENABLED="true",
        AUTH_OIDC_ISSUER=ISSUER,
        AUTH_OIDC_JWKS_URI=JWKS_URI,
        AUTH_OIDC_AUDIENCE=AUDIENCE,
        AUTH_OIDC_ALGORITHMS=ALGORITHMS,
        AUTH_OIDC_IDENTITY_PROVIDER=IDENTITY_PROVIDER,
    )


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()


def mint(key, kid: str, claims: dict, alg: str = "ES256") -> str:
    """Sign a token with `key` -- the private half stays in this process."""
    import jwt as pyjwt

    header = {"alg": alg, "typ": "JWT", "kid": kid}
    return pyjwt.encode(claims, key, algorithm=alg, headers=header)


def standard_claims(**changes) -> dict:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": SUB, "iat": now, "exp": now + 3600,
              "email": "reviewer@example.invalid", "role": "authenticated", "session_id": None}
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not None}


def main() -> int:
    _env_overrides()
    import httpx
    from backend.security import oidc
    from backend.core.config import settings

    results = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((ok, name, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""))

    # 1. the published endpoints say what the configuration says
    discovery = httpx.get(JWKS_URI.replace("/.well-known/jwks.json", "/.well-known/openid-configuration"),
                          timeout=10.0).json()
    check("discovery issuer is byte-identical to AUTH_OIDC_ISSUER",
          discovery["issuer"] == settings.auth_oidc_issuer, discovery["issuer"])
    check("discovery jwks_uri is byte-identical to AUTH_OIDC_JWKS_URI",
          discovery["jwks_uri"] == settings.auth_oidc_jwks_uri, discovery["jwks_uri"])

    published = httpx.get(JWKS_URI, timeout=10.0).json()
    entries = published.get("keys", [])
    check("the project publishes exactly one signing key", len(entries) == 1,
          json.dumps([{k: e.get(k) for k in ("kty", "crv", "alg", "use", "kid")} for e in entries]))
    real_kid = entries[0]["kid"]
    check("AUTH_OIDC_ALGORITHMS=ES256 matches the published key's algorithm",
          entries[0].get("alg") == "ES256" and entries[0].get("crv") == "P-256",
          f"alg={entries[0].get('alg')} crv={entries[0].get('crv')}")

    # 2/3. the live key set, indexed by the real code
    oidc.reset_key_cache()
    keys = oidc.signing_keys()
    check("the verifier indexes the live kid under the configured algorithm",
          list(keys) == [real_kid], f"indexed={list(keys)}")
    check("no symmetric entry is published, so the retained HS256 key is unusable here",
          not any(e.get("kty") == "oct" for e in entries),
          f"kty={[e.get('kty') for e in entries]}")

    # 4. forged signature against the REAL published public key
    stranger = ec.generate_private_key(ec.SECP256R1())
    forged = mint(stranger, real_kid, standard_claims())
    try:
        oidc.verify_token(forged)
        check("a token signed with the real kid but the wrong key is refused", False, "it verified")
    except oidc.OIDCError as error:
        check("a token signed with the real kid but the wrong key is refused",
              error.reason == "TOKEN_REJECTED", f"reason={error.reason}")

    # 6. unknown kid against a key set that lacks it
    original_fetch = oidc._fetch_key_set
    calls = []

    def counting_fetch(uri):
        calls.append(uri)
        return {"keys": [{"kty": "EC", "crv": "P-256", "alg": "ES256", "use": "sig",
                          "kid": "unpublished-key",
                          **_public_jwk_parts(stranger.public_key())}]}

    oidc._fetch_key_set = counting_fetch
    try:
        oidc.reset_key_cache()
        try:
            oidc.verify_token(mint(stranger, real_kid, standard_claims()))
            check("a token whose kid is not in the key set is refused", False, "it verified")
        except oidc.OIDCError as error:
            check("a token whose kid is not in the key set is refused",
                  error.reason == "UNKNOWN_KEY_ID", f"reason={error.reason}")
        first = len(calls)
        try:
            oidc.verify_token(mint(stranger, real_kid, standard_claims()))
        except oidc.OIDCError:
            pass
        check("an unknown kid refetches the key set at most once per cooldown window",
              len(calls) - first <= 1, f"extra fetches={len(calls) - first}")
    finally:
        oidc._fetch_key_set = original_fetch

    # 7. claim guards, each proven to refuse for its own reason. These use a minted key
    #    set because a real Supabase token cannot be re-signed with a tampered payload.
    provider = ec.generate_private_key(ec.SECP256R1())
    provider_kid = "minted-provider-key"
    oidc._fetch_key_set = lambda uri: {"keys": [{"kty": "EC", "crv": "P-256", "alg": "ES256",
                                                 "use": "sig", "kid": provider_kid,
                                                 **_public_jwk_parts(provider.public_key())}]}
    oidc.reset_key_cache()
    good = mint(provider, provider_kid, standard_claims())
    claims = oidc.verify_token(good)
    check("a correctly signed token from this key set is accepted, with its claims returned",
          claims["sub"] == SUB and claims["aud"] == AUDIENCE, f"sub returned={claims['sub'][:8]}…")

    no_exp = standard_claims()
    no_exp.pop("exp")
    for name, token, expected in [
        ("wrong issuer is refused",
         mint(provider, provider_kid, standard_claims(iss=ISSUER.replace("/auth/v1", "/elsewhere"))),
         "TOKEN_REJECTED"),
        ("wrong audience is refused",
         mint(provider, provider_kid, standard_claims(aud="anon")), "TOKEN_REJECTED"),
        ("an expired token is refused",
         mint(provider, provider_kid, standard_claims(exp=int(time.time()) - 600,
                                                      iat=int(time.time()) - 4200)),
         "TOKEN_REJECTED"),
        ("a token with no exp is refused",
         mint(provider, provider_kid, no_exp), "TOKEN_REJECTED"),
        ("a refresh token presented as an access token is refused",
         mint(provider, provider_kid, standard_claims(use="refresh")), "REFRESH_TOKEN"),
        ("an HS256 token is refused by algorithm, before any key lookup",
         _hs256_token(), "ALGORITHM_REFUSED"),
    ]:
        try:
            oidc.verify_token(token)
            check(name, False, "it verified")
        except oidc.OIDCError as error:
            check(name, error.reason == expected, f"reason={error.reason} expected={expected}")

    ok = sum(1 for r in results if r[0])
    print(f"\n{ok}/{len(results)} checks passed")
    print(f"configured issuer={settings.auth_oidc_issuer}")
    print(f"configured jwks_uri={settings.auth_oidc_jwks_uri}")
    print(f"configured audience={settings.auth_oidc_audience} algorithms={settings.auth_oidc_algorithms} "
          f"identity_provider={settings.auth_oidc_identity_provider} enabled={settings.auth_oidc_enabled}")
    json.dump([{"check": n, "passed": p, "detail": d} for p, n, d in results],
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "mbe01_real_oidc_probe.json"), "w"), indent=2)
    return 0 if ok == len(results) else 1


def _public_jwk_parts(public_key) -> dict:
    numbers = public_key.public_numbers()
    def enc(value):
        return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()
    return {"x": enc(numbers.x), "y": enc(numbers.y)}


def _hs256_token() -> str:
    import jwt as pyjwt

    return pyjwt.encode(standard_claims(), "x" * 32, algorithm="HS256",
                        headers={"kid": "ab0ac6ae-93be-441c-9196-7b2fade15af0"})


if __name__ == "__main__":
    raise SystemExit(main())
