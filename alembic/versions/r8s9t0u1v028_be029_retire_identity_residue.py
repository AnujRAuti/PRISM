"""BE-029 (1/2): archive, then retire, the synthetic user-identity residue.

Revision ID: r8s9t0u1v028
Revises: q7r8s9t0u027

What this changes
-----------------
``users.username`` / ``users.email`` are declared unique but no revision ever
enforced it (BE-028 B-1), and the only data standing in the way is a synthetic
fixture residue: accounts with ``username='testuser'`` and
``email='test@example.com'``, each owning exactly one project named
``testproj``, which holds exactly one evidence row named ``foo.jpg``. The rows
were written repeatedly by the pre-BE-027 ``test_basic_crud`` fixture, which
could keep "succeeding" only because the schema did not enforce the constraint
it claimed (see ``tests/integration/test_migration_and_crud.py``).

Product-owner ruling (BE-029 OQ-2): these are synthetic test-fixture garbage,
NOT accounts to be merged, so **all** members of each duplicate group are
retired and none is treated as canonical. This migration therefore archives
and removes the residue; the unique indexes are added by the next revision
(``s9t0u1v2w029``) only once the data precondition holds.

Safety properties, in execution order
--------------------------------------
1. ``identity_retirement_archive`` is created first and written first: every
   row is preserved verbatim (``to_jsonb``, original primary key included)
   before anything is deleted, and ``downgrade()`` restores from it literally.
2. The five-check residue predicate is re-evaluated against the live tables
   immediately before the DELETEs. Any candidate that no longer satisfies every
   check aborts the whole migration.
3. The predicate is derived from the catalog: for each foreign key pointing at
   ``users``, ``projects`` or ``evidence`` (composite keys abort as unsupported)
   the referencing rows must themselves be inside the retirement set. Nothing
   is retired that anything else still points at.
4. The audit ledger is read-only here: any ``audit_ledger_events`` row naming a
   candidate as actor, project or resource aborts the migration, and the event
   count is compared before and after. No ledger row is ever written or removed.
5. Retirement order is ``evidence`` -> ``projects`` -> ``users``, the reverse of
   the dependency direction, and each DELETE's row count must equal the number
   of archived rows for that table.
6. Everything runs in one transaction (PostgreSQL DDL and DML are transactional
   and Alembic wraps the revision), so an abort at any step leaves no partial
   state: no archived-but-not-retired rows, no retired-but-not-archived rows.

Deliberately NOT done here
--------------------------
* No user is merged, no foreign key is reassigned, no username or email is
  rewritten (§3/§14/§16: canonical selection is impossible for this set -- every
  member is equally synthetic -- so the owner classified the whole set as
  residue instead).
* ``external_subject`` is neither backfilled nor made NOT NULL (OQ-3, undecided).
* No application-level IntegrityError handling (OQ-5, undecided).
* A database with no residue (a fresh migration from base) is a no-op: the
  archive table is created, the guards pass vacuously, nothing is deleted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "r8s9t0u1v028"
down_revision: Union[str, Sequence[str], None] = "q7r8s9t0u027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ARCHIVE_TABLE = "identity_retirement_archive"

# The residue is defined by these four literals and nothing else. They are
# fixture values written by a test, not real identities.
RESIDUE_USERNAME = "testuser"
RESIDUE_EMAIL = "test@example.com"
RESIDUE_PROJECT_NAME = "testproj"
RESIDUE_EVIDENCE_FILENAME = "foo.jpg"

# Retirement order and the FK direction it respects.
RETIRE_ORDER = ("evidence", "projects", "users")
RESTORE_ORDER = ("users", "projects", "evidence")

NOW = sa.text("now()")

# Each CTE exposes its ids as a column named `id`, so one `IN (SELECT id FROM …)`
# shape works for every check and no value ever has to be bound from Python.
_CAND_USERS = (
    "cand_users AS (SELECT u.id FROM users u WHERE u.username ="
    f" '{RESIDUE_USERNAME}' AND u.email = '{RESIDUE_EMAIL}')")
_CAND_PROJECTS = (
    "cand_projects AS (SELECT p.id FROM projects p WHERE p.owner_id IN"
    " (SELECT id FROM cand_users))")
_CAND_EVIDENCE = (
    "cand_evidence AS (SELECT e.id FROM evidence e WHERE e.project_id IN"
    f" (SELECT id FROM cand_projects) AND e.filename = '{RESIDUE_EVIDENCE_FILENAME}')")
_WITH_CTES = ("WITH " + ", ".join((_CAND_USERS, _CAND_PROJECTS, _CAND_EVIDENCE)) + "\n")

# Source table -> (live table, id CTE). Used for archiving, retiring and
# restoring; the archive is always keyed off the live CTE set.
_SOURCES = {
    "users": ("users", "cand_users"),
    "projects": ("projects", "cand_projects"),
    "evidence": ("evidence", "cand_evidence"),
}

#: Static shape checks. Each must return 0 or the migration aborts. They encode
#: "this row is fixture garbage" rather than "this row looks old", so a real
#: account can never be swept up by accident.
_SHAPE_CHECKS = (
    (
        "owns exactly one project",
        f"{_WITH_CTES} SELECT count(*) FROM cand_users cu WHERE"
        " (SELECT count(*) FROM projects p WHERE p.owner_id = cu.id) <> 1",
    ),
    (
        "that project is named testproj",
        f"{_WITH_CTES} SELECT count(*) FROM cand_projects cp WHERE NOT EXISTS"
        f" (SELECT 1 FROM projects p WHERE p.id = cp.id AND p.name ="
        f" '{RESIDUE_PROJECT_NAME}')",
    ),
    (
        "every candidate project holds evidence",
        f"{_WITH_CTES} SELECT count(*) FROM cand_projects cp WHERE"
        " (SELECT count(*) FROM evidence e WHERE e.project_id = cp.id) < 1",
    ),
    (
        "every child of a candidate project is foo.jpg",
        f"{_WITH_CTES} SELECT count(*) FROM evidence e WHERE e.project_id IN"
        f" (SELECT id FROM cand_projects) AND e.filename <>"
        f" '{RESIDUE_EVIDENCE_FILENAME}'",
    ),
    (
        "no audit ledger involvement (actor, project or resource)",
        f"{_WITH_CTES} SELECT count(*) FROM audit_ledger_events l WHERE"
        " l.actor_id IN (SELECT id FROM cand_users)"
        " OR l.project_id IN (SELECT id FROM cand_projects)"
        " OR l.resource_id IN (SELECT id FROM cand_users UNION"
        "                     SELECT id FROM cand_projects UNION"
        "                     SELECT id FROM cand_evidence)",
    ),
)

# Foreign keys enumerated from the catalog. A reference from one retirement-set
# table to another is expected (projects.owner_id, evidence.project_id) and is
# handled by the retirement order; every other reference must be empty.
_EXCLUDED_FK_REFS = {
    ("projects", "owner_id"),      # retired with its owner, last in RESTORE order
    ("evidence", "project_id"),    # retired first
}

_FK_COLUMNS = """
SELECT cl.relname AS table_name, a.attname AS column_name,
       array_length(c.conkey, 1) AS arity
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f' AND ns.nspname = 'public'
  AND c.confrelid = {ref}::regclass
