"""BE-037 G1 runtime probe: the analysis endpoints over a real socket.

Runs on the host against the disposable API container (AUTH_MODE=enforcing) and
the disposable PostgreSQL/Redis. Synthetic fixtures only; nothing here can
reach pofa_dev, pofa_test, pofa_redis or pofa_minio: the database DSN is
handled through backend.db.safety.arm_verification, which refuses protected
names, and the only Redis key touched belongs to this run's queue.
"""

import json
import os
import sys
from uuid import uuid4

os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:56379/0")
os.environ.setdefault("S3_ENDPOINT", "http://127.0.0.1:59000")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("AUTH_MODE", "development")

import urllib.error
import urllib.request

BASE = "http://127.0.0.1:58000"

from backend.core.config import settings
from backend.db.models import (
    AnalysisJob,
    ApiClient,
    Evidence,
    Project,
    User,
    UserRoleAssignment,
)
from backend.db.safety import arm_verification
from backend.db.session import get_engine, get_session
from backend.services import authorization as auth_service

arm_verification(os.environ["DATABASE_URL"])
with get_engine().connect() as conn:
    from sqlalchemy import text

    server_db = conn.execute(text("SELECT current_database(), current_user")).all()
print(f"connected to: {server_db}")
print(f"host settings.auth_mode = {settings.auth_mode!r} "
      "(container env is the enforcing one; this process only writes fixtures)")
print(f"queue key = {settings.analysis_queue_name}")

created = {"org": [], "project": [], "evidence": [], "job": [], "user": [], "client": []}


def org(label):
    session = get_session()
    try:
        row = auth_service.create_organization(
            session, name=f"G1 live {label}", code=f"g1live-{label}-{uuid4().hex[:8]}")
        session.commit()
        session.refresh(row)
        created["org"].append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def project(org_id):
    session = get_session()
    try:
        owner = User(username=f"g1live-owner-{uuid4().hex[:8]}",
                     email=f"{uuid4().hex[:8]}@example.com")
        session.add(owner)
        session.commit()
        session.refresh(owner)
        created["user"].append(str(owner.id))
        row = Project(name=f"G1 live project {uuid4().hex[:6]}",
                      owner_id=str(owner.id), organization_id=org_id)
        session.add(row)
        session.commit()
        session.refresh(row)
        created["project"].append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def evidence(project_id):
    session = get_session()
    try:
        row = Evidence(filename="g1live.jpg", content_type="image/jpeg",
                       storage_key=f"quarantine/{uuid4()}/original", file_size=1,
                       status="uploaded_quarantine",
                       sha256=uuid4().hex + uuid4().hex, project_id=project_id)
        session.add(row)
        session.commit()
        session.refresh(row)
        created["evidence"].append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def job(evidence_id):
    session = get_session()
    try:
        row = AnalysisJob(evidence_id=evidence_id, status="queued",
                          attempt_count=0, job_type="fingerprint")
        session.add(row)
        session.commit()
        session.refresh(row)
        created["job"].append(str(row.id))
        return str(row.id)
    finally:
        session.close()


def user(label, role, scope_type, scope_id):
    session = get_session()
    try:
        row = User(username=f"g1live-{label}-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@example.com")
        session.add(row)
        session.commit()
        session.refresh(row)
        user_id = str(row.id)
        created["user"].append(user_id)
        kwargs = {scope_type.lower() + "_id": scope_id}
        auth_service.assign_role(session, user_id=user_id, role_name=role,
                                 scope_type=scope_type, **kwargs)
        session.commit()
        return user_id
    finally:
        session.close()


