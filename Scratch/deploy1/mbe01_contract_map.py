"""Dump the OpenAPI contract as the code actually produces it, and map the frontend's calls onto it.

`openapi.json` in the repository is a hand-committed snapshot (memory: it silently
goes stale), so the M-BE-01 step-6 contract map must be built from the live
`app.openapi()`, not from that file. The frontend's axios client prefixes every
call with `/api/v1`, so a route the backend mounts at the root is invisible to it.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:/CODING/Projects/Proof-Of-Action-Final")
OUT = Path(__file__).with_name("mbe01_live_openapi.json")
PY = REPO / "backend" / ".venv312_repro" / "Scripts" / "python.exe"

DUMP = r"""
import json
from backend.app.main import app
print(json.dumps(app.openapi()))
"""


def dump() -> dict:
    proc = subprocess.run([str(PY), "-c", DUMP], cwd=str(REPO), capture_output=True, text=True,
                          env={**os.environ,
                               "DATABASE_URL":
                               "postgresql+psycopg2://postgres:postgres@localhost:5432/poa_disp_owner"})
    if proc.returncode:
        raise SystemExit(proc.stderr[-2000:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


def frontend_calls() -> list[str]:
    src = subprocess.run(["git", "show", "origin/fullstack:frontend/src/services/api.js"],
                         cwd=str(REPO), capture_output=True, text=True).stdout
    if not src:
        raise SystemExit("could not read the frontend api.js")
    calls = []
    for match in re.finditer(r"""api\.(get|post|patch|put|delete)\(\s*[`'"]([^`'"]+)[`'"]""", src):
        verb, path = match.group(1).upper(), match.group(2)
        path = re.sub(r"\$\{[^}]*\}", "{}", path)
        calls.append(f"{verb} {path}")
    return sorted(set(calls))


def path_matches(pattern: str, call: str) -> bool:
    """Any {param} segment matches any other segment, in either direction."""
    want, got = pattern.split("/"), call.split("/")
    if len(want) != len(got):
        return False
    return all(a == b or a.startswith("{") or b.startswith("{") for a, b in zip(want, got))


def main() -> int:
    spec = dump()
    OUT.write_text(json.dumps(spec, indent=2, sort_keys=True))
    paths = spec["paths"]
    operations = {(method.upper(), path) for path, ops in paths.items() for method in ops}

    def find(method: str, call: str) -> tuple[list[str], list[str]]:
        prefixed, root = [], []
        for _, declared in operations:
            if not path_matches(declared, "/api/v1" + call):
                if path_matches(declared, call):
                    root.append(declared)
                continue
            prefixed.append(declared)
        return sorted(prefixed), sorted(root)

    print(f"live contract: {len(paths)} paths, {len(operations)} operations -> {OUT.name}")
    committed = json.loads((REPO / "openapi.json").read_text())
    print(f"committed snapshot: {len(committed['paths'])} paths")
    print("\nFRONTEND CALL -> BACKEND ROUTE")
    misses, root_only, ok = [], [], []
    reachable: set[str] = set()
    for call in frontend_calls():
        method, path = call.split(" ", 1)
        prefixed, root = find(method, path)
        if prefixed:
            print(f"  OK    {call:<46} -> {', '.join(prefixed)}")
            ok.append(call)
            reachable.update(prefixed)
        elif root:
            print(f"  ROOT  {call:<46} -> {', '.join(root)} (NOT under /api/v1)")
            root_only.append((call, root))
            reachable.update(root)
        else:
            print(f"  MISS  {call:<46} -> no matching operation")
            misses.append(call)
    print(f"\n{len(ok)} matched, {len(root_only)} root-mounted only, {len(misses)} missing")
    print("\nOPERATIONS THE FRONTEND NEVER CALLS:")
    for method, path in sorted(operations):
        if path not in reachable:
            print(f"   {method} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
