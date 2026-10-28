"""M-BE-01 step 5: does our verifier accept the key family Supabase actually publishes?

Supabase's legacy configuration signs access tokens with HS256 and a shared
secret; its JWT signing keys feature publishes asymmetric keys, ES256 being the
family Supabase creates by default. backend/security/oidc.py refuses `kty: oct`
by design, so a legacy project can never work here -- and an ES256 project only
works if this process can actually verify an EC/P-256 JWK with the installed
cryptography build. The existing suite exercises the full accept/reject matrix
with RS256; it never signs a token with EC. That gap is what this measures.

Nothing is guessed about a real project: the key set is served from a local
fixture, so this says "our code accepts the family", not "this project works".
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time

sys.path.insert(0, r"D:/CODING/Projects/Proof-Of-Action-Final")

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg2://postgres:postgres@localhost:5432/poa_disp_owner")
os.environ.setdefault("JWT_SECRET", "probe-not-a-secret")

from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
import jwt  # noqa: E402

from backend.core import config as config_module  # noqa: E402
from backend.security import oidc  # noqa: E402

ISSUER = "https://probe.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "0f6f0f6f-0000-4000-8000-000000000001"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:200]))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""))


def b64num(value: int, length: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


def configure(algorithms: str) -> None:
    settings = config_module.settings
    settings.auth_oidc_enabled = True
    settings.auth_oidc_issuer = ISSUER
    settings.auth_oidc_jwks_uri = "https://probe.invalid/jwks.json"
    settings.auth_oidc_audience = AUDIENCE
    settings.auth_oidc_algorithms = algorithms
    oidc.reset_key_cache()


def main() -> int:
    private_key = ec.generate_private_key(ec.SECP256R1())
    numbers = private_key.public_key().public_numbers()
    jwk = {"kty": "EC", "crv": "P-256", "use": "sig", "kid": KID, "alg": "ES256",
           "x": b64num(numbers.x, 32), "y": b64num(numbers.y, 32)}
    key_set = {"keys": [jwk]}
    oidc._fetch_key_set = lambda uri: key_set          # type: ignore[assignment]

    def token(**overrides) -> str:
        now = int(time.time())
        claims = {"sub": "reviewer-uuid", "iss": ISSUER, "aud": AUDIENCE,
                  "iat": now, "exp": now + 300, "email": "r@example.test"}
        claims.update(overrides)
        return jwt.encode(claims, private_key, algorithm="ES256",
                          headers={"kid": KID})

    # 1. the family Supabase issues, end to end
    configure("ES256")
    claims = oidc.verify_token(token())
    check("an ES256 (kty EC / P-256) access token verifies through the real code path",
          claims["sub"] == "reviewer-uuid" and claims["aud"] == AUDIENCE, claims)

    # 2. the EC entry must survive key-set indexing, not just decoding
    check("an EC entry is indexed by kid (ALLOWED_KEY_TYPES covers kty EC)",
          oidc.signing_keys().get(KID) is not None)

    # 3. an RS256-only configuration must refuse the same token rather than
    #    downgrade anything
    configure("RS256")
    try:
        oidc.verify_token(token())
        check("RS256-only config refuses an ES256 token", False, "it accepted it")
    except oidc.OIDCError as error:
        check("RS256-only config refuses an ES256 token",
              error.reason == "ALGORITHM_REFUSED", error.reason)

    # 4. the legacy Supabase posture: HS256 with the project secret
    configure("ES256,RS256")
    legacy = jwt.encode({"sub": "x", "iss": ISSUER, "aud": AUDIENCE,
                         "iat": int(time.time()), "exp": int(time.time()) + 300},
                        "super-secret-project-jwt-secret", algorithm="HS256",
                        headers={"kid": KID})
    try:
        oidc.verify_token(legacy)
        check("a legacy HS256 token signed with the project secret is refused",
              False, "it verified")
    except oidc.OIDCError as error:
        check("a legacy HS256 token signed with the project secret is refused",
              error.reason in {"ALGORITHM_REFUSED", "TOKEN_REJECTED"}, error.reason)

    # 5. a published oct entry can never become the verification key
    configure("ES256,HS256")
    oidc.reset_key_cache()
    key_set_with_oct = {"keys": [jwk, {"kty": "oct", "kid": "key-oct", "alg": "HS256",
                                       "k": base64.urlsafe_b64encode(b"0" * 32).decode()}]}
    oidc._fetch_key_set = lambda uri: key_set_with_oct  # type: ignore[assignment]
    indexed = oidc.signing_keys()
    check("a symmetric entry in the key set is never indexed",
          "key-oct" not in indexed and KID in indexed, json.dumps(sorted(indexed)))

    # 6. audience and issuer still bind under ES256
    configure("ES256")
    for label, kwargs in (("wrong audience", {"aud": "service_role"}),
                          ("wrong issuer", {"iss": "https://evil.example/auth/v1"})):
        try:
            oidc.verify_token(token(**kwargs))
            check(f"ES256 path still refuses a {label} token", False, "it verified")
        except oidc.OIDCError as error:
            check(f"ES256 path still refuses a {label} token",
                  error.reason == "TOKEN_REJECTED", error.reason)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
