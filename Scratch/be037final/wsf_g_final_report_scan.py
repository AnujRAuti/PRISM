"""BE-037 WS-G final scan: the placed report plus every repo file this task touched.

Reuses the shape patterns from ``wsf_g_secret_sweep.py`` and adds the run's
throwaway credential values, because the report is the artifact that leaves the
scratch tree. Prints only paths, pattern names and counts — never a value.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")

_spec = importlib.util.spec_from_file_location("sweep", HERE / "wsf_g_secret_sweep.py")
sweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sweep)

RUN_IDS = ("be037wf7e3", "be037fin7c1f1")
VALUES = [f"{rid}{suffix}"
          for rid in RUN_IDS
          for suffix in ("pw", "pw2", "rtpw", "secret", "admin")]

TARGETS = [
    REPO / "docs" / "BE-037 Final Backend Completion and Acceptance Report.md",
    REPO / ".env.example",
    REPO / "docs" / "storage.md",
    REPO / "tests" / "integration" / "test_storage.py",
    REPO / "tests" / "integration" / "test_be037c_redis_timeout_integration.py",
    REPO / "tests" / "integration" / "test_be037e2_ledger_identity_matrix.py",
]


def main() -> int:
    hits_total = 0
    for path in TARGETS:
        if not path.is_file():
            print(f"MISSING {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        shapes = {n: len(p.findall(text)) for n, p in sweep.PATTERNS.items()}
        shapes = {k: v for k, v in shapes.items() if v}
        values = {v: text.count(v) for v in VALUES if v in text}
        hits_total += sum(shapes.values()) + sum(values.values())
        print(f"{path.relative_to(REPO)}: shapes={shapes or '{}'} values={values or '{}'}")
    print(f"total credential-shaped matches across the placed report and all "
          f"touched repo files: {hits_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
