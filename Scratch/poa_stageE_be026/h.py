"""BE-026 Stage E shared harness helpers.

Drives two *separate* uvicorn processes over real TCP so that concurrent
requests are genuinely concurrent (two server processes, two connection pools,
one PostgreSQL). Every effect is read back from Postgres/PostGIS/MinIO.

Env: BASE_URL, BASE_URL2, DATABASE_URL, LABEL, AUTH_MODE_PASS.
Rows created here are tagged with LABEL and removed by teardown(); audit ledger
rows are never touched.
"""

import io
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from PIL import Image
from sqlalchemy import text
from sqlalchemy.engine import create_engine

from backend.core.config import settings
from backend.db.session import get_session
from backend.services import audit_ledger as audit_service
from backend.services import authorization as auth_service

BASE = os.environ["BASE_URL"].rstrip("/")
BASE2 = os.environ.get("BASE_URL2", BASE).rstrip("/")
PASS = os.environ.get("AUTH_MODE_PASS", "enforcing")
LABEL = os.environ.get("LABEL", uuid.uuid4().hex[:8])
engine = create_engine(os.environ["DATABASE_URL"])
RUN_STARTED = datetime.now(timezone.utc) - timedelta(seconds=10)

PASSED = FAILED = 0
FAILURES: list[str] = []
NOTES: list[str] = []
tracked = {"users": [], "projects": [], "orgs": [], "units": [], "claims": [],
           "activities": [], "evidence": [], "clients": [], "assignments": [],
           "sessions": [], "operations": []}


# ---------------------------------------------------------------------------
# bookkeeping
# ---------------------------------------------------------------------------

def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
    else:
        FAILED += 1
        FAILURES.append(f"{name} :: {str(detail)}")
        print(f"FAIL {name} :: {str(detail)[:400]}")
    return bool(condition)


def note(text_value):
    NOTES.append(str(text_value))
    print("NOTE:", text_value)


def track_evidence(evidence_id):
    """Remember one harness-created Evidence id so teardown can remove it."""
    if evidence_id and str(evidence_id).lower() not in ("none", ""):
        tracked["evidence"].append(str(evidence_id))
    return str(evidence_id) if evidence_id else None


def section(title):
    print(f"\n===== {title} =====")


def summary():
    print(f"checks={PASSED + FAILED} passed={PASSED} failed={FAILED}")
    print("teardown_remaining=" + json.dumps(residue()))
    for line in FAILURES:
        print("FAILED::", line)
    print("GATE:", "PASS" if FAILED == 0 else "FAIL")
    return 0 if FAILED == 0 else 1


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------

def hdr(principal_id):
    return {"Authorization": f"Bearer dev-user-{principal_id}"}


def client_hdr(client_id):
    return {"Authorization": f"Bearer dev-client-{client_id}"}


def iso(minutes=0, seconds=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes,
                                                   seconds=seconds)).isoformat()


def jpeg(size=16, color=(20, 120, 220)):
    out = io.BytesIO()
    Image.new("RGB", (size, size), color=color).save(out, format="JPEG")
    return out.getvalue()


def png_bytes(size=64):
    out = io.BytesIO()
    Image.new("RGB", (size, size), color=(200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


def noise_image(min_bytes):
    """Incompressible image comfortably over `min_bytes` (real image signature)."""
    import random
    rnd = random.Random(1234)
    w = h = 900
    data = bytes(rnd.randrange(256) for _ in range(w * h * 3 // 4))
    img = Image.frombytes("RGB", (w, h), data + b"\x00" * (w * h * 3 - len(data)))
    out = io.BytesIO()
    img.save(out, format="PNG", compress_level=0)
    if out.getbuffer().nbytes < min_bytes:
        w = h = 1400
        data = bytes(rnd.randrange(256) for _ in range(w * h * 3))
        img = Image.frombytes("RGB", (w, h), data)
        out = io.BytesIO()
        img.save(out, format="PNG", compress_level=0)
    return out.getvalue()


def q(sql, **params):
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(sql), params).fetchall()]


def q1(sql, **params):
    rows = q(sql, **params)
    return rows[0] if rows else None


def scalar(sql, **params):
    row = q1(sql, **params)
    return row[0] if row else None


def audit_events(event_type, resource_id=None, since=True):
    sql = ("select payload, actor_id, project_id, resource_type, sequence_number"
           " from audit_ledger_events where event_type=:t")
    params = {"t": event_type}
    if since:
        sql += " and created_at >= :s"
        params["s"] = RUN_STARTED
    if resource_id:
        sql += " and resource_id=:r"
        params["r"] = resource_id
    sql += " order by sequence_number"
    return q(sql, **params)


def audit_count(event_type, resource_id=None):
    return len(audit_events(event_type, resource_id))


def payload_of(payload):
    """Audit payloads arrive as dicts (JSONB); tolerate a raw string too."""
    if isinstance(payload, dict):
        return payload
    if payload is None:
        return {}
    return json.loads(payload)


def chain():
    db = get_session()
    try:
        return audit_service.verify_chain(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def new_user(label):
    uid = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id, username, email, is_active, created_at)"
                       " VALUES (:i, :u, :e, true, now())"),
                  {"i": uid, "u": f"se-{LABEL}-{label}", "e": f"{LABEL}.{label}@example.com"})
    tracked["users"].append(uid)
    return uid


