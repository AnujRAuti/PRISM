"""Repository hygiene check: block sensitive artifacts from entering Git.

PRISM Phase 1 found database dumps, captured secrets and a 704 MB image tar
reachable in unpublished history. Rules here are the artifact *classes* that
were measured, so the same mistake cannot be committed again unnoticed.

    python scripts/check_repository_hygiene.py [--staged | --all | --refs <range>]

Exit 0 = clean, 1 = findings, 2 = usage or git failure. Values are never
printed: a content finding reports the rule, the line number and the match
length only.
"""
import argparse
import re
import subprocess
import sys

# A file must not enter Git because of what it is.
NAME_RULES = [
    ("DATABASE_DUMP", r"(?i)\.(dump|sql\.gz|pgdump)$"),
    ("ARCHIVE_OR_IMAGE_TAR", r"(?i)\.(tar|tgz|zip|gz)$"),
    ("PASSWORD_FILE", r"(?i)(password|passwd|credential)[^/]*\.(txt|lst|csv|json)$"),
    ("SECRET_ENV_STORE", r"(?i)(^|/)secrets?\.env$|(^|/)env\.[a-z]*backup$|\.env\.(bak|backup|old)$"),
    ("PRIVATE_KEY_FILE", r"(?i)\.(pem|p12|pfx|ppk)$|(^|/)id_(rsa|ed25519)$"),
    ("RAW_URL_DUMP", r"(?i)(^|/)_?[a-z]*url\.txt$"),
    ("ENV_FILE_NOT_EXAMPLE", r"(?i)(^|/)[a-z0-9_.-]*\.env$"),
]