ORDER BY 1, 2
"""


class RetirementAborted(RuntimeError):
    """Raised when a precondition is not met. The revision is transactional,
    so raising aborts the upgrade with no database change at all."""


def _count(bind, sql: str) -> int:
    value = bind.execute(text(sql)).scalar()
    if value is None:
        raise RetirementAborted(f"guard query returned no row: {sql.strip()[:80]}")
    return int(value)


def _candidate_counts(bind) -> dict:
    return {
        "users": _count(bind, f"{_WITH_CTES} SELECT count(*) FROM cand_users"),
        "projects": _count(bind, f"{_WITH_CTES} SELECT count(*) FROM cand_projects"),
        "evidence": _count(bind, f"{_WITH_CTES} SELECT count(*) FROM cand_evidence"),
    }


def _reference_checks(bind) -> list[tuple[str, int]]:
    """Rows outside the retirement set that still point at it.

    Driven by ``pg_constraint`` rather than a hand-written list, so a foreign
    key added by a later migration is covered here automatically. A composite
    key cannot be tested column-by-column, so it aborts instead of silently
    passing a partial match.
    """
    offenders: list[tuple[str, int]] = []
    for source_table, (ref_table, cte) in _SOURCES.items():
        rows = bind.execute(
            text(_FK_COLUMNS.format(ref=f"'{ref_table}'"))).fetchall()
        for row in rows:
            if row.arity is None or int(row.arity) > 1:
                raise RetirementAborted(
                    f"unsupported composite foreign key "
                    f"{row.table_name}.{row.column_name} -> {ref_table}; the "
                    "residue predicate cannot evaluate it column-by-column")
            if (row.table_name, row.column_name) in _EXCLUDED_FK_REFS:
                continue
            sql = (
                f"{_WITH_CTES} SELECT count(*) FROM \"{row.table_name}\" t"
                f" WHERE t.\"{row.column_name}\" IN (SELECT id FROM {cte})")
            count = _count(bind, sql)
            if count:
                offenders.append(
                    (f"{source_table}: {row.table_name}.{row.column_name}", count))
    return offenders


def _run_residue_predicate(bind, counts: dict, stage: str) -> None:
    """Evaluate the full predicate and abort on the first failing check.

    Called twice: once before archiving (so a blocked database never gets as far
    as writing) and once immediately before the DELETEs, per BE-029 §5/"re-run
    the residue predicate immediately before retirement".
    """
    problems: list[str] = []

    if counts["users"] != counts["projects"]:
        problems.append(
            f"candidate users ({counts['users']}) and their projects "
            f"({counts['projects']}) differ in count")
    if counts["users"] and not counts["evidence"]:
        problems.append("candidates own projects but no foo.jpg evidence")

    for description, sql in _SHAPE_CHECKS:
        failures = _count(bind, sql)
        if failures:
            problems.append(f"{description}: {failures} violating row(s)")

    for description, count in _reference_checks(bind):
        problems.append(f"non-retirement reference into the set: {description} = {count}")

    if problems:
        raise RetirementAborted(
            f"BE-029 identity residue predicate FAILED at the {stage} stage; "
            "nothing has been retired. Findings:\n  - " + "\n  - ".join(problems))


def _ledger_events(bind) -> int:
    return _count(bind, "SELECT count(*) FROM audit_ledger_events")


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        ARCHIVE_TABLE,
        sa.Column("source_table", sa.String(length=32), nullable=False),
        sa.Column("source_id", UUID(as_uuid=False), nullable=False),
        sa.Column("row_json", JSONB, nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), server_default=NOW,
                  nullable=False),
        sa.CheckConstraint(
            "source_table IN ('users', 'projects', 'evidence')",
            name="ck_retirement_archive_source_table"),
        sa.PrimaryKeyConstraint("source_table", "source_id"),
    )

    counts = _candidate_counts(bind)
    if not counts["users"]:
        return  # Nothing to retire (e.g. a database migrated from base).

    # Stage 1: prove the candidates are residue before writing anything.
    _run_residue_predicate(bind, counts, stage="pre-archive")

    ledger_before = _ledger_events(bind)

    # Stage 2: archive-before-retire. `to_jsonb(t)` keeps the original primary
    # key and every column value, which is what makes downgrade() a literal
    # restore instead of a reconstruction.
    for source_table in RETIRE_ORDER:
        live_table, cte = _SOURCES[source_table]
        bind.execute(text(
            f"{_WITH_CTES} INSERT INTO {ARCHIVE_TABLE}"
            f" (source_table, source_id, row_json)"
            f" SELECT '{source_table}', t.id, to_jsonb(t) FROM {live_table} t"
            f" WHERE t.id IN (SELECT id FROM {cte})"))

    archived = {
        source_table: _count(
            bind, f"SELECT count(*) FROM {ARCHIVE_TABLE}"
                  f" WHERE source_table = '{source_table}'")
        for source_table in RETIRE_ORDER
    }
    for source_table in RETIRE_ORDER:
        if archived[source_table] != counts[source_table]:
            raise RetirementAborted(
                f"BE-029 archive incomplete for {source_table}: archived "
                f"{archived[source_table]}, predicate counted "
                f"{counts[source_table]}. Aborting before any deletion.")

    # Stage 3: re-run the predicate immediately before retirement, against the
    # live tables again. A row inserted concurrently, or a reference that
    # appeared since stage 1, aborts here rather than deleting data.
    _run_residue_predicate(bind, _candidate_counts(bind), stage="pre-retirement")

    # Stage 4: retire in evidence -> projects -> users order, keyed strictly on
    # what was archived, and require the row counts to match exactly.
    for source_table in RETIRE_ORDER:
        live_table = _SOURCES[source_table][0]
        result = bind.execute(text(
            f"DELETE FROM {live_table} WHERE id IN"
            f" (SELECT source_id FROM {ARCHIVE_TABLE}"
            f" WHERE source_table = '{source_table}')"))
        deleted = result.rowcount if result.rowcount is not None else -1
        if deleted != archived[source_table]:
            raise RetirementAborted(
                f"BE-029 retired {deleted} {live_table} rows but archived "
                f"{archived[source_table]}; aborting so nothing is lost.")

    # Stage 5: §6 verification, in-database.
    remaining = _count(bind, f"{_WITH_CTES} SELECT count(*) FROM cand_users")
    if remaining:
        raise RetirementAborted(
            f"BE-029 retirement left {remaining} residue user row(s) behind")
    for column in ("username", "email"):
        groups = _count(
            bind, f"SELECT count(*) FROM (SELECT {column} FROM users"
                  f" GROUP BY {column} HAVING count(*) > 1) d")
        if groups:
            raise RetirementAborted(
                f"BE-029 retirement left {groups} duplicate {column} group(s)")
    ledger_after = _ledger_events(bind)
    if ledger_after != ledger_before:
        raise RetirementAborted(
            f"BE-029 does not write the audit ledger, so its event count cannot"
            f" move: {ledger_before} before, {ledger_after} after. Another"
            " process appended events while this revision ran -- stop the API"
            " and workers, then run the migration again.")


def downgrade() -> None:
    """Restore every archived row literally, then drop the archive."""
    bind = op.get_bind()

    # FK-safe direction: users exist before the projects that reference them,
    # projects before the evidence that references them.
    for source_table in RESTORE_ORDER:
        live_table = _SOURCES[source_table][0]
        archived = _count(
            bind, f"SELECT count(*) FROM {ARCHIVE_TABLE}"
                  f" WHERE source_table = '{source_table}'")
        if not archived:
            continue
        bind.execute(text(
            f"INSERT INTO {live_table}"
            f" SELECT (r).* FROM (SELECT jsonb_populate_record(NULL::{live_table},"
            f" a.row_json) AS r FROM {ARCHIVE_TABLE} a"
            f" WHERE a.source_table = '{source_table}') s"))
        restored = _count(
            bind, f"SELECT count(*) FROM {live_table} t WHERE t.id IN"
                  f" (SELECT source_id FROM {ARCHIVE_TABLE}"
                  f" WHERE source_table = '{source_table}')")
        if restored != archived:
            raise RetirementAborted(
                f"BE-029 downgrade restored {restored} of {archived} archived "
                f"{live_table} rows; keeping the archive intact so no snapshot "
                "is lost")

    for source_table in RETIRE_ORDER:
        bind.execute(text(
            f"DELETE FROM {ARCHIVE_TABLE} WHERE source_table = '{source_table}'"))
    leftover = _count(bind, f"SELECT count(*) FROM {ARCHIVE_TABLE}")
    if leftover:
        raise RetirementAborted(
            f"BE-029 downgrade would drop {ARCHIVE_TABLE} while {leftover}"
            " snapshot row(s) remain unrestored")
    op.drop_table(ARCHIVE_TABLE)
