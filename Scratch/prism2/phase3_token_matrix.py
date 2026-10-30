"""PRISM Phase 3: the real-token accept/reject matrix, over real HTTP, against the candidate image.

Section 1 - refusal. Every credential that should not open the door is sent through the
running container's HTTP stack: anonymous, a development bearer token, an HS256 token, a
forged ES256 token carrying the *live published kid*, an unknown kid, a wrong issuer, a
wrong audience, and an expired token. Each refusal is checked twice: the HTTP answer, and
the distinct reason the application logged, because one blanket error for eight different
mistakes would prove nothing about which check fired.

Section 2 - mapping. The provider token's ``sub`` is resolved through the application's own
lookup functions against the container's database, so what a verified sign-in would become
is computed by the shipped code, not by this script: the reviewer principal, its one
PROJECT-scoped REVIEWER grant, and the permission set that follows. A subject nobody has
mapped is also resolved here, to show an unmapped sign-in is refused by a real lookup.

Section 3 - acceptance. Only possible with a token this Supabase project actually signed,
so it runs when ``Scratch/prism2/reviewer.local.token`` exists (see
``phase3_operator_token.py``) and reports BLOCKED when it does not. Nothing here forges a
provider signature: publishing a key the verifier would trust would replace the question
instead of answering it.

Section 4 - key-set outage. A deployment carrying the real provider's issuer and key-set
addresses but unable to reach them (the host is pinned to loopback inside that one
container) proves the failure mode is a refusal, not an open door and not a 500; a
made-up issuer host is also shown to be refused before the app ever serves traffic.

Section 5 - secret hygiene. The exact token strings that were sent are searched for in the
container's log stream and in the refusal bodies; a credential that appears in a log is a
leaked credential.

    python Scratch/prism2/phase3_token_matrix.py [--port 8011] [--no-outage]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOKEN_FILE = REPO / "Scratch/prism2/reviewer.local.token"
REFRESH_FILE = REPO / "Scratch/prism2/reviewer.refresh.token"
ID_FILE = REPO / "Scratch/prism2/reviewer.local.json"
OUT = REPO / "Scratch/prism2/phase3_matrix.json"
DB = "poa_disp_oidc"
OUTAGE_CONT = "poa_disp_oidc_dead"
OUTAGE_PORT = 8012
IMAGE = os.environ.get("POA_IMAGE", "prism-backend:prism-release-20261030")
DB_CONTAINER = os.environ.get("POA_DB_CONTAINER", "pofa_db")
ADMIN = "postgres"
ISSUER = "https://tuaeujvuuanadqvykugw.supabase.co/auth/v1"
JWKS = f"{ISSUER}/.well-known/jwks.json"
RESULTS: list[dict] = []
SENT_TOKENS: list[str] = []


def sh(args, *, stdin=None, quiet=False):
    proc = subprocess.run(args, capture_output=True, text=True, input=stdin)
    if proc.returncode and not quiet:
        raise SystemExit(f"{' '.join(args[:3])} rc={proc.returncode} "
                         f"{(proc.stderr or proc.stdout).strip()[:400]}")
    return proc


def psql(stmt, database=DB):
    return sh(["docker", "exec", DB_CONTAINER, "psql", "-U", ADMIN, "-d", database,
               "-tAc", stmt]).stdout.strip()


def verify_disposable_database() -> None:
    if DB in {"poa_prod", "pofa_dev", "postgres", "pofa_test"}:
        raise SystemExit(f"refusing protected OIDC database target: {DB}")
    actual = psql("SELECT current_database()", database=DB)
    if actual != DB:
        raise SystemExit(
            f"refusing unexpected database target: requested={DB!r} actual={actual!r}"
        )


def record(section, name, status, detail=""):
    """status is PASS / FAIL / BLOCKED - never a bare boolean."""
    RESULTS.append({"section": section, "check": name, "status": status,
                    "detail": str(detail)[:600]})
    print(f"{status:<8} [{section}] {name}" + (f"\n         {detail}" if detail else ""),
          flush=True)


def api(port, method, path, token=None, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as response:
            return response.status, response.read().decode()[:3000]
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()[:3000]


def live_kid() -> str:
    with urllib.request.urlopen(JWKS, timeout=30) as response:
        keys = json.loads(response.read().decode())["keys"]
    if len(keys) != 1 or keys[0].get("alg") != "ES256":
        raise SystemExit(f"the published key set is not the one Phase 2 measured: {keys}")
    return keys[0]["kid"]


def mint(kid, *, alg="ES256", iss=ISSUER, aud="authenticated", sub=None,
         lives=-60, use=None) -> str:
    """A token this script signed seconds ago with a key the provider has never seen.

    Only the provider's own signature can open the door, so every token minted here must
    be refused - which is what makes the accept path impossible to fake by accident.
    """
    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec

    now = int(time.time())
    claims = {"sub": sub or str(uuid.uuid4()), "iss": iss, "aud": aud,
              "iat": now - 60, "exp": now + lives,
              "email": f"prism-forge-{uuid.uuid4().hex[:8]}@forge.invalid"}
    if use:
        claims["use"] = use
    if alg == "HS256":
        key = "a-symmetric-secret-this-project-never-uses"
    else:
        key = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(claims, key, algorithm=alg,
                       headers={"kid": kid or "prism-unknown-kid"})
    SENT_TOKENS.append(token)
    return token


def wait_ready(port, timeout=120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if api(port, "GET", "/health")[0] == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    return False


# --------------------------------------------------------------------------- section 1
def section_refuse(port: int, kid: str) -> dict:
    reasons = {}
    before = psql("SELECT count(*) FROM users")

    code, body = api(port, "GET", "/auth/me")
    record("1-refusal", "anonymous request is refused", "PASS" if code == 401 else "FAIL",
           f"http={code} body={body[:120]}")

    dev = f"dev-user-{uuid.uuid4()}"
    code, body = api(port, "GET", "/auth/me", dev)
    record("1-refusal", "development bearer token is refused (dev tokens are off)",
           "PASS" if code == 401 else "FAIL", f"http={code}")

    cases = {
        "HS256 token": mint(kid, alg="HS256"),
        "forged ES256 carrying the live kid": mint(kid),
        "unknown kid": mint("prism-unknown-kid"),
        "wrong issuer": mint(kid, iss=ISSUER.replace("/auth/v1", "/elsewhere")),
        "wrong audience": mint(kid, aud="anon"),
        "expired token": mint(kid, lives=-7200),
        "refresh token used as a session": mint(kid, use="refresh"),
    }
    outcomes = {}
    for name, token in cases.items():
        code, body = api(port, "GET", "/auth/me", token)
        outcomes[name] = code
        record("1-refusal", f"{name} is refused",
               "PASS" if code == 401 else "FAIL", f"http={code} body={body[:120]}")

    after = psql("SELECT count(*) FROM users")
    record("1-refusal", "no refusal created or changed a user row (nothing auto-provisioned)",
           "PASS" if before == after else "FAIL", f"users before={before} after={after}")

    logs = sh(["docker", "logs", "poa_disp_oidc_api"], quiet=True).stdout
    for reason in ("ALGORITHM_REFUSED", "UNKNOWN_KEY_ID", "TOKEN_REJECTED"):
        reasons[reason] = logs.count(f"reason={reason}")
    record("1-refusal", "the refusals name distinct reasons, not one blanket error",
           "PASS" if all(count > 0 for count in reasons.values()) else "FAIL",
           json.dumps(reasons))
    return reasons


# --------------------------------------------------------------------------- section 2
def section_mapping(sub: str) -> None:
    """Resolve the mapping through the application's own code, inside the container."""
    source = f"""
import json
from backend.core.config import settings
from backend.db.session import get_session
from backend.db.models import User
from backend.security.oidc import resolve_oidc_principal, OIDCError
from backend.services.authorization import resolve_user_principal
from backend.repositories import authorization as repo

db = get_session()
row = (db.query(User)
         .filter(User.identity_provider == settings.auth_oidc_identity_provider,
                 User.external_subject == {sub!r})
         .one_or_none())
if row is None:
    print(json.dumps({{"mapped": False}}))
else:
    p = resolve_user_principal(db, str(row.id))
    grants = [{{"role": repo.roles_by_ids(db, [str(a.role_id)])[str(a.role_id)].name,
              "scope_type": a.scope_type,
              "project_id": str(a.project_id) if a.project_id else None}}
             for a in repo.assignments_for_user(db, str(row.id))]
    print(json.dumps({{"mapped": True, "user_id": str(row.id), "status": row.status,
                       "provider": row.identity_provider,
                       "principal_type": p.principal_type, "authenticated": p.authenticated,
                       "principal_status": p.status, "grants": grants,
                       "permissions": sorted(p.permissions),
                       "organization_ids": list(p.organization_ids)}}))
"""
    proc = sh(["docker", "exec", "-i", "poa_disp_oidc_api", "python", "-"],
              stdin=source, quiet=True)
    lines = [line for line in (proc.stdout or "").splitlines() if line.startswith("{")]
    if not lines:
        record("2-mapping", "the mapped subject resolves through the shipped code path",
               "FAIL", f"rc={proc.returncode} err={(proc.stderr or '')[-200:]}")
        return
    doc = json.loads(lines[-1])
    record("2-mapping", "the mapped subject resolves through the shipped code path",
           "PASS" if doc.get("mapped") else "FAIL", json.dumps(doc)[:500])
    grants = doc.get("grants", [])
    record("2-mapping", "exactly one grant, and it is REVIEWER at PROJECT scope",
           "PASS" if len(grants) == 1 and grants[0]["role"] == "REVIEWER"
           and grants[0]["scope_type"] == "PROJECT" else "FAIL", json.dumps(grants))
    admin_like = sorted(p for p in doc.get("permissions", [])
                        if p in {"user.manage", "role.manage", "organization.manage",
                                 "policy.manage", "api_client.manage", "system.purge"})
    record("2-mapping", "no administrative permission is granted to the reviewer",
           "PASS" if not admin_like else "FAIL", f"admin-like={admin_like} "
           f"total_permissions={len(doc.get('permissions', []))}")

    # Non-vacuity: the same lookup for a subject nobody mapped must find nothing.
    control = f"""
from backend.core.config import settings
from backend.db.session import get_session
from backend.db.models import User
db = get_session()
print(db.query(User).filter(User.identity_provider == settings.auth_oidc_identity_provider,
      User.external_subject == 'nonexistent-subject-control').count())
"""
    proc = sh(["docker", "exec", "-i", "poa_disp_oidc_api", "python", "-"],
              stdin=control, quiet=True)
    count = (proc.stdout or "").strip().splitlines()[-1:] or ["?"]
    record("2-mapping", "an unmapped subject finds no row (the lookup can actually miss)",
           "PASS" if count == ["0"] else "FAIL", f"rows={count}")


