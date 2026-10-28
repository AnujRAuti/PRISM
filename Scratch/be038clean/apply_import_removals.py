"""Apply the unused-import plan: delete whole statements, rebuild partial ones.

Runs the same analysis as plan_import_removals.py (so a stale edit cannot be
applied by accident) and then rewrites only the import statements themselves:
full removal when none of a statement's bindings survive, otherwise a rebuilt
``from X import ...`` keeping the module path, the surviving aliases and the
original one-per-line style for multi-line statements.

Everything else in each file is left byte-for-byte alone. --dry-run prints the
replacement text without writing.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_import_removals import (  # noqa: E402
    collect_candidates,
    external_refs,
    module_dots,
)


def alias_source(alias: ast.alias) -> str:
    return f"{alias.name} as {alias.asname}" if alias.asname else alias.name


def rebuild(node: ast.Import | ast.ImportFrom, keep: list[ast.alias]) -> str:
    if isinstance(node, ast.Import):
        return f"import {', '.join(alias_source(a) for a in keep)}"
    module = node.module or ""
    level = "." * (node.level or 0)
    names = [alias_source(a) for a in keep]
    joined = ", ".join(names)
    if len(f"from {level}{module} import {joined}") <= 88:
        return f"from {level}{module} import {joined}"
    body = "".join(f"    {name},\n" for name in names)
    return f"from {level}{module} import (\n{body})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", default="", help="restrict to paths containing this substring")
    args = parser.parse_args()

    candidates = collect_candidates()
    blocked = external_refs(candidates)

    touched = 0
    removed_stmts = 0
    rebuilt = 0
    skipped = 0
    for path, unused in sorted(candidates.items()):
        if args.only and args.only not in str(path):
            continue
        dots = module_dots(path)
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        lines = src.splitlines(keepends=True)

        # group the unused aliases by their owning statement
        per_stmt: dict[int, tuple[ast.stmt, list[str]]] = {}
        for alias, (node, _a) in unused.items():
            if (dots, alias) in blocked:
                skipped += 1
                continue
            key = node.lineno
            entry = per_stmt.setdefault(key, (node, []))
            entry[1].append(alias)
        if not per_stmt:
            continue

        # process bottom-up so earlier line numbers stay valid
        for key in sorted(per_stmt, reverse=True):
            node, gone = per_stmt[key]
            keep = [
                a
                for a in node.names
                if (a.asname or a.name.split(".")[0]) not in gone
            ]
            start, end = node.lineno, node.end_lineno
            if keep:
                new = rebuild(node, keep) + "\n"
                rebuilt += 1
            else:
                new = ""
                removed_stmts += 1
            if args.apply:
                lines[start - 1 : end] = [new] if new else []
            else:
                print(f"--- {dots}:{start}-{end}")
                print(f"    drop: {', '.join(gone)}")
                print(f"    new : {new.rstrip() if new else '<statement deleted>'}")
        if args.apply:
            path.write_text("".join(lines), encoding="utf-8", newline="\n")
        touched += 1

    print(
        f"files touched={touched} statements deleted={removed_stmts} "
        f"statements rebuilt={rebuilt} aliases skipped(blocked)={skipped} "
        f"applied={args.apply}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
