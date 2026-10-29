"""PRISM Phase 3: obtain a REAL provider token locally, without the secret ever leaving this machine.

The accept path of reviewer authentication can only be measured with a token this
Supabase project actually signed. Nobody may type that project password into chat, and
no access or refresh token should be pasted anywhere either, so this is the secure local
procedure instead: the password is read with a hidden prompt, exchanged over TLS against
the project's own token endpoint, and only the resulting token is written to a gitignored
file that :mod:`phase3_token_matrix.py` reads.

What is deliberately NOT printed: the password, the access token, the refresh token, the
publishable key. What IS printed: the HTTP status, the provider's own error code, and the
token's *public* header/claim shape (alg, kid, issuer, audience, expiry, and whether ``sub``
equals the subject the backend has mapped) - all of which are needed to interpret the result
and none of which are credentials.

    python Scratch/prism2/phase3_operator_token.py            # interactive prompt
    echo PASSWORD | python Scratch/prism2/phase3_operator_token.py --from-stdin

The expected project ref is the one PRISM Phase 2 reconfirmed from the live endpoints; if the
frontend configuration points anywhere else this refuses rather than signing into a
look-alike project.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPECTED_REF = "tuaeujvuuanadqvykugw"
ID_FILE = REPO / "Scratch/prism2/reviewer.local.json"
TOKEN_FILE = REPO / "Scratch/prism2/reviewer.local.token"
REFRESH_FILE = REPO / "Scratch/prism2/reviewer.refresh.token"
META_FILE = REPO / "Scratch/prism2/reviewer.meta.local.json"
ENV_CANDIDATES = [
    REPO / "frontend/.env",
    REPO / "Scratch/mbe01-frontend/frontend/.env",
]
LOCAL_CANDIDATES = [
    REPO / "frontend/.env.local",
    REPO / "Scratch/mbe01-frontend/frontend/.env.local",
]
KEY_NAMES = ("VITE_SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_ANON_KEY",
             "VITE_SUPABASE_KEY")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def first_existing(paths: list[Path]) -> Path | None:
    return next((p for p in paths if p.is_file()), None)


def b64json(segment: str) -> dict:
    pad = "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment + pad))


def describe(token: str) -> dict:
    """Public shape only: header fields and claim names, never the credential."""
    parts = token.split(".")
    if len(parts) != 3:
        return {"jwt_shaped": False, "note": "opaque (a refresh token is not a session proof)"}
    header, claims = b64json(parts[0]), b64json(parts[1])
    exp = claims.get("exp")
    return {
        "jwt_shaped": True,
        "alg": header.get("alg"),
        "kid": header.get("kid"),
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
        "use": claims.get("use"),
        "expires_at": (datetime.fromtimestamp(exp, timezone.utc).isoformat()
                       if isinstance(exp, int) else None),
        "sub_is_mapped_subject": claims.get("sub") == json.loads(
            ID_FILE.read_text(encoding="utf-8"))["external_subject"],
        "fingerprint": hashlib_sha256(token)[:12],
    }


def hashlib_sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-stdin", action="store_true",
                        help="read the password from a stdin line (for a non-interactive retry)")
    parser.add_argument("--email")
    args = parser.parse_args()

    env_file = first_existing(ENV_CANDIDATES)
    local_file = first_existing(LOCAL_CANDIDATES)
    if env_file is None:
        print("BLOCKED: no frontend .env found, so the project URL is unknown.")
        return 2
    base = read_env(env_file).get("VITE_SUPABASE_URL", "").rstrip("/")
    ref_match = re.search(r"https://([a-z0-9]+)\.supabase\.co", base)
    if not ref_match:
        print(f"BLOCKED: VITE_SUPABASE_URL in {env_file} is not a Supabase project URL.")
        return 2
    if ref_match.group(1) != EXPECTED_REF:
        print(f"REFUSED: the frontend points at project {ref_match.group(1)!r}, but PRISM Phase 2 "
              f"reconfirmed {EXPECTED_REF!r}. Signing into the wrong project would prove nothing.")
        return 2
    print(f"project ref (from {env_file.name}, cross-checked) : {ref_match.group(1)}")

    key: str | None = None
    key_name = ""
    for candidate in LOCAL_CANDIDATES:
        if candidate.is_file():
            found = read_env(candidate)
            for name in KEY_NAMES:
                if found.get(name):
                    key, key_name = found[name], name
                    break
        if key:
            break
    if key is None:
        print("BLOCKED: no publishable key found in frontend/.env.local. Add one line, "
              "VITE_SUPABASE_PUBLISHABLE_KEY=<Publishable key from Project Settings -> API>, "
              "then re-run. That file is gitignored; the key is never printed here.")
        return 2
    print(f"publishable key (read, length only)               : {key_name}, {len(key)} chars")

    email = args.email or json.loads(ID_FILE.read_text(encoding="utf-8"))["email"]
    if args.from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass(f"Supabase password for {email} (hidden, never stored): ")
    if not password:
        print("BLOCKED: no password supplied; nothing was sent.")
        return 2

    url = f"{base}/auth/v1/token?grant_type=password"
    request = urllib.request.Request(
        url, method="POST",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"apikey": key, "Content-Type": "application/json"})
    print(f"POST {url}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
            status = response.status
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:400]
        # The provider's own error body is public operational information, not a credential.
        print(f"PROVIDER REFUSED http={error.code} body={detail}")
        print("Nothing was written. The password is not retained by this process.")
        return 1

    if not isinstance(body, dict) or "access_token" not in body:
        print(f"UNEXPECTED RESPONSE http={status} keys={sorted(body) if isinstance(body, dict) else body}")
        return 1

    TOKEN_FILE.write_text(body["access_token"], encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    refresh = body.get("refresh_token")
    if isinstance(refresh, str) and refresh:
        REFRESH_FILE.write_text(refresh, encoding="utf-8")
        os.chmod(REFRESH_FILE, 0o600)
    META_FILE.write_text(json.dumps({
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "token_type": body.get("token_type"),
        "expires_in": body.get("expires_in"),
        "refresh_token_present": bool(refresh),
    }, indent=2), encoding="utf-8")
    print(f"OK http={status}; wrote the access token to "
          f"{TOKEN_FILE.relative_to(REPO)} (gitignored, 0600)"
          + (f" and the refresh token to {REFRESH_FILE.relative_to(REPO)}" if refresh else "")
          + ". Neither value is printed.")
    print("access token shape : " + json.dumps(describe(body["access_token"])))
    if refresh:
        print("refresh token shape: " + json.dumps(describe(refresh)))
    print("\nNext: python Scratch/prism2/phase3_token_matrix.py")
    print("  and: python -m backend.security.oidc_preflight "
          "--expected-project-ref " + EXPECTED_REF + " --token-file "
          + str(TOKEN_FILE.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
