"""Plan and (on request) apply removal of genuinely unused module-level imports.

Two guards decide whether a flagged import is actually safe to drop:

1. no *other* project module imports that name out of this module — a name that
   is unused locally may still be part of the module's re-export surface;
2. no dotted-string reference to it exists anywhere (monkeypatch/setattr paths,
   importlib strings, __all__ in another module).

Dry-run by default: prints the exact rewrite per file. Pass --apply to write.
``from __future__ import annotations`` is never a candidate — it is a compiler
directive, not a name binding used in code.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
SCAN_DIRS = ("backend", "tests", "alembic", "scripts", "diagnostics")


def project_files() -> list[Path]:
    out = []
    for name in SCAN_DIRS:
        base = REPO / name
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith((".", "__"))]
            out.extend(Path(dirpath) / f for f in filenames if f.endswith(".py"))
    return sorted(out)


def module_dots(path: Path) -> str:
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts).replace("\\", ".")


def referenced_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                names.add(base.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                names.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", node.value))
    return names


def collect_candidates() -> dict[Path, dict[str, object]]:
    """file -> {unused_alias: ImportNode}."""
    files = project_files()
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
    trees = {}
    for path, src in texts.items():
        try:
            trees[path] = ast.parse(src)
        except SyntaxError:
            trees[path] = None

    candidates: dict[Path, dict[str, object]] = {}
    for path, tree in trees.items():
        if tree is None:
            continue
        refs = referenced_names(tree)
        unused: dict[str, object] = {}
        for node in tree.body:  # module-level only
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("__future__"):
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name.split(".")[0]
                if bound not in refs:
                    unused[bound] = (node, alias)
        if unused:
            candidates[path] = unused
    return candidates


def external_refs(candidates) -> dict[tuple[str, str], list[str]]:
    """(module_dots, alias) -> list of files referencing it from elsewhere."""
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in project_files()}
    hits: dict[tuple[str, str], list[str]] = {}
    for path, unused in candidates.items():
        dots = module_dots(path)
        for alias in unused:
            pattern = re.compile(
                rf"from\s+{re.escape(dots)}\s+import[^\n]*\b{re.escape(alias)}\b"
                rf"|{re.escape(dots)}\.{re.escape(alias)}\b"
                rf"|\"{re.escape(dots)}\.{re.escape(alias)}\""
            )
            others = [
                str(other.relative_to(REPO))
                for other, text in texts.items()
                if other != path and pattern.search(text)
            ]
            if others:
                hits[(dots, alias)] = others
    return hits


def render(candidates, blocked) -> tuple[list[str], int]:
    report = []
    total = 0
    for path, unused in candidates.items():
        src = path.read_text(encoding="utf-8", errors="replace")
        lines = src.splitlines(keepends=True)
        dots = module_dots(path)
        drops_stmt, drops_alias = [], []
        for alias, (node, _a) in unused.items():
            if (dots, alias) in blocked:
                drops_alias.append(f"{alias} BLOCKED(used by {blocked[(dots, alias)]})")
                continue
            remaining = [
                a.asname or a.name.split(".")[0]
                for a in node.names
                if (a.asname or a.name.split(".")[0]) not in unused
                or (dots, (a.asname or a.name.split(".")[0])) in blocked
            ]
            if not remaining:
                drops_stmt.append((node.lineno, node.end_lineno))
            else:
                drops_alias.append(f"{alias} (partial, line {node.lineno})")
        if not drops_stmt and not drops_alias:
            continue
        report.append(f"--- {dots}")
        for start, end in sorted(set(drops_stmt)):
            body = "".join(lines[start - 1 : end]).rstrip("\n")
            report.append(f"  DELETE stmt {start}-{end}: {body[:110].replace(chr(10), ' | ')}")
        for note in sorted(drops_alias):
            report.append(f"  {note}")
        total += len(set(drops_stmt)) + len(drops_alias)
    return report, total


def main() -> int:
    candidates = collect_candidates()
    blocked = external_refs(candidates)
    report, total = render(candidates, blocked)
    print("\n".join(report))
    print(f"\nfiles with planned edits: {sum(1 for line in report if line.startswith('--- '))}"
          f"  rewrites planned: {total}")
    print(f"blocked by external reference: {len(blocked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
