"""M-BE-01 step 5 (OIDC-B/C): boot the candidate image with the real Supabase OIDC values.

Everything lands in a disposable database (`poa_disp_oidc`) on localhost only. The
posture under test is the deployed one: AUTH_MODE=enforcing and dev bearer tokens
switched OFF, so the only human identity available is a verified provider token.

What a container run measures that a library probe cannot:
  1. the process starts at all with these six values (config validators included);
  2. the running process fetches the live JWKS and indexes the published kid;
  3. every refusal answers 401 over HTTP, including a forgery carrying the live kid;
  4. no refusal path writes a user row, i.e. nothing is auto-provisioned.

A genuinely valid token from this project still needs a real reviewer account,
which is an owner action; the accept path is measured by
tests/integration/test_stage02_reviewer_identity.py against a minted provider.

usage: python mbe01_oidc_boot.py run | clean
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

IMAGE = os.environ.get("POA_IMAGE", "prism-backend:prism-release-20261030")
DB = "poa_disp_oidc"
CONT = "poa_disp_oidc_api"
HOST_PORT = 8011
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("POA_OIDC_BOOT_OUT") or os.path.join(HERE, "mbe01_oidc_boot.json")
PROTECTED = {"pofa_dev", "pofa_test", "poa_prod", "poa_restore_probe"}
ADMIN = "postgres"
IN_URL = f"postgresql+psycopg2://{ADMIN}:{ADMIN}@host.docker.internal:5432/{DB}"
HEAD = "y5z6a7b8c035"

ISSUER = "https://tuaeujvuuanadqvykugw.supabase.co/auth/v1"
JWKS = "https://tuaeujvuuanadqvykugw.supabase.co/auth/v1/.well-known/jwks.json"
EVIDENCE = []


def sh(args, *, stdin=None, quiet=False):
    p = subprocess.run(args, capture_output=True, text=True, input=stdin)
    if p.returncode and not quiet:
        raise SystemExit(f"{' '.join(args[:3])} rc={p.returncode}\n"
                         f"{(p.stderr or p.stdout).strip()[:600]}")
    return p


def psql(stmt, db="postgres"):
    return sh(["docker", "exec", "pofa_db", "psql", "-U", ADMIN, "-d", db,
               "-tAc", stmt]).stdout.strip()


def record(name, ok, detail=""):
    EVIDENCE.append({"check": name, "passed": bool(ok), "detail": str(detail)[:400]})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ->  {detail}" if detail else ""),
          flush=True)


def api(method, path, token=None, body=None):
    return fetch(f"http://127.0.0.1:{HOST_PORT}/api/v1{path}", method=method,
                 token=token, body=body)


def raw(path):
    return fetch(f"http://127.0.0.1:{HOST_PORT}{path}", limit=4000)


def fetch(url, *, method="GET", token=None, body=None, limit=200):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, resp.read().decode()[:limit]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:limit]


def disposable_minio_credentials():
    """Read the already-running disposable MinIO's own root credentials out of its
    container environment, so no secret is typed into this file or printed."""
    env = sh(["docker", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}",
              "poa_disp_minio"]).stdout
    found = {}
    for line in env.splitlines():
        for key, name in (("MINIO_ROOT_USER", "s3_access_key"),
                          ("MINIO_ROOT_PASSWORD", "s3_secret_key")):
            if line.startswith(f"{key}=") and "=" not in line.split("=", 1)[1]:
                found[name] = line.split("=", 1)[1]
    return found


def exec_in_container(source):
    return sh(["docker", "exec", "-i", CONT, "python", "-"], stdin=source, quiet=True)


def container_json(source, *, attempts: int = 4, pause: float = 5.0):
    """Return (parsed_json_or_None, detail) for a `python -` run in the container.

    Each exec is a fresh process with a cold JWKS cache, so its first provider
    fetch can transiently fail while the container is still settling; retry
    before judging the check and never let unparseable output crash the gate.
    """
    detail = "no output"
    for attempt in range(1, attempts + 1):
        proc = exec_in_container(source)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip().splitlines()
        if proc.returncode == 0 and out:
            try:
                return json.loads(out.splitlines()[-1]), f"attempts={attempt}"
            except json.JSONDecodeError:
                detail = f"unparseable={out[-120:]}"
        else:
            detail = f"rc={proc.returncode} err={(err[-1] if err else '')[:160]}"
        if attempt < attempts:
            time.sleep(pause)
    return None, detail


def es256_token(kid: str | None, claims: dict | None = None) -> str:
    """Signed by a key pair this script generated seconds ago. The provider never
    signed it, so the only way the backend can accept it is by not checking."""
    from cryptography.hazmat.primitives.asymmetric import ec
    import jwt
    now = int(time.time())
    payload = {"sub": str(uuid4()), "iss": ISSUER, "aud": "authenticated",
               "iat": now, "exp": now + 3600,
               "email": f"forge-{uuid4().hex[:8]}@forge.invalid"} | (claims or {})
    return jwt.encode(payload, ec.generate_private_key(ec.SECP256R1()),
                      algorithm="ES256", headers={"kid": kid or "local-unknown-kid"})


def hs256_token() -> str:
    import jwt
    now = int(time.time())
    return jwt.encode({"sub": str(uuid4()), "iss": ISSUER, "aud": "authenticated",
                       "iat": now, "exp": now + 600},
                      "a-symmetric-secret-the-provider-never-uses",
                      algorithm="HS256", headers={"kid": "hs256-previous-key"})


def run() -> int:
    if DB in PROTECTED:
        raise SystemExit(f"refusing: {DB} is not disposable")
    sh(["docker", "rm", "-f", CONT], quiet=True)

    psql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
         f"WHERE datname='{DB}' AND pid <> pg_backend_pid()")
    psql(f"DROP DATABASE IF EXISTS {DB}")
    psql(f"CREATE DATABASE {DB} OWNER {ADMIN}")
    sh(["docker", "run", "--rm", "-e", f"DATABASE_URL={IN_URL}",
        IMAGE, "alembic", "upgrade", "head"])
    head = psql("SELECT version_num FROM alembic_version", db=DB)
    record("disposable schema reached the release head", head == HEAD, head)

    env = {
        "DATABASE_URL": IN_URL,
        "ENVIRONMENT": "development",
        "AUTH_MODE": "enforcing",
        "AUTH_DEV_TOKENS_ENABLED": "false",
        "AUTH_OIDC_ENABLED": "true",
        "AUTH_OIDC_ISSUER": ISSUER,
        "AUTH_OIDC_JWKS_URI": JWKS,
        "AUTH_OIDC_AUDIENCE": "authenticated",
        "AUTH_OIDC_ALGORITHMS": "ES256",
        "AUTH_OIDC_IDENTITY_PROVIDER": "supabase",
        "CORS_ALLOW_ORIGINS": f"http://127.0.0.1:{HOST_PORT}",
        "REDIS_URL": "redis://host.docker.internal:16379/0",
        "S3_ENDPOINT": "http://host.docker.internal:9100",
        **disposable_minio_credentials(),
    }
    args = ["docker", "run", "-d", "--name", CONT, "-p", f"127.0.0.1:{HOST_PORT}:8000"]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    args.append(IMAGE)
    sh(args)

    deadline, health = time.time() + 180, None
    while time.time() < deadline:
        try:
            health = api("GET", "/health")
            if health[0] == 200:
                break
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    record("the candidate boots with the six AUTH_OIDC_* values and serves /health",
           health is not None and health[0] == 200, str(health))
    if not health or health[0] != 200:
        print(sh(["docker", "logs", CONT], quiet=True).stdout[-1500:])
        return 1

    code, body = raw("/ready")
    legs = {}
    try:
        doc = json.loads(body)
        legs = {name: check.get("status") for name, check in doc.get("checks", {}).items()}
    except json.JSONDecodeError:
        pass
    record("/ready is healthy on every dependency leg", code == 200 and all(
        status == "healthy" for status in legs.values()),
        f"http={code} legs={json.dumps(legs)}")

    cfg, cfg_detail = container_json(
        "from backend.core.config import settings as s; import json; print(json.dumps({"
        "'enabled': s.auth_oidc_enabled, 'issuer': s.auth_oidc_issuer,"
        "'jwks_uri': s.auth_oidc_jwks_uri, 'audience': s.auth_oidc_audience,"
        "'algorithms': s.auth_oidc_algorithms, 'provider': s.auth_oidc_identity_provider,"
        "'auth_mode': s.auth_mode, 'dev_tokens': s.auth_dev_tokens_enabled}))")
    record("the running process loaded all six values, enforcing, dev tokens off",
           cfg == {"enabled": True, "issuer": ISSUER, "jwks_uri": JWKS,
                   "audience": "authenticated", "algorithms": "ES256",
                   "provider": "supabase", "auth_mode": "enforcing",
                   "dev_tokens": False},
           json.dumps(cfg) if cfg is not None else cfg_detail)

    published, keys_detail = container_json(
        "from backend.security import oidc; import json;"
        "print(json.dumps(sorted(oidc.signing_keys())))")
    record("the live JWKS is reachable from inside the container and indexes the published kid",
           isinstance(published, list) and len(published) == 1,
           f"kids={published}" if published is not None else keys_detail)

    users_before = psql("SELECT count(*) FROM users", db=DB)

    code, body = api("GET", "/auth/me")
    record("anonymous /auth/me is refused", code == 401, f"{code} {body[:80]}")

    code, body = api("GET", "/auth/me", f"dev-user-{uuid4()}")
    record("a development bearer token is refused while the provider is enabled",
           code == 401, f"{code} {body[:80]}")

    code, body = api("GET", "/auth/me", hs256_token())
    record("an HS256 token is refused over HTTP", code == 401, f"{code} {body[:80]}")

    live_kid = published[0] if published else "ab0ac6ae-93be-441c-9196-7b2fade15af0"
    code, body = api("GET", "/auth/me", es256_token(live_kid))
    record("a forged ES256 token carrying the live kid is refused over HTTP",
           code == 401, f"{code} {body[:80]}")

    code, body = api("GET", "/auth/me", es256_token(None))
    record("a token with an unknown kid is refused over HTTP", code == 401,
           f"{code} {body[:80]}")

    code, body = api("GET", "/auth/me", es256_token(live_kid, {"iss": ISSUER.replace("/auth/v1", "/elsewhere")}))
    record("a forged token for the wrong issuer is refused over HTTP", code == 401,
           f"{code} {body[:80]}")

    code, body = api("POST", "/projects", es256_token(live_kid),
                     {"name": f"forge-{uuid4().hex[:6]}"})
    record("a forged token cannot create a project", code == 401, f"{code} {body[:80]}")

    users_after = psql("SELECT count(*) FROM users", db=DB)
    record("no user row was created by any refusal (nothing auto-provisioned)",
           users_before == users_after, f"before={users_before} after={users_after}")

    refusal_reasons = sh(["docker", "logs", CONT], quiet=True).stdout
    counted = {reason: refusal_reasons.count(f"reason={reason}")
               for reason in ("ALGORITHM_REFUSED", "UNKNOWN_KEY_ID", "TOKEN_REJECTED")}
    record("the refusals name distinct reasons rather than one blanket error",
           all(v > 0 for v in counted.values()), json.dumps(counted))

    summary = {"passed": sum(e["passed"] for e in EVIDENCE), "total": len(EVIDENCE),
               "users": [users_before, users_after], "reasons": counted}
    print(json.dumps(summary))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "checks": EVIDENCE}, fh, indent=2)
    return 0 if all(e["passed"] for e in EVIDENCE) else 1


def clean() -> int:
    sh(["docker", "rm", "-f", CONT], quiet=True)
    psql(f"DROP DATABASE IF EXISTS {DB}")
    remaining = psql(f"SELECT count(*) FROM pg_database WHERE datname='{DB}'")
    print(f"{DB} containers removed; pg_database rows left = {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(clean() if len(sys.argv) > 1 and sys.argv[1] == "clean" else run())