def set_status(user_id, status_value):
    with engine.begin() as c:
        c.execute(text("UPDATE users SET status=:s WHERE id=:i"),
                  {"s": status_value, "i": user_id})


def new_org(label):
    db = get_session()
    try:
        org = auth_service.create_organization(db, name=f"SE {LABEL} {label}",
                                               code=f"se-{LABEL}-{label}")
        db.commit()
        db.refresh(org)
        oid = str(org.id)
    finally:
        db.close()
    tracked["orgs"].append(oid)
    return oid


def new_unit(org_id, label):
    db = get_session()
    try:
        unit = auth_service.create_organizational_unit(
            db, organization_id=org_id, name=f"SE {LABEL} {label} unit",
            code=f"se-{LABEL}-{label}-u")
        db.commit()
        db.refresh(unit)
        uid = str(unit.id)
    finally:
        db.close()
    tracked["units"].append(uid)
    return uid


def grant(user_id, role, scope="GLOBAL", scope_id=None):
    db = get_session()
    try:
        kwargs = {}
        if scope == "ORGANIZATION":
            kwargs["organization_id"] = scope_id
        elif scope == "PROJECT":
            kwargs["project_id"] = scope_id
        auth_service.assign_role(db, user_id=user_id, role_name=role,
                                 scope_type=scope, **kwargs)
        db.commit()
    finally:
        db.close()


def new_project(actor_id, owner_id, name, org_id, unit_id):
    r = requests.post(f"{BASE}/api/v1/projects", json={"name": name, "owner_id": owner_id},
                      headers=hdr(actor_id), timeout=60)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    tracked["projects"].append(pid)
    with engine.begin() as c:
        c.execute(text("UPDATE projects SET organization_id=:o, organizational_unit_id=:u"
                       " WHERE id=:i"), {"o": org_id, "u": unit_id, "i": pid})
    return pid


def new_claim(project_id, claimant_id, title=None):
    r = requests.post(f"{BASE}/api/v1/projects/{project_id}/claims",
                      json={"claimant_id": claimant_id, "title": title or f"se {LABEL} claim"},
                      headers=hdr(claimant_id), timeout=60)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    tracked["claims"].append(cid)
    return cid


def new_activity(project_id, actor_id):
    r = requests.post(f"{BASE}/api/v1/projects/{project_id}/activities",
                      json={"actor_id": actor_id, "verb": "observed"},
                      headers=hdr(actor_id), timeout=60)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    tracked["activities"].append(aid)
    return aid


def new_api_client(actor_id, name, scopes):
    r = requests.post(f"{BASE}/api/v1/auth/clients",
                      json={"name": name, "scopes": scopes},
                      headers=hdr(actor_id), timeout=60)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    tracked["clients"].append(cid)
    return cid


# ---------------------------------------------------------------------------
# field surface callers
# ---------------------------------------------------------------------------

def create_assignment(actor, user_id, project_id, **extra):
    body = {"user_id": user_id, "project_id": project_id}
    body.update({k: v for k, v in extra.items() if v is not None})
    return requests.post(f"{BASE}/api/v1/field/assignments", json=body,
                         headers=hdr(actor), timeout=60)


def assignment_id(response):
    if not response.ok:
        return None
    return response.json().get("id")


def open_session(actor, aid, device=None, label=None):
    body = {"assignment_id": aid}
    if device:
        body["client_device_id"] = device
    if label:
        body["session_label"] = label
    return requests.post(f"{BASE}/api/v1/field/sessions", json=body,
                         headers=hdr(actor), timeout=60)


