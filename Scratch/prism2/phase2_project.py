"""PRISM Phase 2: reconfirm the ACTUAL Supabase project from live evidence.

Prior reports are treated as claims, not facts. This reads the project URL from
every place the running code actually looks, then asks that project's own
endpoints what issuer, audience and signing keys it publishes. URLs, issuers,
algorithms and key ids are public metadata; every credential-like value is
printed only as a length and a digest prefix.
"""
import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
SOURCES = [
    ".env",
    "frontend/.env",
    "Scratch/mbe01-frontend/.env.example",
    "Scratch/mbe01-frontend/frontend/.env",
    "Scratch/mbe01-frontend/frontend/.env.local",
    "docker-compose.yml",
]
KEY_RX = re.compile(r"(?i)([a-z0-9_]*(?:SUPABASE|OIDC|ANON|KEY|URL|ISSUER|AUDIENCE)[a-z0-9_]*)\s*[=:]\s*(.+)")


def digest(value):
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:10]


# Value-first: a printed secret is a finding regardless of what the key is named.
DSN_WITH_CREDENTIAL = re.compile(r"://[^/\s]*:[^/\s]+@")
TEMPLATE = re.compile(r"^\$\{[A-Za-z0-9_]+(:-.*)?\}$")
CREDENTIAL_NAME = re.compile(
    r"(?i)(secret|password|passwd|token|api_?key|access_?key|private_?key|credential|_pw\b)")
PUBLIC_METADATA = ("URL", "ISSUER", "JWKS", "AUDIENCE", "ALGORITHM", "PROVIDER",
                   "ENABLED", "REF", "MODE", "TTL")


def is_public(name, value):
    if DSN_WITH_CREDENTIAL.search(value):
        return False
    if TEMPLATE.match(value):
        return True
    if CREDENTIAL_NAME.search(name):
        return False
    return any(t in name.upper() for t in PUBLIC_METADATA)


def show(label, name, value):
    shown = value if is_public(name, value) else f"<hidden len={len(value)} sha256:{digest(value)}>"
    print(f"   {name} = {shown}")
    return value


def read_env(path):
    found = {}
    if not path.exists():
        print(f"{path.relative_to(REPO)}: ABSENT")
        return found
    print(f"{path.relative_to(REPO)}:")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = KEY_RX.search(line)
        if m:
            found[m.group(1).upper()] = m.group(2).strip().strip('"').strip("'")
            show(path.name, m.group(1), found[m.group(1).upper()])
    if not found:
        print("   (no supabase/oidc-shaped keys)")
    return found


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "prism-phase2"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return f"ERROR {type(e).__name__}: {e}", ""


def main():
    refs = set()
    for rel in SOURCES:
        env = read_env(REPO / rel)
        print()
        for name, value in env.items():
            m = re.search(r"https://([a-z0-9]{15,25})\.supabase\.(co|in)", value)
            if m:
                refs.add(m.group(1))
                print(f"   -> project ref from {rel} ({name}): {m.group(1)}")

    print("== distinct project refs the code actually points at ==")
    print(sorted(refs) or ["NONE FOUND"])
    if len(refs) != 1:
        print("MULTIPLE/NO REF - cannot reconfirm a single project")
        return 1
    ref = refs.pop()

    base = f"https://{ref}.supabase.co/auth/v1"
    print(f"\n== live endpoints for {ref} ==")
    status, body = get(base + "/.well-known/openid-configuration")
    print(f"GET {base}/.well-known/openid-configuration -> {status}")
    issuer = None
    if status == 200:
        cfg = json.loads(body)
        issuer = cfg.get("issuer")
        print(f"   issuer                = {issuer}")
        print(f"   jwks_uri              = {cfg.get('jwks_uri')}")
        print(f"   id_token_signing_alg  = {cfg.get('id_token_signing_alg_values_supported')}")
        print(f"   subject_types         = {cfg.get('subject_types_supported')}")
        print(f"   authorization_endpoint= {cfg.get('authorization_endpoint')}")
    status, body = get(base + "/.well-known/jwks.json")
    print(f"\nGET {base}/.well-known/jwks.json -> {status}")
    if status == 200:
        jwks = json.loads(body)
        for k in jwks.get("keys", []):
            print(f"   kid={k.get('kid')} kty={k.get('kty')} alg={k.get('alg')} "
                  f"use={k.get('use')} crv={k.get('crv')} x5t={bool(k.get('x5t'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
