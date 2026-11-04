---
name: owasp-top-10
description: Assess and remediate applications against the OWASP Top 10 (2021)—broken access control, injection, crypto failures, SSRF—with per-category detection and concrete fixes.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: medium
---

# OWASP Top 10

## 1. Purpose

Provide a structured pass over the ten most critical web application risk categories, with category-specific detection techniques, framework-correct fixes, and verification evidence. This is the practical "are we exposed to the classics?" assessment. It is not a replacement for a full threat model or a penetration test.

**Authorization boundary:** only assess applications you own or have explicit written permission to test. Static review is always allowed on your own code; any dynamic probing requires a named scope, a time window, and an out-of-scope list.

## 2. Activation Conditions

- Baseline security assessment of a web app or API.
- Security questionnaire/review before a launch or enterprise sales cycle.
- Mapping scan results to a recognized framework for prioritization.
- Training a team on concrete failure modes present in *their* code.
- Keywords: OWASP, Top 10, A01, broken access control, A03 injection, A10 SSRF, security baseline.

## 3. When Not to Use

- Deep protocol-level or cryptographic design review (use threat-modeling and secure-code-review).
- Infrastructure/cloud posture (use cloud-security-engineering).
- Compliance certification claims—OWASP Top 10 coverage is not a compliance certificate.
- As a target list for a live external penetration test without authorization.

## 4. Required Context

1. Application architecture, routes inventory, and authentication scheme.
2. Technology stack and versions.
3. Data classification and tenancy model.
4. Existing scan reports and known exclusions.
5. Environment where testing is permitted, plus test accounts and roles (for authorized dynamic checks only).

## 5. Operating Procedure

1. **Build the route and role matrix**: endpoint × allowed roles × object ownership rules. This underpins A01.
2. **A01 Broken Access Control** — test horizontal (tenant A reading tenant B) and vertical (user reaching admin) access; verify server-side enforcement on every route; check forced browsing to hidden paths; check CORS misconfigurations.
3. **A02 Cryptographic Failures** — TLS config, hashing for passwords (Argon2id/bcrypt), encryption at rest, no secrets in URLs, `Secure`/`HttpOnly`/`SameSite` cookies.
4. **A03 Injection** — SQL (parameterization), OS command, LDAP, template (SSTI), and log injection; verify ORM escape hatches are not used with raw input.
5. **A04 Insecure Design** — missing rate limits, unlimited password attempts, business-logic abuse (negative quantities, coupon stacking), missing workflow states.
6. **A05 Security Misconfiguration** — default creds, debug mode in prod, directory listing, permissive CORS, verbose errors, unneeded features, missing security headers.
7. **A06 Vulnerable and Outdated Components** — dependency inventory and CVEs; unsupported runtimes.
8. **A07 Identification and Authentication Failures** — credential stuffing defenses, session rotation, MFA, secure recovery flows, no user enumeration.
9. **A08 Software and Data Integrity Failures** — unsigned updates, insecure deserialization, CI/CD supply chain, untrusted packages.
10. **A09 Security Logging and Monitoring Failures** — auth events, access control failures, tamper resistance, alerting, retention.
11. **A10 SSRF** — user-controlled URLs, allowlists, metadata endpoints, redirect handling, DNS rebinding.
12. **Score and prioritize** findings (severity × exploitability × data sensitivity), then produce a remediation plan with owners.

## 6. Tools and Technologies

| Category | Tools |
|---|---|
| A01 | Manual route matrix, `ffuf` (authorized), test suites for IDOR |
| A02 | `testssl.sh`, `sslyze`, `nuclei -t ssl`, openssl |
| A03 | Semgrep, CodeQL, `sqlmap` (authorized only), template probes |
| A04 | Load/abuse test scripts, business-rule test cases |
| A05 | `nuclei`, `nikto` (authorized), header analyzers (securityheaders.com equivalent local) |
| A06 | `pip-audit`, `npm audit`, `osv-scanner`, `trivy` |
| A07 | `hydra` (authorized lab), rate-limit tests, session analysis |
| A08 | `cosign`, `sigstore`, SBOM review (`syft`) |
| A09 | Log review, SIEM queries, alert simulation |
| A10 | Interactsh/self-hosted OOB, allowlist review |

## 7. Practical Implementation

**A01 — ownership enforcement (FastAPI dependency):**

```python
from fastapi import Depends, HTTPException

def owned_invoice(invoice_id: str, principal=Depends(current_principal), db=Depends(get_db)):
    row = db.execute(
        "SELECT * FROM invoices WHERE id = %s AND tenant_id = %s",
        (invoice_id, principal.tenant_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404)  # do not reveal existence
    return row
```

**A01 — deny-by-default route registration:**

