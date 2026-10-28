"""BE-037 Phase B Stage I — is a presigned download URL an availability signal?

The download endpoint only signs a URL locally; nothing in that path proves the
object can be fetched. This asks the question a client actually experiences:
issue the URL, then fetch it, and time /ready in the same breath, once per phase.
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
FO = os.environ["FO_TOKEN"]
EID = os.environ["EID"]
PHASE = os.environ.get("PHASE", "up")


def issue():
    req = urllib.request.Request(BASE + f"/api/v1/evidence/{EID}/download",
                                 headers={"Authorization": "Bearer " + FO})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())["download_url"], round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, None, round((time.time() - t0) * 1000)
    except Exception as e:
        return "ERR", None, round((time.time() - t0) * 1000)


def fetch(url):
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = r.read()
            return f"{r.status} {len(data)} bytes", round((time.time() - t0) * 1000)
    except Exception as e:
        return f"FAIL {type(e).__name__}: {str(e)[:130]}", round((time.time() - t0) * 1000)


def ready(timeout=40):
    t0 = time.time()
    try:
        with urllib.request.urlopen(BASE + "/ready", timeout=timeout) as r:
            return r.status, r.read()[:170].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:170].decode("utf-8", "replace"), round((time.time() - t0) * 1000)
    except Exception as e:
        return "ERR", type(e).__name__, round((time.time() - t0) * 1000)


print(f"PHASE={PHASE} {time.strftime('%H:%M:%S', time.gmtime())}", flush=True)
code, url, ms = issue()
print(f"  issue_download -> {code} ({ms}ms) host={'none' if not url else url.split('/')[2]}", flush=True)
if url:
    out, fms = fetch(url)
    print(f"  client_fetch -> {out} ({fms}ms)", flush=True)
st, body, rms = ready()
print(f"  /ready -> {st} ({rms}ms) {body[:120]!r}", flush=True)
