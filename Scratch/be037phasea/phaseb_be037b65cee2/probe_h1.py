"""BE-037 Phase B Stage H (run A) — audit chain verification over the real API.

Everything here is read through the running disposable API with real principals:
  * an ADMINISTRATOR (has audit.read) walks the whole chain, bounded ranges,
    the anchored verification with its checkpoint digest, and both baseline names;
  * a FIELD_OFFICER (no audit.read) must be refused, which is the positive control
    proving the guard still binds authenticated principals;
  * an application-path write appends to the ledger, then the chain is re-verified
    to prove append + continuity under real load rather than in a unit test.

Reads only, except the one audited user creation.
"""
import json
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://api:8000"
RESULTS = []


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
            ct = r.headers.get("Content-Type", "")
            return r.status, (json.loads(raw) if "json" in ct else raw[:300])
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:300].decode("utf-8", "replace")}


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail), flush=True)


def show(title, code, payload):
    print(f"--- {title} -> HTTP {code}", flush=True)
    print(json.dumps(payload, indent=2, sort_keys=True)[:3000], flush=True)


def make_user(role, prefix):
    code, user = call("POST", "/api/v1/auth/users", data={
        "username": f"{prefix}_{uuid.uuid4().hex[:8]}",
        "email": f"{prefix}-{uuid.uuid4().hex[:8]}@example.invalid"})
    uid = (user or {}).get("id")
    if role and uid:
        call("POST", f"/api/v1/auth/users/{uid}/roles",
             data={"role_name": role, "scope_type": "GLOBAL"})
    return uid, f"dev-user-{uid}"


print("=== H1 principals ===")
ADMIN_ID, ADMIN = make_user("ADMINISTRATOR", "be037b_h_admin")
OFFicer_ID, OFFICER = make_user("FIELD_OFFICER", "be037b_h_officer")
check("H1 ADMINISTRATOR user created", ADMIN_ID is not None, f"user id {ADMIN_ID}")
check("H1 FIELD_OFFICER user created", OFFicer_ID is not None, f"user id {OFFicer_ID}")

print()
print("=== H2 whole-chain verify (authenticated ADMINISTRATOR) ===")
code, v = call("GET", "/api/v1/audit/verify", token=ADMIN)
show("GET /api/v1/audit/verify", code, v)
check("H2 /audit/verify returns 200 for audit.read", code == 200, f"HTTP {code}")
check("H2 whole chain is valid", v.get("valid") is True, f"valid={v.get('valid')}")
check("H2 no chain failures reported", v.get("failures") == [], f"failures={v.get('failures')}")
check("H2 events were actually walked", (v.get("checked_events") or 0) > 50,
      f"checked_events={v.get('checked_events')}")
check("H2 range starts at sequence 1", v.get("first_sequence") == 1,
      f"first={v.get('first_sequence')}")
HEAD_SEQ = v.get("last_sequence")
print(f"HEAD_SEQ={HEAD_SEQ}  CHECKED={v.get('checked_events')}", flush=True)

print()
print("=== H3 bounded range verify ===")
code, v2 = call("GET", f"/api/v1/audit/verify?from_sequence=1&to_sequence={HEAD_SEQ}",
                token=ADMIN)
check("H3 explicit full range also valid", code == 200 and v2.get("valid") is True,
      f"HTTP {code} valid={v2.get('valid')} checked={v2.get('checked_events')}")
code, v3 = call("GET", f"/api/v1/audit/verify?from_sequence=5&to_sequence=12", token=ADMIN)
show("GET /audit/verify?from_sequence=5&to_sequence=12", code, v3)
check("H3 partial-range walk is valid and covers 8 events",
      code == 200 and v3.get("valid") is True and v3.get("checked_events") == 8,
      f"HTTP {code} valid={v3.get('valid')} checked={v3.get('checked_events')}")
code, v4 = call("GET", "/api/v1/audit/verify?to_sequence=0", token=ADMIN)
check("H3 out-of-range bound is rejected by validation, not ignored",
      code == 422, f"HTTP {code} " + json.dumps(v4)[:160])

print()
print("=== H4 anchored verification + checkpoint + classification ===")
code, a1 = call("GET", "/api/v1/audit/verify/anchored", token=ADMIN)
show("GET /api/v1/audit/verify/anchored (default baseline)", code, a1)
check("H4 anchored verify 200 + valid", code == 200 and a1.get("valid") is True,
      f"HTTP {code} valid={a1.get('valid')}")
CP = a1.get("checkpoint") or {}
check("H4 checkpoint publishes row count and head bounds",
      CP.get("rows") == a1.get("checked_events") and CP.get("min_sequence") == 1
      and CP.get("max_sequence") == HEAD_SEQ,
      f"checkpoint={json.dumps(CP)[:200]}")
check("H4 checkpoint publishes tail hashes (the anti-TRUNCATE anchor)",
      bool(CP.get("tail_event_hash")) and bool(CP.get("tail_previous_hash")),
      f"tail_event_hash={str(CP.get('tail_event_hash'))[:16]}... "
      f"tail_previous_hash={str(CP.get('tail_previous_hash'))[:16]}...")
CL = a1.get("classification") or {}
check("H4 default baseline is the fail-closed empty one",
      CL.get("baseline_name") == "none" and CL.get("degraded") is False
      and CL.get("new_gaps") == [] and CL.get("known_historical_gaps") == [],
      f"classification={json.dumps(CL)[:300]}")