```python
PUBLIC = {"/healthz", "/metrics", "/v1/login"}

@app.middleware("http")
async def require_auth(request, call_next):
    if request.url.path not in PUBLIC:
        principal = authenticate(request)     # raises 401
        request.state.principal = principal
    return await call_next(request)
```

**A02 — password hashing (Python, Argon2id):**

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

hashed = ph.hash(password)
try:
    ph.verify(hashed, candidate)
except VerifyMismatchError:
    raise InvalidCredentials
```

**A03 — parameterized query vs. string building (Node):**

```js
// VULN
const rows = await pool.query(`SELECT * FROM users WHERE email = '${email}'`);
// FIXED
const rows = await pool.query('SELECT * FROM users WHERE email = $1', [email]);
```

**A04 — rate limiting login by principal + IP (Redis):**

```python
def check_login_limit(redis, email: str, ip: str) -> None:
    for key, limit in ((f"login:email:{email}", 5), (f"login:ip:{ip}", 20)):
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, 900)
        if count > limit:
            raise TooManyAttempts(retry_after=redis.ttl(key))
```

**A05 — security headers (nginx):**

```nginx
add_header Content-Security-Policy "default-src 'self'; frame-ancestors 'none'; base-uri 'none'" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
```

**A06 — dependency scan:**

```bash
pip-audit -r requirements.txt --strict
npm audit --omit=dev --audit-level=high
osv-scanner --lockfile=package-lock.json
syft dir:. -o spdx-json > sbom.spdx.json && grype sbom:sbom.spdx.json
```

**A10 — SSRF-safe fetcher (Go):**

```go
var allowed = map[string]bool{"api.partner.com": true}

func safeClient() *http.Client {
    return &http.Client{
        Timeout: 5 * time.Second,
        CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
        Transport: &http.Transport{
            DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
                host, _, _ := net.SplitHostPort(addr)
                if !allowed[host] { return nil, fmt.Errorf("host not allowed: %s", host) }
                ip, err := net.DefaultResolver.LookupHost(ctx, host)
                if err != nil { return nil, err }
                if isPrivateIP(ip[0]) { return nil, errors.New("private address blocked") }
                var d net.Dialer
                return d.DialContext(ctx, network, addr)
            },
        },
    }
}
```

## 8. Quality Standards

- Each of the ten categories has an explicit verdict: pass, fail, or not-applicable with reason.
- Findings reference the specific CWE where possible (e.g. A01 → CWE-639 IDOR).
- Fixes are framework-idiomatic, not hand-rolled crypto or custom escaping.
- Authorization is enforced server-side; client-side hiding never counts as a control.
- Evidence is reproducible: a request/response pair or a failing test.
- Residual risk and accepted exceptions are documented with an expiry date.

## 9. Verification and Testing

- Re-run the automated scans and confirm the finding disappears.
- Write regression tests per fixed issue: cross-tenant read → 404/403; injection payload → no error leak and no data.
- Verify headers with `curl -sI https://host | grep -i -E 'content-security|strict-transport'`.
- TLS: `testssl.sh --severity HIGH https://host` and confirm no high findings.
- Logging: trigger an auth failure and confirm an audit event with actor, IP, and outcome.

## 10. Security Considerations

- Get written authorization before any active testing; define scope, window, and rate limits.
- Never test destructive payloads (`DROP TABLE`, mass account creation) on shared environments.
- Use dedicated test accounts; never reuse real user credentials.
- Out-of-band callbacks (A10) must target infrastructure you control.
- Handle findings confidentially until fixed; do not publish exploit details.
- Ensure any fix does not introduce a regression (e.g. strict CSP breaking the app) — test in staging.

## 11. Failure Handling

- **Cannot test a category:** mark "not verified" explicitly instead of "pass".
- **Fix would break clients:** ship a staged enforcement (report-only CSP, permissive then strict), with a date.
- **Findings disputed:** supply the exact request/response and the code path.
- **Legacy component cannot be upgraded:** add compensating controls (WAF rule, network restriction), document the residual risk and the migration ticket.
- **Too many findings to fix at once:** order by exploitability and data impact; fix authentication and A01/A03 first.

## 12. Expected Deliverables

1. Route × role × ownership matrix.
2. Per-category verdict table with evidence.
3. Findings with severity, CWE, location, and fix.
4. Remediation plan with owners and dates.
5. Re-test results and residual-risk register.

## 13. References

- OWASP Top 10 (2021) — https://owasp.org/Top10/
- OWASP Cheat Sheet Series — https://cheatsheetseries.owasp.org/
- OWASP ASVS — https://owasp.org/www-project-application-security-verification-standard/
- CWE Top 25 — https://cwe.mitre.org/top25/
- NIST SP 800-63B (digital identity) — https://pages.nist.gov/800-63-4/
- OWASP WSTG — https://owasp.org/www-project-web-security-testing-guide/
