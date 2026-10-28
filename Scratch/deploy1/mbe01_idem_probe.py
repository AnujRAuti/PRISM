"""Measure what an Idempotency-Key actually does on the four routes outside the evidence family.

The owner's 2026-10-16 decision starts enforcement with evidence ingestion, and that
route is now fixed and tested. The remaining routes that *declare* the header --
POST /integrations/systems, /clients, /references, /claims -- still call the same
two helpers with ``principal.principal_id`` whatever the principal type is. The key
store's ``client_id`` is a NOT NULL foreign key to ``api_clients.id``, so for a human
caller the insert cannot succeed; ``record_idempotency`` swallows the IntegrityError
and rolls back. Each of those routes commits its business write *before* recording
the key, so the predicted consequence is a lost key, not a lost row -- but a
prediction is not a measurement, so this checks all three facts:

  1. the request is accepted (201);
  2. the created row is still in the database afterwards;
  3. no idempotency key was persisted, which is why a retry creates a second row.

Runs against a disposable database only. Prints counts and ids, never a DSN.
"""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
PY = REPO / "backend" / ".venv312_repro" / "Scripts" / "python.exe"
TARGET = os.environ.get("PROBE_DB", "poa_disp_prod")
DSN = f"postgresql+psycopg2://postgres:postgres@localhost:5432/{TARGET}"

SCRIPT = r"""
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.core.config import settings
from backend.db.models import ExternalSystem, IdempotencyKey, User, UserRoleAssignment
from backend.db.session import get_session
from backend.services import authorization as auth_service

settings.auth_mode = "enforcing"
client = TestClient(app)

session = get_session()
try:
    auth_service.ensure_default_catalogue(session)
    user = User(username=f"probe-{uuid4().hex[:8]}", email=f"{uuid4().hex[:8]}@probe.test")
    session.add(user)
    session.commit()
    user_id = str(user.id)
    auth_service.assign_role(session, user_id=user_id, role_name="ADMINISTRATOR",
                             scope_type="GLOBAL")
    session.commit()
finally:
    session.close()

headers = {"Authorization": f"Bearer dev-user-{user_id}"}
code = f"PROBE{uuid4().hex[:10]}"
key = f"probe-{uuid4().hex[:8]}"
body = {"name": "probe system", "code": code, "system_type": "FIELD_SYSTEM"}

first = client.post("/api/v1/integrations/systems", json=body,
                    headers={**headers, "Idempotency-Key": key})
replay = client.post("/api/v1/integrations/systems", json=body,
                     headers={**headers, "Idempotency-Key": key})

session = get_session()
try:
    rows = session.query(ExternalSystem).filter(ExternalSystem.code == code).count()
    keys = session.query(IdempotencyKey).filter(IdempotencyKey.idempotency_key == key).count()
finally:
    session.close()
    s2 = get_session()
    try:
        s2.query(ExternalSystem).filter(ExternalSystem.code == code).delete(
            synchronize_session=False)
        s2.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user_id).delete(
            synchronize_session=False)
        s2.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        s2.commit()
    finally:
        s2.close()

print(f"first request   : {first.status_code}")
print(f"retry, same key : {replay.status_code}")
print(f"external_systems rows with that code: {rows}")
print(f"idempotency_keys rows with that key : {keys}")
"""

proc = subprocess.run([str(PY), "-c", SCRIPT], cwd=str(REPO),
                      env={**os.environ, "DATABASE_URL": DSN,
                           "AUTH_MODE": "enforcing", "AUTH_DEV_TOKENS_ENABLED": "true"})
print(f"\n(probe database: {TARGET})")
sys.exit(proc.returncode)