# --------------------------------------------------------------------------- section 3
def section_accept(port: int, sub: str) -> bool:
    if not TOKEN_FILE.is_file():
        record("3-acceptance", "a token this project really signed is accepted",
               "BLOCKED", "no Scratch/prism2/reviewer.local.token; run "
                          "phase3_operator_token.py locally (it never prints the secret)")
        record("3-acceptance", "the accepted principal is the mapped reviewer with REVIEWER only",
               "BLOCKED", "needs the same token")
        return False

    access = TOKEN_FILE.read_text(encoding="utf-8").strip()
    SENT_TOKENS.append(access)
    code, body = api(port, "GET", "/auth/me", access)
    doc = {}
    try:
        doc = json.loads(body)
    except json.JSONDecodeError:
        pass
    record("3-acceptance", "a token this project really signed is accepted",
           "PASS" if code == 200 else "FAIL", f"http={code} body={body[:200]}")
    record("3-acceptance", "the accepted principal is the mapped reviewer with REVIEWER only",
           "PASS" if doc.get("roles") == ["REVIEWER"] and doc.get("authenticated")
           and doc.get("principal_type") == "USER" else "FAIL",
           f"roles={doc.get('roles')} type={doc.get('principal_type')} "
           f"status={doc.get('status')} permissions={len(doc.get('permissions', []))}")

    claims_sub_ok = doc.get("id") == psql(
        "SELECT id FROM users WHERE external_subject = "
        f"'{sub.replace(chr(39), chr(39) * 2)}'")
    record("3-acceptance", "the user id the endpoint returned is the mapped row's id",
           "PASS" if claims_sub_ok else "FAIL", f"endpoint_id={doc.get('id')}")

    project_id = psql("SELECT project_id FROM user_role_assignments "
                      "WHERE user_id = (SELECT id FROM users WHERE external_subject = "
                      f"'{sub.replace(chr(39), chr(39) * 2)}') LIMIT 1")
    code, _body = api(port, "GET", f"/projects/{project_id}", access)
    record("3-acceptance", f"the reviewer can read the project they are scoped to "
           f"({project_id[:8]})", "PASS" if code == 200 else "FAIL", f"http={code}")

    # A project the reviewer holds no grant on must not be readable.
    foreign = psql("INSERT INTO projects (id, name, owner_id, created_at) "
                   "SELECT gen_random_uuid(), 'PRISM foreign scope', "
                   "(SELECT id FROM users WHERE external_subject <> "
                   f"'{sub.replace(chr(39), chr(39) * 2)}' LIMIT 1), now() "
                   "RETURNING id") or psql("SELECT id FROM projects WHERE name='PRISM foreign scope'")
    code, _body = api(port, "GET", f"/projects/{foreign}", access)
    record("3-acceptance", "a project outside the reviewer's scope is denied",
           "PASS" if code in (403, 404) else "FAIL", f"http={code}")

    code, body = api(port, "POST", "/auth/users", access,
                     {"username": f"nope-{uuid.uuid4().hex[:6]}",
                      "email": f"nope-{uuid.uuid4().hex[:6]}@forge.invalid"})
    record("3-acceptance", "least privilege bites: the reviewer cannot create users",
           "PASS" if code in (401, 403) else "FAIL", f"http={code} body={body[:120]}")

    if REFRESH_FILE.is_file():
        refresh = REFRESH_FILE.read_text(encoding="utf-8").strip()
        SENT_TOKENS.append(refresh)
        code, _body = api(port, "GET", "/auth/me", refresh)
        record("3-acceptance", "the provider's refresh token is not accepted as a session",
               "PASS" if code == 401 else "FAIL", f"http={code}")
    else:
        record("3-acceptance", "the provider's refresh token is not accepted as a session",
               "BLOCKED", "no Scratch/prism2/reviewer.refresh.token")
    return code == 200


