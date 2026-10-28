"""PRISM-1: does the actual server process refuse a misconfigured identity setup?

``backend/core/config.py`` builds ``settings`` at import time, and uvicorn imports
the app module before it binds a socket, so an import failure IS the startup
failure. This script therefore runs a real interpreter per configuration combo and
records the exit code plus the refusal line, instead of only constructing
``Settings()`` inside pytest.

Two things matter beyond "it raised":
  * the positive controls must boot, otherwise a blanket refusal proves nothing;
  * development must stay usable with nothing set, because the hardening belongs
    in the production guard rather than in the shared defaults.

Nothing here writes to a database (no engine connect happens during import), and
no secret value is printed: only hosts, booleans and the refusal text.

usage: python Scratch/prism/config_boot_matrix.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("D:/CODING/Projects/Proof-Of-Action-Final")
PYTHON = str(ROOT / "backend" / ".venv312_repro" / "Scripts" / "python.exe")
OUT = ROOT / "Scratch" / "prism" / "config_boot_matrix.json"

# Public provider metadata (not secrets): the project's published issuer and key
# set, verified reachable in mbe01_oidc_discovery.json. Kept out of source code.
ISSUER = "https://tuaeujvuuanadqvykugw.supabase.co/auth/v1"
JWKS = ISSUER + "/.well-known/jwks.json"
STRONG_JWT = "k" * 40

#: The complete, safe production base. Each case breaks exactly one thing.
PRODUCTION = {
    "ENVIRONMENT": "production",
    "JWT_SECRET": STRONG_JWT,
    "AUTH_MODE": "enforcing",
    "AUTH_DEV_TOKENS_ENABLED": "false",
    "CORS_ALLOW_ORIGINS": "https://poa.invalid.example",
    "AUTH_OIDC_ENABLED": "true",
    "AUTH_OIDC_ISSUER": ISSUER,
    "AUTH_OIDC_JWKS_URI": JWKS,
    "AUTH_OIDC_AUDIENCE": "authenticated",
    "AUTH_OIDC_ALGORITHMS": "ES256",
    "AUTH_OIDC_IDENTITY_PROVIDER": "supabase",
}

CASES = [
    # (name, expect_boot, overrides, removes, expected reason fragment)
    ("production fully configured", True, {}, (), ""),
    ("production with the verifier off", False, {"AUTH_OIDC_ENABLED": "false"}, (),
     "auth_oidc_enabled must be true in production"),
    ("production with the shipped placeholder issuer", False,
     {"AUTH_OIDC_ISSUER": "https://supabase.auth.local",
      "AUTH_OIDC_JWKS_URI": "https://supabase.auth.local/.well-known/jwks"}, (),
     "auth_oidc_issuer uses the non-public host"),
    ("production with loopback as the provider", False,
     {"AUTH_OIDC_ISSUER": "https://localhost:5432/auth/v1",
      "AUTH_OIDC_JWKS_URI": "https://localhost:5432/.well-known/jwks.json"}, (),
     "auth_oidc_issuer uses the non-public host"),
    ("production with keys from a different host", False,
     {"AUTH_OIDC_JWKS_URI": "https://other-project.supabase.co/auth/v1/.well-known/jwks.json"}, (),
     "must be served by the same host"),
    ("production with no provider name", False,
     {"AUTH_OIDC_IDENTITY_PROVIDER": "  "}, (),
     "auth_oidc_identity_provider must name the provider"),
    ("production with the HMAC algorithm", False, {"AUTH_OIDC_ALGORITHMS": "HS256"}, (),
     "only contain asymmetric algorithms"),
    ("production on the development jwt default", False, {"JWT_SECRET": "changeme"}, (),
     "jwt_secret is unsafe for production"),
    ("production in development auth mode", False, {"AUTH_MODE": "development"}, (),
     "auth_mode must be 'enforcing' in production"),
    ("production with development bearer tokens on", False,
     {"AUTH_DEV_TOKENS_ENABLED": "true"}, (),
     "auth_dev_tokens_enabled must be false in production"),
    ("production with wildcard CORS", False, {"CORS_ALLOW_ORIGINS": "*"}, (),
     "cors_allow_origins must be an explicit origin allowlist"),
    # The unconfigured deployment: exactly what a fresh checkout has.
    ("development with nothing set", True,
     {}, ("ENVIRONMENT", "JWT_SECRET", "AUTH_MODE", "AUTH_DEV_TOKENS_ENABLED",
          "CORS_ALLOW_ORIGINS", "AUTH_OIDC_ENABLED", "AUTH_OIDC_ISSUER",
          "AUTH_OIDC_JWKS_URI", "AUTH_OIDC_AUDIENCE", "AUTH_OIDC_ALGORITHMS",
          "AUTH_OIDC_IDENTITY_PROVIDER"), ""),
    # A placeholder is refused in development too: it fails every sign-in there as
    # loudly as it would in production, and the fix must not be production-only.
    ("development with the verifier on a placeholder host", False,
     {"AUTH_OIDC_ISSUER": "https://supabase.auth.local",
      "AUTH_OIDC_JWKS_URI": "https://supabase.auth.local/.well-known/jwks",
      "AUTH_OIDC_ALGORITHMS": "ES256", "AUTH_OIDC_ENABLED": "true",
      "AUTH_MODE": "enforcing", "AUTH_DEV_TOKENS_ENABLED": "false",
      "CORS_ALLOW_ORIGINS": "http://localhost:5173"}, (),
     "auth_oidc_issuer uses the non-public host"),
]

PROBE = """
import sys
try:
    import backend.app.main
    import backend.core.config as c
except Exception as exc:
    text = str(exc)
    reason = next((line.strip() for line in text.splitlines()
                   if "Value error," in line), text.splitlines()[0])
    print("REFUSED", reason[:300])
    sys.exit(3)
print("BOOT", c.settings.environment, c.settings.auth_mode,
      c.settings.auth_dev_tokens_enabled, c.settings.auth_oidc_enabled)
"""


def run_case(name, expect_boot, overrides, removes, expected_reason):
    env = {**os.environ, "DATABASE_URL":
           "postgresql+psycopg2://poa_runtime:unused@127.0.0.1:1/nonexistent_probe",
           **PRODUCTION, **overrides}
    for key in removes:
        env.pop(key, None)
    proc = subprocess.run([PYTHON, "-c", PROBE], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, timeout=180)
    stdout = (proc.stdout or "").strip()
    booted = proc.returncode == 0
    reason = stdout[len("REFUSED"):].strip() if stdout.startswith("REFUSED") else ""
    if not reason and not booted:
        # Not a config refusal: the process died some other way, which must not be
        # counted as the guard working.
        reason = f"UNEXPECTED rc={proc.returncode} {(proc.stderr or '')[-200:]}"
    passed = booted == expect_boot and (expect_boot or expected_reason in reason)
    detail = stdout if booted else (reason or f"rc={proc.returncode}")
    print(f"{'PASS' if passed else 'FAIL'}  {name} (expected "
          f"{'boot' if expect_boot else 'refusal: ' + expected_reason}) -> {detail[:300]}")
    return {"case": name, "expect_boot": expect_boot, "returncode": proc.returncode,
            "booted": booted, "expected_reason": expected_reason,
            "reason": reason[:300], "passed": passed, "detail": detail[:400]}


def main() -> int:
    results = [run_case(*case) for case in CASES]
    summary = {"passed": sum(r["passed"] for r in results), "total": len(results)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "results": results}, indent=2),
                   encoding="utf-8")
    print(json.dumps(summary))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