check("H4 writer policy is reported", bool(a1.get("writer_policy")),
      f"writer_policy={a1.get('writer_policy')}")

code, a2 = call("GET", "/api/v1/audit/verify/anchored?baseline=none", token=ADMIN)
check("H4 explicit 'none' baseline matches the default",
      code == 200 and json.dumps(a2.get("classification"), sort_keys=True)
      == json.dumps(CL, sort_keys=True), f"HTTP {code}")
code, a3 = call("GET",
               "/api/v1/audit/verify/anchored?baseline=pofa-dev-pre-be030-test-cleanup",
               token=ADMIN)
show("GET /audit/verify/anchored?baseline=pofa-dev-pre-be030-test-cleanup", code, a3)
check("H4 a registered foreign baseline is accepted and still reports no gaps here",
      code == 200 and a3.get("valid") is True
      and (a3.get("classification") or {}).get("baseline_name")
      == "pofa-dev-pre-be030-test-cleanup",
      f"HTTP {code} classification={json.dumps(a3.get('classification'))[:220]}")
check("H4 the pofa-dev baseline does NOT bless anything on this ledger",
      (a3.get("classification") or {}).get("known_historical_gaps") == [],
      f"known={json.dumps((a3.get('classification') or {}).get('known_historical_gaps'))}")
code, a4 = call("GET", "/api/v1/audit/verify/anchored?baseline=is-made-up", token=ADMIN)
check("H4 an unknown baseline name is rejected rather than silently defaulted",
      code == 422, f"HTTP {code} " + json.dumps(a4)[:200])

print()
print("=== H5 authorization actually binds an authenticated principal ===")
code, off = call("GET", "/api/v1/audit/verify", token=OFFICER)
check("H5 FIELD_OFFICER (no audit.read) is refused the chain walk",
      code == 403, f"HTTP {code} " + json.dumps(off)[:200])
code, anon = call("GET", "/api/v1/audit/verify")
check("H5 anonymous request in dev mode is NOT refused (recorded as finding G2, not a probe failure)",
      code == 200, f"HTTP {code} -- dev-mode anonymous bypass, see BE-037B-G2")
show("GET /api/v1/audit/verify (anonymous, dev mode)", code, anon)

print()
print("=== H6 application-path append, then re-verify continuity ===")
TAIL_BEFORE = CP.get("tail_event_hash")
code, created = call("POST", "/api/v1/auth/users", data={
    "username": f"be037b_h_append_{uuid.uuid4().hex[:8]}",
    "email": f"be037b-h-append-{uuid.uuid4().hex[:8]}@example.invalid"})
check("H6 an application write succeeded", code in (200, 201), f"HTTP {code}")
NEW_UID = (created or {}).get("id")
time.sleep(1.5)

code, a5 = call("GET", "/api/v1/audit/verify/anchored", token=ADMIN)
CP5 = a5.get("checkpoint") or {}
print(f"   before: seq={HEAD_SEQ} rows={CP.get('rows')}", flush=True)
print(f"   after : seq={CP5.get('max_sequence')} rows={CP5.get('rows')}", flush=True)
check("H6 the ledger advanced after the application write",
      (CP5.get("max_sequence") or 0) > HEAD_SEQ,
      f"head {HEAD_SEQ} -> {CP5.get('max_sequence')}")
check("H6 the chain is still valid after the append",
      a5.get("valid") is True and a5.get("failures") == [],
      f"valid={a5.get('valid')} failures={a5.get('failures')}")
check("H6 the checkpoint tail hash changed (new head is anchored)",
      CP5.get("tail_event_hash") != TAIL_BEFORE,
      f"before={str(TAIL_BEFORE)[:16]}... after={str(CP5.get('tail_event_hash'))[:16]}...")

code, evs = call("GET", f"/api/v1/audit/events?event_type=USER_CREATED"
                       f"&resource_id={NEW_UID}", token=ADMIN)
items = (evs or {}).get("items") or []
print(f"   /audit/events?resource_id=<new user> -> HTTP {code}, {len(items)} items, "
      f"total={(evs or {}).get('total')}", flush=True)
check("H6 the appended event is retrievable through the audit API",
      code == 200 and len(items) == 1, f"HTTP {code} count={len(items)}")
if items:
    ev = items[0]
    show("the appended USER_CREATED event", 200, ev)
    check("H6 the appended row links to its predecessor by hash",
          bool(ev.get("previous_hash")) and ev.get("hash_algorithm") == "SHA-256",
          f"seq={ev.get('sequence_number')} alg={ev.get('hash_algorithm')} prev="
          f"{str(ev.get('previous_hash'))[:16]}...")
    check("H6 the appended head sequence matches the anchored checkpoint",
          ev.get("sequence_number") == CP5.get("max_sequence"),
          f"event seq={ev.get('sequence_number')} checkpoint={CP5.get('max_sequence')}")

print()
print("=== SUMMARY ===")
for n, s, d in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", d)
t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"H1_RESULT: total={t} pass={p} fail={t-p}")
print(f"H1_HEAD_SEQ_AFTER={CP5.get('max_sequence')} H1_ROWS_AFTER={CP5.get('rows')}")
