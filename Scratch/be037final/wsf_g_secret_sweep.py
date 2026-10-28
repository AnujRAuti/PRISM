"""BE-037 WS-G: secret-hygiene sweep over this task's whole scratch tree.

Complements the run-credential scan in ``wsf_f5_safeguards.py``: instead of
matching known throwaway values, it looks for *shapes* that must never be
written down anywhere — a live presigned-object URL, a credential scope in a
query string, a bearer JWT, or a run-id-derived password.

The sweep only ever prints file paths, pattern names and match counts. It never
prints a matched value, so running it cannot itself leak a secret into a log.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("D:/CODING/Scratch/be037final")

PATTERNS = {
    "presigned_object_url": re.compile(r"[?&]X-Amz-Signature=[0-9a-f]{16,}", re.I),
    "credential_scope_in_query": re.compile(r"[?&]?X-Amz-Credential=[^\s&,\"']{6,}", re.I),
    "bearer_jwt": re.compile(r"[Bb]earer\s+[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    "run_derived_password": re.compile(r"\b(?:be037wf7e3|be037fin7c1f1)[A-Za-z0-9\-]*(?:pw2?|rtpw|secret|admin)\b"),
    "dsn_with_inline_password": re.compile(
        r"postgres(?:ql)?(?:\+\w+)?:\/\/[^\s\"'@*]{2,}:[^\s\"'@*][^\s\"'@]{3,}@"),
    "amz_date_pair": re.compile(r"X-Amz-Date=\d{8}T\d{6}Z", re.I),
}

SKIP_PARTS = {"__pycache__", ".git"}


def main() -> int:
    rows = {}
    total_files = 0
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
        if SKIP_PARTS & set(path.parts):
            continue
        total_files += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        found = {}
        for name, pattern in PATTERNS.items():
            n = len(pattern.findall(text))
            if n:
                found[name] = n
        if found:
            rows[str(path.relative_to(ROOT))] = found
    print(f"scanned {total_files} files under {ROOT}")
    for file, found in rows.items():
        print(f"  {file}: {found}")
    print(f"files with any secret-shaped match: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
