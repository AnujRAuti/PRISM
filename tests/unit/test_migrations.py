"""Static verification of the Alembic revision graph (BE-023 §6).

The migration chain is the thing a fresh test database is built from, so a
broken graph does not fail loudly at test time -- it fails as a confusing
collection of missing tables much later. These checks run with no database
connection and assert the graph is what the project claims it is:

* exactly one head (``o5p6q7r8s025``, the BE-025 assignment-scope head),
* a single linear root-to-head path (no multi-parent merge nodes),
* no ``down_revision`` pointing at a revision that does not exist.

Why this parses the source instead of using ``alembic.script.ScriptDirectory``
--------------------------------------------------------------------------
``ScriptDirectory`` would work, but it is an installed-package dependency:
on a machine where Alembic is missing or the repository is checked out
without the venv, the import fails and this check reports a confusing
``ModuleNotFoundError`` instead of the graph problem it exists to catch.

Parsing the revision headers keeps the check hermetic -- no venv, no
database, no environment -- so a broken migration graph is always reported
as a broken migration graph. It reads the same ``revision`` and
``down_revision`` values Alembic itself reads, so it cannot disagree with
Alembic about what the graph is.

One note on the top-level ``alembic/`` directory: it has no ``__init__.py``,
but it does *not* shadow the installed distribution. Python prefers a regular
package over a same-named namespace directory, so ``import alembic`` still
resolves to site-packages once ``pytest.ini`` puts the repo root on
``sys.path``. ``python -m alembic upgrade head`` is unaffected.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

# BE-023 §6: selectable with `-m be023`.
pytestmark = pytest.mark.be023

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"

#: The single expected head. Bumping this is a deliberate act, not an
#: accident: a new migration that is not wired into the chain, or a second
#: head created by a parallel branch merge, must fail here.
#: Bumped by BE-025 (M1 assignment scope/ID matrix, down_revision
#: n4o5p6q7r022), then by BE-026 (three field-operations tables, one additive
#: revision, down_revision o5p6q7r8s025), then by BE-028 (three indexes that
#: were always declared but never created, down_revision p6q7r8s9t026), then by
#: BE-029 (two revisions: archive-and-retire the synthetic identity residue, then the
#: unique username/email indexes it unblocks, down_revision q7r8s9t0u027), then by
#: BE-030 (one linear revision: append-only enforcement trigger + event-type CHECK,
#: down_revision s9t0u1v2w029), then by D2 (one data-only revision: the baseline
#: authorization catalogue seed, down_revision t0u1v2w3x030), each time after
#: confirming `alembic heads` reports exactly one head.
EXPECTED_HEAD = "u1v2w3x4y031"

#: BE-023 revision count at the time this test was written (19), advanced by
#: each milestone that genuinely adds a migration. BE-025 added one: 20.
#: BE-026 adds one: 21. BE-028 adds one (missing indexes, no data changes): 22.
#: BE-029 adds two (residue retirement, then identity uniqueness): 24.
#: BE-030 adds one (append-only enforcement trigger + event-type CHECK): 25.
#: D2 adds one (authorization catalogue seed — data only, no schema change): 26.
EXPECTED_REVISION_COUNT = 26


@dataclass(frozen=True)
class Revision:
    identifier: str
    down: tuple[str, ...]
    filename: str


def _literal(node: ast.AST | None):
    """Evaluate a literal/tuple-of-literals node; return None if not literal."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        parts = []
        for element in node.elts:
            if not isinstance(element, ast.Constant):
                return None
            parts.append(element.value)
        return tuple(parts)
    return None


def _module_revision(path: Path) -> Revision | None:
    """Extract revision / down_revision from one migration module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    identifier = None
    down = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value = node.value
        else:
            continue
        if name == "revision":
            identifier = _literal(value)
        elif name == "down_revision":
            down = _literal(value)
    if identifier is None:
        return None
    if down is None:
        parents: tuple[str, ...] = ()
    elif isinstance(down, tuple):
        parents = down
    else:
        parents = (down,)
    return Revision(identifier=identifier, down=parents, filename=path.name)


def load_revisions() -> list[Revision]:
    """Parse every migration file. Fails loudly on an unparseable header."""
    paths = sorted(VERSIONS_DIR.glob("*.py"))
    assert paths, f"no migration files found under {VERSIONS_DIR}"
    revisions = []
    for path in paths:
        revision = _module_revision(path)
        assert revision is not None, (
            f"{path.name} declares no literal 'revision' identifier; the "
            "revision graph cannot be verified"
        )
        revisions.append(revision)
    return revisions


@pytest.fixture(scope="module")
def revisions() -> list[Revision]:
    return load_revisions()


def test_every_migration_declares_a_literal_revision(revisions):
    """A non-literal revision id silently breaks the chain; refuse to guess."""
    assert all(r.identifier for r in revisions)


def test_revision_count_is_as_expected(revisions):
    assert len(revisions) == EXPECTED_REVISION_COUNT


def test_revision_identifiers_are_unique(revisions):
    seen = [r.identifier for r in revisions]
    duplicates = {i for i in seen if seen.count(i) > 1}
    assert not duplicates, f"duplicate revision identifiers: {sorted(duplicates)}"


def test_down_revisions_all_exist(revisions):
    """A dangling parent means Alembic cannot build the chain at all."""
    known = {r.identifier for r in revisions}
    dangling = {
        r.filename: parent
        for r in revisions
        for parent in r.down
        if parent not in known
    }
    assert not dangling, f"down_revision references unknown revisions: {dangling}"


def test_exactly_one_head(revisions):
    """More than one head means `upgrade head` is ambiguous."""
    parents = {p for r in revisions for p in r.down}
    heads = sorted(r.identifier for r in revisions if r.identifier not in parents)
    assert heads == [EXPECTED_HEAD], (
        f"expected a single head {EXPECTED_HEAD!r}, found {heads}. "
        "A merge may have created a second head, or a new migration may not "
        "be reachable from the chain."
    )


def test_single_root(revisions):
    """A linear history has exactly one revision with no parent."""
    roots = sorted(r.identifier for r in revisions if not r.down)
    assert roots == ["bb4bf0dd8fb7"], f"expected one root, found {roots}"


def test_no_merge_revisions(revisions):
    """BE-023 does not use merge revisions; a tuple down_revision is a smell."""
    merges = {r.filename: r.down for r in revisions if len(r.down) > 1}
    assert not merges, f"merge revisions present: {merges}"


def test_graph_is_fully_reachable_from_the_head(revisions):
    """Every revision must be an ancestor of the head, or it never runs."""
    by_id = {r.identifier: r for r in revisions}
    seen: set[str] = set()
    stack = [EXPECTED_HEAD]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(by_id[current].down)
    orphans = sorted(set(by_id) - seen)
    assert not orphans, (
        f"revisions not reachable from head {EXPECTED_HEAD}: {orphans}. "
        "`alembic upgrade head` would never apply these."
    )
