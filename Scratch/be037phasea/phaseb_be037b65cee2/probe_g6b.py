"""BE-037 Phase B Stage G (run D) — corrected webhook/SSRF measurement.

Run C's G6b/G6c rows were INVALID: the external system was never created (invalid
system_type), so every subscription POST failed schema validation (422 on a null
external_system_id) before the SSRF validator or the permission guard ever ran.
This run creates a real external system first, so the SSRF boundary, the auth
boundary and the delivery fanout are genuinely exercised. No secret material is
printed.
"""
import json
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://api:8000"
EVIDENCE_ID = "7f703702-7976-4070-9215-5536e967245b"
FO_ID = "20dc9d67-4945-4f6a-8d5c-5369115e41e1"   # FIELD_OFFICER recipient from run C
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


ADMIN_ID, ADMIN = make_user("ADMINISTRATOR", "g9adm")
SUP_ID, SUP = make_user("SUPERVISOR", "g9sup")

print("=== G9a integration writes require integration.manage (valid body this time) ===")
code, body = call("POST", "/api/v1/integrations/systems", data={
    "name": "BE-037B anonymous check", "code": f"ANON_{uuid.uuid4().hex[:6]}",
    "system_type": "OTHER"})
check("G9a anonymous external-system creation is rejected", code in (401, 403),
      f"HTTP {code} " + json.dumps(body)[:120])

code, sys1 = call("POST", "/api/v1/integrations/systems", token=ADMIN, data={
    "name": "BE-037B disposable sink", "code": f"BE037B_{uuid.uuid4().hex[:6]}",
    "system_type": "OTHER"})
check("G9a external system registered as ADMINISTRATOR", code == 201,
      f"HTTP {code} " + json.dumps({k: v for k, v in (sys1 or {}).items()
                                    if k in {"id", "code", "status", "system_type"}})[:160])
SYS_ID = (sys1 or {}).get("id")
ARTIFACT["external_system_id"] = SYS_ID
if SYS_ID is None:
    print("ABORT: no external system id, later checks would be vacuous")
    raise SystemExit(1)

print("\n=== G9b SSRF boundary on subscription creation (real external_system_id) ===")
private_sinks = [
    ("loopback-ipv4", "http://127.0.0.1:9099/hook"),
    ("loopback-hostname", "http://localhost:9099/hook"),
    ("docker-bridge-gateway", "http://172.18.0.1:9099/hook"),
    ("container-alias", "http://api:8000/hook"),
    ("db-alias", "http://db:5432/hook"),
    ("cloud-metadata", "http://169.254.169.254/latest/meta-data/"),
    ("rfc1918-10", "http://10.0.5.9:9099/hook"),
    ("rfc1918-192", "http://192.168.1.1:9099/hook"),
    ("unspecified-0000", "http://0.0.0.0:9099/hook"),
    ("file-scheme", "file:///etc/passwd"),
    ("non-http-scheme", "gopher://203.0.113.10:70/hook"),
]
for label, url in private_sinks:
    code, body = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
        "external_system_id": SYS_ID, "endpoint_url": url,
        "subscribed_events": ["fusion.completed"]})
    rejected = code in (400, 422)
    schema_only = "external_system_id" in json.dumps(body)
    check(f"G9b SSRF/scheme rejection for {label}", rejected and not schema_only,
          f"HTTP {code} " + json.dumps(body)[:170])

print("\n=== G9c subscriptions on non-routable TEST-NET sinks (public, unreachable here) ===")
code, sub_active = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
    "external_system_id": SYS_ID, "endpoint_url": "http://203.0.113.10:9099/hook",
    "subscribed_events": ["fusion.completed"]})
ACTIVE_SUB = (sub_active or {}).get("id")
check("G9c active subscription accepted for TEST-NET-1 sink", code == 201 and ACTIVE_SUB,
      "HTTP " + str(code) + " " + json.dumps({k: v for k, v in (sub_active or {}).items()
                                              if k in {"id", "status", "endpoint_url"}})[:160])

code, sub_disabled = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
    "external_system_id": SYS_ID, "endpoint_url": "http://198.51.100.10:9099/hook",
    "subscribed_events": ["fusion.completed"]})
DISABLED_SUB = (sub_disabled or {}).get("id")
code, patched = call("PATCH", f"/api/v1/integrations/webhooks/{DISABLED_SUB}", token=ADMIN,
                     data={"status": "DISABLED"})
