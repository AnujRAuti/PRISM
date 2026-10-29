"""PRISM Phase 2: does the identity configuration fail closed?

Every case runs the real release gate (`python -m backend.security.oidc_preflight`)
in a subprocess with one configuration value changed, so what is observed is what
the deployment would actually do. The project endpoints are the ones measured in
phase2_project.out - fetched from the live provider, not copied from a report.

A case PASSES when the gate accepts a correct configuration, and REFUSES when the
configuration is a placeholder, an algorithm the provider does not publish, a
split authority, an unreachable key set, the wrong project, or production with
the verifier off. Only hosts, algorithm names and check outcomes are printed.
"""
import json
import os
import secrets
import subprocess
import sys

REF = "tuaeujvuuanadqvykugw"
ISSUER = f"https://{REF}.supabase.co/auth/v1"
JWKS = f"{ISSUER}/.well-known/jwks.json"
PY = sys.executable

REAL = {
    "AUTH_OIDC_ENABLED": "true",
    "AUTH_OIDC_ISSUER": ISSUER,
    "AUTH_OIDC_JWKS_URI": JWKS,
    "AUTH_OIDC_AUDIENCE": "authenticated",
    "AUTH_OIDC_ALGORITHMS": "ES256",
    "AUTH_OIDC_IDENTITY_PROVIDER": "supabase",
}

CASES = [
    # (name, expectation, env overrides, preflight args)
    ("measured project, ES256, correct ref", "GATE-BLOCKED-NO-TOKEN", {},
     ["--expected-project-ref", REF]),
    ("compose default RS256 against an ES256 provider", "GATE-FAIL",
     {"AUTH_OIDC_ALGORITHMS": "RS256"}, ["--expected-project-ref", REF]),
    ("HMAC algorithm offered (algorithm-confusion vector)", "REFUSE-BOOT",
     {"AUTH_OIDC_ALGORITHMS": "HS256"}, ["--expected-project-ref", REF]),
    ("no algorithms configured at all", "REFUSE-BOOT",
     {"AUTH_OIDC_ALGORITHMS": ""}, ["--expected-project-ref", REF]),
    ("placeholder issuer supabase.auth.local", "REFUSE-BOOT",
     {"AUTH_OIDC_ISSUER": "http://supabase.auth.local/auth/v1",
      "AUTH_OIDC_JWKS_URI": "http://supabase.auth.local/auth/v1/.well-known/jwks.json"},
     ["--expected-project-ref", REF]),
    ("blank issuer while enabled", "REFUSE-BOOT", {"AUTH_OIDC_ISSUER": ""},
     ["--expected-project-ref", REF]),
    ("blank audience while enabled", "REFUSE-BOOT", {"AUTH_OIDC_AUDIENCE": ""},
     ["--expected-project-ref", REF]),
    ("issuer and JWKS on different authorities", "REFUSE-BOOT",
     {"AUTH_OIDC_JWKS_URI": "https://someone-else.supabase.co/auth/v1/.well-known/jwks.json"},
     ["--expected-project-ref", REF]),
    ("JWKS path unreachable (must fail closed, not open)", "GATE-FAIL",
     {"AUTH_OIDC_JWKS_URI": f"{ISSUER}/.well-known/jwks-missing.json"},
     ["--expected-project-ref", REF]),
    ("correct config, wrong expected project ref", "GATE-FAIL", {},
     ["--expected-project-ref", "aaaaaaaaaaaaaaaaaaaaa"]),
    ("production with the verifier off", "REFUSE-BOOT",
     {"ENVIRONMENT": "production", "AUTH_MODE": "enforcing",
      "AUTH_OIDC_ENABLED": "false",
      "AUTH_DEV_TOKENS_ENABLED": "false", "CORS_ALLOW_ORIGINS": "https://example.invalid",
      "__jwt_secret__": True},
     ["--expected-project-ref", REF]),
]


def run(case_env, args):
    env = dict(os.environ)
    env.update(REAL)
    env.update({k: v for k, v in case_env.items() if not k.startswith("__")})
    if case_env.get("__jwt_secret__"):
        env["JWT_SECRET"] = secrets.token_hex(32)
    env.setdefault("PYTHONPATH", ".")
    proc = subprocess.run([PY, "-m", "backend.security.oidc_preflight", "--json", *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)
    return proc


def refuse_message(stderr):
    for line in stderr.splitlines():
        text = line.strip()
        if text.startswith("Value error,") or text.startswith("ValueError:"):
            text = text.replace("Value error, ", "")
            return text.split("[type=")[0].strip()[:200]
    return (stderr.strip().splitlines() or [""])[-1][:200]


def classify(proc):
    if "ValidationError" in proc.stderr or "ValueError" in proc.stderr:
        return "REFUSE-BOOT", refuse_message(proc.stderr)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return "ERROR", (proc.stderr or proc.stdout)[:200]
    failing = [c["name"] for c in payload["checks"] if c["status"] == "FAIL"]
    blocked = [c["name"] for c in payload["checks"] if c["status"] == "BLOCKED"]
    detail = (f"verdict={payload['verdict']} failing={failing or '-'} "
              f"blocked={blocked or '-'}")
    if not failing and blocked == ["probe_token"]:
        return "GATE-BLOCKED-NO-TOKEN", detail
    return ("GATE-PASS" if payload["verdict"] == "PASS"
            else "GATE-FAIL" if payload["verdict"] == "FAIL" else "GATE-BLOCKED"), detail


def main():
    token_file = sys.argv[1] if len(sys.argv) > 1 else None
    if token_file:
        CASES[0] = (CASES[0][0], "GATE-PASS", CASES[0][2], CASES[0][3] + ["--token-file", token_file])
        print(f"probe token supplied from {token_file} (value never read into this output)\n")
    mismatches = 0
    for name, expectation, case_env, args in CASES:
        outcome, detail = classify(run(case_env, args))
        ok = outcome == expectation
        mismatches += 0 if ok else 1
        print(f"[{'OK ' if ok else 'UNEXPECTED'}] {name}\n        wanted={expectation} "
              f"saw={outcome} :: {detail}")
    print(f"\ncases: {len(CASES)}  as-designed: {len(CASES) - mismatches}  "
          f"unexpected: {mismatches}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
