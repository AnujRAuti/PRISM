---
name: authentication-and-authorization-security
description: Design and audit authn/authz—session vs token, OAuth2/OIDC, MFA, password storage, RBAC/ABAC, object-level checks, and the failure modes attackers exploit.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: high
---

# Authentication and Authorization Security

## 1. Purpose

Get identity right. Authentication proves who a principal is; authorization decides what they may do. Most severe web vulnerabilities in practice are authorization failures (IDOR, missing function-level checks) plus broken authentication (session theft, weak reset flows). This skill provides a design checklist, concrete implementation patterns, and an audit procedure for existing systems.

**Scope:** systems you own or are explicitly authorized to assess. Never attempt credential attacks against systems without written permission.

## 2. Activation Conditions

- Building login, registration, password reset, MFA, or SSO.
- Introducing OAuth2/OIDC, API keys, or service-to-service auth.
- Reviewing multi-tenant access control.
- A pentest or bug report mentions IDOR, session fixation, or JWT issues.
- Keywords: authn, authz, OAuth2, OIDC, JWT, session, CSRF, RBAC, ABAC, MFA, password reset, IDOR, tenant isolation, privilege escalation.

## 3. When Not to Use

- Cryptography design questions unrelated to identity (use secure-code-review).
- Network-level access control (use network-security-analysis).
- Cloud IAM policies (use cloud-iam-security).
- Agent/tool permissions (use agent-permission-management).

## 4. Required Context

1. Actors and roles, and what each may access.
2. Tenancy model: single-tenant, multi-tenant shared schema, per-tenant schema/DB.
3. Session mechanism: cookies, JWT, opaque tokens, MFA.
4. Identity providers involved (internal, Okta, Entra ID, Google).
5. Threat exposure: internet-facing? admin console? mobile clients?
6. Compliance requirements (password rules, session timeouts, audit retention).

## 5. Operating Procedure

**Design phase**

1. **Model principals**: users, admins, services, API clients; define role inventory and permissions matrix.
2. **Choose the session model**: server-side sessions with opaque cookies (simplest, revocable) vs. short-lived JWT + refresh rotation (stateless, needs revocation design).
3. **Define token lifetimes**: access ≤ 15 min, refresh 7–30 days with rotation and reuse detection; sessions idle timeout 30 min for admin.
4. **Choose MFA**: TOTP or WebAuthn/passkeys (phishing-resistant, preferred); SMS only if unavoidable.
5. **Design password handling**: Argon2id (or bcrypt cost ≥ 12), breached-password check (k-anonymity), no composition rules, no periodic rotation.
6. **Design recovery**: single-use, time-limited tokens; identical response for known/unknown emails; invalidate sessions after reset.
7. **Design authorization**: deny by default; permission checks server-side at the object level; central policy module so checks cannot be forgotten.

**Audit phase**

8. **Enumerate every endpoint** and record required permission and ownership filter.
9. **Test horizontal access**: user A's token against user B's resources (expect 404/403, no data).
10. **Test vertical access**: normal user against admin endpoints.
11. **Test token handling**: signature verification, `alg: none` rejection, `kid` injection, expiry, audience/issuer validation, refresh rotation.
12. **Test session hygiene**: fixation, logout invalidation, concurrent session policy, cookie flags.
13. **Test account flows**: registration enumeration, reset token reuse, MFA bypass via alternate flows, OAuth `state`/PKCE validation, open redirect on `redirect_uri`.
14. **Test rate limits** on login, OTP, reset, and registration.
15. **Report and fix**; add regression tests for each.

## 6. Tools and Technologies

| Need | Tools |
|---|---|
| Standards | OAuth 2.1 draft, OIDC Core, RFC 9700 (OAuth Security BCP) |
| Libraries | `Authlib`, `python-jose`/`joserfc`, `passport`, `next-auth`, Spring Security |
| Password hashing | Argon2id (`argon2-cffi`), bcrypt, scrypt |
| MFA | `pyotp`, WebAuthn (`webauthn` libs) |
| Testing | `jwt_tool`, `ffuf` (authorized), custom pytest suites |
| Static analysis | Semgrep auth rules, CodeQL |
| Policy engines | Casbin, OPA, Cedar |
| Secrets | Vault, KMS |

## 7. Practical Implementation

**Password hashing + verification (Python):**

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import hmac

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)

def hash_password(pw: str) -> str:
    if len(pw) < 12:
        raise ValueError("password must be at least 12 characters")
    return ph.hash(pw)

def verify_password(stored: str, candidate: str) -> bool:
    try:
        return ph.verify(stored, candidate)
    except (VerifyMismatchError, VerificationError):
        return False
```

**Session cookie configuration (FastAPI):**

```python
resp.set_cookie(
    "session",
    value=opaque_session_id,
    httponly=True,
    secure=True,
    samesite="lax",       # "strict" for admin surfaces
    max_age=1800,
    path="/",
)
# Store only a hash of the session id server-side:
# sessions(id_hash PK, user_id, created_at, last_seen, ip_hash, ua_hash, revoked_at)
```

**JWT validation done correctly (Python, PyJWT):**

```python
import jwt
from jwt import InvalidTokenError

def verify_access_token(token: str, jwks_client, issuer: str, audience: str) -> dict:
    header = jwt.get_unverified_header(token)
    key = jwks_client.get_signing_key(header["kid"]).key
    try:
        return jwt.decode(
            token, key,
            algorithms=["RS256", "ES256"],   # never trust header alg; never allow "none"
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,                        # clock skew only
        )
    except InvalidTokenError as exc:
        raise Unauthorized("invalid token") from exc
