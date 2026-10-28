"""BE-037 Phase B Stage I — object-storage (MinIO) outage behaviour.

Storage is one of the three *required* readiness checks, so the interesting
questions are: does readiness actually flip, does the download path fail loudly
or hand the client a URL that cannot be used, and does a failed upload leave an
orphan metadata row behind in PostgreSQL?

Invoked once per STAGE (up | down | restore); the outage is toggled from the
host. Uploads go to this run's disposable bucket only, with a synthetic in-memory
PNG. Secrets are never printed.
"""
import hashlib
import json
import os
import struct
import time
import urllib.error
import urllib.request
import zlib

import psycopg2

BASE = "http://127.0.0.1:8000"
ADMIN = os.environ["ADMIN_TOKEN"]
FO = os.environ["FO_TOKEN"]          # evidence.create / evidence.read lives here
STAGE = os.environ.get("STAGE", "up")
DSN = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
MARK = os.environ.get("MARK", "be037b-I-minio-outage")


def png_bytes():
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * 32 for _ in range(32))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def multipart(filename, payload, content_type):
    boundary = "----be037bI"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    return body, "multipart/form-data; boundary=" + boundary


def call(method, path, data=None, content_type=None, timeout=20, token=None):
    headers = {"Authorization": "Bearer " + (token or ADMIN)}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()[:320].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:320].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except Exception as e:
        return "ERR", type(e).__name__ + ": " + str(e)[:220], round((time.time() - t0) * 1000)


def fetch(url, timeout=10):
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            b = r.read()
            return r.status, f"{len(b)} bytes sha256={hashlib.sha256(b).hexdigest()[:16]}", round((time.time() - t0) * 1000)
    except Exception as e:
        return "ERR", type(e).__name__ + ": " + str(e)[:180], round((time.time() - t0) * 1000)


def ready():
    code, body, ms = call("GET", "/ready")
    try:
        checks = {k: v.get("status") for k, v in json.loads(body).get("checks", {}).items()}
    except Exception:
        checks = {"raw": body[:90]}
    return code, checks, ms


def sql(query, params=()):
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall() if cur.description else None
        conn.rollback()
        return rows
    finally:
        conn.close()


def upload(label):
    body, ctype = multipart(f"{MARK}.png", png_bytes(), "image/png")
    code, resp, ms = call("POST", "/api/v1/evidence", data=body, content_type=ctype, token=FO)
    print(f"{label} POST /evidence -> {code} ({ms}ms) {resp[:190]!r}", flush=True)
    eid = None
    try:
        eid = json.loads(resp)["evidence_id"]
    except Exception:
        pass
    return code, eid


def download_and_fetch(eid, label):
    code, resp, ms = call("GET", f"/api/v1/evidence/{eid}/download", token=FO)
    print(f"{label} GET download -> {code} ({ms}ms) {resp[:150]!r}", flush=True)
    url = None
    try:
        url = json.loads(resp)["download_url"]
    except Exception:
        pass
    if url:
        c2, b2, m2 = fetch(url)
        print(f"{label} fetch presigned URL -> {c2} ({m2}ms) {b2}", flush=True)


def get_eid():
    eid = os.environ.get("EID")
    if eid:
        return eid.strip()
    with open("/tmp/be037b_i_eid") as fh:
        return fh.read().strip()


print(f"# STAGE={STAGE} mark={MARK} {time.strftime('%H:%M:%S', time.gmtime())}", flush=True)

if STAGE == "up":
    code, checks, ms = ready()
    print(f"M1 ready(storage UP) -> {code} ({ms}ms) {checks}", flush=True)
    code, eid = upload("M2")
    if eid:
        print(f"M2 EID={eid}", flush=True)
        download_and_fetch(eid, "M3")
        print(f"M3 row={sql('SELECT id, status, storage_key FROM evidence WHERE id=%s', (eid,))}", flush=True)
        with open("/tmp/be037b_i_eid", "w") as fh:
            fh.write(eid)

if STAGE == "down":
    eid = get_eid()
    code, checks, ms = ready()
    print(f"M4 ready(storage DOWN) -> {code} ({ms}ms) {checks}", flush=True)
    code, checks, ms = ready()
    print(f"M4 ready again -> {code} {checks}", flush=True)
    print(f"M5 metadata read (DB only) -> {sql('SELECT id,status FROM evidence WHERE id=%s', (eid,))}", flush=True)
    download_and_fetch(eid, "M6")
    code, eid2 = upload("M7")
    if eid2 is None:
        print("M7 upload rejected; is there an orphan evidence row?", flush=True)
    rows = sql("SELECT id, status, storage_key, created_at FROM evidence "
               "ORDER BY created_at DESC LIMIT 4")
    print(f"M7 newest evidence rows = {rows}", flush=True)
    print(f"M7 evidence rows with no object written (status counts) = "
          f"{sql('SELECT status, count(*) FROM evidence GROUP BY status ORDER BY status')}", flush=True)
    code, body, ms = call("GET", "/api/v1/audit/verify")
    print(f"M8 dbread during storage outage -> {code} {body[:90]!r}", flush=True)

if STAGE == "restore":
    eid = get_eid()
    for i in range(15):
        code, checks, ms = ready()
        if code == 200:
            print(f"M9 recovered after ~{i * 2}s -> {code} ({ms}ms) {checks}", flush=True)
            break
        time.sleep(2)
    else:
        print(f"M9 NOT recovered within 30s -> {code} {checks}", flush=True)
    download_and_fetch(eid, "M10")
    upload("M11")
    print(f"M12 evidence by status = "
          f"{sql('SELECT status, count(*) FROM evidence GROUP BY status ORDER BY status')}", flush=True)
    code, body, ms = call("GET", "/api/v1/audit/verify")
    print(f"CLOSE chain -> {code} {body[:120]!r}", flush=True)
print(f"# stage done {time.strftime('%H:%M:%S', time.gmtime())}", flush=True)
