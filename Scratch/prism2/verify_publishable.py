"""PRISM Phase 1b verification: apply the repository hygiene rules to every
object a push of the intended branch would actually publish.

`scripts/check_repository_hygiene.py --refs` only sees one tree. A push uploads
the whole unpublished ancestry, so this walks `git rev-list --objects <range>`,
dedupes by blob sha, and reuses the checker's own rules and inert-value logic
without copying them. A finding prints rule, path, line and match length only.

usage: python Scratch/prism2/verify_publishable.py [range]
"""
import re
import subprocess
import sys
from collections import Counter
from importlib import import_module
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
RANGE = sys.argv[1] if len(sys.argv) > 1 else "origin/Backend..HEAD"

sys.path.insert(0, str(REPO / "scripts"))
hyg = import_module("check_repository_hygiene")

NAME_RULES = [(n, re.compile(r)) for n, r in hyg.NAME_RULES]
CONTENT_RULES = [(n, re.compile(r)) for n, r in hyg.CONTENT_RULES]


def git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=REPO)
    return proc.stdout


def main():
    objects = git("rev-list", "--objects", RANGE).splitlines()
    commits = int(git("rev-list", "--count", RANGE).strip())
    blob_paths = {}
    for line in objects:
        parts = line.split(" ", 1)
        sha = parts[0]
        if len(parts) == 1:
            continue
        blob_paths.setdefault(parts[0], set()).add(parts[1])

    name_hits = []
    content_hits = Counter()
    scanned = 0
    for sha, paths in sorted(blob_paths.items(), key=lambda kv: sorted(kv[1])[0]):
        for name, rx in NAME_RULES:
            for p in sorted(paths):
                if rx.search(p):
                    name_hits.append((name, p, sha[:10]))
        text = git("cat-file", "-p", sha)
        if len(text) > 2_000_000 or "\x00" in text[:8000]:
            continue
        scanned += 1
        for i, line in enumerate(text.splitlines(), 1):
            for name, rx in CONTENT_RULES:
                for m in rx.finditer(line):
                    if name in ("DSN_WITH_PASSWORD", "REDIS_URL_WITH_PASSWORD") \
                            and hyg.dsn_is_inert(line, m):
                        continue
                    content_hits[(name, sorted(paths)[0], i)] += 1

    print(f"rev-list lines in {RANGE}      : {len(objects)}")
    print(f"commits that a push publishes : {commits}")
    print(f"unique blobs                  : {len(blob_paths)}")
    print(f"blobs content-scanned         : {scanned}")
    print(f"name-rule findings            : {len(name_hits)}")
    kinds = Counter(h[0] for h in name_hits)
    for k, v in sorted(kinds.items()):
        print(f"   {k} = {v}")
    print(f"content-rule findings         : {len(content_hits)}")
    for (name, path, line) in sorted(content_hits):
        print(f"   {path}:{line}  [{name}]")
    print("VERDICT: " + ("CLEAN - nothing sensitive is publishable"
                         if not name_hits and not content_hits
                         else "FINDINGS PRESENT"))
    return 0 if not name_hits and not content_hits else 1


if __name__ == "__main__":
    sys.exit(main())
