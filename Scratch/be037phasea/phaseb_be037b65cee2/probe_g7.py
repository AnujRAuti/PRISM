"""BE-037 Phase B Stage G (run E) — retention policy -> archive -> audit -> webhook chain.

Age was injected on one disposable evidence row (created_at moved back 10 days via
the owner role on the disposable database) because PolicyRules require
retention_days > 0 and resources ingested minutes ago can never be aged out.

retention_states was 0 rows before this run; that baseline is recorded separately.
"""
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://api:8000"
EVIDENCE_ID = "988d9235-c13a-47c9-805c-6b2869b059eb"
RESULTS = []
ARTIFACT = {}


def call(method, path, token=None, data=None):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and "json" in r.headers.get("Content-Type", "") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:220].decode("utf-8", "replace")}
    except Exception as e:
        return -1, {"_err": type(e).__name__ + ": " + str(e)[:150]}


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail), flush=True)


def make_user(role, prefix):
    code, u = call("POST", "/api/v1/auth/users", data={
        "username": f"be037b_{prefix}_{uuid.uuid4().hex[:8]}",
        "email": f"be037b-{prefix}-{uuid.uuid4().hex[:8]}@example.invalid"})
    uid = u.get("id")
    if role:
        call("POST", f"/api/v1/auth/users/{uid}/roles",
             data={"role_name": role, "scope_type": "GLOBAL"})
    return uid, f"dev-user-{uid}"


ADMIN_ID, ADMIN = make_user("ADMINISTRATOR", "gEadm")
FO_ID, FO = make_user("FIELD_OFFICER", "gEfo")

print("=== G-E1 policy identity + version + activation ===")
code, pol = call("POST", "/api/v1/retention/policies", token=ADMIN, data={
    "name": f"BE-037B disposable policy {uuid.uuid4().hex[:6]}",
    "resource_type": "EVIDENCE", "scope_type": "GLOBAL"})
POL_ID = (pol or {}).get("id")
check("G-E1 retention policy created", code in (200, 201) and POL_ID,
      f"HTTP {code} " + json.dumps({k: v for k, v in (pol or {}).items()
                                    if k in {"id", "resource_type", "scope_type", "status"}})[:160])

code, ver = call("POST", f"/api/v1/retention/policies/{POL_ID}/versions", token=ADMIN, data={
    "rules": {"retention_days": 30, "archive_after_days": 1,
              "anchor": "INGESTED_AT", "allow_derived_cleanup": False}})
VER_ID = (ver or {}).get("id")
check("G-E1 policy version created", code in (200, 201) and VER_ID, f"HTTP {code} " + json.dumps(ver)[:160])

code, act = call("POST", f"/api/v1/retention/policies/versions/{VER_ID}/activate", token=ADMIN, data={})
check("G-E1 policy version activated", code in (200, 201, 204), f"HTTP {code} " + json.dumps(act)[:160])
ARTIFACT.update({"policy_id": POL_ID, "version_id": VER_ID})

print("\n=== G-E2 dry-run evaluation now sees an applicable policy for an aged resource ===")
code, ev = call("POST", "/api/v1/retention/evaluate", token=ADMIN,
                data={"resource_type": "EVIDENCE", "resource_id": EVIDENCE_ID})
check("G-E2 evaluate returns 200 with the policy attached", code == 200, f"HTTP {code} " + json.dumps(ev)[:220])
check("G-E2 aged evidence is archive_eligible under the activated policy",
      bool((ev or {}).get("archive_eligible")), f"archive_eligible={(ev or {}).get('archive_eligible')} "
      f"blocking={json.dumps((ev or {}).get('blocking_reasons'))[:120]}")

print("\n=== G-E3 FIELD_OFFICER must not be able to archive (permission boundary) ===")
code, denied = call("POST", f"/api/v1/retention/archive/EVIDENCE/{EVIDENCE_ID}", token=FO, data={})
check("G-E3 archive denied for FIELD_OFFICER", code in (403, 401), f"HTTP {code} " + json.dumps(denied)[:120])

print("\n=== G-E4 archive action through the authenticated administrator path ===")
code, ar = call("POST", f"/api/v1/retention/archive/EVIDENCE/{EVIDENCE_ID}", token=ADMIN, data={})
check("G-E4 archive accepted", code in (200, 201, 202), f"HTTP {code} " + json.dumps(ar)[:260])
ARTIFACT["archive_response"] = {k: v for k, v in (ar or {}).items()
                                if isinstance(v, (str, int, float, type(None)))} if isinstance(ar, dict) else str(ar)[:200]

print("\n=== G-E5 re-evaluate + resource detail reflect the archived state ===")
code, ev2 = call("POST", "/api/v1/retention/evaluate", token=ADMIN,
                 data={"resource_type": "EVIDENCE", "resource_id": EVIDENCE_ID})
print("   OBSERVE post-archive evaluation ->", f"HTTP {code}", json.dumps(ev2)[:220])
code, res = call("GET", f"/api/v1/retention/resources/EVIDENCE/{EVIDENCE_ID}", token=ADMIN)
check("G-E5 retention resource detail readable after archive", code == 200, f"HTTP {code} " + json.dumps(res)[:220])
code, ops = call("GET", "/api/v1/retention/operations", token=ADMIN)
ops_list = ops if isinstance(ops, list) else (ops or {}).get("items", [])
check("G-E5 an ARCHIVE operation row was recorded",
      any((o or {}).get("operation") == "ARCHIVE" for o in ops_list),
      f"HTTP {code} operations={len(ops_list)} " + json.dumps([o.get('operation') for o in ops_list])[:120])

print("\n=== ARTIFACTS ===")
print(json.dumps(ARTIFACT, indent=2))
t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"\nG_RESULT_E: total={t} pass={p} fail={t-p}")
for n, s, d in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", d)
