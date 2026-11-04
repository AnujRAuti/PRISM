"""Read-only runner for diagnostics/audit_gap_diagnostic.sql.

Executes ONLY the sections named below. Every statement is a SELECT;
this script opens no transaction that writes and issues no DDL/DML.
Results are printed verbatim so they can be pasted back verbatim.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Make the repo root importable so "backend.core.config" resolves, regardless
# of the caller's cwd and without requiring PYTHONPATH to be set externally.
# ROOT (not ROOT/"backend") is what must be on sys.path: the package being
# imported is "backend", so it is the root that must be searchable.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.core.config import settings  # noqa: E402

SQL_PATH = ROOT / "diagnostics" / "audit_gap_diagnostic.sql"

# Only these sections execute, per the explicit request.
#
# NOTE: the SQL file declares one "-- SECTION 9." banner whose body holds the
# sub-labelled statements 9a-9e. split_sections() keys on the banner, so the
# whole of Section 9 is requested as "9" -- listing "9a".."9e" here would
# match nothing and silently skip every reset-feasibility query.
WANTED = {"0", "1", "3", "7", "9", "10", "11"}


def _strip_comment_lines(chunk: str) -> str:
    """Drop full-line SQL comments, including '-- ===' banner rules.

    A naive `startswith('--')` is not enough: a section banner can be
    written as '-- SECTION 0. Ledger overview', and the descriptive tail
    of that comment line must be removed too, not just the marker.
    """
    out = []
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("--"):
            continue
        out.append(line)
    return "\n".join(out).strip()


def split_sections(text_body: str) -> dict[str, str]:
    """Split the file into SECTION-keyed chunks of SQL statements."""
    # Consume the WHOLE banner comment line, not just the "SECTION n."
    # prefix. Otherwise the descriptive tail ("Ledger overview / baseline
    # shape") survives as the first line of the chunk and gets glued onto
    # the front of the first SQL statement.
    parts = re.split(r"^--\s*SECTION\s+([0-9a-z]+)\.[^\n]*\n", text_body,
                     flags=re.MULTILINE | re.IGNORECASE)
    sections = {}
    for i in range(1, len(parts), 2):
        key = parts[i].strip()
        body = _strip_comment_lines(parts[i + 1])
        if body:
            sections[key] = body
    return sections


def main() -> int:
    engine = create_engine(settings.database_url)
    sections = split_sections(SQL_PATH.read_text(encoding="utf-8"))
    executed = 0
    with engine.connect() as conn:
        for key in sorted(sections, key=lambda k: (len(k), k)):
            if key not in WANTED:
                continue
            print(f"\n{'='*70}\nSECTION {key}\n{'='*70}")
            for stmt in [s.strip() for s in sections[key].split(";") if s.strip()]:
                result = conn.execute(text(stmt))
                cols = list(result.keys())
                rows = result.fetchall()
                header = " | ".join(cols)
                print(header)
                print("-" * len(header))
                for row in rows:
                    print(" | ".join("NULL" if v is None else str(v) for v in row))
                if not rows:
                    print("(0 rows)")
                print(f"[{len(rows)} row(s)]")
                executed += 1
    engine.dispose()
    print(f"\n[executed {executed} statement(s) across sections "
          f"{sorted(WANTED & set(sections))}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