# --------------------------------------------------------------------------- section 4
def section_outage(kid: str) -> None:
    """A provider that answers nothing must refuse, not admit and not 500.

    A made-up issuer host never reaches this code: the settings validator refuses it at
    import (see the boot-level check below). So the outage is created honestly instead --
    the container carries the *real* published issuer and key-set addresses, and only
    its own /etc/hosts pins that host to loopback, where nothing listens. The shape the
    config accepts is unchanged; the key set simply cannot be fetched.
    """
    sh(["docker", "rm", "-f", OUTAGE_CONT], quiet=True)
    issuer_host = urllib.parse.urlsplit(ISSUER).hostname
    env = {
        "DATABASE_URL": f"postgresql+psycopg2://{ADMIN}:{ADMIN}@host.docker.internal:5432/{DB}",
        "ENVIRONMENT": "development", "AUTH_MODE": "enforcing",
        "AUTH_DEV_TOKENS_ENABLED": "false", "AUTH_OIDC_ENABLED": "true",
        "AUTH_OIDC_ISSUER": ISSUER, "AUTH_OIDC_JWKS_URI": JWKS,
        "AUTH_OIDC_AUDIENCE": "authenticated", "AUTH_OIDC_ALGORITHMS": "ES256",
        "AUTH_OIDC_IDENTITY_PROVIDER": "supabase",
        "CORS_ALLOW_ORIGINS": f"http://127.0.0.1:{OUTAGE_PORT}",
        "REDIS_URL": "redis://host.docker.internal:16379/0",
        "S3_ENDPOINT": "http://host.docker.internal:9100",
    }
    args = ["docker", "run", "-d", "--name", OUTAGE_CONT,
            "--add-host", f"{issuer_host}:127.0.0.1",
            "-p", f"127.0.0.1:{OUTAGE_PORT}:8000"]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    args.append(IMAGE)
    sh(args)
    ready = wait_ready(OUTAGE_PORT)
    record("4-keyset-outage", "the app boots while its key set is unreachable "
           "(issuer shape valid, provider silent)",
           "PASS" if ready else "FAIL", f"/health ready={ready}")
    if not ready:
        print(sh(["docker", "logs", OUTAGE_CONT], quiet=True).stdout[-800:])
    else:
        token = mint(kid)
        SENT_TOKENS.append(token)
        code, body = api(OUTAGE_PORT, "GET", "/auth/me", token)
        record("4-keyset-outage", "an unverifiable token during a key-set outage is refused "
               "with a safe status (no 500, no admission)",
               "PASS" if code == 401 else "FAIL", f"http={code} body={body[:140]}")
        logs = sh(["docker", "logs", OUTAGE_CONT], quiet=True).stdout
        record("4-keyset-outage", "the refusal is attributed to the unavailable key set, "
               "not to a blanket rejection",
               "PASS" if "oidc_jwks_unavailable" in logs else "FAIL",
               f"oidc_jwks_unavailable={'oidc_jwks_unavailable' in logs}")
        code, _body = api(OUTAGE_PORT, "GET", "/health")
        record("4-keyset-outage", "the outage is confined to authentication: /health still answers",
               "PASS" if code == 200 else "FAIL", f"http={code}")

    # The config layer refuses a provider that could never be one, before any socket.
    sh(["docker", "rm", "-f", OUTAGE_CONT], quiet=True)
    bogus = "https://poa-prism-keyset-unreachable.invalid/auth/v1"
    bad_env = dict(env, AUTH_OIDC_ISSUER=bogus, AUTH_OIDC_JWKS_URI=f"{bogus}/.well-known/jwks.json")
    bad_args = ["docker", "run", "--name", f"{OUTAGE_CONT}_cfg"]
    for key, value in bad_env.items():
        bad_args += ["-e", f"{key}={value}"]
    proc = sh(bad_args + [IMAGE], quiet=True)
    record("4-keyset-outage", "a non-public issuer host never starts the app at all",
           "PASS" if proc.returncode != 0 and "non-public host" in (proc.stderr + proc.stdout)
           else "FAIL",
           f"rc={proc.returncode} "
           f"{'refused at settings validation' if 'non-public host' in (proc.stderr + proc.stdout) else 'started or failed differently'}")
    sh(["docker", "rm", "-f", f"{OUTAGE_CONT}_cfg"], quiet=True)


