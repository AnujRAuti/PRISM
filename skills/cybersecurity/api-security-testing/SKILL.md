---
name: api-security-testing
description: Test APIs for authorization bypass, injection, mass assignment, rate-limit gaps, and data exposure—with an authorized, non-destructive methodology and repeatable scripts.
metadata:
  domain: cybersecurity
  version: 1.0.0
  risk: high
---

# API Security Testing

## 1. Purpose

Validate an API's security controls using black-box and grey-box methods against the OWASP API Security Top 10. This skill provides a scope-controlled test plan, reusable probes, and evidence capture, with explicit rules that prevent destructive or unauthorized testing.

**Authorization boundary (mandatory):** only test APIs you own or have written permission to test. Record the scope, environment, window, allowed test accounts, and forbidden actions. Never test production with destructive payloads; prefer a staging environment seeded with synthetic data. If scope is unclear, stop and ask.

## 2. Activation Conditions

- Pre-release security validation of a REST/GraphQL/RPC API.
- Onboarding an inherited API, or after auth changes.
- Responding to a security questionnaire or pentest that requires an app-level pass.
- Keywords: API security, OWASP API Top 10, BOLA, BOPLA, mass assignment, rate limit test, fuzzing API, authorization testing.

## 3. When Not to Use

- Source-level review only (use secure-code-review).
- Load/performance testing (use performance-testing).
- Testing third-party APIs without contractual authorization.
- When a WAF or production dependency could be impacted and no maintenance window exists.

## 4. Required Context

1. Written authorization and scope document (in-scope hosts, excluded endpoints, time window).
2. Environment URLs and test accounts for each role (and a second tenant for isolation tests).
3. API documentation (OpenAPI spec) or the ability to enumerate endpoints.
4. Rate limits and throttling policy, so tests do not trigger account lockouts for real users.
5. Data-sensitivity map to know what constitutes a leak.
6. Escalation contact during the test window.

## 5. Operating Procedure

1. **Confirm scope in writing**; restate in-scope hosts, methods, and exclusions. Default to GET-only until explicit approval for state-changing tests.
2. **Enumerate the surface**: spec endpoints plus shadow endpoints (older API versions `/v1`, `/internal`, `/debug`, `/graphql`).
3. **Build the auth matrix**: for each endpoint, expected role requirement and object ownership rule.
4. **API1 BOLA** — access objects across users/tenants with a valid token; ID enumeration with different ID formats (UUID vs. numeric).
5. **API2 Broken Authentication** — token lifetimes, refresh flows, JWT tampering, credential stuffing resistance (rate limits without locking real accounts).
6. **API3 BOPLA / excessive data exposure** — compare response fields to what the client needs; look for `password_hash`, `internal_notes`, `ssn`, stack traces; check `?fields=`/`include=` abuse.
7. **API4 Resource consumption** — unbounded pagination, expensive filters, large payload acceptance, compression bombs, recursive GraphQL queries.
8. **API5 Broken function-level authz** — vertical escalation to admin endpoints, HTTP method swapping (`GET` allowed where `POST` is checked).
9. **API6 Business-flow abuse** — replay, coupon reuse, negative quantities, workflow state skipping.
10. **API8 Misconfiguration** — CORS, verbose errors, missing security headers, default credentials, deprecated TLS, exposed docs/admin consoles.
11. **API9 Inventory** — undocumented versions and debug routes still live.
12. **API10 Unsafe consumption** — SSRF via callbacks/URLs, trust in third-party responses.
13. **Record evidence** per probe: request (redacted), response status/length, timestamp, outcome; then write the report and retest after fixes.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Spec-based scanning | Schemathesis, `nuclei`, Postman/Newman |
| Interception | mitmproxy, Burp Suite (authorized) |
| Fuzzing | `ffuf` (allowlisted paths only), Schemathesis properties |
| JWT | `jwt_tool` |
| GraphQL | `graphql-cop`, introspection queries |
| Evidence | `httpie`, `curl -w` timings, custom pytest suite |
| CI integration | Schemathesis + pytest in a security test job |

## 7. Practical Implementation

**Non-destructive BOLA probe (two tenants):**

```bash
BASE=https://staging.example.com
TOKEN_A=$(cat .secrets/token_a)   # never echo tokens
OBJ_B=$(cat .secrets/object_b_id)

curl -s -o /tmp/out.json -w 'status=%{http_code} size=%{size_download}\n' \
  -H "Authorization: Bearer ${TOKEN_A}" \
  "${BASE}/v1/invoices/${OBJ_B}"

jq -e 'has("total_cents")' /tmp/out.json && echo "POSSIBLE BOLA: object leaked"
```

**Python probe suite (pytest), read-only by default:**

