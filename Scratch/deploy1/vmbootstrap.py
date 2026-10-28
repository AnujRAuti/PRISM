"""Create the deployment's first credential, and prove the app can write to the ledger.

There is no login endpoint and production disables development tokens, so the
first credential has to be minted server-side. This uses the application's own
service (backend.services.integration.create_api_client) rather than hand-written
INSERTs, so the credential is hashed the way the API verifies it and the creation
is recorded through the normal audit path.

Two things fall out of that:
  * a working authenticating credential for the smoke probes, kept on this VM in a
    0600 file and never printed;
  * a non-empty audit ledger, so the backup/restore comparison is not comparing
    two empty tables.

The connection is the app's own DATABASE_URL, i.e. the least-privileged
poa_runtime identity, which also proves that identity can INSERT an audit event.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path.home() / "proof-of-action"
HOST_TOKEN = Path.home() / ".poa_smoke_credential"
# The container's filesystem is separate from the host's, so the token is written
# in-container under /tmp and copied out with docker cp.
CONTAINER_TOKEN = "/tmp/.poa_smoke_credential"

# Narrow on purpose: reads plus the audit read used by the smoke probe.
SCOPES = ["project.read", "evidence.read", "audit.read"]

BASE = "http://127.0.0.1:8000"

INSIDE = f'''
import os
from backend.db.session import get_session
from backend.services import integration as integration_service
from backend.core.config import settings
from sqlalchemy.engine import make_url

db = get_session()
try:
    client, secret = integration_service.create_api_client(
        db, name="vm-smoke-probe", scopes={SCOPES!r}
    )
    db.commit()
    with open({CONTAINER_TOKEN!r}, "w") as handle:
        handle.write(f"{{client.id}}:{{secret}}")
    os.chmod({CONTAINER_TOKEN!r}, 0o600)
    print("runtime identity :", make_url(settings.database_url).username)
    print("client id        :", client.id)
    print("scopes granted   :", ",".join(client.scopes))
    print("secret length    :", len(secret), "(written to file only)")
finally:
    db.close()
'''


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, cwd=str(REPO), **kw)


def status_for(path: str, bearer: str | None) -> str:
    """Fetch a path; the credential travels on stdin, never in argv (ps-visible)."""
    args = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}"]
    if bearer is None:
        return run([*args, f"{BASE}{path}"]).stdout.strip()
    config = f'header = "Authorization: Bearer {bearer}"\n'
    return run([*args, "--config", "-", f"{BASE}{path}"], input=config).stdout.strip()


def main() -> int:
    proc = run(["docker", "exec", "-i", "pofa_api", "python", "-c", INSIDE])
    if proc.returncode:
        print(proc.stderr.strip()[-600:])
        raise SystemExit("bootstrap failed")
    print(proc.stdout.strip())

    copied = run(["docker", "cp", f"pofa_api:{CONTAINER_TOKEN}", str(HOST_TOKEN)])
    if copied.returncode:
        raise SystemExit("could not copy credential out: " + copied.stderr.strip()[-300:])
    os.chmod(HOST_TOKEN, 0o600)
    run(["docker", "exec", "pofa_api", "rm", "-f", CONTAINER_TOKEN])
    bearer = HOST_TOKEN.read_text().strip()
    print(f"credential stored on VM: {HOST_TOKEN} (mode 600)")

    ledger = run(["docker", "exec", "pofa_db", "psql", "-U", "poa_owner", "-d", "poa_prod",
                  "-tAc", "select count(*), coalesce(string_agg(distinct event_type, ','),'-') "
                          "from audit_ledger_events"])
    print("ledger rows, event types:", ledger.stdout.strip() or ledger.stderr.strip()[-200:])

    for path in ("/api/v1/projects", "/api/v1/auth/me"):
        print(f"GET {path}: anonymous={status_for(path, None)} "
              f"with-credential={status_for(path, bearer)}")
    return 0


if __name__ == "__main__":
    main()
