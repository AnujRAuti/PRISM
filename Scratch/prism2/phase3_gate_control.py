"""PRISM Phase 3 control: prove the release gate's probe-token branch actually verifies.

``python -m backend.security.oidc_preflight`` reports BLOCKED while no token exists, which
is honest but untested. This writes a token this script signed with a throwaway key - the
provider never signed it, so the gate must refuse it - runs the gate against the real
configuration, and checks that the refusal names the verification outcome rather than
crashing or passing. The forged token is deleted again; no credential is printed.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FORGED = REPO / "Scratch/prism2/_control_forged.token"
ISSUER = "https://tuaeujvuuanadqvykugw.supabase.co/auth/v1"
ENV = {
    "PYTHONPATH": str(REPO),
    "ENVIRONMENT": "development",
    "AUTH_MODE": "enforcing",
    "AUTH_OIDC_ENABLED": "true",
    "AUTH_OIDC_ISSUER": ISSUER,
    "AUTH_OIDC_JWKS_URI": f"{ISSUER}/.well-known/jwks.json",
    "AUTH_OIDC_AUDIENCE": "authenticated",
    "AUTH_OIDC_ALGORITHMS": "ES256",
    "AUTH_OIDC_IDENTITY_PROVIDER": "supabase",
    "DATABASE_URL": "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test",
}


def forged_token() -> str:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec

    now = int(time.time())
    return jwt.encode(
        {"sub": str(uuid.uuid4()), "iss": ISSUER, "aud": "authenticated",
         "iat": now - 60, "exp": now + 600},
        ec.generate_private_key(ec.SECP256R1()), algorithm="ES256",
        headers={"kid": "ab0ac6ae-93be-441c-9196-7b2fade15af0"})


def main() -> int:
    FORGED.write_text(forged_token(), encoding="utf-8")
    os.chmod(FORGED, 0o600)
    env = {**os.environ, **ENV}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "backend.security.oidc_preflight",
             "--expected-project-ref", "tuaeujvuuanadqvykugw",
             "--token-file", str(FORGED), "--json"],
            capture_output=True, text=True, env=env, cwd=str(REPO))
    finally:
        FORGED.unlink()
    doc = json.loads(proc.stdout)
    probe = next(check for check in doc["checks"] if check["name"] == "probe_token")
    print(f"verdict      : {doc['verdict']}  rc={proc.returncode}")
    print(f"probe_token  : {probe['status']} - {probe['detail']}")
    print(f"file removed : {not FORGED.exists()}")
    ok = doc["verdict"] == "FAIL" and probe["status"] == "FAIL" and proc.returncode == 1
    print("CONTROL " + ("PASS: a token the provider did not sign is refused by the gate"
                        if ok else "FAIL: the gate did not behave as expected"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
