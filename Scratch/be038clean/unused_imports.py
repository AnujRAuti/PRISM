"""Unused-import scan over backend/ using the stdlib AST only.

No linter is installed in the project venv, and installing one would change
dependencies, so this does the narrow job by hand: for every module, collect the
names it imports at module level and check whether each name is ever referenced
anywhere else in that file (loads, attribute roots, annotations, decorator
arguments, __all__ entries, docstring-free string refs excluded).

Results are reported per file with line numbers; nothing is edited here.
Importers that re-export (``__init__.py``) and lines carrying a ``noqa`` comment
are reported separately, because removing those breaks the public surface.
"""

from __future__ import annotations

import ast
import os
import re
from collections import defaultdict
from pathlib import Path

REPO = Path("D:/CODING/Projects/Proof-Of-Action-Final")
ROOT = REPO / "backend"
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


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
            if id(node) in docstrings:
                continue
            # string annotations and __all__ entries both reference by token
            names.update(IDENT.findall(node.value))
    return names


def main() -> None:
    unused = defaultdict(list)
    reexport = defaultdict(list)
    noqa = defaultdict(list)
    modules = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "__")) and d != "node_modules")
        for name in sorted(filenames):
            if name.endswith(".py"):
                modules.append(Path(dirpath) / name)
    for path in modules:
        src = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            print(f"PARSE FAIL {path}: {exc}")
            continue
        lines = src.splitlines()
        imported: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound = alias.asname or alias.name.split(".")[0]
                    imported.append((node.lineno, bound))
        refs = referenced_names(tree)
        imported_lines = {lineno for lineno, _ in imported}
        for lineno, bound in imported:
            if bound in refs:
                continue
            text = lines[lineno - 1]
            rel = str(path.relative_to(REPO))
            if "noqa" in text:
                noqa[rel].append((lineno, bound))
            elif path.name == "__init__.py":
                reexport[rel].append((lineno, bound))
            else:
                unused[rel].append((lineno, bound))
        # imports whose statement line is itself referenced by other aliases on
        # the same line are handled above per-alias, nothing to do here
        del imported_lines

    total = sum(len(v) for v in unused.values())
    print(f"scanned {len(modules)} modules under backend/")
    print(f"genuinely unused imports (non-__init__, no noqa): {total} in {len(unused)} files")
    for rel, hits in sorted(unused.items()):
        print(f"  {rel}: {', '.join(f'{n}:{name}' for n, name in hits)}")
    print(f"\n__init__.py re-export candidates (do NOT auto-delete): "
          f"{sum(len(v) for v in reexport.values())} in {len(reexport)} files")
    for rel, hits in sorted(reexport.items()):
        print(f"  {rel}: {', '.join(f'{n}:{name}' for n, name in hits)}")
    print(f"\nnoqa-marked imports (intentional): {sum(len(v) for v in noqa.values())} in {len(noqa)} files")
    for rel, hits in sorted(noqa.items()):
        print(f"  {rel}: {', '.join(f'{n}:{name}' for n, name in hits)}")


if __name__ == "__main__":
    main()
