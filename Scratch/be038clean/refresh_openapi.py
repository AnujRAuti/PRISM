"""Refresh the committed OpenAPI contract snapshot from the current app.

The tracked ``openapi.json`` is a manual snapshot; the last commit that touched
it predates BE-032R/BE-037, so it no longer described the deployed surface. This
rewrites it in place using the same formatting the file already uses, and prints
only counts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
sys.path.insert(0, str(REPO))


def main() -> int:
    from backend.app.main import app

    target = REPO / "openapi.json"
    before = json.loads(target.read_text(encoding="utf-8"))
    spec = app.openapi()

    old_ops = {f"{m.upper()} {p}" for p, ms in before.get("paths", {}).items() for m in ms}
    new_ops = {f"{m.upper()} {p}" for p, ms in spec.get("paths", {}).items() for m in ms}
    print(f"operations before={len(old_ops)} after={len(new_ops)}")
    print(f"added:   {sorted(new_ops - old_ops)}")
    print(f"removed: {sorted(old_ops - new_ops)}")

    text = json.dumps(spec, indent=2, sort_keys=False) + "\n"
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {target} ({target.stat().st_size} bytes)")

    reread = json.loads(target.read_text(encoding="utf-8"))
    print(f"round-trip identical to generated spec: {reread == spec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
