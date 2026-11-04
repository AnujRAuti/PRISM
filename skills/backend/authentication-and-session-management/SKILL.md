---
name: authentication-and-session-management
description: Implement backend authentication and sessions correctly—password hashing, session cookies vs. tokens, rotation, revocation, MFA, and account recovery.
metadata:
  domain: backend
  version: 1.0.0
  risk: high
---

# Authentication and Session Management

## 1. Purpose

Establish who a caller is, keep that state secure over time, and end it reliably. Authentication bugs are the highest-severity class in web applications: stolen cookies, non-revocable JWTs, session fixation, missing rotation, and unsafe password recovery. This skill covers credential storage, session versus token strategy, cookie flags, rotation and revocation, MFA, recovery flows, and the tests that prove them.

**Scope:** authentication for systems you own. Never test credential attacks against systems you do not own or lack written authorization for. Do not implement your own cryptography: use vetted libraries and platform session primitives.

## 2. Activation Conditions

- Adding login, sessions, or token issuance to a service.
- Replacing a home-grown auth scheme.
- Security review finding session or token weaknesses.
- Adding MFA, SSO, or "log out everywhere".
- Keywords: authentication, session, cookie, JWT, refresh token, password hashing, Argon2, bcrypt, MFA, TOTP, WebAuthn, rotation, revocation, CSRF, session fixation, OAuth.

## 3. When Not to Use

- Authorization policy (permissions/roles) — separate concern (see agent-permission-management for agent contexts or your policy layer).
- Service-to-service identity using mTLS/SPIFFE (infrastructure-level).
- Full OAuth/OIDC provider implementation — use a maintained identity provider.

## 4. Required Context

1. Client types: browser, mobile, server-to-server, CLI.
2. Threat model: XSS, CSRF, token theft, session replay.
3. Compliance needs (data retention, MFA requirements).
4. Existing identity provider (Okta, Auth0, Keycloak, Cognito).
5. Session lifetime and revocation requirements.

## 5. Operating Procedure

1. **Choose the mechanism by client**:
   - Browser first-party: `HttpOnly`, `Secure`, `SameSite=Lax` session cookie backed by server-side state.
   - Mobile/CLI: short-lived access token + rotating refresh token in secure storage.
   - Third-party API: OAuth 2.1 with PKCE; never the implicit flow.
2. **Hash passwords with Argon2id** (or bcrypt at cost ≥ 12 as a minimum); never SHA-256/MD5; salt per password; enforce a minimum length (12+) and check against a breach corpus.
3. **Create sessions server-side**: random 128-bit+ identifier, stored hashed in the database, with creation time, last-seen, IP/user-agent (informational only), and absolute + idle expiry.
4. **Rotate the session ID on privilege change** (login, MFA completion, password change) to prevent session fixation.
5. **Set cookie flags** and scope: `HttpOnly; Secure; SameSite=Lax; Path=/; __Host-` prefix where possible.
6. **Protect state-changing requests from CSRF**: `SameSite` plus a double-submit or synchronizer token for cross-site flows.
7. **Issue short-lived access tokens (≤ 15 min) with revocation support**: maintain a token/session version per user so "log out everywhere" actually works.
8. **Store refresh tokens hashed with rotation** and reuse detection: a reused token invalidates the whole family.
9. **Support MFA (TOTP or WebAuthn)** and require step-up for sensitive actions; store recovery codes hashed, single-use.
10. **Design recovery safely**: single-use, short-TTL, hashed tokens delivered out-of-band; identical response time and message whether or not the account exists.
11. **Rate-limit and lock out** credential guessing with per-account and per-IP counters; use constant-time comparison for secrets.
12. **Log security events** (login success/failure, MFA changes, token revocation) without logging credentials or raw tokens.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Password hashing | Argon2 (`argon2-cffi`), bcrypt (`passlib`), scrypt |
| Sessions | Server-side session store (Redis/DB), `starlette.middleware.sessions`, `express-session` |
| Tokens | `PyJWT`, `jose`, `jsonwebtoken`; asymmetric signing (EdDSA/ES256) |
| MFA | `pyotp`, WebAuthn (`webauthn` libs, SimpleWebAuthn) |
| Identity provider | Keycloak, Auth0, Okta, Cognito, Zitadel |
| Breach corpora | Have I Been Pwned k-anonymity API |
| Testing | `pytest` + `httpx`, Playwright e2e login flows |

## 7. Practical Implementation

**Password hashing with Argon2id:**

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)   # tune to ~100-250 ms

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(stored_hash: str, password: str) -> tuple[bool, str | None]:
    try:
        ph.verify(stored_hash, password)
        return True, (ph.hash(password) if ph.check_needs_rehash(stored_hash) else None)
    except (VerifyMismatchError, VerificationError):
        return False, None
```

**Login with rotation and constant-time behavior:**

```python
import hmac, secrets
from datetime import datetime, timedelta, timezone

SESSION_TTL = timedelta(days=14)
IDLE_TTL = timedelta(hours=12)

