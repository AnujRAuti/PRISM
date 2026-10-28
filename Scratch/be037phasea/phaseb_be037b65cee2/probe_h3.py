"""BE-037 Phase B Stage H (run E) — tamper DETECTION and gap CLASSIFICATION, live.

Stage H's remaining question is not whether the walls hold (run B/C measured that)
but whether a break in the chain would actually be *seen*, and whether the seen
break is correctly labelled new vs blessed. That cannot be shown on a healthy
ledger, so this run creates controlled damage on the disposable ledger, observes it
through the real API, and then removes exactly what it created.

Controlled rows are tagged action='be037b-forged-probe' so the later removal can
select them by marker instead of by a hand-carried sequence number.

STAGE=insert  runtime identity commits two forged rows after the current head,
              then the API is asked to verify (bounded + whole + anchored, both
              registered baselines).
STAGE=gap     re-verify after the lower forged row has been removed by the owner
              path — this is what a real historical gap looks like.
STAGE=final   re-verify after both forged rows are gone; must be clean again.

Nothing here runs as superuser from Python; the owner-side deletions are a separate
psql step and are logged in their own evidence file.
"""
import json
import os
import urllib.error
import urllib.request

import psycopg2

BASE = "http://api:8000"
STAGE = os.environ.get("STAGE", "insert")
# the ADMINISTRATOR created by run A; its user id is already in the Stage H evidence.
ADMIN = "dev-user-2387cd58-7fa2-4435-9960-59499cf09795"
MARKER = "be037b-forged-probe"


def call(path, token=ADMIN):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:300].decode("utf-8", "replace")}


def dump(title):
    code, body = call(title[1])
    print(f"--- {title[0]} -> HTTP {code}", flush=True)
    print(json.dumps(body, indent=2, sort_keys=True)[:2600], flush=True)
    return code, body


FORGED = ("INSERT INTO audit_ledger_events (id, sequence_number, event_type, action, "
          "resource_type, payload, metadata, previous_hash, event_hash, created_at) "
          "VALUES (gen_random_uuid(), %s, 'USER_CREATED', '" + MARKER + "', 'probe', "
          "'{}'::json, '{}'::json, repeat('a',64), repeat('b',64), now())")

if STAGE == "insert":
    conn = psycopg2.connect(os.environ["DATABASE_URL"]
                            .replace("postgresql+psycopg2://", "postgresql://", 1))
    conn.autocommit = True          # committed on purpose: the API must be able to see it
    cur = conn.cursor()
    cur.execute("SELECT max(sequence_number), count(*) FROM audit_ledger_events")
    head, rows = cur.fetchone()
    print(f"HEAD_BEFORE={head} ROWS_BEFORE={rows}", flush=True)
    cur.execute(FORGED, (head + 1,))
    cur.execute(FORGED, (head + 2,))
    cur.execute("SELECT sequence_number, event_type, previous_hash, event_hash "
                "FROM audit_ledger_events WHERE action='%s' ORDER BY 1", (MARKER,))
    for r in cur.fetchall():
        print("FORGED ROW:", r[0], r[1], str(r[2])[:12] + "...", str(r[3])[:12] + "...",
              flush=True)
    cur.close()
    conn.close()

print()
print(f"===== STAGE={STAGE}: what does the integrated stack report? =====")
dump(("bounded range over the tail",
      f"/api/v1/audit/verify?from_sequence=80&to_sequence=100"))
dump(("whole chain", "/api/v1/audit/verify"))
code, anchored_none = dump(("anchored, default (fail-closed) baseline",
                            "/api/v1/audit/verify/anchored"))
dump(("anchored, blessed pofa-dev baseline",
      "/api/v1/audit/verify/anchored?baseline=pofa-dev-pre-be030-test-cleanup"))

cl = (anchored_none or {}).get("classification") or {}
print(f"STAGE_{STAGE}_VALID={(anchored_none or {}).get('valid')}", flush=True)
print(f"STAGE_{STAGE}_STATUS={cl.get('status')} degraded={cl.get('degraded')}", flush=True)
print(f"STAGE_{STAGE}_NEW_GAPS={json.dumps(cl.get('new_gaps'))[:400]}", flush=True)
print(f"STAGE_{STAGE}_KNOWN_GAPS={json.dumps(cl.get('known_historical_gaps'))[:400]}",
      flush=True)
print(f"STAGE_{STAGE}_HARD={json.dumps(cl.get('hard_anomalies'))[:400]}", flush=True)
print(f"STAGE_{STAGE}_FAILURES={json.dumps((anchored_none or {}).get('failures'))[:600]}",
      flush=True)
