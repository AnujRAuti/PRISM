"""BE-037 Phase B Stage G (run C) — webhook fanout + dispute/notification integration.

Measured through the running API only; the webhook worker is executed separately so
each step's DB effect is attributable. Secrets are never printed.
"""
import json
import urllib.error
import urllib.request
import uuid

BASE = "http://api:8000"
EVIDENCE_ID = "7f703702-7976-4070-9215-5536e967245b"
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
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and "json" in r.headers.get("Content-Type", "") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:200].decode("utf-8", "replace")}
    except Exception as e:
        return -1, {"_err": type(e).__name__ + ": " + str(e)[:160]}


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


ADMIN_ID, ADMIN = make_user("ADMINISTRATOR", "g6adm")
SUP_ID, SUP = make_user("SUPERVISOR", "g6sup")
REV_ID, REV = make_user("REVIEWER", "g6rev")
FO_ID, FO = make_user("FIELD_OFFICER", "g6fo")

print("=== G6a registration of an external system (integration.manage) ===")
code, sys1 = call("POST", "/api/v1/integrations/systems", token=ADMIN, data={
    "name": "BE-037B disposable sink", "code": f"BE037B_{uuid.uuid4().hex[:6]}",
    "system_type": "GENERIC_WEBHOOK"})
check("G6a external system registered", code == 201, f"HTTP {code} " + json.dumps(sys1)[:120])
SYS_ID = (sys1 or {}).get("id")
ARTIFACT["external_system_id"] = SYS_ID

print("\n=== G6b SSRF boundary at the subscription API (no sink may be reachable) ===")
private_sinks = [
    ("loopback", "http://127.0.0.1:9099/hook"),
    ("docker-bridge-gw", "http://172.18.0.1:9099/hook"),
    ("container-alias", "http://api:8000/hook"),
    ("cloud-metadata", "http://169.254.169.254/latest/meta-data/"),
    ("rfc1918-10", "http://10.0.5.9:9099/hook"),
]
for label, url in private_sinks:
    code, body = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
        "external_system_id": SYS_ID, "endpoint_url": url,
        "subscribed_events": ["fusion.completed"]})
    rejected = code in (400, 422)
    check(f"G6b SSRF rejects {label} sink ({url})", rejected,
          f"HTTP {code} " + json.dumps(body)[:150])

print("\n=== G6c subscription lifecycle on non-routable TEST-NET sinks ===")
code, sub_active = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
    "external_system_id": SYS_ID, "endpoint_url": "http://203.0.113.10:9099/hook",
    "subscribed_events": ["fusion.completed", "review_case.created"]})
check("G6c active subscription accepted for TEST-NET-1 sink", code == 201,
      f"HTTP {code} " + json.dumps({k: v for k, v in (sub_active or {}).items()
                                    if k in {"id", "status", "endpoint_url", "subscribed_events"}})[:200])
ACTIVE_SUB = (sub_active or {}).get("id")

code, sub_disabled = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
    "external_system_id": SYS_ID, "endpoint_url": "http://198.51.100.10:9099/hook",
    "subscribed_events": ["fusion.completed"]})
DISABLED_SUB = (sub_disabled or {}).get("id")
code, patched = call("PATCH", f"/api/v1/integrations/webhooks/{DISABLED_SUB}", token=ADMIN,
                     data={"status": "DISABLED"})
check("G6c second subscription can be disabled before fanout", code in (200, 204),
      f"HTTP {code} status={(patched or {}).get('status') if isinstance(patched, dict) else ''}")

code, bad = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
    "external_system_id": SYS_ID, "endpoint_url": "http://203.0.113.11:9099/hook",
    "subscribed_events": ["not.a.real.event"]})
check("G6c unknown webhook event type is rejected", code in (422, 400),
      f"HTTP {code} " + json.dumps(bad)[:150])

code, body = call("POST", "/api/v1/integrations/webhooks", data={
    "external_system_id": SYS_ID, "endpoint_url": "http://203.0.113.12:9099/hook",
    "subscribed_events": ["fusion.completed"]})
check("G6c anonymous subscription creation is denied", code in (401, 403), f"HTTP {code}")

code, foview = call("GET", "/api/v1/integrations/webhooks", token=FO)
check("G6c FIELD_OFFICER cannot read webhook subscriptions (least privilege)",
      code in (403, 401), f"HTTP {code}")

ARTIFACT["active_subscription_id"] = ACTIVE_SUB
ARTIFACT["disabled_subscription_id"] = DISABLED_SUB

print("\n=== G7 fusion run must enqueue a fusion.completed webhook event ===")
code, fr = call("POST", f"/api/v1/fusion/EVIDENCE/{EVIDENCE_ID}", token=SUP, data={})
check("G7 fusion execution accepted for an evidence target", code in (200, 201),
      f"HTTP {code} " + json.dumps(fr)[:180])
FUSION_RUN = ((fr or {}).get("run") or {}).get("id") if isinstance(fr, dict) else None
ARTIFACT["fusion_run_id"] = FUSION_RUN
ARTIFACT["fusion_http"] = code

print("\n=== G8 dispute workflow must emit notification outbox events ===")
code, disp = call("POST", "/api/v1/disputes", token=REV, data={
    "target_type": "EVIDENCE", "target_id": EVIDENCE_ID,
    "reason": "BE-037B phase B stage G probe", "description": "disposable integration check"})
check("G8 dispute created against evidence", code in (201, 200),
      f"HTTP {code} " + json.dumps(disp)[:180])
DISPUTE_ID = (disp or {}).get("id")
ARTIFACT["dispute_id"] = DISPUTE_ID

code, assigned = call("POST", f"/api/v1/disputes/{DISPUTE_ID}/assign", token=SUP,
                      data={"assigned_to": FO_ID})
check("G8 dispute assigned to a user", code in (200, 201),
      f"HTTP {code} status={(assigned or {}).get('status') if isinstance(assigned, dict) else ''}")
code, escalated = call("POST", f"/api/v1/disputes/{DISPUTE_ID}/escalate", token=SUP,
                       data={"escalated_to": SUP_ID, "reason": "BE-037B escalation path check"})
check("G8 dispute escalated to a supervisor", code in (200, 201),
      f"HTTP {code} status={(escalated or {}).get('status') if isinstance(escalated, dict) else ''}")

code, hist = call("GET", f"/api/v1/disputes/{DISPUTE_ID}/history", token=SUP)
check("G8 dispute history is readable", code == 200, f"HTTP {code}")
code, mine = call("GET", "/api/v1/notifications", token=FO)
check("G8 notification list endpoint reachable for the recipient", code == 200,
      f"HTTP {code} rows={len(mine) if isinstance(mine, list) else mine}")

print("\n=== ARTIFACTS (ids only, no secrets) ===")
print(json.dumps(ARTIFACT, indent=2))
with open("/tmp/g6_artifacts.json", "w") as fh:
    json.dump(ARTIFACT, fh)

t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"\nG_RESULT_C: total={t} pass={p} fail={t-p}")
for n, s, d in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", d)