```python
import os, pytest, httpx

BASE = os.environ["API_BASE"]
A = {"Authorization": f"Bearer {os.environ['TOKEN_A']}"}
B_OBJ = os.environ["OBJECT_B_ID"]

@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        yield c

def test_bola_read_other_tenant(client):
    r = client.get(f"/v1/invoices/{B_OBJ}", headers=A)
    assert r.status_code in (403, 404), f"BOLA: got {r.status_code}"
    assert "total_cents" not in r.text

def test_no_sensitive_fields_in_listing(client):
    r = client.get("/v1/users", headers=A, params={"limit": 5})
    assert r.status_code == 200
    body = r.text.lower()
    for leak in ("password_hash", "ssn", "internal_notes", "api_key"):
        assert leak not in body

def test_http_method_not_allowed(client):
    r = client.request("PUT", f"/v1/invoices/{B_OBJ}", headers=A, json={"total_cents": 1})
    assert r.status_code in (403, 404, 405)
```

**Mass assignment probe:**

```bash
curl -s -X PATCH "${BASE}/v1/users/me" \
  -H "Authorization: Bearer ${TOKEN_ME}" -H 'Content-Type: application/json' \
  -d '{"display_name":"x","role":"admin","is_verified":true}' | jq .
# Expect: 400 unknown field, or 200 with role unchanged.
```

**GraphQL introspection and depth limit check:**

```bash
curl -s "${BASE}/graphql" -H "Authorization: Bearer ${TOKEN_A}" \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ __schema { types { name } } }"}' | jq -r '.data.__schema.types[].name' | head

# Depth-bomb (authorized, low volume): expect rejection, not 200
curl -s "${BASE}/graphql" -H "Authorization: Bearer ${TOKEN_A}" -H 'Content-Type: application/json' \
  -d '{"query":"{ a { a { a { a { a { a { a { id } } } } } } } }"}' -o /dev/null -w '%{http_code}\n'
```

**Rate-limit verification (careful, low volume, test account):**

```bash
for i in $(seq 1 25); do
  curl -s -o /dev/null -w '%{http_code} ' -X POST "${BASE}/v1/auth/login" \
    -H 'Content-Type: application/json' -d '{"email":"test@example.com","password":"wrong"}'
done; echo
# Expect a 429 (and Retry-After) before 25 attempts.
```

**CORS misconfiguration check:**

```bash
curl -s -I -X OPTIONS "${BASE}/v1/orders" \
  -H 'Origin: https://evil.example' \
  -H 'Access-Control-Request-Method: GET' | grep -i 'access-control-'
# Must not return Access-Control-Allow-Origin: https://evil.example with credentials.
```

## 8. Quality Standards

- Every test has an expected result stated before execution.
- Evidence includes full request/response (with secrets redacted) and timestamps.
- Tests are idempotent and clean up any state they create.
- Findings include severity, exact endpoint, reproduction steps, and business impact.
- No finding is reported without a reproducible request.
- Scope violations trigger immediate stop, not "one more check".

## 9. Verification and Testing

- Re-run the probe suite after fixes; each vulnerability has a regression test.
- Confirm the fix at the control point (e.g. authorization in SQL, not UI hiding).
- Verify negative cases too: legitimate access still works, so the fix did not over-block.
- Check logs during testing to confirm security events are recorded.
- Evidence: before/after HTTP status codes and bodies, pytest output, CI job link.

## 10. Security Considerations

- Never use real user accounts or production PII; use seeded synthetic data.
- Avoid denial-of-service-inducing payloads (huge arrays, deep recursion at scale) unless explicitly approved with monitoring.
- Redact tokens and cookies in all reports and terminal history (`set +o history` for sensitive commands).
- Do not exfiltrate data beyond the minimum needed to prove the issue; capture one record, not the table.
- Stop immediately if you observe other users' production data or evidence of an active compromise; notify the contact.
- Treat API responses and error messages as untrusted input in your tooling (no `eval`).

## 11. Failure Handling

- **Rate-limited during testing:** back off, request an allowlist for the test IP, and reduce concurrency.
- **Unexpected 500s during normal probes:** stop and report; you may have found a real defect or a fragile path.
- **Auth keeps expiring:** automate token refresh in the fixture; do not hardcode long-lived admin tokens.
- **Cannot distinguish 403 vs 404:** record the actual behavior; both can be acceptable, but consistency matters.
- **Findings disputed:** provide the raw request and the parallel control request that should have behaved differently.

## 12. Expected Deliverables

1. Authorization and scope record.
2. Endpoint inventory and role matrix.
3. Probe suite (code) and execution log.
4. Findings report with severity and reproduction steps.
5. Fix verification results.
6. Residual risks and recommendations (rate limits, schema validation, monitoring).

## 13. References

- OWASP API Security Top 10 — https://owasp.org/API-Security/
- OWASP Web Security Testing Guide — https://owasp.org/www-project-web-security-testing-guide/
- Schemathesis — https://schemathesis.readthedocs.io/
- RFC 9700 OAuth 2.0 Security BCP — https://www.rfc-editor.org/rfc/rfc9700
- PortSwigger Web Security Academy (authorization labs) — https://portswigger.net/web-security
- NIST SP 800-115 (technical security testing) — https://csrc.nist.gov/pubs/sp/800/115/final