```

**Object-level authorization (SQL + guard):**

```python
def get_document(doc_id: str, principal: Principal, db) -> Document:
    row = db.execute(
        """SELECT d.* FROM documents d
           JOIN document_acl a ON a.doc_id = d.id
           WHERE d.id = %s AND a.user_id = %s""",
        (doc_id, principal.user_id),
    ).fetchone()
    if row is None:
        raise NotFound()   # 404 prevents existence disclosure
    return Document(**row)
```

**Deny-by-default permission decorator:**

```python
from functools import wraps

def requires(permission: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(request, *a, **kw):
            principal = request.state.principal
            if permission not in principal.permissions:
                raise Forbidden()
            return fn(request, *a, **kw)
        return wrapper
    return deco

@requires("billing.invoice.read")
def view_invoice(request, invoice_id): ...
```

**OAuth2 authorization code with PKCE (client side):**

```python
import secrets, hashlib, base64

verifier = secrets.token_urlsafe(64)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
state = secrets.token_urlsafe(32)
# authorize URL params: response_type=code, code_challenge=challenge,
# code_challenge_method=S256, state=state, redirect_uri=<exact match>
# On callback: verify state (constant-time), then exchange code with code_verifier.
```

**Login rate limiting and lockout (Redis):**

```python
def register_failed_attempt(redis, user_key: str, ip: str) -> None:
    pipe = redis.pipeline()
    pipe.incr(f"fail:u:{user_key}"); pipe.expire(f"fail:u:{user_key}", 900)
    pipe.incr(f"fail:ip:{ip}");      pipe.expire(f"fail:ip:{ip}", 900)
    user_fail, ip_fail, *_ = pipe.execute()
    if user_fail >= 5 or ip_fail >= 20:
        raise TooManyAttempts()
```

## 8. Quality Standards

- Authorization decisions are made server-side on every request, at object level.
- No secrets or tokens in URLs, logs, or error messages.
- Cookies: `HttpOnly`, `Secure`, `SameSite`; session ID high-entropy and rotated on login.
- JWT: signature verified with an allowlisted algorithm; `iss`/`aud`/`exp` validated; keys rotated.
- Password storage uses a memory-hard KDF with tuned parameters.
- Account recovery cannot be used to take over an account (single-use, short TTL, no enumeration).
- MFA available for all privileged roles; mandatory for admins.
- All auth events logged with actor, IP, outcome, and correlation ID.

## 9. Verification and Testing

```bash
# Run the auth test suite; each test maps to an RFC 9700 / ASVS item
pytest -q tests/security/test_authn.py tests/security/test_authz.py

# Manual probes (authorized environments only)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $USER_A_TOKEN" \
  http://localhost:8000/v1/invoices/$USER_B_INVOICE   # expect 404

# JWT tampering checks
python - <<'PY'
import jwt
t = jwt.decode(open('token.txt').read().strip(), options={"verify_signature": False})
print({k: t[k] for k in ("iss","aud","exp","sub")})
PY
```

Expected evidence: cross-tenant requests denied, expired/`alg=none` tokens rejected, reset token single-use, rate limits enforced, logs show the denials.

## 10. Security Considerations

- Treat all tokens, cookies, and headers from clients as untrusted.
- CSRF: `SameSite=Lax` plus token-based protection for state-changing requests on cookie-auth APIs.
- Do not implement custom crypto or custom JWT parsing; use vetted libraries.
- Rotate signing keys with a `kid` and overlap window; publish JWKS with cache headers.
- Prevent user enumeration in login, registration, and password reset.
- Bind reset and invite tokens to a single purpose and short TTL; store only hashes.
- Validate `redirect_uri` against an exact allowlist; reject wildcards and open redirects.
- Admin surfaces: separate domain/cookie scope, stronger session policy, IP allowlisting where feasible.
- Log authorization failures as security events; alert on spikes (credential stuffing).

## 11. Failure Handling

- **Users locked out after tightening:** provide a support path with identity verification, not a blanket bypass.
- **Legacy MD5/SHA1 hashes:** rehash on successful login; force reset for inactive accounts.
- **Session store outage:** fail closed for admin actions; never fall back to unsigned cookies.
- **JWT revocation needed but stateless:** introduce short expiry plus a revocation list keyed by `jti`, or move to opaque sessions.
- **MFA lost device:** recovery codes issued at enrollment, single-use, hashed at rest.

## 12. Expected Deliverables

1. Permission matrix (roles × resources × actions).
2. Session/token design with lifetimes and revocation semantics.
3. Implemented or patched authn/authz code.
4. Endpoint authorization audit table with results.
5. Regression tests for IDOR, token tampering, rate limits, reset flows.
6. Security logging and alerting specification.

## 13. References

- OWASP ASVS v4/v5 — https://owasp.org/www-project-application-security-verification-standard/
- OWASP Authentication Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Authorization Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- RFC 9700 OAuth 2.0 Security Best Current Practice — https://www.rfc-editor.org/rfc/rfc9700
- OpenID Connect Core — https://openid.net/specs/openid-connect-core-1_0.html
- NIST SP 800-63B — https://pages.nist.gov/800-63-4/
- OWASP WSTG — Authentication / Authorization testing — https://owasp.org/www-project-web-security-testing-guide/
