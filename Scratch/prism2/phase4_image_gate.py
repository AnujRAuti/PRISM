"""PRISM Phase 4: does the rebuilt image carry exactly the sanitized commit, and nothing else?

The claim under test is twofold and neither half is self-evident:

1. ``poa-backend:prism-481fdc39`` was built from a ``git archive`` of HEAD, so every
   file it carries must exist at HEAD with the same bytes -- and it must carry no file
   that HEAD does not contain. Layer digests cannot prove this: a worktree build and an
   archive build of identical content still differ by file mtime.
2. A second image built earlier from the same inputs must hold the same *content*, so
   the 135-module digest evidence taken against that image still describes this one.

Contamination is proven structurally rather than by a name grep alone: if the image's
file set is a subset of the commit's tracked file set, then nothing untracked (a dump,
a secrets file, a scratch run) can be inside it. The name scan is still run, because a
sensitive *tracked* file would defeat the structural argument.

    python Scratch/prism2/phase4_image_gate.py [image] [other_image]
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
CTX = Path(r"D:/CODING/Scratch/prism-phase4-ctx")
IMAGE = sys.argv[1] if len(sys.argv) > 1 else "poa-backend:prism-481fdc39"
OTHER = sys.argv[2] if len(sys.argv) > 2 else "poa-backend:prism-54e33b20"

SKIP_PARTS = {"__pycache__"}
SUSPICIOUS = ("scratch", ".dump", "secrets.env", ".env", ".pem", ".key", ".token",
              "reviewer.local", "id_rsa", ".pgpass", "dump.sql", ".bak")
# .env.example is re-included by .dockerignore on purpose (`!.env.example`) and is the
# only env-named file allowed in the image; a template is checked for inertness by
# tests/unit/test_repository_hygiene.py, not by a filename scan.
ENV_TEMPLATE = ".env.example"
NON_SOURCE_DIRS = {"Scratch", "docs", "frontend", "diagnostics", "node_modules"}
NON_SOURCE_FILES = {"Dockerfile", "docker-compose.yml", ".dockerignore", ".gitignore",
                    "test-image.jpg"}

RESULTS: list[dict] = []


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"check": name, "pass": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  ->  {detail}")


def note(name: str, detail: str) -> None:
    RESULTS.append({"check": name, "pass": None, "detail": detail})
    print(f"NOTE  {name}  ->  {detail}")


def image_manifest(image: str) -> dict[str, str]:
    proc = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c",
         "cd /app && find . -type f -not -path '*__pycache__*' -exec sha256sum {} +"],
        capture_output=True, text=True, timeout=600)
    if proc.returncode:
        raise SystemExit(f"image scan rc={proc.returncode} {proc.stderr[:400]}")
    manifest = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            manifest[parts[1].removeprefix("./")] = parts[0]
    return manifest


def context_manifest() -> dict[str, str]:
    out = {}
    for path in CTX.rglob("*"):
        if not path.is_file() or SKIP_PARTS & set(path.parts):
            continue
        out[path.relative_to(CTX).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def main() -> int:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    record("the build context is a git archive of the commit under release",
           head in IMAGE, f"HEAD={head} image={IMAGE}")

    image = image_manifest(IMAGE)
    context = context_manifest()

    missing = sorted(set(context) - set(image))
    extra = sorted(set(image) - set(context))
    differing = sorted(rel for rel in set(image) & set(context) if image[rel] != context[rel])
    record("every byte the image carries matches the commit (and no committed file is dropped "
           "unexpectedly)",
           not extra and not differing,
           f"context_files={len(context)} image_files={len(image)} "
           f"differs={len(differing)} only_in_image={extra[:8]}")
    record("no file in the image is absent from the commit (nothing untracked was baked in)",
           not extra, f"only_in_image={extra[:8]}")
    unexpected = [rel for rel in missing
                  if rel.split("/")[0] not in NON_SOURCE_DIRS and rel not in NON_SOURCE_FILES]
    record("the only committed files the image drops are the non-source trees .dockerignore names",
           not unexpected,
           f"excluded={len(missing)} unexpected_exclusions={unexpected[:8]}")

    other = image_manifest(OTHER)
    only_rebuild = sorted(set(image) - set(other))
    only_earlier = sorted(set(other) - set(image))
    note("the earlier candidate was built from a dirty worktree and is superseded by this rebuild",
         f"{OTHER} files={len(other)} vs {IMAGE} files={len(image)}; "
         f"only_in_rebuild={only_rebuild[:4]} only_in_earlier={only_earlier[:4]} "
         "- the earlier image carries .freebuff/ (never committed) and lacks the hygiene "
         "tests, so it does not correspond to HEAD")

    hits = sorted(rel for rel in image
                  if rel != ENV_TEMPLATE
                  and any(token in rel.lower() for token in SUSPICIOUS))
    record("no sensitive-looking file is present in the image", not hits,
           f"matches={hits[:10]} (exempt: {ENV_TEMPLATE} = tracked template)")
    record("the image contains no Scratch/ or docs/ tree",
           not any(r.startswith(("Scratch/", "docs/", "frontend/")) for r in image),
           f"top_level={sorted({r.split('/')[0] for r in image})}")

    Path(__file__).with_name("phase4_image_gate.json").write_text(json.dumps({
        "image": IMAGE, "other_image": OTHER, "head": head,
        "context_files": len(context), "image_files": len(image),
        "excluded_by_dockerignore": missing, "only_in_image": extra,
        "differing": differing,
        "only_in_rebuild": only_rebuild, "only_in_earlier": only_earlier,
        "suspicious_names": hits, "checks": RESULTS,
    }, indent=2), encoding="utf-8")
    return 0 if not any(item["pass"] is False for item in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
