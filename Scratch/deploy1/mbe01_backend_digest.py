"""Does the candidate image carry exactly this worktree's backend code?

`poa-backend:mbe01-wt1` was built from commit 26a37aa8 plus uncommitted edits in
the working tree, so "the image == the source" needs a measurement, not a label.
This hashes every Python module under `backend/` on both sides and compares the
two sets, so the release evidence can name the number of files proven identical
and list any that are not -- instead of asserting it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
IMAGE = sys.argv[1] if len(sys.argv) > 1 else "poa-backend:mbe01-wt1"


def is_app_module(rel_parts: tuple[str, ...]) -> bool:
    """App code only: the virtualenvs that live under backend/ are not modules."""
    return not any(part.startswith(".") or part == "__pycache__" for part in rel_parts)


def local_digests() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in (REPO / "backend").rglob("*.py"):
        rel = path.relative_to(REPO)
        if not is_app_module(rel.parts):
            continue
        out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def main() -> int:
    proc = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh", IMAGE, "-c",
         "find /app/backend -name '*.py' -not -path '*__pycache__*' "
         "-exec sha256sum {} +"],
        capture_output=True, text=True, timeout=300)
    if proc.returncode:
        raise SystemExit(f"image scan rc={proc.returncode}\n{proc.stderr[:400]}")
    in_image = {}
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            in_image[parts[1].removeprefix("/app/")] = parts[0]

    local = local_digests()
    only_local = sorted(set(local) - set(in_image))
    only_image = sorted(set(in_image) - set(local))
    differing = sorted(rel for rel in set(local) & set(in_image)
                       if local[rel] != in_image[rel])

    print(f"image           : {IMAGE}")
    print(f"modules compared: local={len(local)} in_image={len(in_image)}")
    print(f"identical       : {len(set(local) & set(in_image)) - len(differing)}")
    print(f"differing       : {len(differing)} {differing[:10]}")
    print(f"only in worktree: {len(only_local)} {only_local[:10]}")
    print(f"only in image   : {len(only_image)} {only_image[:10]}")

    verdict = not differing and not only_image and not only_local
    print(f"\nVERDICT: image carries exactly the worktree's backend code = {verdict}")
    Path(__file__).with_name("mbe01_backend_digest.json").write_text(json.dumps({
        "image": IMAGE, "modules_local": len(local), "modules_in_image": len(in_image),
        "identical": len(set(local) & set(in_image)) - len(differing),
        "differing": differing, "only_in_worktree": only_local,
        "only_in_image": only_image, "verdict_exact": verdict,
    }, indent=2))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