def call(method, path, token=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except Exception as error:  # noqa: BLE001 - probe reports the raw failure
        return "EXC", repr(error)


session = get_session()
try:
    auth_service.ensure_default_catalogue(session)
    session.commit()
finally:
    session.close()

org_a, org_b = org("a"), org("b")
proj_a, proj_b = project(org_a), project(org_b)
ev_a, ev_b = evidence(proj_a), evidence(proj_b)
job_a, job_b = job(ev_a), job(ev_b)

officer_a = user("officer-a", "FIELD_OFFICER", "PROJECT", proj_a)
citizen_a = user("citizen-a", "CITIZEN", "PROJECT", proj_a)
officer_b = user("officer-b", "FIELD_OFFICER", "PROJECT", proj_b)
client_id = None
session = get_session()
try:
    row = ApiClient(name=f"g1live-client-{uuid4().hex[:8]}",
                    scopes=["intelligence.reprocess", "evidence.read"],
                    project_id=proj_a, status="ACTIVE")
    session.add(row)
    session.commit()
    session.refresh(row)
    client_id = str(row.id)
    created["client"].append(client_id)
finally:
    session.close()

checks = []


def record(name, expected, actual, note=""):
    checks.append((name, expected, actual, "PASS" if expected == actual else "FAIL", note))


def job_count():
    session = get_session()
    try:
        return session.query(AnalysisJob).count()
    finally:
        session.close()


body_a = {"evidence_id": ev_a, "job_type": "fingerprint"}
body_b = {"evidence_id": ev_b, "job_type": "fingerprint"}

status, payload = call("GET", "/health")
record("GET /health (service reachable)", 200, status, payload[:60])

status, payload = call("POST", "/api/v1/analysis/jobs", body=body_a)
record("anonymous POST /analysis/jobs", 401, status, payload[:80])

status, payload = call("GET", f"/api/v1/analysis/jobs/{job_a}")
record("anonymous GET /analysis/jobs/{id}", 401, status, payload[:80])

status, payload = call("POST", "/api/v1/analysis/jobs", token="not-a-real-token",
                       body=body_a)
record("invalid bearer POST", 401, status, payload[:80])

status, payload = call("GET", "/api/v1/analysis/jobs/not-a-uuid",
                       token=f"dev-user-{officer_a}")
record("malformed job id (authorized principal)", 422, status, payload[:80])

status, payload = call("POST", "/api/v1/analysis/jobs", token=f"dev-user-{citizen_a}",
                       body=body_a)
record("CITIZEN (evidence.read only) POST", 403, status, payload[:80])

before = job_count()
status, payload = call("POST", "/api/v1/analysis/jobs", token=f"dev-user-{officer_b}",
                       body=body_a)
record("cross-org FIELD_OFFICER POST (org B -> org A evidence)", 404, status,
       f"body={payload[:60]} job_rows_before={before} after={job_count()}")

status, payload = call("GET", f"/api/v1/analysis/jobs/{job_a}",
                       token=f"dev-user-{officer_b}")
record("cross-org FIELD_OFFICER GET (org B -> org A job)", 404, status, payload[:80])

status, payload = call("POST", "/api/v1/analysis/jobs", token=f"dev-user-{officer_a}",
                       body=body_a)
created_job = json.loads(payload).get("job_id") if status == 202 else None
record("authorized FIELD_OFFICER POST (own project)", 202, status, payload[:90])

status, payload = call("GET", f"/api/v1/analysis/jobs/{created_job}",
                       token=f"dev-user-{officer_a}")
record("authorized FIELD_OFFICER GET (own job)", 200, status, payload[:90])

status, payload = call("GET", f"/api/v1/analysis/jobs/{job_a}",
                       token=f"dev-user-{citizen_a}")
record("CITIZEN GET (own project job)", 200, status, payload[:90])

created["job"].append(created_job) if created_job else None

import redis as redis_lib

queue = redis_lib.Redis.from_url(settings.redis_url)
queued = queue.llen(settings.analysis_queue_name)
print(f"disposable redis queue length after the authorized POST: {queued}")

status, payload = call("POST", "/api/v1/analysis/jobs",
                       token=f"dev-client-{client_id}", body=body_a)
service_job = json.loads(payload).get("job_id") if status == 202 else None
if service_job:
    created["job"].append(service_job)
record("service-to-service API client POST (own project)", 202, status, payload[:90])

status, payload = call("GET", f"/api/v1/analysis/jobs/{job_b}",
                       token=f"dev-client-{client_id}")
record("service-to-service API client GET (other org's job)", 404, status,
       payload[:80])

failures = [c for c in checks if c[3] == "FAIL"]
print("\n=== G1 live-endpoint matrix ===")
for name, expected, actual, verdict, note in checks:
    print(f"[{verdict}] {name}: expected {expected} got {actual} :: {note}")
print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")

# Clean only this run's queue key, then the fixture rows.
queue.delete(settings.analysis_queue_name, f"{settings.analysis_queue_name}:processing")
queue.close()

session = get_session()
try:
    session.query(AnalysisJob).filter(
        AnalysisJob.id.in_(created["job"])).delete(synchronize_session=False)
    session.query(Evidence).filter(
        Evidence.id.in_(created["evidence"])).delete(synchronize_session=False)
    session.query(UserRoleAssignment).filter(
        UserRoleAssignment.user_id.in_(created["user"])).delete(
        synchronize_session=False)
    session.query(UserRoleAssignment).filter(
        UserRoleAssignment.project_id.in_(created["project"])).delete(
        synchronize_session=False)
    session.query(ApiClient).filter(
        ApiClient.id.in_(created["client"])).delete(synchronize_session=False)
    session.query(Project).filter(
        Project.id.in_(created["project"])).delete(synchronize_session=False)
    session.query(User).filter(User.id.in_(created["user"])).delete(
        synchronize_session=False)
    session.query(AnalysisJob).filter(
        AnalysisJob.evidence_id.in_(created["evidence"])).delete(
        synchronize_session=False)
    session.commit()
finally:
    session.close()

leftover = job_count()
print(f"analysis_jobs rows after fixture cleanup: {leftover}")
sys.exit(1 if failures else 0)
