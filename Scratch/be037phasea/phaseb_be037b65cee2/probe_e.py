"""BE-037 Phase B Stage E — API integration probe.

Runs INSIDE be037b65cee2_client (the disposable internal network only).
Everything it touches belongs to run be037b65cee2. No host, no internet route
exists from this container (`internal: true` network), and no protected
database or container is reachable by name.
"""
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://api:8000"
RESULTS = []
SUFFIX = uuid.uuid4().hex[:8]


def call(method, path, token=None, body=None, origin=None, raw=None, content_type=None):
    url = BASE + path
    data = None
    headers = {}
    if raw is not None:
        data = raw
        headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = r.read()
            ctype = r.headers.get("Content-Type", "")
            parsed = None
            if "json" in ctype:
                try:
                    parsed = json.loads(payload)
                except Exception:
                    parsed = None
            return r.status, dict(r.headers), parsed, payload
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            parsed = json.loads(payload)
        except Exception:
            parsed = None
        return e.code, dict(e.headers), parsed, payload


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(("PASS  " if ok else "FAIL  ") + name + ("  | " + str(detail) if detail else ""), flush=True)


def expect(name, method, path, status, **kw):
    code, hdrs, parsed, raw = call(method, path, **kw)
    ok = code == status
    detail = f"HTTP {code} (expected {status})"
    if parsed is not None and not ok:
        detail += " body=" + json.dumps(parsed)[:300]
    check(name, ok, detail)
    return code, hdrs, parsed


print("=== E1  process / HTTP surface ===")
for p in ("/health", "/healthz", "/ready", "/api/v1/health"):
    expect(f"E1 {p} returns 200", "GET", p, 200)
code, hdrs, parsed, raw = call("GET", "/ready")
checks = (parsed or {}).get("checks", {})
dep_ok = all(
    checks.get(k, {}).get("status") == "healthy" for k in ("postgresql", "redis", "storage")
)
check(
    "E1 /ready reports postgresql+redis+storage healthy",
    dep_ok,
    {k: v.get("status") for k, v in checks.items()},
)
check("E1 /ready marks those checks required=true",
      all(checks.get(k, {}).get("required") is True for k in ("postgresql", "redis", "storage")),
      {k: checks.get(k, {}).get("required") for k in ("postgresql", "redis", "storage")})

print()
print("=== E2a  authorization bootstrap through the real API path ===")
org_code, _, org = expect(
    "E2 anonymous POST /auth/organizations succeeds in development mode (dev bypass)",
    "POST", "/api/v1/auth/organizations", 201,
    body={"name": f"BE-037 Phase B Disposable Org {SUFFIX}", "code": f"be037b-org-{SUFFIX}"},
)
org_id = (org or {}).get("id")
user_code, _, user = expect(
    "E2 anonymous POST /auth/users creates a disposable test user",
    "POST", "/api/v1/auth/users", 201,
    body={"username": f"be037b_admin_{SUFFIX}",
          "email": f"be037b-admin-{SUFFIX}@example.invalid"},
)
user_id = (user or {}).get("id")
print("   synthetic org_id=", org_id, "user_id=", user_id)
expect("E2 anonymous POST /auth/users/{id}/roles grants ADMINISTRATOR GLOBAL",
       "POST", f"/api/v1/auth/users/{user_id}/roles", 201,
       body={"role_name": "ADMINISTRATOR", "scope_type": "GLOBAL"})

ADMIN_TOKEN = f"dev-user-{user_id}"
code, hdrs, me, _raw = call("GET", "/api/v1/auth/me", token=ADMIN_TOKEN)
check("E2 valid dev bearer token authenticates on a guarded endpoint",
      code == 200 and (me or {}).get("id") == user_id
      and (me or {}).get("authenticated") is True
      and (me or {}).get("status") == "ACTIVE",
      f"HTTP {code} " + json.dumps(me)[:200])

print()
print("=== E2b  credential rejection matrix ===")
expect("E2 unknown dev-user uuid is rejected", "GET", "/api/v1/auth/me", 401,
       token=f"dev-user-{uuid.uuid4()}")
expect("E2 malformed bearer token is rejected", "GET", "/api/v1/auth/me", 401,
       token="not-a-dev-token")
expect("E2 non-uuid dev-user suffix is rejected", "GET", "/api/v1/auth/me", 401,
       token="dev-user-notauuid")
expect("E2 api-client shaped token with unknown client is rejected", "GET", "/api/v1/auth/me", 401,
       token=f"{uuid.uuid4()}:disposable-secret")
code, hdrs, parsed, _raw = call("GET", "/api/v1/projects?limit=1")
print(f"OBSERVE development-mode anonymous bypass on guarded GET /projects -> HTTP {code} "
      f"(this bypass is why AUTH_MODE=enforcing is required in production)")

print()
print("=== E2c  CORS allowlist ===")
code, hdrs, _, _raw = call("GET", "/health", origin="http://be037b-client.invalid")
acao = hdrs.get("access-control-allow-origin") or hdrs.get("Access-Control-Allow-Origin")
check("E2 configured origin is allowed by CORS", acao == "http://be037b-client.invalid",
      f"Access-Control-Allow-Origin={acao}")
code, hdrs, _, _raw = call("GET", "/health", origin="http://evil.example")
acao2 = hdrs.get("access-control-allow-origin") or hdrs.get("Access-Control-Allow-Origin")
check("E2 unconfigured origin is NOT granted CORS", acao2 is None,
      f"Access-Control-Allow-Origin={acao2!r}")

