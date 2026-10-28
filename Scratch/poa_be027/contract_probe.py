"""BE-027 audit probe: measure three contract facts instead of reasoning about them.

1. CORS: what headers does the shipped middleware actually return for a random
   cross-origin request, given allow_origins=["*"] + allow_credentials=True?
2. Strict validation: does POST /api/v1/projects accept unknown extra fields?
3. OpenAPI (§29): are the project endpoints documented, and are request and
   response schemas attached?

Read-only apart from one created project, which is deleted again.
"""
import json
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

from backend.app.main import app  # noqa: E402
from backend.db.session import get_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

client = TestClient(app)

print("=== 1. CORS: uncredentialed simple request from an arbitrary origin ===")
r = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
print("status", r.status_code)
print(json.dumps({k: v for k, v in r.headers.items()
                  if k.lower().startswith("access-control")}, indent=2))

print("=== CORS preflight from an arbitrary origin ===")
r = client.options("/api/v1/projects", headers={
    "Origin": "https://evil.example",
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization",
})
print("status", r.status_code)
print(json.dumps({k: v for k, v in r.headers.items()
                  if k.lower().startswith("access-control")}, indent=2))

print("=== 2. Extra-field strictness on POST /api/v1/projects ===")
session = get_session()
try:
    owner_id = str(uuid4())
    session.execute(
        text("INSERT INTO users (id, username, email, is_active, status,"
             " identity_provider, created_at, updated_at)"
             " VALUES (:id, :u, :e, true, 'ACTIVE', 'local', now(), now())"),
        {"id": owner_id, "u": f"probe-{uuid4().hex[:8]}",
         "e": f"{uuid4().hex[:8]}@example.com"},
    )
    session.commit()
    body = {"name": "BE-027 probe extra field", "owner_id": owner_id,
            "is_admin": True, "status": "APPROVED", "role": "OWNER"}
    r = client.post("/api/v1/projects", json=body)
    print("status with three unknown fields:", r.status_code)
    print("response:", r.text[:200])
    created_id = None
    if r.status_code == 201:
        created_id = r.json()["id"]
        row = session.execute(
            text("SELECT id, name, owner_id FROM projects WHERE id = CAST(:i AS uuid)"),
            {"i": created_id},
        ).first()
        print("persisted row:", row)
finally:
    if created_id:
        session.execute(text("DELETE FROM projects WHERE id = CAST(:i AS uuid)"),
                        {"i": created_id})
    session.execute(text("DELETE FROM users WHERE id = CAST(:i AS uuid)"), {"i": owner_id})
    session.commit()
    session.close()

print("=== 3. OpenAPI surface for the project endpoints ===")
spec = client.get("/openapi.json").json()
for path in sorted(spec["paths"]):
    if path.startswith("/api/v1/projects"):
        for method, op in spec["paths"][path].items():
            req = op.get("requestBody", {}).get("content", {}).get("application/json", {})
            codes = sorted(op["responses"])
            print(f"{method.upper():6} {path:45} request={bool(req)} responses={codes}")
print("total documented paths:", len(spec["paths"]))
print("docs endpoints:", client.get("/docs").status_code,
      "redoc:", client.get("/redoc").status_code)