async def login(conn, email: str, password: str, request) -> tuple[str, str]:
    user = await conn.fetchrow("SELECT id, password_hash, is_active FROM app_user WHERE email = $1", email.lower())

    # Verify against a dummy hash when the user is missing to equalize timing
    stored = user["password_hash"] if user else DUMMY_HASH
    ok, new_hash = verify_password(stored, password)

    if not user or not ok or not user["is_active"]:
        await record_auth_event(conn, email, "login_failed", request)
        raise InvalidCredentials()          # identical error for all failure modes

    if new_hash:
        await conn.execute("UPDATE app_user SET password_hash = $2 WHERE id = $1", user["id"], new_hash)

    session_id = secrets.token_urlsafe(32)                       # 256 bits of entropy
    await conn.execute(
        """INSERT INTO session (id_hash, user_id, created_at, last_seen_at, expires_at, ua, ip)
           VALUES ($1, $2, now(), now(), $3, $4, $5)""",
        sha256(session_id), user["id"], datetime.now(timezone.utc) + SESSION_TTL,
        request.headers.get("user-agent", "")[:255], request.client.host,
    )
    await record_auth_event(conn, email, "login_success", request)
    return session_id, set_session_cookie(session_id)
```

**Session cookie flags:**

```python
def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        key="__Host-sid",
        value=session_id,
        max_age=14 * 24 * 3600,
        httponly=True,          # not readable by JavaScript (mitigates XSS token theft)
        secure=True,            # HTTPS only
        samesite="lax",         # blocks cross-site POST; use "strict" for admin panels
        path="/",
    )
```

**Session validation middleware with idle and absolute expiry:**

```python
async def current_user(request, conn) -> Principal | None:
    raw = request.cookies.get("__Host-sid")
    if not raw:
        return None
    row = await conn.fetchrow(
        """SELECT s.user_id, s.created_at, s.last_seen_at, s.expires_at, s.revoked_at, u.role
           FROM session s JOIN app_user u ON u.id = s.user_id
           WHERE s.id_hash = $1""",
        sha256(raw),
    )
    now = datetime.now(timezone.utc)
    if row is None or row["revoked_at"] is not None or row["expires_at"] < now:
        return None
    if row["last_seen_at"] < now - IDLE_TTL:
        return None
    await conn.execute("UPDATE session SET last_seen_at = now() WHERE id_hash = $1", sha256(raw))
    return Principal(user_id=row["user_id"], role=row["role"])
```

**Refresh token rotation with reuse detection:**

```python
async def rotate_refresh(conn, presented: str) -> tuple[str, str]:
    token_hash = sha256(presented)
    row = await conn.fetchrow(
        """SELECT id, family_id, user_id, used_at, revoked_at, expires_at
           FROM refresh_token WHERE token_hash = $1 FOR UPDATE""",
        token_hash,
    )
    if row is None:
        raise InvalidToken()

    if row["used_at"] is not None:                    # replay of a rotated token
        await conn.execute("UPDATE refresh_token SET revoked_at = now() WHERE family_id = $1", row["family_id"])
        raise TokenReuseDetected()

    if row["revoked_at"] is not None or row["expires_at"] < now():
        raise InvalidToken()

    await conn.execute("UPDATE refresh_token SET used_at = now() WHERE id = $1", row["id"])

    new_raw = secrets.token_urlsafe(48)
    await conn.execute(
        """INSERT INTO refresh_token (token_hash, family_id, user_id, expires_at)
           VALUES ($1, $2, $3, now() + interval '30 days')""",
        sha256(new_raw), row["family_id"], row["user_id"],
    )
    return issue_access_token(row["user_id"]), new_raw
```

**Access token (JWT) with a session version for revocation:**

```python
import jwt
from datetime import datetime, timedelta, timezone

def issue_access_token(user_id: str, session_version: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "sv": session_version, "iat": now, "exp": now + timedelta(minutes=10),
         "iss": "https://api.example.com", "aud": "example-api", "jti": secrets.token_hex(8)},
        PRIVATE_KEY, algorithm="ES256", headers={"kid": "2026-11"},
    )

def verify_access_token(token: str, expected_version: int) -> dict:
    claims = jwt.decode(token, PUBLIC_KEY, algorithms=["ES256"],
                        audience="example-api", issuer="https://api.example.com",
                        options={"require": ["exp", "iat", "sub", "aud", "iss"]})
    if claims.get("sv") != expected_version:
        raise InvalidToken("session revoked")
    return claims
```

**TOTP MFA enrollment and verification:**

```python
import pyotp

def start_mfa(user_email: str) -> tuple[str, str]:
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user_email, issuer_name="Example")
    return secret, uri          # store secret encrypted; show QR of uri

def verify_mfa(secret: str, code: str) -> bool:
    # valid_window=1 tolerates one 30 s step of clock skew
    return pyotp.TOTP(secret).verify(code, valid_window=1)
