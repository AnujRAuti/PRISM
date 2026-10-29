"""PRISM2 Phase 1: scan every object that the unpushed range would publish.

The question is not what HEAD tracks - it is what a `git push` of this range would upload.
`git rev-list --objects <upstream>..HEAD` lists exactly the objects that reachability adds,
so this scans that set: by filename (dumps, tars, env backups) and by content (credential
shapes). A hit is reported as rule name + line number + value length. No matched value, and
no line of source, is ever printed.

usage: python Scratch/prism2/scan_history.py [upstream]
"""

from __future__ import annotations

import re
import subprocess
import sys

REPO = r"D:/CODING/Projects/Proof-Of-Action-Final"
UPSTREAM = sys.argv[1] if len(sys.argv) > 1 else "origin/Backend"

# Credential shapes. Group 0 is the whole match; only its LENGTH is reported.
CONTENT_RULES: list[tuple[str, re.Pattern]] = [
    ("JWT_OR_OPAQUE_TOKEN", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("SUPABASE_KEY", re.compile(r"\bsb[._-]?(?:publishable|secret|anon|service)[A-Za-z0-9_./-]{8,}")),
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("GITHUB_TOKEN", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}")),
    ("CLOUD_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("DSN_WITH_PASSWORD", re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s/@]*:[^\s@]+@", re.I)),
    ("REDIS_URL_WITH_PASSWORD", re.compile(r"redis://:[^\s@]+@", re.I)),
    ("AZURE_ACCOUNT_KEY", re.compile(r"AccountKey=[A-Za-z0-9+/=]{20,}")),
    ("SECRET_ASSIGNMENT", re.compile(
        r"(?i)^\s*(?:export\s+)?[A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|API_?KEY|ACCESS_?KEY|"
        r"PRIVATE_?KEY|CREDENTIAL|SIGNING_?KEY)[A-Z0-9_]*\s*[=:]\s*[\"']?(?!<|\{\{|example|CHANGE|PLACEHOLDER)"
        r"[A-Za-z0-9+/._-]{12,}[\"']?\s*$")),
]

# Sensitive by name regardless of contents.
NAME_RULES: list[tuple[str, re.Pattern]] = [
    ("DATABASE_DUMP", re.compile(r"(?i)\.(dump|sql\.gz|sql.gz)$")),
    ("SQL_DATA_EXPORT", re.compile(r"(?i)\.(sql)$")),
    ("SQLITE_DATABASE", re.compile(r"(?i)\.(db|sqlite|sqlite3)$")),
    ("IMAGE_OR_ARCHIVE_TAR", re.compile(r"(?i)\.(tar|tgz|zip|gz)$")),
    ("ENV_BACKUP_OR_SECRET_FILE", re.compile(r"(?i)(secrets?\.env|env\.owner|\.env\.bak|\.env\.backup|env\.bak)$")),
    ("ENV_FILE_NOT_EXAMPLE", re.compile(r"(?i)\.env$")),
    ("PASSWORD_FILE", re.compile(r"(?i)password|passwd|credential")),
    ("PRIVATE_KEY_FILE", re.compile(r"(?i)\.(pem|key|ppk|p12|pfx)$|id_rsa|id_ed25519")),
    ("MODEL_OR_EVIDENCE_BINARY", re.compile(r"(?i)\.(pt|onnx|engine|pkl)$")),
]

IGNORE_NOISE = re.compile(r"(?i)(\.env\.example$|/MANIFEST_|restore_list_|secret_scan\.py$|secret_severity\.py$|"
                          r"secret_sweep|secret-scan|token=token|test-token|placeholder)")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def main() -> int:
    lines = git("rev-list", "--objects", f"{UPSTREAM}..HEAD").splitlines()
    pairs = []
    for line in lines:
        parts = line.split(" ", 1)
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))

    blob_types = {}
    for sha, _ in pairs:
        if sha not in blob_types:
            blob_types[sha] = git("cat-file", "-t", sha).strip()

    print(f"objects listed in {UPSTREAM}..HEAD : {len(lines)}  "
          f"(unique sha {len(blob_types)})")

    findings: list[tuple[str, str, str, int]] = []   # (rule, path, kind, length)
    scanned = 0
    for sha, path in pairs:
        if blob_types.get(sha) != "blob":
            continue
        for rule, pattern in NAME_RULES:
            if pattern.search(path) and not IGNORE_NOISE.search(path):
                findings.append((rule, path, "filename", 0))
        # Content scan: bounded to text files under 8 MB.
        size = int(git("cat-file", "-s", sha).strip() or 0)
        if size > 8 * 1024 * 1024:
            findings.append(("LARGE_BLOB_SKIPPED_FOR_CONTENT", path, "size", size))
            continue
        body = subprocess.run(["git", "cat-file", "blob", sha], cwd=REPO,
                              capture_output=True).stdout
        if b"\x00" in body[:4096]:
            findings.append(("BINARY_BLOB", path, "binary", size))
            continue
        scanned += 1
        text = body.decode("utf-8", "replace")
        for number, line in enumerate(text.splitlines(), 1):
            for rule, pattern in CONTENT_RULES:
                hit = pattern.search(line)
                if hit and not IGNORE_NOISE.search(line):
                    findings.append((rule, f"{path}:{number}", "content", len(hit.group(0))))

    print(f"text blobs content-scanned: {scanned}")
    print(f"findings: {len(findings)}")
    order = ["PRIVATE_KEY_BLOCK", "PRIVATE_KEY_FILE", "PASSWORD_FILE", "DATABASE_DUMP",
             "SQL_DATA_EXPORT", "SQLITE_DATABASE", "ENV_BACKUP_OR_SECRET_FILE",
             "ENV_FILE_NOT_EXAMPLE", "JWT_OR_OPAQUE_TOKEN", "SUPABASE_KEY", "GITHUB_TOKEN",
             "CLOUD_ACCESS_KEY", "AZURE_ACCOUNT_KEY", "DSN_WITH_PASSWORD",
             "REDIS_URL_WITH_PASSWORD", "SECRET_ASSIGNMENT", "IMAGE_OR_ARCHIVE_TAR",
             "BINARY_BLOB", "LARGE_BLOB_SKIPPED_FOR_CONTENT", "MODEL_OR_EVIDENCE_BINARY"]
    seen_paths = set()
    for rule in order:
        rows = [f for f in findings if f[0] == rule]
        if not rows:
            continue
        print(f"\n## {rule}  ({len(rows)})")
        for _, where, kind, length in sorted(set(rows)):
            seen_paths.add(where.split(":")[0])
            suffix = f" matched_length={length}" if kind == "content" else (
                f" bytes={length}" if length else "")
            print(f"   {where}  [{kind}]{suffix}")

    print(f"\ndistinct paths flagged: {len(seen_paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
