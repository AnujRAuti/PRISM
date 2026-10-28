"""BE-037 Phase B Stage F — evidence + object-storage integration probe.

Runs inside be037b65cee2_client. Only synthetic, locally generated images are
uploaded, and only to this run's disposable MinIO instance.
"""
import io
import json
import urllib.error
import urllib.request
import uuid

from PIL import Image, ImageDraw

BASE = "http://api:8000"
RESULTS = []
SUFFIX = uuid.uuid4().hex[:8]


def call(method, path, token=None, data=None, content_type=None, expect_json=True):
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            parsed = json.loads(body) if expect_json and "json" in r.headers.get("Content-Type", "") else body
            return r.status, parsed, body
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"_raw": body[:200].decode("utf-8", "replace")}
        return e.code, parsed, body


def check(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", str(detail)))
    print(("PASS  " if ok else "FAIL  ") + name + "  | " + str(detail), flush=True)


def expect(name, method, path, status, **kw):
    code, parsed, body = call(method, path, **kw)
    check(name, code == status, f"HTTP {code} (expected {status}) "
          + ("" if code == status else json.dumps(parsed)[:220]))
    return code, parsed


def multipart(field, filename, payload, content_type):
    boundary = "----be037b" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    return body, "multipart/form-data; boundary=" + boundary


def synthetic_png(label):
    img = Image.new("RGB", (320, 120), (24, 68, 120))
    d = ImageDraw.Draw(img)
    d.text((10, 20), label, fill=(255, 255, 255))
    d.text((10, 45), "BE-037 PHASE B SYNTHETIC TEST IMAGE", fill=(255, 255, 0))
    d.text((10, 70), "NOT REAL FIELD EVIDENCE - DISPOSABLE RUN", fill=(200, 255, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def synthetic_jpeg(label):
    img = Image.new("RGB", (320, 120), (120, 68, 24))
    d = ImageDraw.Draw(img)
    d.text((10, 20), label, fill=(255, 255, 255))
    d.text((10, 45), "BE-037 PHASE B SYNTHETIC JPEG", fill=(255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


print("=== F0  bootstrap an authorized disposable principal (FIELD_OFFICER) ===")
_, user = expect("F0 create disposable test user", "POST", "/api/v1/auth/users", 201,
                 data=json.dumps({"username": f"be037b_upl_{SUFFIX}",
                                  "email": f"be037b-upl-{SUFFIX}@example.invalid"}).encode(),
                 content_type="application/json")
user_id = user["id"]
expect("F0 grant FIELD_OFFICER (evidence.create)", "POST", f"/api/v1/auth/users/{user_id}/roles",
       201, data=json.dumps({"role_name": "FIELD_OFFICER", "scope_type": "GLOBAL"}).encode(),
       content_type="application/json")
TOKEN = f"dev-user-{user_id}"

print()
print("=== F1  upload through the supported application flow ===")
png = synthetic_png(f"run be037b65cee2 {SUFFIX}")
print(f"   synthetic PNG generated in-container: {len(png)} bytes")
body, ctype = multipart("file", "be037b-synthetic.png", png, "image/png")
code, up, _ = call("POST", "/api/v1/evidence", token=TOKEN, data=body, content_type=ctype)
check("F1 POST /api/v1/evidence accepts the synthetic image", code == 201,
      f"HTTP {code} " + json.dumps(up)[:240])
evidence_id = (up or {}).get("evidence_id")
api_storage_key = (up or {}).get("storage_key")
api_size = (up or {}).get("size")
print("   evidence_id=", evidence_id, "storage_key=", api_storage_key, "size=", api_size,
      "api_status=", (up or {}).get("status"))

print()
print("=== F2  metadata returned by the API ===")
code, meta, _ = call("GET", f"/api/v1/evidence/{evidence_id}", token=TOKEN)
check("F2 GET /evidence/{id} returns metadata", code == 200, f"HTTP {code}")
check("F2 stored status is the quarantine state (not 'trusted')",
      (meta or {}).get("status") == "uploaded_quarantine",
      f"db status={(meta or {}).get('status')} api status={(up or {}).get('status')}")
check("F2 metadata agrees with the upload result",
      (meta or {}).get("file_size") == api_size == len(png)
      and (meta or {}).get("content_type") == (up or {}).get("content_type") == "image/png",
      f"size {meta and meta.get('file_size')} / {api_size} / {len(png)}")

print()
print("=== F3  presigned download returns exactly the uploaded bytes ===")
code, dl, _ = call("GET", f"/api/v1/evidence/{evidence_id}/download", token=TOKEN)
check("F3 download URL issued after authorization", code == 200 and (dl or {}).get("download_url"),
      f"HTTP {code} keys={sorted((dl or {}).keys())}")
url = (dl or {}).get("download_url", "")
check("F3 presigned URL points at the disposable MinIO service only",
      url.startswith("http://minio:9000/"), url.split("?")[0])
try:
    with urllib.request.urlopen(url, timeout=20) as r:
        got = r.read()
    check("F3 downloaded bytes equal the uploaded bytes", got == png,
          f"fetched {len(got)} bytes, sha match={got == png}")
except Exception as e:
    check("F3 downloaded bytes equal the uploaded bytes", False, f"{type(e).__name__}: {e}")

print()
print("=== F4  rejected inputs (MIME / malformed / empty / oversized) ===")
b, c = multipart("file", "note.txt", b"hello, not an image", "text/plain")
expect("F4 disallowed declared MIME rejected with 415", "POST", "/api/v1/evidence", 415,
       token=TOKEN, data=b, content_type=c)
b, c = multipart("file", "fake.png", bytes(range(256)) * 4, "image/png")
expect("F4 malformed payload with an image MIME rejected with 415", "POST", "/api/v1/evidence",
       415, token=TOKEN, data=b, content_type=c)
jpeg_bytes = synthetic_jpeg("mislabeled")
b2, c2 = multipart("file", "mislabeled.png", jpeg_bytes, "image/png")
expect("F4 real JPEG bytes declared as image/png rejected with 415 (declared!=actual)",
       "POST", "/api/v1/evidence", 415, token=TOKEN, data=b2, content_type=c2)
b, c = multipart("file", "empty.png", b"", "image/png")
expect("F4 empty payload rejected with 400", "POST", "/api/v1/evidence", 400,
       token=TOKEN, data=b, content_type=c)
oversize = b"\x89PNG\r\n\x1a\n" + bytes(11 * 1024 * 1024)
b, c = multipart("file", "huge.png", oversize, "image/png")
expect("F4 oversized payload rejected with 413", "POST", "/api/v1/evidence", 413,
       token=TOKEN, data=b, content_type=c)

print()
print("=== F5  no valid evidence record without its object ===")
code, listed, _ = call("GET", f"/api/v1/evidence/{uuid.uuid4()}", token=TOKEN)
check("F5 unknown evidence id is 404 (no phantom record)", code == 404, f"HTTP {code}")

print()
print("=== F6  geospatial write/read path on the created evidence ===")
b = json.dumps({"latitude": 37.5665, "longitude": 126.9780}).encode()
expect("F6 valid coordinates accepted", "PATCH", f"/api/v1/evidence/{evidence_id}/location", 200,
       token=TOKEN, data=b, content_type="application/json")
b = json.dumps({"latitude": 95.0, "longitude": 126.9780}).encode()
expect("F6 out-of-range latitude rejected", "PATCH", f"/api/v1/evidence/{evidence_id}/location",
       422, token=TOKEN, data=b, content_type="application/json")
b = json.dumps({"latitude": 37.5, "longitude": 200.0}).encode()
expect("F6 out-of-range longitude rejected", "PATCH", f"/api/v1/evidence/{evidence_id}/location",
       422, token=TOKEN, data=b, content_type="application/json")
code, nearby, _ = call("GET", "/api/v1/evidence/nearby?latitude=37.57&longitude=126.98&radius=2000",
                       token=TOKEN)
ids = [i.get("evidence_id") or i.get("id") for i in (nearby or {}).get("items", [])]
check("F6 PostGIS nearby query returns the located evidence",
      code == 200 and evidence_id in ids, f"HTTP {code} ids={ids}")

print()
print("=== F7  retention: permission boundary, then dry-run as an authorized principal ===")
b = json.dumps({"resource_type": "EVIDENCE", "resource_id": evidence_id}).encode()
code, denied, _ = call("POST", "/api/v1/retention/evaluate", token=TOKEN, data=b,
                       content_type="application/json")
check("F7 FIELD_OFFICER (no retention.read) is refused the retention dry-run",
      code == 403, f"HTTP {code} " + json.dumps(denied)[:180]
      + " | FIELD_OFFICER catalogue has no retention.read")

_, admin = expect("F7 create disposable admin user", "POST", "/api/v1/auth/users", 201,
                  data=json.dumps({"username": f"be037b_adm_{SUFFIX}",
                                   "email": f"be037b-adm-{SUFFIX}@example.invalid"}).encode(),
                  content_type="application/json")
expect("F7 grant ADMINISTRATOR (retention.read)", "POST",
       f"/api/v1/auth/users/{admin['id']}/roles", 201,
       data=json.dumps({"role_name": "ADMINISTRATOR", "scope_type": "GLOBAL"}).encode(),
       content_type="application/json")
ADMIN_TOKEN = f"dev-user-{admin['id']}"

code, ret, _ = call("POST", "/api/v1/retention/evaluate", token=ADMIN_TOKEN, data=b,
                    content_type="application/json")
check("F7 authorized retention dry-run answers for the synthetic evidence", code == 200,
      f"HTTP {code} " + json.dumps(ret)[:240])
check("F7 dry-run returns the eligibility verdict fields",
      all(k in (ret or {}) for k in ("eligible", "archive_eligible", "deletion_eligible",
                                     "blocking_reasons")),
      f"keys={sorted((ret or {}).keys())[:14]}")
check("F7 freshly uploaded evidence is not deletion-eligible and states why",
      (ret or {}).get("deletion_eligible") is False
      and bool((ret or {}).get("blocking_reasons")),
      json.dumps({k: (ret or {}).get(k) for k in ("deletion_eligible", "blocking_reasons")})[:200])
code, meta_after, _ = call("GET", f"/api/v1/evidence/{evidence_id}", token=TOKEN)
check("F7 evidence record still present after evaluation (no deletion performed)",
      code == 200, f"HTTP {code}")

print()
print("=== IDS for the report ===")
print("EVIDENCE_ID=" + str(evidence_id))
print("STORAGE_KEY=" + str(api_storage_key))
print("USER_ID=" + str(user_id))
print("PROJECT_OWNER=" + str(user_id))

print()
print("=== SUMMARY ===")
total = len(RESULTS)
passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
for name, status, detail in RESULTS:
    if status == "FAIL":
        print("FAILING CHECK:", name, "|", detail)
print(f"F_RESULT: total={total} pass={passed} fail={total-passed}")
