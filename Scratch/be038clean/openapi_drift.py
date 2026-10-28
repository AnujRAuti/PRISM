"""Measure whether the committed root openapi.json still matches the app.

Writes the freshly generated spec into scratch and prints a structural diff
summary. Never prints field values, only counts and paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
SCRATCH = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))


def walk(node, prefix=""):
    """Yield (kind, dotted-path) for every operation/schema/param slot."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{prefix}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{prefix}[{index}]")


def main() -> int:
    from backend.app.main import app

    fresh = app.openapi()
    fresh_path = SCRATCH / "openapi_fresh.json"
    fresh_path.write_text(json.dumps(fresh, sort_keys=True, indent=2), encoding="utf-8")

    committed_path = REPO / "openapi.json"
    committed = json.loads(committed_path.read_text(encoding="utf-8"))

    fresh_ops = {
        f"{m.upper()} {p}" for p, ms in fresh.get("paths", {}).items() for m in ms
    }
    old_ops = {
        f"{m.upper()} {p}" for p, ms in committed.get("paths", {}).items() for m in ms
    }
    print(f"committed file: {committed_path} ({committed_path.stat().st_size} bytes)")
    print(f"generated spec: {fresh_path} ({fresh_path.stat().st_size} bytes)")
    print(f"operations committed={len(old_ops)} fresh={len(fresh_ops)}")
    print(f"ops only in committed: {sorted(old_ops - fresh_ops)}")
    print(f"ops only in fresh:     {sorted(fresh_ops - old_ops)}")

    # security requirements per operation, the BE-037 G1 surface
    def sec(ops_spec):
        out = {}
        for path, methods in ops_spec.get("paths", {}).items():
            for method, op in methods.items():
                if isinstance(op, dict):
                    out[f"{method.upper()} {path}"] = bool(op.get("security"))
        return out

    s_old, s_new = sec(committed), sec(fresh)
    changed = sorted(k for k in set(s_old) & set(s_new) if s_old[k] != s_new[k])
    print(f"ops whose security block changed: {len(changed)}")
    for k in changed[:30]:
        print(f"  {k}: committed={s_old[k]} fresh={s_new[k]}")

    n_old = sum(1 for _ in walk(committed))
    n_new = sum(1 for _ in walk(fresh))
    print(f"leaf-node count committed={n_old} fresh={n_new}")
    print(f"byte-identical: {json.dumps(committed, sort_keys=True) == json.dumps(fresh, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