def close_session_http(actor, sid, reason="done"):
    return requests.post(f"{BASE}/api/v1/field/sessions/{sid}/close",
                         json={"reason": reason}, headers=hdr(actor), timeout=60)


def sync(officer, op, *, data=None, content_type="image/jpeg", anonymous=False,
         base=None, headers=None, client=None, filename="capture.jpg", **fields):
    form = {"client_operation_id": op}
    form.update({k: v for k, v in fields.items() if v is not None})
    if headers is None:
        if client:
            headers = client_hdr(client)
        elif anonymous or officer is None:
            headers = {}
        else:
            headers = hdr(officer)
    return requests.post(f"{base or BASE}/api/v1/field/sync", headers=headers, timeout=180,
                         files={"file": (filename,
                                         data if data is not None else jpeg(), content_type)},
                         data=form)


def sync_raw(op, *, raw_form, data=None, content_type="image/jpeg", officer=None, base=None):
    """Send an arbitrary (including unknown/duplicate) multipart form."""
    headers = {} if officer is None else hdr(officer)
    files = {"file": ("capture.jpg", data if data is not None else jpeg(), content_type)}
    return requests.post(f"{base or BASE}/api/v1/field/sync", headers=headers, timeout=180,
                         files=files, data=raw_form)


def burst(n, fn, split_bases=True):
    """Fire n real requests concurrently across the two server processes."""
    def run(i):
        base = BASE if (not split_bases or i % 2 == 0) else BASE2
        return fn(i, base)

    with ThreadPoolExecutor(max_workers=min(n, 16)) as pool:
        return list(pool.map(run, range(n)))


def op_row(client_op=None, user=None, op_id=None):
    if op_id:
        return q1("select id, status, sync_count, evidence_id, request_hash, payload_sha256,"
                  " project_id, claim_id, session_id, assignment_id, conflict_reason,"
                  " resolution_status, latitude, longitude, captured_at, queued_at, uploaded_at,"
                  " timestamp_flags, file_size, received_at, processed_at, created_at"
                  " from field_capture_operations where id=:i", i=op_id)
    return q1("select id, status, sync_count, evidence_id, request_hash, payload_sha256,"
              " project_id, claim_id, session_id, assignment_id, conflict_reason,"
              " resolution_status, latitude, longitude, captured_at, queued_at, uploaded_at,"
              " timestamp_flags, file_size, received_at, processed_at, created_at"
              " from field_capture_operations"
              " where client_operation_id=:c and user_id=:u", c=client_op, u=user)


def assignment_row(aid):
    return q1("select status, organization_id, organizational_unit_id, claim_id, activity_id,"
              " project_id, user_id, valid_from, expires_at, closed_reason, revoked_at"
              " from field_assignments where id=:i", i=aid)


#: Columns a leftover-reservation clone must not copy verbatim.
_CLONE_OVERRIDES = {"id", "created_at", "updated_at"}


def clone_as_pending(src_op_id, *, status="PENDING", rewind_seconds=None):
    """Recreate one operation identity as a leftover row (crash simulation).

    The server computed the stored ``request_hash``, so replaying the original
    bytes and metadata against the freed identity exercises the *real*
    stale-reservation adoption path in ``_settle_existing``. The durable source
    row is kept (its identity is renamed out of the way) and both rows are
    removed by teardown.
    """
    src = q1("select client_operation_id, user_id from field_capture_operations"
             " where id=:i", i=src_op_id)
    if src is None:
        raise RuntimeError(f"clone source {src_op_id} missing")
    client_op, user_id = str(src[0]), str(src[1])
    cols = [r[0] for r in q("select column_name from information_schema.columns"
                            " where table_name='field_capture_operations'"
                            " order by ordinal_position")]
    clone_id = str(uuid.uuid4())
    select_parts = []
    params = {"i": src_op_id, "cid": clone_id, "orig": client_op}
    for col in cols:
        if col == "id":
            select_parts.append(":cid")
        elif col == "client_operation_id":
            # The source row has been renamed out of the way; the clone takes
            # the freed identity back.
            select_parts.append(":orig")
        elif col == "created_at":
            select_parts.append("now()")
        elif col == "updated_at":
            select_parts.append("now()")
        elif col == "status":
            select_parts.append(f"'{status}'")
        elif col == "evidence_id":
            select_parts.append("null")
        elif col == "processed_at":
            select_parts.append("null")
        elif col in ("received_at", "last_synced_at"):
            if rewind_seconds:
                select_parts.append(f"(now() - interval '{int(rewind_seconds)} seconds')")
            else:
                select_parts.append("now()")
        else:
            select_parts.append(col)
    with engine.begin() as c:
        c.execute(text("UPDATE field_capture_operations SET client_operation_id=:n"
                       " WHERE id=:i"),
                  {"n": f"{client_op}~archived", "i": src_op_id})
        c.execute(text(f"INSERT INTO field_capture_operations ({', '.join(cols)})"
                       f" SELECT {', '.join(select_parts)}"
                       " FROM field_capture_operations WHERE id=:i"), params)
    tracked["operations"].append(clone_id)
    return clone_id, client_op


