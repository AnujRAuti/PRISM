"""BE-037 Phase B Stage I — readiness probe, run from inside the api container.

Polls the three things an operator would watch during a dependency outage:
  /health   (what the container healthcheck actually tests)
  /ready    (what the app claims is readiness — PostgreSQL only, by code)
  a real authenticated read that must touch PostgreSQL
and, when ASK_QUEUE is set, whether the Redis-backed path still behaves.

It prints one compact line per poll so the outage window can be read directly off
the timeline. No secrets are printed; the token is read from the environment.
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
POLLS = int(os.environ.get("POLLS", "12"))
INTERVAL = float(os.environ.get("INTERVAL", "3"))
WHICH = os.environ.get("WHICH", "db")          # db | redis | minio
ADMIN = os.environ.get("ADMIN_TOKEN", "")


def get(path, token=None, timeout=8):
    headers = {"Authorization": "Bearer " + token} if token else {}
    req = urllib.request.Request(BASE + path, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, body[:120].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:160].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except Exception as e:
        return "ERR", type(e).__name__ + ": " + str(e)[:120], round((time.time() - t0) * 1000)


print(f"# WHICH={WHICH} polls={POLLS} interval={INTERVAL}s", flush=True)
for i in range(POLLS):
    ts = time.strftime("%H:%M:%S", time.gmtime())
    hs, hb, hms = get("/health")
    rs, rb, rms = get("/ready")
    ds, db, dms = get("/api/v1/audit/verify", ADMIN)
    extra = ""
    if WHICH == "redis" and i % 2 == 0:
        # the Redis-backed enqueue path: does it fail loudly or silently?
        code, body, ms = get("/api/v1/analysis/jobs", ADMIN)
        extra = f" | GET_jobs={code} {body[:60]!r} {ms}ms"
    if WHICH == "minio" and i % 2 == 0:
        code, body, ms = get("/api/v1/evidence/988d9235-c13a-47c9-805c-6b2869b059eb/download",
                             ADMIN)
        extra = f" | download={code} {body[:70]!r} {ms}ms"
    print(f"{ts} health={hs}({hms}ms) ready={rs}({rms}ms) {rb[:60]!r} "
          f"dbread={ds}({dms}ms) {db[:70]!r}{extra}", flush=True)
    if i < POLLS - 1:
        time.sleep(INTERVAL)
print("# polling finished", flush=True)