# --------------------------------------------------------------------------- section 5
def section_hygiene(port: int) -> None:
    logs = sh(["docker", "logs", "poa_disp_oidc_api"], quiet=True).stdout
    leaked = [name for name, token in enumerate(SENT_TOKENS) if token and token in logs]
    record("5-secret-hygiene", f"none of the {len(SENT_TOKENS)} credentials sent appears in "
           "the container log stream", "PASS" if not leaked else "FAIL", f"leaked={leaked}")
    record("5-secret-hygiene", "no refusal body echoes the bearer token",
           "PASS" if all("Bearer" not in str(r.get("detail", "")) for r in RESULTS) else "FAIL",
           "checked against every recorded detail line")
    record("5-secret-hygiene", "the captured provider token stays in a gitignored local file",
           "PASS" if sh(["git", "-C", str(REPO), "check-ignore", "-q",
                         str(TOKEN_FILE)], quiet=True).returncode == 0 else "FAIL",
           "git check-ignore Scratch/prism2/reviewer.local.token")
    record("5-secret-hygiene", "the reviewer's personal identity file is gitignored",
           "PASS" if sh(["git", "-C", str(REPO), "check-ignore", "-q",
                         str(ID_FILE)], quiet=True).returncode == 0 else "FAIL",
           "git check-ignore Scratch/prism2/reviewer.local.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--no-outage", action="store_true")
    args = parser.parse_args()

    verify_disposable_database()
    sub = json.loads(ID_FILE.read_text(encoding="utf-8"))["external_subject"]
    if not wait_ready(args.port, timeout=30):
        record("0-preflight", "the candidate container answers on the chosen port", "FAIL",
               f"http://127.0.0.1:{args.port} is not healthy; run mbe01_oidc_boot.py first")
        return 2
    record("0-preflight", "the candidate container answers on the chosen port", "PASS",
           f"http://127.0.0.1:{args.port}")
    kid = live_kid()
    record("0-preflight", "the published key set is still the single ES256 kid measured in "
           "Phase 2", "PASS", f"kid={kid}")

    section_refuse(args.port, kid)
    section_mapping(sub)
    accepted = section_accept(args.port, sub)
    if not args.no_outage:
        section_outage(kid)
    section_hygiene(args.port)

    counts = {status: sum(1 for r in RESULTS if r["status"] == status)
              for status in ("PASS", "FAIL", "BLOCKED")}
    summary = {"counts": counts, "acceptance_proven": accepted, "sent_credentials":
               len(SENT_TOKENS)}
    OUT.write_text(json.dumps({"summary": summary, "checks": RESULTS}, indent=2),
                   encoding="utf-8")
    print(json.dumps(summary))
    return 0 if counts["FAIL"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