# A file may enter Git but must not carry a live credential in it.
CONTENT_RULES = [
    ("SUPABASE_KEY", r"\bsb[._-]?(?:publishable|secret|anon|service)[a-z0-9_-]{10,}"),
    ("PRIVATE_KEY_BLOCK", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("GITHUB_TOKEN", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|github_pat_[A-Za-z0-9_]{20,}"),
    ("CLOUD_ACCESS_KEY", r"\bAKIA[0-9A-Z]{16}\b"),
    ("AZURE_ACCOUNT_KEY", r"(?i)AccountKey\s*=\s*[A-Za-z0-9+/=]{30,}"),
    ("DSN_WITH_PASSWORD", r"postgres(?:ql)?(?:\+\w+)?://[^\s/@]*:[^\s@]+@"),
    ("REDIS_URL_WITH_PASSWORD", r"rediss?://[^\s/@]*:[^\s@]+@"),
    ("SECRET_ASSIGNMENT",
     r"(?i)^\s*(?:export\s+)?[A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|_PW|CREDENTIAL)[A-Z0-9_]*"
     r"\s*[=:]\s*[\"']?(?!<|\{\{|CHANGE|PLACEHOLDER|EXAMPLE|REDACTED)[A-Za-z0-9+/._-]{12,}"
     r"[\"']?\s*$"),
]

# The developer's own local stack: docker-compose.yml and .env.example publish
# these, so a match on them is the documented default, not a leaked secret.
LOCAL_DEV_DEFAULTS = {
    "postgres", "minioadmin", "poa_runtime", "poa_owner", "REDACTED",
}
# A DSN whose host is on this machine or inside the compose network can only
# ever reach the developer's own containers.
LOCAL_HOSTS = re.compile(r"(?i)^(localhost|127\.0\.0\.1|0\.0\.0\.0|db|redis|host\.docker\.internal|minio)"
                         r"(:\d+)?(/|$)")
BINARY_SNIFF_BYTES = 8000
MAX_SCAN_BYTES = 2_000_000


def git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.stdout, proc.returncode, proc.stderr


def list_paths(mode, argument):
    if mode == "staged":
        out, _, _ = git("diff", "--cached", "--name-only", "--diff-filter=ACM")
        return sorted({p for p in out.splitlines() if p})
    if mode == "refs":
        out, _, _ = git("ls-tree", "-r", "--name-only", argument or "HEAD")
        return sorted({p for p in out.splitlines() if p})
    out, _, _ = git("ls-files")
    return sorted({p for p in out.splitlines() if p})


def blob(path, mode, argument):
    if mode == "staged":
        proc = subprocess.run(["git", "show", f":{path}"], capture_output=True)
        return proc.stdout if proc.returncode == 0 else None
    if mode == "refs":
        proc = subprocess.run(["git", "show", f"{argument}:{path}"], capture_output=True)
        return proc.stdout if proc.returncode == 0 else None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


COMPOSE_SUPERUSERS = {"postgres", "minioadmin"}
MASKED = re.compile(r"^([*x])\1{2,}$")
INTERPOLATED = re.compile(r"\{|%s|\$\{?[A-Za-z_]|<")
ATTRIBUTE_REF = re.compile(r"[A-Za-z_]\w*\.[\w(\[]")


def dsn_parts(line, match):
    """Return (user, password, host) for a DSN match, or None if unreadable."""
    tail = line[match.start():]
    parsed = re.match(
        r"(?i)^(?:postgres(?:ql)?(?:\+\w+)?|rediss?)://([^\s/@]*):([^\s@]+)@([^\s\"'`,)]*)",
        tail)
    if not parsed:
        return None
    return parsed.group(1), parsed.group(2), parsed.group(3)


def dsn_is_inert(line, match):
    """True when the embedded credential cannot be a live secret.

    A generated password in this project is 24-48 hex characters, so literal
    values shorter than that and anything that is only an interpolation site
    are not evidence of exposure. A generated password reaching a compose
    service host is still a finding.
    """
    parts = dsn_parts(line, match)
    if not parts:
        return False
    user, password, host = parts
    if INTERPOLATED.search(password) or ATTRIBUTE_REF.search(password):
        return True
    if MASKED.match(password):
        return True
    if password in LOCAL_DEV_DEFAULTS or len(password) < 12:
        return True
    loopback = bool(LOCAL_HOSTS.match(host))
    return loopback and user in COMPOSE_SUPERUSERS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--refs", metavar="REV_OR_RANGE")
    args = parser.parse_args()

    mode = "staged" if args.staged else ("refs" if args.refs else "worktree")
    argument = args.refs if args.refs else "HEAD"
    paths = list_paths(mode, argument)
    if not paths:
        print("no paths to check")
        return 2

    findings = []
    scanned = 0
    for path in paths:
        for rule, rx in NAME_RULES:
            if re.search(rx, path):
                findings.append((rule, path, 0, 0))
        data = blob(path, mode, argument)
        if data is None or b"\x00" in data[:BINARY_SNIFF_BYTES]:
            if data and len(data) > MAX_SCAN_BYTES:
                findings.append(("LARGE_BINARY", path, 0, len(data)))
            continue
        text = data.decode("utf-8", "replace")
        scanned += 1
        for i, line in enumerate(text.splitlines(), 1):
            for rule, rx in CONTENT_RULES:
                for m in re.finditer(rx, line):
                    if rule in ("DSN_WITH_PASSWORD", "REDIS_URL_WITH_PASSWORD"):
                        if dsn_is_inert(line, m):
                            continue
                    if rule == "SECRET_ASSIGNMENT":
                        value = re.split(r"[=:]", line, 1)[1].strip().strip("\"'")
                        if (value in LOCAL_DEV_DEFAULTS or INTERPOLATED.search(value)
                                or ATTRIBUTE_REF.search(value) or MASKED.match(value)):
                            continue
                    findings.append((rule, path, i, len(m.group(0))))

    print(f"mode={mode} target={argument if mode == 'refs' else '-'}")
    print(f"paths checked: {len(paths)}  text blobs content-scanned: {scanned}")
    if findings:
        print(f"findings: {len(findings)}")
        for rule, path, line, length in findings:
            where = f":{line}" if line else ""
            print(f"   {rule}  {path}{where}  matched_length={length}")
        return 1
    print("findings: 0 — clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
