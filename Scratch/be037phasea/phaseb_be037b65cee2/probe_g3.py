"""BE-037 Phase B Stage G (run B) — failure path: analysis job whose object is gone.

The host deleted this evidence's quarantine object BEFORE the job existed, so the
running worker must fail the job. The check is that failure is recorded as failure
and never reported as success.
"""
import io
import json
import time
import urllib.error
import urllib.request
import uuid

from PIL import Image, ImageDraw

BASE = "http://api:8000"
EVIDENCE_ID = "39b1fbb2-0d80-4305-87b4-abb6d001cbae"
RESULTS = []


def call(method, path, token=None, data=None, content_type=None):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, (json.loads(body) if "json" in r.headers.get("Content-Type", "") else body)
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"_raw": body[:200].decode("utf-8", "replace")}


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail), flush=True)


code, user = call("POST", "/api/v1/auth/users", data=json.dumps({
    "username": f"be037b_g1b_{uuid.uuid4().hex[:8]}",
    "email": f"be037b-g1b-{uuid.uuid4().hex[:8]}@example.invalid"}).encode(),
    content_type="application/json")
uid = (user or {}).get("id")
call("POST", f"/api/v1/auth/users/{uid}/roles",
     data=json.dumps({"role_name": "FIELD_OFFICER", "scope_type": "GLOBAL"}).encode(),
     content_type="application/json")
TOKEN = f"dev-user-{uid}"

print("=== G4b  job against evidence whose stored object was deleted first ===")
code, ev = call("GET", f"/api/v1/evidence/{EVIDENCE_ID}", token=TOKEN)
check("G4b metadata row still exists before the job (DB says uploaded, storage says gone)",
      code == 200, f"HTTP {code}")
code, dl = call("GET", f"/api/v1/evidence/{EVIDENCE_ID}/download", token=TOKEN)
print(f"   OBSERVE presigned download for the missing object -> HTTP {code} "
      + json.dumps(dl)[:200], flush=True)

code, job = call("POST", "/api/v1/analysis/jobs", token=TOKEN,
                 data=json.dumps({"evidence_id": EVIDENCE_ID,
                                  "job_type": "fingerprint"}).encode(),
                 content_type="application/json")
check("G4b job accepted for evidence with no object", code == 202,
      f"HTTP {code} " + json.dumps(job)[:200])
job_id = (job or {}).get("job_id")

deadline = time.time() + 240
seen_statuses = []
final = None
while time.time() < deadline:
    code, cur = call("GET", f"/api/v1/analysis/jobs/{job_id}", token=TOKEN)
    st = (cur or {}).get("status")
    if not seen_statuses or seen_statuses[-1] != st:
        seen_statuses.append(st)
        print(f"   status observed: {st} (attempt_count={(cur or {}).get('attempt_count')})",
              flush=True)
    final = cur
    if st == "completed":
        break
    if st == "failed":
        break
    time.sleep(2)

print("   final job:", json.dumps(final)[:400], flush=True)
check("G4b job is marked failed, never completed (no silent success)",
      (final or {}).get("status") == "failed", f"status={(final or {}).get('status')}")
check("G4b failure carries an error message", bool((final or {}).get("error")),
      f"error={(final or {}).get('error')}")
check("G4b worker used its bounded retry count before declaring failure",
      (final or {}).get("attempt_count") == 3, f"attempt_count={(final or {}).get('attempt_count')}")
check("G4b no AnalysisResult was stored for the failed job",
      (final or {}).get("result") is None, f"result={json.dumps((final or {}).get('result'))[:120]}")
print("G4b_STATUS_TRACE=" + ",".join(str(s) for s in seen_statuses))

print()
print("=== SUMMARY ===")
for n, s, d in RESULTS:
    if s == "FAIL":
        print("FAILING CHECK:", n, "|", d)
t = len(RESULTS)
p = sum(1 for _, s, _ in RESULTS if s == "PASS")
print(f"G_RESULT_B: total={t} pass={p} fail={t-p}")