def delete_operation(op_id):
    with engine.begin() as c:
        c.execute(text("DELETE FROM field_capture_operations WHERE id=:i"), {"i": op_id})
    if op_id in tracked["operations"]:
        tracked["operations"].remove(op_id)


def restore_identity(src_op_id, client_operation_id):
    """Put a freed identity back on its durable row after the clone is gone."""
    with engine.begin() as c:
        c.execute(text("UPDATE field_capture_operations SET client_operation_id=:c"
                       " WHERE id=:i"), {"c": client_operation_id, "i": src_op_id})


def try_delete(table, row_id):
    """Attempt one delete; return (ok, error_text). Used for integrity probes."""
    with engine.connect() as c:
        try:
            c.execute(text(f"DELETE FROM {table} WHERE id=:i"), {"i": row_id})
            c.rollback()
            return True, ""
        except Exception as error:  # noqa: BLE001 - the error *is* the result
            c.rollback()
            return False, str(error).splitlines()[0][:300]


def evidence_row(eid):
    return q1("select project_id, claim_id, file_size, content_type, storage_key, status,"
              " location, sha256 from evidence where id=:i", i=eid)


# ---------------------------------------------------------------------------
# teardown / residue
# ---------------------------------------------------------------------------

def quarantine_keys():
    import boto3
    s3 = boto3.client("s3", endpoint_url=settings.s3_endpoint,
                      aws_access_key_id=settings.s3_access_key,
                      aws_secret_access_key=settings.s3_secret_key)
    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_quarantine_bucket):
        for item in page.get("Contents", []):
            objects.append(item["Key"])
    return objects