check("G9c second subscription disabled before fanout", code in (200, 204) and DISABLED_SUB,
      f"HTTP {code} status=" + str((patched or {}).get("status") if isinstance(patched, dict) else ""))

code, bad = call("POST", "/api/v1/integrations/webhooks", token=ADMIN, data={
    "external_system_id": SYS_ID, "endpoint_url": "http://203.0.113.11:9099/hook",
    "subscribed_events": ["not.a.real.event"]})
check("G9c unknown webhook event type rejected", code in (422, 400)
      and "external_system_id" not in json.dumps(bad), "HTTP " + str(code) + " " + json.dumps(bad)[:150])

code, anonsub = call("POST", "/api/v1/integrations/webhooks", data={
    "external_system_id": SYS_ID, "endpoint_url": "http://203.0.113.12:9099/hook",
    "subscribed_events": ["fusion.completed"]})
check("G9c anonymous subscription creation rejected", code in (401, 403),
      "HTTP " + str(code) + " " + json.dumps(anonsub)[:120])

code, foview = call("GET", "/api/v1/integrations/webhooks", token=f"dev-user-{FO_ID}")
check("G9c FIELD_OFFICER cannot read subscriptions (least privilege)", code in (403, 401),
      f"HTTP {code}")

ARTIFACT["active_subscription_id"] = ACTIVE_SUB
ARTIFACT["disabled_subscription_id"] = DISABLED_SUB

print("\n=== G9d recipient-facing notification read (run C timing gap closed) ===")
code, inbox = call("GET", "/api/v1/notifications", token=f"dev-user-{FO_ID}")
items = (inbox or {}).get("items") if isinstance(inbox, dict) else inbox
check("G9d notification created by the worker is readable by its recipient",
      code == 200 and len(items or []) >= 1,
      f"HTTP {code} items={len(items or [])} total={(inbox or {}).get('total') if isinstance(inbox, dict) else ''}")
if isinstance(inbox, dict) and items:
    nid = items[0].get("id")
    code, one = call("GET", f"/api/v1/notifications/{nid}", token=f"dev-user-{FO_ID}")
    check("G9d single notification detail readable", code == 200, f"HTTP {code}")
    code, dl = call("GET", f"/api/v1/notifications/{nid}/deliveries", token=f"dev-user-{FO_ID}")
    print("   OBSERVE delivery rows via API ->", f"HTTP {code}", json.dumps(dl)[:220])
    code, read = call("POST", f"/api/v1/notifications/{nid}/read", token=f"dev-user-{FO_ID}")
    check("G9d recipient can mark the notification read", code in (200, 204), f"HTTP {code}")
    code, other = call("GET", f"/api/v1/notifications/{nid}", token="dev-user-" + SUP_ID)
    print("   OBSERVE cross-user notification read (SUP token) ->", f"HTTP {code}")

print("\n=== G9e fusion run must enqueue a second webhook event for the new subscriptions ===")
code, fr = call("POST", f"/api/v1/fusion/EVIDENCE/{EVIDENCE_ID}", token=SUP, data={})
RUN_ID = ((fr or {}).get("run") or {}).get("id") if isinstance(fr, dict) else None
check("G9e fusion execution accepted", code == 200 and RUN_ID, f"HTTP {code} run={RUN_ID}")
ARTIFACT["fusion_run_id"] = RUN_ID

print("\n   Waiting 75s for the running webhook worker loop (15s cadence) to sweep and attempt delivery...")
time.sleep(75)

code, subs = call("GET", "/api/v1/integrations/webhooks", token=ADMIN)
for s in (subs if isinstance(subs, list) else []):
    print("   OBSERVE subscription", s.get("id"), "status=", s.get("status"),
          "endpoint=", s.get("endpoint_url"), "consecutive_failures=", s.get("consecutive_failures"),
          "last_delivery_at=", s.get("last_delivery_at"))

print("\n=== ARTIFACTS (ids only, no secrets) ===")
print(json.dumps(ARTIFACT, indent=2))
with open("/tmp/g9_artifacts.json", "w") as fh:
    json.dump(ARTIFACT, fh)

t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"\nG_RESULT_D: total={t} pass={p} fail={t-p}")
for n, s, d in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", d)
