"""BE-037 I1 live setup: put real jobs on the disposable queue.

Creates synthetic org/project/evidence/principal rows in the disposable
database, then POSTs through the live enforcing API so the payloads are the
exact shape the worker consumes. Job ids and fixture ids are written to
i1-live-state.json so the recovery check and the cleanup know what they own.
"""

import json
import os
import sys
from uuid import uuid4

import urllib.error
import urllib.request

BASE = "http://127.0.0.1:58000"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i1-live-state.json")

from backend.db.models import Evidence, Project, User, UserRoleAssignment
from backend.db.safety import arm_verification
from backend.db.session import get_session
from backend.services import authorization as auth_service

arm_verification(os.environ["DATABASE_URL"])

created = {"org": [], "project": [], "evidence": [], "job": [], "user": []}

session = get_session()
try:
    auth_service.ensure_default_catalogue(session)
    session.commit()
finally:
    session.close()

session = get_session()
try:
    organization = auth_service.create_organization(
        session, name="I1 live org", code=f"i1live-{uuid4().hex[:8]}")
    session.commit()
    session.refresh(organization)
    org_id = str(organization.id)
    created["org"].append(org_id)

    owner = User(username=f"i1live-owner-{uuid4().hex[:8]}",
                 email=f"{uuid4().hex[:8]}@example.com")
    session.add(owner)
    session.commit()
    session.refresh(owner)
    project = Project(name=f"I1 live project {uuid4().hex[:6]}",
                      owner_id=str(owner.id), organization_id=org_id)
    session.add(project)
    session.commit()
    session.refresh(project)
    project_id = str(project.id)
    created["project"].append(project_id)
    created["user"].append(str(owner.id))

    officer = User(username=f"i1live-officer-{uuid4().hex[:8]}",
                   email=f"{uuid4().hex[:8]}@example.com")
    session.add(officer)
    session.commit()
    session.refresh(officer)
    officer_id = str(officer.id)
    created["user"].append(officer_id)
    auth_service.assign_role(session, user_id=officer_id, role_name="FIELD_OFFICER",
                             scope_type="PROJECT", project_id=project_id)
    session.commit()

    evidence_ids = []
    for index in range(3):
        row = Evidence(filename=f"i1live-{index}.jpg", content_type="image/jpeg",
                       storage_key=f"quarantine/{uuid4()}/original", file_size=1,
                       status="uploaded_quarantine", sha256=uuid4().hex + uuid4().hex,
                       project_id=project_id)
        session.add(row)
        session.commit()
        session.refresh(row)
        evidence_ids.append(str(row.id))
        created["evidence"].append(str(row.id))
finally:
    session.close()


def post(path, token=None, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


job_ids = []
for evidence_id in evidence_ids:
    status, payload = post("/api/v1/analysis/jobs",
                           token=f"dev-user-{officer_id}",
                           body={"evidence_id": evidence_id, "job_type": "fingerprint"})
    if status != 202:
        print(f"enqueue failed: {status} {payload}")
        sys.exit(1)
    job_ids.append(payload["job_id"])
    created["job"].append(payload["job_id"])
    print(f"enqueued job {payload['job_id']} for evidence {evidence_id} "
          f"status={payload.get('status')}")

with open(OUT, "w", encoding="utf-8") as handle:
    json.dump({"created": created, "job_ids": job_ids,
               "officer_id": officer_id, "project_id": project_id}, handle, indent=1)
print(f"state written to {OUT}")
