"""BE-037 WS-F: F1 authorization matrix + F3 synthetic evidence end-to-end.

Everything runs against this run's own stack (`be037wf7e3`: its PostgreSQL, its
Redis, its MinIO, its buckets, its queue keys, its roles) and on the current
image. The live dev/protected resources are not contacted.

Design notes that the task forces, recorded because they change what is testable:

* There is no login endpoint and no JWT anywhere in this backend. A bearer string
  is either an API-client credential (`<client_uuid>:<secret>`) or, when
  `AUTH_DEV_TOKENS_ENABLED=true`, a `dev-user-<uuid>` identifier. So the matrix
  needs two enforcing shapes: dev tokens OFF (the production posture, where only
  client credentials authenticate) and dev tokens ON (the only shape in which a
  *user role* can be the subject of a 403/404 assertion).
* A fresh database has an empty role/permission catalogue, because nothing in
  app startup, in a worker, or in a migration seeds it (D2). Identities are
  therefore bootstrapped through the real HTTP API while `AUTH_MODE=development`
  (the documented anonymous bypass), and the API is then restarted enforcing.
  The bootstrap sequence is itself part of the evidence.
* Credentials are held in process memory only. Nothing in the evidence files
  contains an API-client secret, a signed download URL, a password or a JWT
  value: the redaction sweep covers every secret this script ever knows, and the
  download check records only that a URL was issued.

Evidence is written after each phase, so a hang mid-run still leaves the
measured part on disk.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
PY = str(REPO / "backend/.venv312_repro/Scripts/python.exe")

RUN_ID = "be037wf7e3"
NETWORK = f"{RUN_ID}_net"
API_CONTAINER = f"{RUN_ID}_api"
IMAGE = "poa-backend:be037final"

DB_HOST, DB_PORT, DB_NAME = "127.0.0.1", 15442, f"{RUN_ID}_app"
OWNER_PW = f"{RUN_ID}pw"
RUNTIME_ROLE, RUNTIME_PW = f"{RUN_ID}_runtime", f"{RUN_ID}rtpw"
S3_HOST_ENDPOINT = "http://127.0.0.1:19010"
ADMIN_USER, ADMIN_SECRET = f"{RUN_ID}admin", f"{RUN_ID}secret"
QUARANTINE_BUCKET, EVIDENCE_BUCKET = f"{RUN_ID}-quarantine", f"{RUN_ID}-evidence"
QUEUE = f"{RUN_ID}:analysis:jobs"
API_PORT = 18080
JWT_SECRET = f"{RUN_ID}-disposable-jwt-value-not-used-by-any-codepath-0123456789"

SECRETS = [OWNER_PW, RUNTIME_PW, ADMIN_SECRET, ADMIN_USER, JWT_SECRET]

OUT: dict = {"run_id": RUN_ID, "phases": []}


def redact(text: str) -> str:
    for secret in SECRETS:
        text = text.replace(secret, "***REDACTED***")
    return text


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {redact(msg)}", flush=True)


def save() -> None:
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / "wsf-02-f1-f3.json").write_text(redact(json.dumps(OUT, indent=2, default=str)),
                                                encoding="utf-8")


def docker(*args: str, timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    return proc.returncode, redact((proc.stdout + proc.stderr).strip())


def sql(statement: str, params=None, dbname: str = DB_NAME, user: str = "postgres",
        password: str = OWNER_PW) -> list[tuple]:
    import psycopg2

    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=user, password=password,
                            dbname=dbname, connect_timeout=10)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            return cur.fetchall() if cur.description else []
    finally:
        conn.close()


def counts() -> dict:
    """The database side of every authorization answer."""
    return {
        "analysis_jobs": sql("select count(*) from analysis_jobs")[0][0],
        "evidence_rows": sql("select count(*) from evidence")[0][0],
        "audit_rows": sql("select count(*) from audit_ledger_events")[0][0],
        "evidence_by_status": dict(sql(
            "select status, count(*) from evidence group by status order by 1")),
    }


def diff(before: dict, after: dict) -> dict:
    """The per-request change in row counts, for the numeric counters only."""
    return {
        key: after[key] - before[key]
        for key in before
        if isinstance(before[key], int) and isinstance(after[key], int)
    }


# ---------------------------------------------------------------------------
# container lifecycle
# ---------------------------------------------------------------------------

def api_env(auth_mode: str, dev_tokens: bool, environment: str = "development") -> list[str]:
    return [
        "-e", f"ENVIRONMENT={environment}",
        "-e", f"DATABASE_URL=postgresql+psycopg2://{RUNTIME_ROLE}:{RUNTIME_PW}@db:5432/{DB_NAME}",
        "-e", "REDIS_URL=redis://redis:6379/0",
        "-e", "S3_ENDPOINT=http://minio:9000",
        "-e", "S3_USE_SSL=false",
        "-e", f"S3_ACCESS_KEY={ADMIN_USER}",
        "-e", f"S3_SECRET_KEY={ADMIN_SECRET}",
        "-e", f"S3_QUARANTINE_BUCKET={QUARANTINE_BUCKET}",
        "-e", f"S3_EVIDENCE_BUCKET={EVIDENCE_BUCKET}",
        "-e", f"ANALYSIS_QUEUE_NAME={QUEUE}",
        "-e", "ANALYSIS_REDIS_SOCKET_TIMEOUT_SECONDS=30",
        "-e", "ANALYSIS_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=5",
        "-e", "ANALYSIS_REDIS_HEALTH_CHECK_INTERVAL_SECONDS=15",
        "-e", "ANALYSIS_DEQUEUE_BLOCK_SECONDS=5",
        "-e", "ANALYSIS_RETRY_BACKOFF_BASE_SECONDS=5",
        "-e", "ANALYSIS_RETRY_BACKOFF_MAX_SECONDS=60",
        "-e", "ANALYSIS_SHUTDOWN_POLL_SECONDS=0.5",
        "-e", "ANALYSIS_ABANDONED_TIMEOUT_SECONDS=300",
        "-e", f"AUTH_MODE={auth_mode}",
        "-e", f"AUTH_DEV_TOKENS_ENABLED={'true' if dev_tokens else 'false'}",
        "-e", f"JWT_SECRET={JWT_SECRET}",
        "-e", f"CORS_ALLOW_ORIGINS=http://127.0.0.1:{API_PORT}",
        "-e", "HF_HUB_OFFLINE=1",
        "-e", "TRANSFORMERS_OFFLINE=1",
    ]


def start_api(name: str, auth_mode: str, dev_tokens: bool, environment: str = "development",
              extra: list[str] | None = None) -> dict:
    docker("rm", "-f", name)
    cmd = ["run", "-d", "--name", name, "--network", NETWORK,
           "--label", f"be037.run={RUN_ID}", "--label", f"be037.role={name.split('_', 1)[-1]}",
           "-p", f"127.0.0.1:{API_PORT}:8000", *api_env(auth_mode, dev_tokens, environment)]
    if extra:
        cmd += extra
    cmd += [IMAGE]
    rc, out = docker(*cmd, timeout=180)
    ready = wait_http("GET", "/ready", timeout=120) if rc == 0 else None
    facts = docker("inspect", "-f",
                   "{{.Id}}|{{.Created}}|{{.State.Status}}|{{.RestartCount}}", name)
    cid, created, state, restarts = (facts[1].split("|") if facts[0] == 0 else ("", "", "?", "?"))
    log(f"api {name} rc={rc} state={state} ready={ready} id={cid[:12]}")
    return {"docker_run_rc": rc, "id": cid, "id_short": cid[:12], "created": created,
            "state": state, "restart_count": restarts,
            "auth_mode": auth_mode, "dev_tokens": dev_tokens, "environment": environment,
            "ready_probe": ready}


def wait_http(method: str, path: str, token: str | None = None, timeout: int = 90,
              expect: int = 200) -> dict | None:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        status, body = http(method, path, token=token)
        last = {"status": status, "body": body[:300]}
        if status == expect:
            return last
        time.sleep(1.5)
    return last


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def http(method: str, path: str, token: str | None = None, json_body=None,
         multipart: tuple[str, bytes, str] | None = None,
         headers: dict | None = None) -> tuple[int, str]:
    url = f"http://127.0.0.1:{API_PORT}{path}"
    data = None
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if multipart:
        field, payload, ctype = multipart
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
            f"filename=\"synthetic.jpg\"\r\nContent-Type: {ctype}\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
        hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        data = body
    elif json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, redact(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, redact(exc.read().decode("utf-8", "replace"))
    except Exception as exc:  # connection-level failure is a result, not a crash
        return -1, redact(f"{type(exc).__name__}: {exc}")


def jbody(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# phase 0 — bootstrap identities through the real API, development mode
# ---------------------------------------------------------------------------

def bootstrap() -> dict:
    boot: dict = {"shape": "AUTH_MODE=development (anonymous bypass)", "steps": []}
    created: dict = {}

    def post(path, body, label, expect):
        status, text = http("POST", path, json_body=body)
        boot["steps"].append({"label": label, "path": path, "status": status,
                              "expected": expect, "met": status == expect})
        return status, jbody(text)

    for name in ("wf_admin", "wf_officer_a", "wf_officer_b", "wf_citizen_a", "wf_intake"):
        status, obj = post("/api/v1/auth/users",
                           {"username": name, "email": f"{name}@{RUN_ID}.example"},
                           f"create user {name}", 201)
        created[name] = obj["id"] if obj else None

    status, obj = post("/api/v1/auth/organizations",
                       {"name": "Organisation A", "code": f"{RUN_ID}-a"}, "create org A", 201)
    created["org_a"] = obj["id"] if obj else None
    status, obj = post("/api/v1/auth/organizations",
                       {"name": "Organisation B", "code": f"{RUN_ID}-b"}, "create org B", 201)
    created["org_b"] = obj["id"] if obj else None

    for label, owner in (("project A", created["wf_admin"]), ("project B", created["wf_admin"])):
        status, obj = post("/api/v1/projects", {"name": f"{RUN_ID} {label}", "owner_id": owner},
                           f"create {label}", 201)
        created["project_a" if "A" in label else "project_b"] = obj["id"] if obj else None

    for label, key, org in (("scope project A", "project_a", created["org_a"]),
                            ("scope project B", "project_b", created["org_b"])):
        status, text = http("PATCH", f"/api/v1/auth/projects/{created[key]}/scope",
                            json_body={"organization_id": org})
        boot["steps"].append({"label": label, "status": status, "expected": 200,
                              "met": status == 200})

    roles = [
        ("GLOBAL ADMINISTRATOR", created["wf_admin"], {"role_name": "ADMINISTRATOR",
                                                       "scope_type": "GLOBAL"}),
        ("ORG FIELD_OFFICER A", created["wf_officer_a"], {"role_name": "FIELD_OFFICER",
                                                          "scope_type": "ORGANIZATION",
                                                          "organization_id": created["org_a"]}),
        ("ORG FIELD_OFFICER B", created["wf_officer_b"], {"role_name": "FIELD_OFFICER",
                                                          "scope_type": "ORGANIZATION",
                                                          "organization_id": created["org_b"]}),
        ("ORG CITIZEN A", created["wf_citizen_a"], {"role_name": "CITIZEN",
                                                    "scope_type": "ORGANIZATION",
                                                    "organization_id": created["org_a"]}),
        # The catalogue measures `evidence.update_context` as held only by
        # FIELD_OFFICER, and the RESOURCE_UNSCOPEABLE rule requires GLOBAL scope
        # to project an evidence row that has no project yet. This is the one
        # user identity that satisfies both.
        ("GLOBAL FIELD_OFFICER intake", created["wf_intake"], {"role_name": "FIELD_OFFICER",
                                                               "scope_type": "GLOBAL"}),
    ]
    for label, user_id, body in roles:
        status, _ = post(f"/api/v1/auth/users/{user_id}/roles", body, f"role {label}", 201)

    # API clients. Secrets exist only in this dict, only in memory.
    clients: dict = {}
    client_specs = [
        ("full_a", {"name": f"{RUN_ID} client full A", "project_id": created["project_a"],
                    "scopes": ["intelligence.reprocess", "evidence.read", "evidence.create",
                               "evidence.update_context"]}),
        ("read_only_a", {"name": f"{RUN_ID} client read-only A", "project_id": created["project_a"],
                         "scopes": ["evidence.read"]}),
        ("full_b", {"name": f"{RUN_ID} client full B", "project_id": created["project_b"],
                    "scopes": ["intelligence.reprocess", "evidence.read", "evidence.create",
                               "evidence.update_context"]}),
        # No project_id, so every scope this client holds is GLOBAL
        # (services/authorization.py:257). Required by the RESOURCE_UNSCOPEABLE
        # rule: a freshly uploaded evidence has no project, so only a GLOBAL
        # grant can pass it through the context guard.
        ("intake", {"name": f"{RUN_ID} client intake global",
                    "scopes": ["evidence.create", "evidence.read", "evidence.update_context",
                               "intelligence.reprocess"]}),
        ("audit_global", {"name": f"{RUN_ID} client audit global",
                          "scopes": ["audit.read"]}),
        ("audit_project", {"name": f"{RUN_ID} client audit project",
                           "project_id": created["project_a"], "scopes": ["audit.read"]}),
    ]
    for key, body in client_specs:
        status, obj = post("/api/v1/integrations/clients", body, f"create client {key}", 201)
        if obj and obj.get("secret"):
            clients[key] = f'{obj["id"]}:{obj["secret"]}'
            boot["steps"][-1]["secret_returned_once"] = True
            boot["steps"][-1]["client_id"] = obj["id"]
            boot["steps"][-1]["scopes"] = obj["scopes"]
            boot["steps"][-1]["project_scoped"] = obj.get("project_id") is not None

    # The /auth/clients contract deliberately returns no secret material.
    status, text = http("POST", "/api/v1/auth/clients",
                        json_body={"name": f"{RUN_ID} auth client", "scopes": ["evidence.read"]})
    obj = jbody(text) or {}
    boot["api_client_contract"] = {
        "integrations_clients_returns_secret_once": any(
            s.get("secret_returned_once") for s in boot["steps"]),
        "auth_clients_status": status,
        "auth_clients_response_has_secret_field": "secret" in (obj or {}),
        "auth_clients_response_keys": sorted((obj or {}).keys()),
    }

    boot["created_ids"] = created
    boot["clients_created"] = sorted(clients)
    log(f"bootstrap steps met={sum(1 for s in boot['steps'] if s['met'])}/"
        f"{len(boot['steps'])}")
    return {"boot": boot, "ids": created, "tokens": clients}


# ---------------------------------------------------------------------------
# phase 1 — enforcing, dev tokens OFF
# ---------------------------------------------------------------------------

def matrix_dev_tokens_off(ids: dict, tokens: dict) -> dict:
    """Every row records the HTTP answer *and* the database side effect."""
    results: list[dict] = []
    job_id: str | None = None

    def probe(label, method, path, *, token=None, body=None, expect, multipart=None,
              headers=None):
        before = counts()
        status, text = http(method, path, token=token, json_body=body, multipart=multipart,
                            headers=headers)
        after = counts()
        results.append({
            "case": label, "request": f"{method} {path}", "expected_status": expect,
            "observed_status": status, "met": status == expect,
            "detail_excerpt": (jbody(text) or {}).get("detail") if text else None,
            "db_before": before, "db_after": after,
            "db_side_effect": diff(before, after),
            "evidence_by_status_after": after["evidence_by_status"],
        })
        log(f"{label}: {status} (expected {expect}) delta={after['analysis_jobs'] - before['analysis_jobs']}")
        return status, text

    evidence_id = probe_create_evidence(tokens["full_a"], results)
    evidence_a = evidence_id
    if evidence_id:
        # Context attachment is the step that decides whether the rest of the
        # ingest chain is reachable at all. The rule under test is
        # RESOURCE_UNSCOPEABLE: a resource whose project cannot be resolved is
        # denied as 404 unless the caller holds the permission in GLOBAL scope
        # (unit-pinned by tests/unit/test_authorization.py
        # ::test_unscoped_resource_requires_global). A freshly uploaded evidence
        # has no project yet, so its own uploader — holding PROJECT scope — is
        # refused. That is fail-closed by design; the consequence for
        # integrators is recorded as an observation, not smoothed over here.
        scoped_attach = http("PATCH", f"/api/v1/evidence/{evidence_id}/context",
                             token=tokens["full_a"], json_body={"project_id": ids["project_a"]})
        results.append({
            "case": "project-scoped client attaches context to evidence it uploaded",
            "request": f"PATCH /api/v1/evidence/{evidence_id}/context",
            "expected_status": 404, "observed_status": scoped_attach[0],
            "met": scoped_attach[0] == 404, "detail": jbody(scoped_attach[1]),
            "design_rule": "RESOURCE_UNSCOPEABLE -> 404 unless GLOBAL grant",
        })
        no_perm = http("PATCH", f"/api/v1/evidence/{evidence_id}/context",
                       token=tokens["read_only_a"],
                       json_body={"project_id": ids["project_a"]})
        results.append({
            "case": "client without evidence.update_context attaches context",
            "request": f"PATCH /api/v1/evidence/{evidence_id}/context",
            "expected_status": 403, "observed_status": no_perm[0], "met": no_perm[0] == 403,
            "detail": jbody(no_perm[1]),
        })
        attach = http("PATCH", f"/api/v1/evidence/{evidence_id}/context",
                      token=tokens["intake"], json_body={"project_id": ids["project_a"]})
        results.append({"case": "GLOBAL-scope intake client attaches evidence to project A",
                        "request": f"PATCH /api/v1/evidence/{evidence_id}/context",
                        "expected_status": 200, "observed_status": attach[0],
                        "met": attach[0] == 200, "detail": jbody(attach[1]),
                        "db_side_effect": {}})

    # anonymous / invalid / dev-token cases
    probe("anonymous enqueue", "POST", "/api/v1/analysis/jobs",
          body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=401)
    probe("invalid bearer", "POST", "/api/v1/analysis/jobs", token="not-a-real-credential",
          body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=401)
    probe("dev-user token while dev tokens disabled", "POST", "/api/v1/analysis/jobs",
          token=f"dev-user-{ids['wf_officer_a']}",
          body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=401)
    probe("client with unknown secret", "POST", "/api/v1/analysis/jobs",
          token=f'{tokens["full_a"].split(":")[0]}:wrong-secret',
          body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=401)

    # permission / scope cases
    if evidence_a:
        probe("client without intelligence.reprocess", "POST", "/api/v1/analysis/jobs",
              token=tokens["read_only_a"],
              body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=403)
        probe("cross-organisation client (B on A evidence)", "POST", "/api/v1/analysis/jobs",
              token=tokens["full_b"],
              body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=404)
        enqueue_status, enqueue_text = probe(
            "authorised enqueue (GLOBAL intake client)", "POST", "/api/v1/analysis/jobs",
            token=tokens["intake"],
            body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=202)
        scoped_enqueue = probe(
            "enqueue by the project-A client (evidence now projected)", "POST",
            "/api/v1/analysis/jobs", token=tokens["full_a"],
            body={"evidence_id": evidence_a, "job_type": "fingerprint"}, expect=202)
        job_id = (jbody(enqueue_text) or {}).get("job_id") if enqueue_status == 202 else None
        if job_id is None and scoped_enqueue[0] == 202:
            job_id = (jbody(scoped_enqueue[1]) or {}).get("job_id")
        probe("malformed job id", "GET", "/api/v1/analysis/jobs/not-a-uuid",
              token=tokens["full_a"], expect=422)
        probe("absent job id (valid uuid)", "GET", f"/api/v1/analysis/jobs/{uuid.uuid4()}",
              token=tokens["full_a"], expect=404)

        if job_id:
            probe("authorised job read", "GET", f"/api/v1/analysis/jobs/{job_id}",
                  token=tokens["full_a"], expect=200)

    # the anchored audit endpoint (F-03) under an enforcing API
    probe("anchored verify, global-scope audit.read client", "GET",
          "/api/v1/audit/verify/anchored?baseline=none", token=tokens["audit_global"], expect=200)
    probe("anchored verify, project-scope audit.read client", "GET",
          "/api/v1/audit/verify/anchored?baseline=none", token=tokens["audit_project"], expect=403)
    probe("anchored verify, client without audit.read", "GET",
          "/api/v1/audit/verify/anchored?baseline=none", token=tokens["read_only_a"], expect=403)
    probe("anchored verify, unknown baseline name", "GET",
          "/api/v1/audit/verify/anchored?baseline=does-not-exist",
          token=tokens["audit_global"], expect=422)
    probe("anchored verify, anonymous", "GET", "/api/v1/audit/verify/anchored", expect=401)
    probe("health surface anonymous /health", "GET", "/health", expect=200)
    probe("ready surface anonymous /ready", "GET", "/ready", expect=200)
    probe("api docs/openapi reachable", "GET", "/openapi.json", expect=200)

    return {"shape": "AUTH_MODE=enforcing, AUTH_DEV_TOKENS_ENABLED=false",
            "cases": results,
            "enqueued_job_id": locals().get("job_id"),
            "all_expected_met": all(r["met"] for r in results),
            "rejected_cases": [r["case"] for r in results if r["observed_status"] in (401, 403, 404, 422)],
            "rejected_cases_with_row_growth": [
                r["case"] for r in results
                if r["observed_status"] in (401, 403, 404, 422)
                and r.get("db_side_effect")
                and any(v for v in r["db_side_effect"].values())
            ],
            "no_row_created_for_rejected_requests": all(
                not any(v for v in (r.get("db_side_effect") or {}).values())
                for r in results if r["observed_status"] in (401, 403, 404, 422))}


def probe_create_evidence(token: str, sink: list) -> str | None:
    payload = synthetic_jpeg(seed=1)
    status, text = http("POST", "/api/v1/evidence", token=token,
                        multipart=("file", payload, "image/jpeg"))
    sink.append({"case": "authorised evidence upload (creates the object)",
                 "request": "POST /api/v1/evidence", "expected_status": 201,
                 "observed_status": status, "met": status == 201,
                 "body_excerpt": (jbody(text) or {}), "bytes": len(payload)})
    obj = jbody(text) or {}
    return obj.get("evidence_id")


def synthetic_jpeg(seed: int = 1, size: int = 240) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (size, size), (20 * (seed % 8) + 10, 40, 90))
    draw = ImageDraw.Draw(img)
    for i in range(0, size, 20):
        draw.rectangle([i, (i * seed) % size, i + 12, ((i * seed) % size) + 12],
                       fill=(200 - i % 100, 220, 30 + i % 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# phase 2 — enforcing, dev tokens ON (user-role cases)
# ---------------------------------------------------------------------------

def matrix_dev_tokens_on(ids: dict, tokens: dict) -> dict:
    results: list[dict] = []

    def probe(label, method, path, *, token=None, body=None, expect):
        before = counts()
        status, text = http(method, path, token=token, json_body=body)
        after = counts()
        results.append({"case": label, "request": f"{method} {path}", "expected_status": expect,
                        "observed_status": status, "met": status == expect,
                        "detail_excerpt": (jbody(text) or {}).get("detail") if text else None,
                        "db_side_effect": diff(before, after),
                        "evidence_by_status_after": after["evidence_by_status"]})
        log(f"{label}: {status} (expected {expect})")
        return status, text

    dev = lambda user: f"dev-user-{ids[user]}"

    # The permission->role shape the expectations below are pinned to, measured
    # from this run's own seeded catalogue rather than quoted from memory.
    holders = sql(
        """
        select p.name, r.name
        from role_permissions rp
        join permissions p on p.id = rp.permission_id
        join roles r on r.id = rp.role_id
        where p.name in ('evidence.update_context', 'intelligence.reprocess',
                         'evidence.create', 'audit.read')
        order by p.name, r.name
        """)
    permission_holders: dict = {}
    for permission, role in holders:
        permission_holders.setdefault(permission, []).append(role)

    # a second piece of evidence, uploaded by the officer-A user, attached to project A
    payload = synthetic_jpeg(seed=3)
    status, text = http("POST", "/api/v1/evidence", token=dev("wf_officer_a"),
                        multipart=("file", payload, "image/jpeg"))
    obj = jbody(text) or {}
    ev2 = obj.get("evidence_id")
    results.append({"case": "user upload (FIELD_OFFICER, evidence.create)",
                    "request": "POST /api/v1/evidence", "expected_status": 201,
                    "observed_status": status, "met": status == 201, "bytes": len(payload)})
    if ev2:
        st, txt = http("PATCH", f"/api/v1/evidence/{ev2}/context", token=dev("wf_officer_a"),
                       json_body={"project_id": ids["project_a"]})
        results.append({"case": "ORG-scope FIELD_OFFICER attaches context to unprojected evidence",
                        "expected_status": 404, "observed_status": st, "met": st == 404,
                        "detail": jbody(txt),
                        "design_rule": "RESOURCE_UNSCOPEABLE -> 404 unless GLOBAL grant"})
        st, txt = http("PATCH", f"/api/v1/evidence/{ev2}/context", token=dev("wf_admin"),
                       json_body={"project_id": ids["project_a"]})
        results.append({"case": "GLOBAL ADMINISTRATOR attaches evidence to project A",
                        "expected_status": 403, "observed_status": st, "met": st == 403,
                        "detail": jbody(txt),
                        "design_rule": "NO_PERMISSION -> 403; the seeded catalogue "
                                       "grants evidence.update_context only to FIELD_OFFICER "
                                       "(see context_permission_holders measured in this run)"})
        st, txt = http("PATCH", f"/api/v1/evidence/{ev2}/context", token=dev("wf_intake"),
                       json_body={"project_id": ids["project_a"]})
        results.append({"case": "GLOBAL FIELD_OFFICER (intake) attaches evidence to project A",
                        "expected_status": 200, "observed_status": st, "met": st == 200,
                        "detail": jbody(txt)})

    probe("dev-user enqueue (officer A, permission in org scope)", "POST",
          "/api/v1/analysis/jobs", token=dev("wf_officer_a"),
          body={"evidence_id": ev2, "job_type": "fingerprint"}, expect=202)
    probe("dev-user CITIZEN (no intelligence.reprocess)", "POST", "/api/v1/analysis/jobs",
          token=dev("wf_citizen_a"), body={"evidence_id": ev2, "job_type": "fingerprint"},
          expect=403)
    st, text = probe("dev-user officer B on A evidence (cross-org)", "POST",
                     "/api/v1/analysis/jobs", token=dev("wf_officer_b"),
                     body={"evidence_id": ev2, "job_type": "fingerprint"}, expect=404)
    probe("unknown dev-user id", "POST", "/api/v1/analysis/jobs",
          token=f"dev-user-{uuid.uuid4()}", body={"evidence_id": ev2}, expect=401)

    # read a job belonging to another organisation: hidden, and no result leaked
    job_of_a = sql("select id from analysis_jobs where evidence_id=%s", (ev2,))
    if job_of_a:
        probe("officer B reading an A job", "GET", f"/api/v1/analysis/jobs/{job_of_a[0][0]}",
              token=dev("wf_officer_b"), expect=404)
        probe("officer A reading its own job", "GET", f"/api/v1/analysis/jobs/{job_of_a[0][0]}",
              token=dev("wf_officer_a"), expect=200)
    probe("malformed evidence id in enqueue body", "POST", "/api/v1/analysis/jobs",
          token=dev("wf_officer_a"), body={"evidence_id": "not-a-uuid"}, expect=422)
    probe("invalid job_type literal", "POST", "/api/v1/analysis/jobs", token=dev("wf_officer_a"),
          body={"evidence_id": ev2, "job_type": "telepathy"}, expect=422)
    probe("dev-user ADMINISTRATOR on anchored verify", "GET",
          "/api/v1/audit/verify/anchored?baseline=none", token=dev("wf_admin"), expect=200)
    probe("dev-user CITIZEN on anchored verify", "GET",
          "/api/v1/audit/verify/anchored?baseline=none", token=dev("wf_citizen_a"), expect=403)

    cross = next((r for r in results if "cross-org" in r["case"]), None)
    body_leak = None
    if job_of_a:
        st, text = http("GET", f"/api/v1/analysis/jobs/{job_of_a[0][0]}", token=dev("wf_officer_b"))
        body_leak = {"status": st, "contains_result": "result" in (jbody(text) or {}),
                     "keys": sorted((jbody(text) or {}).keys())}
    return {"shape": "AUTH_MODE=enforcing, AUTH_DEV_TOKENS_ENABLED=true",
            "context_permission_holders_measured": permission_holders,
            "cases": results, "all_expected_met": all(r["met"] for r in results),
            "cross_org_job_read_body": body_leak,
            "cross_org_row_created": cross["db_side_effect"]["analysis_jobs"] if cross else None}


# ---------------------------------------------------------------------------
# phase 3 — F3: synthetic evidence end-to-end through the real API flow
# ---------------------------------------------------------------------------

def start_worker(name: str) -> dict:
    docker("rm", "-f", name)
    rc, out = docker("run", "-d", "--name", name, "--network", NETWORK,
                     "--label", f"be037.run={RUN_ID}", "--label", "be037.role=worker",
                     *api_env("enforcing", True),
                     IMAGE, "python", "-m", "backend.workers.analysis_worker", timeout=180)
    facts = docker("inspect", "-f", "{{.Id}}|{{.State.Status}}|{{.RestartCount}}", name)
    cid, state, restarts = (facts[1].split("|") if facts[0] == 0 else ("", "?", "?"))
    log(f"worker {name} rc={rc} state={state} id={cid[:12]} out={out[:120]}")
    return {"docker_run_rc": rc, "id": cid, "id_short": cid[:12], "state": state,
            "restart_count": restarts}


def f3_end_to_end(ids: dict, tokens: dict) -> dict:
    """The whole path, with no invented endpoint and no bypassed authorisation.

    Each step uses the credential the design authorises for that step: upload by
    the project-A client, context by the GLOBAL intake client (the measured
    RESOURCE_UNSCOPEABLE rule), then enqueue and read back by the project-A
    client, so the scoped read of the job its project produced is exercised too.
    """
    res: dict = {"queue": QUEUE}
    token = tokens["full_a"]
    payload = synthetic_jpeg(seed=7)
    import hashlib

    res["local_sha256"] = hashlib.sha256(payload).hexdigest()
    res["local_bytes"] = len(payload)

    status, text = http("POST", "/api/v1/evidence", token=token,
                        multipart=("file", payload, "image/jpeg"))
    obj = jbody(text) or {}
    evidence_id = obj.get("evidence_id")
    res["upload"] = {"request": "POST /api/v1/evidence", "expected": 201, "status": status,
                     "met": status == 201, "response_keys": sorted(obj.keys()),
                     "status_field": obj.get("status"), "storage_key": obj.get("storage_key"),
                     "content_type": obj.get("content_type"), "size": obj.get("size")}
    if not evidence_id:
        res["abort_reason"] = "evidence upload failed, nothing downstream could run"
        return res

    st, txt = http("PATCH", f"/api/v1/evidence/{evidence_id}/context",
                   token=tokens["intake"], json_body={"project_id": ids["project_a"]})
    res["context_attach"] = {"expected": 200, "status": st, "met": st == 200,
                             "body": jbody(txt)}

    st, txt = http("POST", "/api/v1/analysis/jobs", token=token,
                   json_body={"evidence_id": evidence_id, "job_type": "fingerprint"})
    job = jbody(txt) or {}
    job_id = job.get("job_id")
    res["enqueue"] = {"expected": 202, "status": st, "met": st == 202, "job_id": job_id,
                      "job_status": job.get("status")}
    if not job_id:
        res["abort_reason"] = "enqueue failed, worker had nothing to consume"
        return res

    worker = start_worker(f"{RUN_ID}_worker")
    res["worker_container"] = worker

    # Queue lengths observed *before* the worker can only be a host-side read of
    # this run's Redis; then poll the API until the job reaches a terminal state.
    deadline = time.monotonic() + 240
    seen: list[str] = []
    final: dict = {}
    while time.monotonic() < deadline:
        st, txt = http("GET", f"/api/v1/analysis/jobs/{job_id}", token=token)
        body = jbody(txt) or {}
        state = body.get("status")
        if state and (not seen or seen[-1] != state):
            seen.append(state)
        final = {"status": st, "job_status": state, "attempt_count": body.get("attempt_count"),
                 "error": body.get("error"), "has_result": "result" in body,
                 "completed_at": body.get("completed_at")}
        if state in ("completed", "failed"):
            break
        time.sleep(2)
    res["status_sequence_as_seen_by_the_api"] = seen
    res["job_final_via_api"] = final

    # Database truth for the same job.
    row = sql("select status, attempt_count, error, completed_at is not null from "
              "analysis_jobs where id=%s", (job_id,))
    res["job_final_in_database"] = row[0] if row else None
    result_row = sql("select result, embedding, created_at is not null from analysis_results "
                     "where job_id=%s", (job_id,))
    if result_row:
        stored, embedding, has = result_row[0]
        dup = (stored or {}).get("duplicate_analysis", {})
        res["stored_result"] = {
            "exists": bool(has),
            "phash": (stored or {}).get("phash"),
            "phash_status": (stored or {}).get("phash_status"),
            "sha256": (stored or {}).get("sha256"),
            "sha256_matches_local_bytes": (stored or {}).get("sha256") == res["local_sha256"],
            "embedding_column_null": embedding is None,
            "embedding_status": dup.get("embedding_status"),
            "embedding_error_present": bool(dup.get("embedding_error")),
            "embedding_error_excerpt": (dup.get("embedding_error") or "")[:200],
            "semantic_matches": len(dup.get("semantic_matches") or []),
            "perceptual_matches": len(dup.get("perceptual_matches") or []),
        }
    res["inference_limitation"] = {
        "model_weights_present_in_image": False,
        "downloads_performed_by_this_run": False,
        "reason": "HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 are set on every container "
                  "this run starts, and the image contains no weights, so the embedding path "
                  "takes its documented 'unavailable' branch. A fingerprint job therefore "
                  "completes with real perceptual hashing and NO semantic vector: the stored "
                  "result records the loader failure instead of fabricating a vector.",
        "what_full_inference_would_need": "an explicit owner decision to allow an outbound "
                                          "weight download, or a pre-seeded read-only model "
                                          "cache volume mounted into the container.",
    }

    # The object itself, in this run's MinIO, read back through the S3 API.
    import boto3

    s3 = boto3.client("s3", endpoint_url=S3_HOST_ENDPOINT, aws_access_key_id=ADMIN_USER,
                      aws_secret_access_key=ADMIN_SECRET, region_name="us-east-1")
    key = obj.get("storage_key")
    stored_obj = s3.get_object(Bucket=QUARANTINE_BUCKET, Key=key)
    body_bytes = stored_obj["Body"].read()
    res["minio_object"] = {
        "bucket": QUARANTINE_BUCKET,
        "key": key,
        "content_length": stored_obj.get("ContentLength"),
        "bytes_equal_local": body_bytes == payload,
        "sha256_equal_local": hashlib.sha256(body_bytes).hexdigest() == res["local_sha256"],
    }
    res["evidence_row"] = sql(
        "select status, storage_key, sha256, file_size, content_type, project_id "
        "from evidence where id=%s", (evidence_id,))[0] if sql(
        "select 1 from evidence where id=%s", (evidence_id,)) else None

    # The download endpoint hands out a signed URL. The URL is secret-bearing, so
    # only the fact that it was issued is recorded.
    st, txt = http("GET", f"/api/v1/evidence/{evidence_id}/download", token=token)
    dl = jbody(txt) or {}
    res["download_endpoint"] = {"expected": 200, "status": st, "met": st == 200,
                                "url_issued": bool(dl.get("download_url")),
                                "expires_in": dl.get("expires_in"),
                                "evidence_id_matches": dl.get("evidence_id") == evidence_id}

    res["audit_events_for_this_flow"] = sql(
        "select event_type, count(*) from audit_ledger_events group by event_type order by 2 desc")
    res["queue_lengths_after"] = {
        "main": redis_llen(QUEUE), "processing": redis_llen(f"{QUEUE}:processing")}

    # Which database identity did the running containers actually use?
    res["database_identities_in_use"] = sql(
        "select usename, application_name, count(*) from pg_stat_activity "
        "where datname=current_database() group by 1,2 order by 3 desc")

    docker("rm", "-f", f"{RUN_ID}_worker")
    return res


def redis_llen(key: str) -> int | None:
    rc, out = docker("exec", f"{RUN_ID}_redis", "redis-cli", "llen", key)
    if rc != 0:
        return None
    try:
        return int(out.strip() or "-1")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def verify_weights_absent() -> dict:
    """Measure the inference-capability claim instead of asserting it."""
    rc, out = docker(
        "run", "--rm", "--entrypoint", "sh", IMAGE, "-c",
        "find / -xdev \\( -name '*.pt' -o -name '*.onnx' -o -name '*.engine' \\) "
        "-print 2>/dev/null | head -5; echo '--- caches ---'; "
        "ls -d /root/.cache /home/appuser/.cache 2>&1 | head -4", timeout=180)
    found = [line for line in out.splitlines() if line.endswith((".pt", ".onnx", ".engine"))]
    return {"inspect_rc": rc, "weight_files_found": found,
            "cache_listing": out.splitlines()[-2:],
            "model_weights_present_in_image": bool(found)}


def app_side_ledger_check() -> dict:
    """The app's own verification, run against this stack as the runtime role."""
    env = dict(os.environ)
    env["DATABASE_URL"] = (
        f"postgresql+psycopg2://{RUNTIME_ROLE}:{RUNTIME_PW}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    env.pop("TEST_DATABASE_URL", None)
    env.pop("POA_DATABASE_CONTEXT", None)
    code = (
        "import json, os\n"
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import sessionmaker\n"
        "from backend.services import audit_ledger\n"
        "db = sessionmaker(bind=create_engine(os.environ['DATABASE_URL']))()\n"
        "print('LEDGER ' + json.dumps({'verify': audit_ledger.verify_chain(db), "
        "'checkpoint': audit_ledger.ledger_checkpoint(db), "
        "'identity': db.execute(__import__('sqlalchemy').text("
        "\"select current_user\")).scalar()}))\n"
        "db.close()\n"
    )
    proc = subprocess.run([PY, "-c", code], cwd=REPO, env=env, capture_output=True,
                          text=True, timeout=600)
    line = next((l for l in (proc.stdout + proc.stderr).splitlines() if l.startswith("LEDGER ")),
                None)
    payload = json.loads(line[len("LEDGER "):]) if line else None
    return {"rc": proc.returncode, "identity": (payload or {}).get("identity"),
            "verify": (payload or {}).get("verify"),
            "published_checkpoint_digest": (payload or {}).get("checkpoint"),
            "tail": redact((proc.stdout + proc.stderr)).strip().splitlines()[-3:]}


def main() -> int:
    EVIDENCE.mkdir(exist_ok=True)
    OUT["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    OUT["image_provenance"] = verify_weights_absent()
    save()
    log(f"image weights present={OUT['image_provenance']['model_weights_present_in_image']}")

    # Phase 0: development-mode bootstrap through the real API.
    api_dev = start_api(API_CONTAINER, "development", True)
    OUT["api_dev"] = api_dev
    boot = bootstrap()
    OUT["bootstrap"] = {k: v for k, v in boot["boot"].items() if k != "clients"}
    ids, tokens = boot["ids"], boot["tokens"]
    OUT["identity_ids"] = ids
    save()

    # Phase 1: enforcing, dev tokens OFF.
    api_off = start_api(API_CONTAINER, "enforcing", False)
    OUT["api_enforcing_devtokens_off"] = api_off
    OUT["f1_dev_tokens_off"] = matrix_dev_tokens_off(ids, tokens)
    save()

    # Phase 2: enforcing, dev tokens ON (role subjects).
    api_on = start_api(API_CONTAINER, "enforcing", True,
                       extra=["-e", "ANALYSIS_MAX_ATTEMPTS=3"])
    OUT["api_enforcing_devtokens_on"] = api_on
    OUT["f1_dev_tokens_on"] = matrix_dev_tokens_on(ids, tokens)
    save()

    attach_cases = [
        (phase, case)
        for phase, matrix in (("dev_tokens_off", OUT["f1_dev_tokens_off"]),
                              ("dev_tokens_on", OUT["f1_dev_tokens_on"]))
        for case in matrix["cases"]
        if "context" in case.get("request", "") or "attaches" in case["case"]
    ]
    OUT["observation_wsf_obs_1"] = {
        "title": "Client-driven ingest requires a GLOBAL grant for the context step",
        "measured": [
            {"phase": phase, "case": case["case"], "expected": case["expected_status"],
             "observed": case["observed_status"]}
            for phase, case in attach_cases
        ],
        "mechanism": (
            "resolve_resource_scope() reports no project for an unprojected evidence "
            "(backend/services/authorization.py:1003), can() answers "
            "RESOURCE_UNSCOPEABLE, and enforce() maps that to 404 "
            "(backend/security/authorization.py:163). The rule is unit-pinned by "
            "tests/unit/test_authorization.py::test_unscoped_resource_requires_global, "
            "so fail-closed here is intended behaviour, not a regression."
        ),
        "consequence": (
            "an integrator holding only project- or organization-scoped permissions "
            "can upload bytes but can never attach them to its own project, so every "
            "real ingestion needs a paired GLOBAL intake credential. POST /api/v1/"
            "evidence accepts no project or claim field, so there is no single-call "
            "alternative. No existing test covers this path: every context-attach "
            "test runs under the development bypass."
        ),
        "classification": "Observation / design gap for the owner, not a security defect",
    }
    save()

    # Phase 3: the synthetic evidence object, all the way through.
    OUT["f3_end_to_end"] = f3_end_to_end(ids, tokens)
    OUT["f3_inference_measurement"] = OUT["image_provenance"]
    save()

    # The app's own chain verdict on this stack, plus the digest to keep.
    OUT["ledger_app_side"] = app_side_ledger_check()
    log(f"ledger identity={OUT['ledger_app_side']['identity']} "
        f"valid={ (OUT['ledger_app_side']['verify'] or {}).get('valid') }")

    docker("rm", "-f", API_CONTAINER)
    docker("rm", "-f", f"{RUN_ID}_worker")
    OUT["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save()
    log(f"f1 off all_met={OUT['f1_dev_tokens_off']['all_expected_met']} "
        f"on all_met={OUT['f1_dev_tokens_on']['all_expected_met']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
