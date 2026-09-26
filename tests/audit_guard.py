"""Static guard against destructive audit-ledger operations (BE-023 §4, §14).

The audit ledger is append-only and tamper-evident. Sequence numbers are
allocated in Python as ``max(sequence_number) + 1`` and are never reused,
so a row deleted from anywhere in the chain leaves a permanent gap that
``verify_chain()`` can never satisfy. Two integration cleanups used to do
exactly that, which produced seven historical gaps spanning 36 sequence
numbers.

This module scans the test tree for destructive operations against
``AuditLedgerEvent`` / ``audit_ledger_events``. It is deliberately
separate from the test that exercises it so the guard can be regression
tested against synthetic sources.

Distinguishing destructive cleanup from legitimate tamper testing
----------------------------------------------------------------
BE-023 §4 permits controlled ``UPDATE`` of ledger rows inside tests that
explicitly guarantee rollback -- that is how tamper detection is verified.
It forbids permanently destroying history. So:

* DELETE / TRUNCATE are always violations. There is no legitimate reason
  for a test to remove a ledger row.
* UPDATE is a violation *unless* the statement is lexically part of a
  rollback-guarded block. ``test_tamper_detection_with_rollback`` and
  ``test_broken_link_detection_with_rollback`` are the legitimate cases
  and must not be flagged.
* UPDATE via ``.update({...})`` (a SQLAlchemy bulk UPDATE) is treated as
  destructive, because bulk updates are used for cleanup sweeps and are
  not the controlled single-row pattern the tamper tests use.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

# Table/model identifiers that mean "the audit ledger".
_MODEL_NAME = "AuditLedgerEvent"
_TABLE_NAME = "audit_ledger_events"

# Test functions permitted to UPDATE ledger rows, because they are the
# controlled tamper-detection tests and guarantee rollback.
_ALLOWED_UPDATE_TESTS = frozenset({
    "test_tamper_detection_with_rollback",
    "test_broken_link_detection_with_rollback",
})


@dataclass(frozen=True)
class Violation:
    """A single destructive audit-ledger operation found in the test tree."""

    file: str
    line: int
    kind: str          # orm_delete | raw_delete | truncate | bulk_update | raw_update
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} [{self.kind}] {self.detail}"


def _normalise(text: str) -> str:
    """Collapse whitespace so multi-line SQL strings still match."""
    return " ".join(text.lower().split())


def _is_ledger_reference(node: ast.AST) -> bool:
    """True if the expression mentions the audit ledger model or table."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == _MODEL_NAME:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == _MODEL_NAME:
            return True
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if _TABLE_NAME in sub.value.lower():
                return True
    return False


def _parent_chain(parents: dict[int, ast.AST], node: ast.AST) -> list[ast.AST]:
    """Outermost-last list of every enclosing node, innermost first."""
    chain: list[ast.AST] = []
    cur: ast.AST | None = node
    while cur is not None:
        chain.append(cur)
        cur = parents.get(id(cur))
    return chain


def _enclosing_test_name(parents: dict[int, ast.AST], node: ast.AST) -> str | None:
    """Nearest enclosing function name, used for the tamper-test allowlist."""
    for ancestor in _parent_chain(parents, node):
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ancestor.name
    return None


def _function_guarantees_rollback(fn: ast.AST) -> bool:
    """True if the function body contains an explicit rollback() call.

    A tamper test that mutates a ledger row is only legitimate if it can
    undo the mutation. Requiring a real ``rollback()`` call (rather than
    trusting the test name) is what makes the allowlist meaningful.
    """
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Attribute) and func.attr == "rollback":
                return True
            if isinstance(func, ast.Name) and func.id == "rollback":
                return True
    return False


def scan_source(source: str, filename: str) -> list[Violation]:
    """Scan one Python source string; return every violation found."""
    violations: list[Violation] = []
    tree = ast.parse(source)

    # Track the enclosing chain so a call knows which test it sits in.
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    for node in ast.walk(tree):
        # --- ORM: session.query(AuditLedgerEvent)...delete()
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "delete"
                and _is_ledger_reference(node.func.value)):
            violations.append(Violation(
                filename, node.lineno, "orm_delete",
                "ORM delete against the audit ledger",
            ))
            continue

        # --- ORM bulk update: query(AuditLedgerEvent).update({...})
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"
                and _is_ledger_reference(node.func.value)):
            enclosing = _enclosing_test_name(parents, node)
            if enclosing in _ALLOWED_UPDATE_TESTS and _function_guarantees_rollback(
                _find_enclosing_function(parents, node)
            ):
                continue
            violations.append(Violation(
                filename, node.lineno, "bulk_update",
                "bulk update against the audit ledger",
            ))
            continue

        # --- Raw SQL strings.
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _TABLE_NAME not in node.value.lower():
                continue
            flat = _normalise(node.value)
            is_docstring = _is_docstring(node, parents)
            if is_docstring:
                # A docstring may legitimately *describe* the pattern it
                # forbids; §14 requires the guard not be fooled by these.
                continue
            if re.search(r"\btruncate\b[^;]*" + _TABLE_NAME, flat):
                violations.append(Violation(
                    filename, node.lineno, "truncate",
                    "TRUNCATE against the audit ledger",
                ))
            elif re.search(r"\bdelete\s+from\s+" + _TABLE_NAME, flat):
                violations.append(Violation(
                    filename, node.lineno, "raw_delete",
                    "raw SQL DELETE against the audit ledger",
                ))
            elif re.search(r"\bupdate\s+" + _TABLE_NAME, flat):
                enclosing = _enclosing_test_name(parents, node)
                fn = _find_enclosing_function(parents, node)
                if enclosing in _ALLOWED_UPDATE_TESTS and _function_guarantees_rollback(fn):
                    continue
                violations.append(Violation(
                    filename, node.lineno, "raw_update",
                    "raw SQL UPDATE against the audit ledger",
                ))

    return violations


def _find_enclosing_function(parents: dict[int, ast.AST], node: ast.AST) -> ast.AST:
    """Walk up the parent chain to the nearest function definition."""
    cur = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = parents.get(id(cur))
    return ast.Module(body=[], type_ignores=[])


def _is_docstring(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    """True if the string constant is a docstring rather than executed code.

    A string is a docstring when it is the first statement of a module,
    class or function body. The constant is wrapped in an ``ast.Expr``, so
    the direct parent is never the definition itself -- that is why the
    ``ast.Expr`` layer has to be peeled off before comparing positions.
    """
    stmt = node
    parent = parents.get(id(stmt))
    if isinstance(parent, ast.Expr):
        stmt = parent
        parent = parents.get(id(stmt))
    if parent is None:
        return False
    if not isinstance(parent, (ast.Module, ast.ClassDef,
                               ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    body = getattr(parent, "body", None)
    if not body:
        return False
    return body[0] is stmt


def scan_test_tree(tests_root: Path, skip_files: frozenset[str] = frozenset()) -> list[Violation]:
    """Scan every ``*.py`` under ``tests_root`` and collect violations.

    ``skip_files`` names files to exclude -- used so the guard's own test
    file, which necessarily contains example violating code as fixtures,
    does not flag itself.
    """
    violations: list[Violation] = []
    for path in sorted(Path(tests_root).rglob("*.py")):
        if path.name in skip_files:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            violations.extend(scan_source(source, path.name))
        except SyntaxError:
            # A file that does not parse cannot hide a delete; the test
            # suite itself will surface the syntax error.
            continue
    return violations
