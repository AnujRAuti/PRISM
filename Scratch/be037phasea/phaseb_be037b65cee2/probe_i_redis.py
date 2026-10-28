"""BE-037 Phase B Stage I — Redis outage behaviour on the disposable stack.

Question: when Redis is gone, does the API keep claiming readiness, does the
Redis-backed write path fail loudly with the right status, and is PostgreSQL
left consistent (no job stranded as `queued` forever)?

Run from inside the api container so the calls cross the compose network the way
a client's do. The outage itself is toggled from the host, so this script is
invoked once per STAGE (up | down | restore) and the host command stitches the
phases into one timeline. Reads the runtime DATABASE_URL for row checks and
rolls every read back; nothing is written except through the real API path.
Secrets are never printed; the token comes from the environment.
"""
import json
import os
import time
import urllib.error
import urllib.request

import psycopg2

BASE = "http://127.0.0.1:8000"
ADMIN = os.environ["ADMIN_TOKEN"]
EVIDENCE_ID = os.environ["EVIDENCE_ID"]
STAGE = os.environ.get("STAGE", "up")
DSN = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)


def call(method, path, body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + ADMIN, "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()[:320].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:320].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except Exception as e:
        return "ERR", type(e).__name__ + ": " + str(e)[:200], round((time.time() - t0) * 1000)


def ready():
    code, body, ms = call("GET", "/ready")
    try:
        parsed = json.loads(body)
    except Exception:
        return code, {"raw": body[:100]}, ms
    checks = {k: v.get("status") for k, v in (parsed.get("checks") or {}).items()}
    return code, {"overall": parsed.get("status"), "checks": checks}, ms


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


def ts():
    return time.strftime("%H:%M:%S", time.gmtime())


def post_job():
    return call("POST", "/api/v1/analysis/jobs",
                {"evidence_id": EVIDENCE_ID, "job_type": "fingerprint"})


print(f"# STAGE={STAGE} evidence={EVIDENCE_ID} {ts()}", flush=True)

if STAGE == "up":
    code, body, ms = post_job()
    print(f"R1 POST_jobs(redis UP) -> {code} ({ms}ms) {body[:200]!r}", flush=True)
    try:
        jid = json.loads(body)["job_id"]
        print(f"R1 row(redis UP) id={jid} "
              f"{sql('SELECT status, error FROM analysis_jobs WHERE id=%s', (jid,))}", flush=True)
    except Exception as e:
        print(f"R1 could not read the job_id: {type(e).__name__} {e}", flush=True)
    code, checks, ms = ready()
    print(f"R2 ready(redis UP) -> {code} ({ms}ms) {checks}", flush=True)

if STAGE == "down":
    code, checks, ms = ready()
    print(f"R3 ready(redis DOWN) -> {code} ({ms}ms) {checks}", flush=True)
    code, body, ms = call("GET", "/api/v1/audit/verify")
    print(f"R4 dbread during redis outage -> {code} ({ms}ms) {body[:100]!r}", flush=True)
    code, body, ms = call("GET", "/health")
    print(f"R5 liveness during redis outage -> {code} ({ms}ms) {body[:100]!r}", flush=True)
    code, body, ms = post_job()
    print(f"R6 POST_jobs(redis DOWN) -> {code} ({ms}ms) {body[:200]!r}", flush=True)
    rows = sql("SELECT id, status, error, created_at FROM analysis_jobs "
               "WHERE evidence_id=%s ORDER BY created_at DESC LIMIT 4", (EVIDENCE_ID,))
    print(f"R6 newest rows for this evidence = {rows}", flush=True)
    print(f"R7 stranded-queued-check total queued rows in DB = "
          f"{sql('SELECT count(*) FROM analysis_jobs WHERE status=%s', ('queued',))}", flush=True)
    print(f"R8 rows whose error says enqueue failed = "
          f"{sql('SELECT count(*) FROM analysis_jobs WHERE error=%s', ('Unable to enqueue analysis job',))}",
          flush=True)
    code, checks, ms = ready()
    print(f"R9 ready again during outage -> {code} ({ms}ms) {checks}", flush=True)

if STAGE == "restore":
    for i in range(15):
        code, checks, ms = ready()
        if code == 200:
            print(f"R10 recovered after ~{i * 2}s -> {code} ({ms}ms) {checks}", flush=True)
            break
        time.sleep(2)
    else:
        print(f"R10 NOT recovered within 30s -> {code} {checks}", flush=True)
    code, body, ms = post_job()
    print(f"R11 POST_jobs(after restore) -> {code} ({ms}ms) {body[:200]!r}", flush=True)
    try:
        jid = json.loads(body)["job_id"]
        for i in range(12):
            time.sleep(3)
            st = sql("SELECT status, attempt_count, error FROM analysis_jobs WHERE id=%s", (jid,))
            print(f"R11 t+{(i + 1) * 3}s row={st}", flush=True)
            if st and st[0][0] in ("completed", "failed"):
                break
    except Exception as e:
        print(f"R11 could not follow the job: {type(e).__name__} {e}", flush=True)
    code, checks, ms = ready()
    print(f"CLOSE ready -> {code} {checks}", flush=True)
    print(f"CLOSE analysis_jobs by status = "
          f"{sql('SELECT status, count(*) FROM analysis_jobs GROUP BY status ORDER BY status')}", flush=True)
    print(f"CLOSE chain = {call('GET', '/api/v1/audit/verify')[1][:130]!r}", flush=True)
print(f"# stage done {ts()}", flush=True)