```

**Recovery flow with equal responses:**

```python
async def request_password_reset(conn, email: str) -> None:
    user = await conn.fetchrow("SELECT id FROM app_user WHERE email = $1", email.lower())
    if user:
        raw = secrets.token_urlsafe(32)
        await conn.execute(
            """INSERT INTO password_reset (token_hash, user_id, expires_at)
               VALUES ($1, $2, now() + interval '30 minutes')""",
            sha256(raw), user["id"],
        )
        await send_email(email, f"https://app.example.com/reset?token={raw}")
    # Always return the same response and similar latency, regardless of account existence
```

**CSRF for cookie-based sessions:**

```python
def require_csrf(request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get("csrf", "")
    if not (header and cookie and hmac.compare_digest(header, cookie)):
        raise HTTPException(403, "CSRF validation failed")
```

**"Log out everywhere":**

```python
async def revoke_all_sessions(conn, user_id: str) -> None:
    await conn.execute(
        """UPDATE session SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL""", user_id)
    await conn.execute(
        """UPDATE refresh_token SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL""", user_id)
    await conn.execute(
        "UPDATE app_user SET session_version = session_version + 1 WHERE id = $1", user_id)
```

## 8. Quality Standards

- Passwords hashed with Argon2id (bcrypt ≥ 12 cost acceptable); rehash on login when parameters change.
- Session identifiers ≥ 128 bits of entropy, stored hashed, rotated at login and privilege change.
- Cookies are `HttpOnly`, `Secure`, `SameSite`, and `__Host-` prefixed on HTTPS-only deployments.
- Access tokens are short-lived and revocable via session version or a deny-list; no long-lived JWTs without revocation.
- Refresh tokens rotate, are stored hashed, and trigger family revocation on reuse.
- Authentication failures are indistinguishable (message and timing) across wrong password, missing user, and disabled account.
- Rate limiting applies to login, MFA, reset, and token endpoints.
- Every auth event is logged with actor, IP, user agent, and outcome—never with secrets.

## 9. Verification and Testing

- Timing test: missing user vs. wrong password response times are within ~10% over 1,000 requests.
- Fixation test: capture the pre-login session ID, log in, confirm it changed.
- Replay test: use a refresh token twice; the second attempt must revoke the family and return the same error shape.
- Revocation test: after "log out everywhere", an old access token is rejected within one token TTL (or immediately if you check the version).
- Cookie test: assert `HttpOnly`, `Secure`, `SameSite` in the `Set-Cookie` header; confirm JS cannot read it.
- CSRF test: a state-changing request without the token header returns 403.
- Rate-limit test: N+1 failed logins trigger throttling without locking out a legitimate user from a different IP incorrectly.
- MFA test: enrollment, verification with clock skew, and single-use recovery codes.

## 10. Security Considerations

- Never build your own crypto primitives, token formats, or "encryption" schemes; use vetted libraries.
- Session store compromise equals account compromise: isolate Redis/DB credentials and encrypt sensitive columns.
- JWT pitfalls: reject `alg: none`, verify `iss`/`aud`/`exp`, pin algorithms, and never trust header values for key selection without a key map.
- Do not put PII or authorization decisions solely inside a JWT claim that cannot be revoked; treat `role` in a token as a hint validated server-side.
- Store secrets (TOTP seeds, refresh tokens, reset tokens) hashed/encrypted; reset tokens single-use.
- Guard against account enumeration in login, registration, and recovery.
- Subdomain cookie scope: set cookies on the narrowest domain; a compromised sibling subdomain can otherwise read them.
- Enforce HTTPS + HSTS; never transmit credentials over HTTP even in internal networks.

## 11. Failure Handling

- **Users randomly logged out:** idle TTL too short, or `last_seen_at` updates failing. Separate idle vs. absolute expiry and monitor.
- **Session table grows unbounded:** add a cleanup job deleting expired/revoked rows, and index `expires_at`.
- **Token theft suspected:** revoke the family, bump `session_version`, and force re-authentication for sensitive actions.
- **Clock skew breaks TOTP:** allow `valid_window=1` and show the user accurate server time guidance.
- **Identity provider outage:** define a fallback (cached JWKS with short TTL, circuit-breaker behavior) and communicate status.
- **Migration from a legacy scheme:** dual-write hashes, rehash on next successful login, and remove the legacy path after the coverage window.

## 12. Expected Deliverables

1. Authentication flow diagram per client type.
2. Credential storage and hashing policy.
3. Session/token schema with lifetimes and revocation.
4. Cookie and CSRF configuration.
5. MFA and recovery flows.
6. Security event logging schema.
7. Test suite covering fixation, replay, revocation, and enumeration.

## 13. References

- OWASP Authentication Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP Password Storage Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- NIST SP 800-63B (Digital Identity Guidelines) — https://pages.nist.gov/800-63-4/
- OAuth 2.0 Security Best Current Practice (RFC 9700) — https://www.rfc-editor.org/rfc/rfc9700
- JSON Web Token Best Current Practices (RFC 8725) — https://www.rfc-editor.org/rfc/rfc8725
- MDN Set-Cookie / SameSite — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
- WebAuthn specification — https://www.w3.org/TR/webauthn-3/
