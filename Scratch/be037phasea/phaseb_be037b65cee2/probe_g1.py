"""BE-037 Phase B Stage G (run A) — analysis worker lifecycle through the real API.

Runs inside be037b65cee2_client. Creates synthetic evidence, enqueues real
analysis jobs, and waits for the RUNNING analysis worker container to claim and
finish them. Nothing here mocks the worker.
"""
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import uuid

from PIL import Image, ImageDraw

BASE = "http://api:8000"
RESULTS = []
SUFFIX = uuid.uuid4().hex[:8]


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
            parsed = json.loads(body) if "json" in r.headers.get("Content-Type", "") else body
            return r.status, parsed
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"_raw": body[:200].decode("utf-8", "replace")}


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail), flush=True)


def multipart(field, filename, payload, content_type):
    boundary = "----be037b" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    return body, "multipart/form-data; boundary=" + boundary


def synthetic_image(label, size=(640, 480)):
    img = Image.new("RGB", size, (30, 90, 150))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, size[0] - 40, size[1] - 40], outline=(255, 255, 0), width=6)
    d.ellipse([120, 140, 300, 300], fill=(220, 60, 60))
    d.text((50, 20), label, fill=(255, 255, 255))
    d.text((50, 340), "BE-037 PHASE B SYNTHETIC - NOT FIELD EVIDENCE", fill=(200, 255, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def upload(token, label):
    payload = synthetic_image(label)
    body, ctype = multipart("file", f"be037b-{label}.png", payload, "image/png")
    code, parsed = call("POST", "/api/v1/evidence", token=token, data=body, content_type=ctype)
    return code, parsed, payload


def create_job(evidence_id, token=None, job_type="fingerprint"):
    body = json.dumps({"evidence_id": evidence_id, "job_type": job_type}).encode()
    return call("POST", "/api/v1/analysis/jobs", token=token, data=body,
                content_type="application/json")


def wait_for_job(job_id, token, timeout):
    """Poll through the real GET endpoint until the job leaves queued/running."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        code, parsed = call("GET", f"/api/v1/analysis/jobs/{job_id}", token=token)
        last = (code, parsed)
        if code == 200 and (parsed or {}).get("status") in ("completed", "failed"):
            return parsed
        time.sleep(2)
    return last[1] if last else None


print("=== G0  authorized disposable principal ===")
code, user = call("POST", "/api/v1/auth/users", data=json.dumps({
    "username": f"be037b_g1_{SUFFIX}", "email": f"be037b-g1-{SUFFIX}@example.invalid"}).encode(),
    content_type="application/json")
check("G0 create disposable user", code == 201, f"HTTP {code} " + json.dumps(user)[:160])
uid = user["id"]
code, granted = call("POST", f"/api/v1/auth/users/{uid}/roles",
                     data=json.dumps({"role_name": "FIELD_OFFICER",
                                      "scope_type": "GLOBAL"}).encode(),
                     content_type="application/json")
check("G0 grant FIELD_OFFICER", code == 201, f"HTTP {code} " + json.dumps(granted)[:160])
TOKEN = f"dev-user-{uid}"

print()
print("=== G1  fingerprint job: queue -> running worker -> DB result ===")
code, ev1, bytes1 = upload(TOKEN, f"g1-{SUFFIX}")
check("G1 upload evidence for the fingerprint job", code == 201, f"HTTP {code}")
ev1_id = (ev1 or {}).get("evidence_id")
sha1 = hashlib.sha256(bytes1).hexdigest()
code, job1 = create_job(ev1_id, token=TOKEN)
check("G1 POST /analysis/jobs (fingerprint) accepted with 202", code == 202,
      f"HTTP {code} " + json.dumps(job1)[:200])
job1_id = (job1 or {}).get("job_id")
print("   waiting for the analysis worker to claim job", job1_id, flush=True)
done1 = wait_for_job(job1_id, TOKEN, 180)
print("   final job:", json.dumps(done1)[:600], flush=True)
check("G1 worker completed the fingerprint job (status=completed)",
      (done1 or {}).get("status") == "completed", f"status={(done1 or {}).get('status')}")
check("G1 worker stamped started_at/completed_at and counted the attempt",
      bool((done1 or {}).get("started_at")) and bool((done1 or {}).get("completed_at"))
      and (done1 or {}).get("attempt_count", 0) >= 1,
      f"attempt_count={(done1 or {}).get('attempt_count')}")
res1 = (done1 or {}).get("result") or {}
check("G1 fingerprint sha256 equals the bytes stored in MinIO (worker read the object)",
      res1.get("sha256") == sha1, f"job={res1.get('sha256')} local={sha1}")
check("G1 perceptual hash computed by the worker", bool(res1.get("phash")),
      f"phash={str(res1.get('phash'))[:24]} status={res1.get('phash_status')}")
dup = res1.get("duplicate_analysis") or {}
print("   duplicate_analysis:", json.dumps(dup)[:400], flush=True)
check("G1 embedding outcome is REPORTED, not silently claimed successful",
      dup.get("embedding_status") in ("success", "failed", "error", "unavailable")
      and (dup.get("embedding_status") != "success" or not dup.get("embedding_error")),
      f"status={dup.get('embedding_status')} error={str(dup.get('embedding_error'))[:160]}")
temp = res1.get("temporal_analysis") or {}
check("G1 temporal analysis returned a verdict object (no crash in the worker)",
      "status" in temp, f"temporal keys={sorted(temp.keys())[:10]}")

print()
print("=== G2  vision job: real CPU inference with the mounted weights ===")
code, ev2, bytes2 = upload(TOKEN, f"g2-{SUFFIX}")
ev2_id = (ev2 or {}).get("evidence_id")
check("G2 upload evidence for the vision job", code == 201, f"HTTP {code}")
code, job2 = create_job(ev2_id, token=TOKEN, job_type="vision")
check("G2 POST /analysis/jobs (vision) accepted with 202", code == 202,
      f"HTTP {code} " + json.dumps(job2)[:200])
job2_id = (job2 or {}).get("job_id")
print("   waiting for vision inference (first model load can be slow)", flush=True)
done2 = wait_for_job(job2_id, TOKEN, 420)
print("   final vision job:", json.dumps(done2)[:400], flush=True)
status2 = (done2 or {}).get("status")
check("G2 vision job reached a terminal state", status2 in ("completed", "failed"),
      f"status={status2} error={str((done2 or {}).get('error'))[:200]}")
code, vis = call("GET", f"/api/v1/evidence/{ev2_id}/vision", token=TOKEN)
if status2 == "completed":
    detections = (vis or {}).get("detections") or []
    check("G2 stored vision result is retrievable through the API", code == 200,
          f"HTTP {code} " + json.dumps(vis)[:200])
    check("G2 vision pipeline produced a persisted analysis (detection rows may legitimately be 0)",
          code == 200, f"detection_count={(vis or {}).get('total')} "
                       f"model={json.dumps((vis or {}).get('result') or {})[:200]}")
else:
    check("G2 vision job failure is reported as failed (no silent success)", False,
          f"status={status2} error={str((done2 or {}).get('error'))[:240]}")
    check("G2 GET /evidence/{id}/vision answers 404 when there is no analysis",
          code == 404, f"HTTP {code}")

print()
print("=== G3  anonymous access to the job-creating endpoint (posture observation) ===")
code, ev3, bytes3 = upload(TOKEN, f"g3-{SUFFIX}")
ev3_id = (ev3 or {}).get("evidence_id")
check("G3 upload evidence for the anonymous-posture case", code == 201, f"HTTP {code}")
code, job3 = create_job(ev3_id, token=None)
print(f"   OBSERVE anonymous POST /analysis/jobs -> HTTP {code} " + json.dumps(job3)[:200],
      flush=True)
check("G3 measurement recorded (any HTTP code is a valid observation; see finding)",
      code in (202, 401, 403), f"HTTP {code}")
if code == 202:
    job3_id = (job3 or {}).get("job_id")
    code, read_anon = call("GET", f"/api/v1/analysis/jobs/{job3_id}", token=None)
    print(f"   OBSERVE anonymous GET /analysis/jobs/{{id}} -> HTTP {code} "
          f"status={(read_anon or {}).get('status')}", flush=True)
    done3 = wait_for_job(job3_id, TOKEN, 180)
    print("   anonymous-created job terminal status:",
          (done3 or {}).get("status"), flush=True)

print()
print("=== G4  upload whose stored object will be removed before processing ===")
code, ev4, bytes4 = upload(TOKEN, f"g4-{SUFFIX}")
ev4_id = (ev4 or {}).get("evidence_id")
key4 = (ev4 or {}).get("storage_key")
check("G4 upload evidence for the missing-object failure path", code == 201, f"HTTP {code}")
print("   NO JOB CREATED YET. Host must delete this object first:")
print("G4_EVIDENCE_ID=" + str(ev4_id))
print("G4_STORAGE_KEY=" + str(key4))
print("G1_EVIDENCE_ID=" + str(ev1_id) + " G2_EVIDENCE_ID=" + str(ev2_id)
      + " G3_EVIDENCE_ID=" + str(ev3_id))

print()
print("=== SUMMARY ===")
total = len(RESULTS)
passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
for name, status, detail in RESULTS:
    if status == "FAIL":
        print("FAILING CHECK:", name, "|", detail)
print(f"G_RESULT_A: total={total} pass={passed} fail={total-passed}")