def teardown(verbose=True):
    """FK-safe removal of harness rows. Audit ledger rows are never touched."""
    with engine.begin() as c:
        def t(k):
            return tuple(tracked[k]) if tracked[k] else None
        storage_keys = []
        if tracked["evidence"]:
            storage_keys = [r[0] for r in c.execute(
                text("SELECT storage_key FROM evidence WHERE id IN :ids"
                     " AND storage_key IS NOT NULL"), {"ids": t("evidence")}) if r[0]]
            c.execute(text("DELETE FROM evidence_metadata WHERE evidence_id IN :ids"),
                      {"ids": t("evidence")})
            c.execute(text("DELETE FROM analysis_results WHERE job_id IN"
                           " (SELECT id FROM analysis_jobs WHERE evidence_id IN :ids)"),
                      {"ids": t("evidence")})
            c.execute(text("DELETE FROM analysis_jobs WHERE evidence_id IN :ids"),
                      {"ids": t("evidence")})
            c.execute(text("DELETE FROM evidence WHERE id IN :ids"), {"ids": t("evidence")})
        # Any evidence created by this run that the harness lost track of (an
        # orphan found at gate level is deleted here only because it is ours).
        orphan_ids = [r[0] for r in c.execute(
            text("select id from evidence where project_id in"
                 " (select id from projects where name like :p)"),
            {"p": f"SE {LABEL} %"})]
        if orphan_ids:
            t_orphan = tuple(orphan_ids)
            keys = [r[0] for r in c.execute(
                text("SELECT storage_key FROM evidence WHERE id IN :ids"
                     " AND storage_key IS NOT NULL"), {"ids": t_orphan}) if r[0]]
            storage_keys.extend(keys)
            c.execute(text("DELETE FROM evidence_metadata WHERE evidence_id IN :ids"),
                      {"ids": t_orphan})
            c.execute(text("DELETE FROM analysis_results WHERE job_id IN"
                           " (SELECT id FROM analysis_jobs WHERE evidence_id IN :ids)"),
                      {"ids": t_orphan})
            c.execute(text("DELETE FROM analysis_jobs WHERE evidence_id IN :ids"),
                      {"ids": t_orphan})
            c.execute(text("DELETE FROM evidence WHERE id IN :ids"), {"ids": t_orphan})
        for col, key in (("user_id", "users"), ("project_id", "projects")):
            if tracked[key]:
                c.execute(text(f"DELETE FROM field_capture_operations WHERE {col} IN :ids"),
                          {"ids": t(key)})
        if tracked["users"]:
            c.execute(text("DELETE FROM field_sessions WHERE user_id IN :ids"), {"ids": t("users")})
            c.execute(text("DELETE FROM field_assignments WHERE user_id IN :ids"),
                      {"ids": t("users")})
        if tracked["projects"]:
            c.execute(text("DELETE FROM field_sessions WHERE project_id IN :ids"),
                      {"ids": t("projects")})
            c.execute(text("DELETE FROM field_assignments WHERE project_id IN :ids"),
                      {"ids": t("projects")})
        if tracked["activities"]:
            c.execute(text("DELETE FROM activities WHERE id IN :ids"), {"ids": t("activities")})
        if tracked["claims"]:
            c.execute(text("DELETE FROM claims WHERE id IN :ids"), {"ids": t("claims")})
        if tracked["projects"]:
            c.execute(text("DELETE FROM user_role_assignments WHERE project_id IN :ids"),
                      {"ids": t("projects")})
            c.execute(text("DELETE FROM projects WHERE id IN :ids"), {"ids": t("projects")})
        if tracked["units"]:
            c.execute(text("DELETE FROM user_role_assignments"
                           " WHERE organizational_unit_id IN :ids"), {"ids": t("units")})
            c.execute(text("DELETE FROM organizational_units WHERE id IN :ids"),
                      {"ids": t("units")})
        if tracked["orgs"]:
            c.execute(text("DELETE FROM user_role_assignments WHERE organization_id IN :ids"),
                      {"ids": t("orgs")})
            c.execute(text("DELETE FROM organizations WHERE id IN :ids"), {"ids": t("orgs")})
        if tracked["users"]:
            c.execute(text("DELETE FROM user_role_assignments WHERE user_id IN :ids"),
                      {"ids": t("users")})
            c.execute(text("DELETE FROM users WHERE id IN :ids"), {"ids": t("users")})
        if tracked["clients"]:
            c.execute(text("DELETE FROM api_clients WHERE id IN :ids"), {"ids": t("clients")})

    if storage_keys:
        import boto3
        s3 = boto3.client("s3", endpoint_url=settings.s3_endpoint,
                          aws_access_key_id=settings.s3_access_key,
                          aws_secret_access_key=settings.s3_secret_key)
        for key in storage_keys:
            s3.delete_object(Bucket=settings.s3_quarantine_bucket, Key=key)
        remaining = [k for k in storage_keys if s3.list_objects_v2(
            Bucket=settings.s3_quarantine_bucket, Prefix=k).get("KeyCount", 0)]
        check("Z.teardown-removed-quarantine-objects", not remaining,
              f"remaining={remaining[:3]} of {len(storage_keys)}")
    if verbose:
        print("teardown: harness rows and quarantine objects removed")


def residue(since=None):
    since = since or RUN_STARTED
    return {
        "field_assignments": scalar("select count(*) from field_assignments"
                                    " where created_at >= :s", s=since),
        "field_sessions": scalar("select count(*) from field_sessions"
                                 " where created_at >= :s", s=since),
        "field_capture_operations": scalar(
            "select count(*) from field_capture_operations where created_at >= :s", s=since),
        "harness_evidence": scalar(
            "select count(*) from evidence where project_id in"
            " (select id from projects where name like :p)", p=f"SE {LABEL} %"),
        "harness_users": scalar("select count(*) from users where username like :p",
                                p=f"se-{LABEL}-%"),
        "harness_orgs": scalar("select count(*) from organizations where code like :p",
                               p=f"se-{LABEL}-%"),
        "harness_projects": scalar("select count(*) from projects where name like :p",
                                   p=f"SE {LABEL} %"),
    }


def wait_ready(base=None, timeout=120):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{base or BASE}/api/v1/health", timeout=10)
            if r.status_code == 200:
                return True
            last = r.status_code
        except Exception as error:  # noqa: BLE001 - probing a starting server
            last = repr(error)
        time.sleep(1.0)
    print(f"wait_ready timed out: {last}")
    return False