print()
print("=== E3  database-backed operations (synthetic data only) ===")
expect("E3 ADMINISTRATOR alone cannot create a project (needs project.create)",
       "POST", "/api/v1/projects", 403, token=ADMIN_TOKEN,
       body={"name": "BE-037 Phase B Synthetic Project", "owner_id": user_id})
expect("E3 grant SUPERVISOR (project.create) to the test user", "POST",
       f"/api/v1/auth/users/{user_id}/roles", 201, token=ADMIN_TOKEN,
       body={"role_name": "SUPERVISOR", "scope_type": "GLOBAL"})
expect("E3 grant FIELD_OFFICER (evidence.create) to the test user", "POST",
       f"/api/v1/auth/users/{user_id}/roles", 201, token=ADMIN_TOKEN,
       body={"role_name": "FIELD_OFFICER", "scope_type": "GLOBAL"})
code, hdrs, proj = expect("E3 authenticated POST /projects creates a record",
                          "POST", "/api/v1/projects", 201, token=ADMIN_TOKEN,
                          body={"name": "BE-037 Phase B Synthetic Project",
                                "owner_id": user_id})
project_id = (proj or {}).get("id")
print("   synthetic project_id=", project_id)
code, hdrs, listed, _raw = call("GET", "/api/v1/projects?limit=1&offset=0", token=ADMIN_TOKEN)
check("E3 GET /projects returns a paginated list", code == 200 and listed is not None,
      f"HTTP {code} keys=" + json.dumps(listed)[:200])
code, hdrs, one = expect("E3 GET /projects/{id} retrieves the created record",
                         "GET", f"/api/v1/projects/{project_id}", 200, token=ADMIN_TOKEN)
check("E3 retrieved record matches", (one or {}).get("id") == project_id,
      json.dumps(one)[:200])
expect("E3 malformed project uuid returns 422", "GET", "/api/v1/projects/not-a-uuid",
       422, token=ADMIN_TOKEN)
expect("E3 unknown-but-valid project uuid returns 404", "GET",
       f"/api/v1/projects/{uuid.uuid4()}", 404, token=ADMIN_TOKEN)

# --- pagination shape and total-after-slicing (BE-025 control) ---
code2, _, proj2, _raw = call("POST", "/api/v1/projects", token=ADMIN_TOKEN, body={
    "name": f"BE-037 Phase B Synthetic Project 2 ({SUFFIX})", "owner_id": user_id})
project2_id = (proj2 or {}).get("id")
code, _, page0, _raw = call("GET", "/api/v1/projects?limit=1&offset=0", token=ADMIN_TOKEN)
code, _, page1, _raw = call("GET", "/api/v1/projects?limit=1&offset=1", token=ADMIN_TOKEN)
code, _, allp, _raw = call("GET", "/api/v1/projects?limit=100&offset=0", token=ADMIN_TOKEN)
total = (allp or {}).get("total")
check("E3 pagination reports total for the whole set, not the sliced page",
      (page0 or {}).get("total") == total and len((page0 or {}).get("items", [])) == 1,
      f"page.total={(page0 or {}).get('total')} page.items={len((page0 or {}).get('items', []))} full.total={total}")
check("E3 offset advances the window to a different record",
      (page0 or {}).get("items", [{}])[0].get("id") != (page1 or {}).get("items", [{}])[0].get("id"),
      f"page0={(page0 or {}).get('items', [None])[0].get('id')} page1={(page1 or {}).get('items', [None])[0].get('id')}")
check("E3 response shape is {items, limit, offset, total}",
      set(["items", "limit", "offset", "total"]) <= set((allp or {}).keys()),
      sorted((allp or {}).keys()))

print()
print("=== E3b  geospatial input validation ===")
expect("E3 nearby with non-numeric latitude is rejected", "GET",
       "/api/v1/evidence/nearby?latitude=abc&longitude=1&radius=100", 422, token=ADMIN_TOKEN)
expect("E3 nearby with out-of-range latitude is rejected", "GET",
       "/api/v1/evidence/nearby?latitude=95&longitude=1&radius=100", 422,
       token=ADMIN_TOKEN)
expect("E3 nearby with negative radius is rejected", "GET",
       "/api/v1/evidence/nearby?latitude=1&longitude=1&radius=-5", 422, token=ADMIN_TOKEN)
code, hdrs, nearby, _raw = call("GET", "/api/v1/evidence/nearby?latitude=37.5&longitude=127.0&radius=1000",
                          token=ADMIN_TOKEN)
check("E3 nearby with valid geometry is accepted", code == 200,
      f"HTTP {code} " + json.dumps(nearby)[:200])

print()
print("=== E3c  audit events generated by the exercised paths ===")
code, hdrs, audit, _raw = call("GET", "/api/v1/audit/events?limit=5", token=ADMIN_TOKEN)
print("   audit read ->", code, json.dumps(audit)[:300] if audit is not None else "")
check("E3 audit events readable through the supported API path", code == 200, f"HTTP {code}")

print()
print("=== SUMMARY ===")
total = len(RESULTS)
passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
failed = total - passed
for name, status, detail in RESULTS:
    if status == "FAIL":
        print("FAILING CHECK:", name, "|", detail)
print(f"E_RESULT: total={total} pass={passed} fail={failed}")
