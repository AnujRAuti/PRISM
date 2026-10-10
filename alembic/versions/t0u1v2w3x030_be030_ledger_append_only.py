"""BE-030: append-only enforcement + event-type domain CHECK for the audit ledger.

Revision ID: t0u1v2w3x030
Revises: s9t0u1v2w029

Implements the owner decisions D-1 = A (a refusing ``BEFORE ROW`` trigger with a
narrow, audited ``SET LOCAL`` exception hatch) and §11 (an event-type domain
``CHECK``). See ``docs/BE-030 Audit Ledger Feasibility Evidence And Migration
Design.md`` for the measurements behind every design choice here; several of the
task-file's original claims were corrected by that pass, and the corrections are
reflected in this revision's structure.

Why a trigger and not a rule / REVOKE (§6, measured)
    Only a ``BEFORE ROW ... RAISE EXCEPTION`` trigger actually *refuses*: rules
    spelled ``DO INSTEAD NOTHING`` silently swallow the write (the caller keeps
    receiving a success it did not earn) and ``REVOKE`` is inert while the
    application connects as the table owner. A ``FOR EACH ROW`` trigger does NOT
    fire on ``TRUNCATE``; that hole is documented and consciously left open (the
    owner accepts it until a non-owner application role exists), and §7.7 of the
    task bars a ``TRUNCATE`` trigger or any statement that mutates rows as a side
    effect of refusing to mutate them.

Trigger body notes (each is a measured failure mode, §7)
    * ``TG_OP`` and never ``TG_TAG`` — ``TG_TAG`` only exists on *event* triggers
      and a row trigger that references it fails every mutation with
      ``column "tg_tag" does not exist``.
    * Explicit ``ERRCODE = 'insufficient_privilege'`` (SQLSTATE 42501) so the
      application can distinguish a policy refusal from an ordinary SQL error.
    * ``%``-free body: SQLAlchemy's psycopg2 dialect doubles a bare ``%`` in the
      literal it ships (measured §2b), so the message carries no placeholders.
    * The exception hatch is a session-scoped custom GUC,
      ``poa.ledger_mutation_exception``, read with ``missing_ok = true`` so an
      unset hatch *refuses* (default-deny). Only ``SET LOCAL`` is sanctioned: a
      plain ``SET`` leaks the hatch for the whole pooled connection (§2c). Hatch
      use is recorded application-side — the trigger itself must not write (§7.5).

The ``CHECK`` (§11) is generated from ``AUDIT_EVENT_TYPES`` so the model and this
migration cannot diverge; §13 has a test that fails if they ever do. Alembic's
drift comparison cannot see a ``CHECK`` (§2a), so the catalog-pinned test — not
``alembic check`` — is what protects it.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from backend.db.models import AUDIT_EVENT_TYPES

revision: str = "t0u1v2w3x030"
down_revision: Union[str, Sequence[str], None] = "s9t0u1v2w029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "audit_ledger_events"
FUNCTION_NAME = "audit_ledger_refuse_mutation"
TRIGGER_NAME = "trg_audit_ledger_append_only"
CHECK_NAME = "ck_audit_ledger_event_type_domain"
HATCH_GUC = "poa.ledger_mutation_exception"


#: The refusal function, spelled exactly as proven on a disposable clone in the
#: feasibility pass (p2a_install_and_probe.py). Body is ``%``-free by design.
FUNCTION_SQL = f"""
CREATE OR REPLACE FUNCTION public.{FUNCTION_NAME}() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF lower(coalesce(current_setting('{HATCH_GUC}', true), ''))
       IN ('true', 'on', '1') THEN
        -- Sanctioned bypass: pass the operation through unchanged. A BEFORE row
        -- trigger's return value REPLACES the row, so UPDATE must RETURN NEW and
        -- DELETE RETURN OLD; returning OLD on UPDATE silently reverts the write to
        -- the pre-image (measured on the disposable clone).
        IF TG_OP = 'UPDATE' THEN
            RETURN NEW;
        ELSE
            RETURN OLD;
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'append-only enforcement refuses UPDATE on the audit ledger'
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'SET LOCAL {HATCH_GUC} to use the sanctioned path';
    ELSE
        RAISE EXCEPTION 'append-only enforcement refuses DELETE on the audit ledger'
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'SET LOCAL {HATCH_GUC} to use the sanctioned path';
    END IF;
END
$fn$
"""

TRIGGER_SQL = (
    f"CREATE TRIGGER {TRIGGER_NAME} "
    f"BEFORE UPDATE OR DELETE ON public.{TABLE} "
    f"FOR EACH ROW EXECUTE FUNCTION public.{FUNCTION_NAME}()"
)


def _event_type_in_list() -> str:
    """The 94-value IN list, generated from the single source of truth."""
    return ", ".join(f"'{value}'" for value in sorted(AUDIT_EVENT_TYPES))


def _trigger_exists(bind) -> bool:
    return bool(bind.execute(text(
        "SELECT 1 FROM pg_trigger t"
        " JOIN pg_class c ON c.oid = t.tgrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE t.tgname = :name AND c.relname = :table AND n.nspname = 'public'"
        " AND NOT t.tgisinternal"
    ), {"name": TRIGGER_NAME, "table": TABLE}).fetchone())


def _function_exists(bind) -> bool:
    return bool(bind.execute(text(
        "SELECT 1 FROM pg_proc p"
        " JOIN pg_namespace n ON n.oid = p.pronamespace"
        " WHERE p.proname = :name AND n.nspname = 'public'"
    ), {"name": FUNCTION_NAME}).fetchone())


def _check_exists(bind) -> bool:
    return bool(bind.execute(text(
        "SELECT 1 FROM pg_constraint"
        " WHERE conname = :name"
        " AND conrelid = CAST(:table AS regclass)"
    ), {"name": CHECK_NAME, "table": f"public.{TABLE}"}).fetchone())


def _out_of_domain_rows(bind) -> int:
    """Rows whose event_type is NULL or outside the vocabulary (§11.1 precondition)."""
    return int(bind.execute(text(
        f"SELECT count(*) FROM {TABLE}"
        f" WHERE event_type IS NULL OR event_type NOT IN ({_event_type_in_list()})"
    )).scalar())


class EnforcementPreconditionFailed(RuntimeError):
    """Raised when the database is not in the shape this revision expects."""


def upgrade() -> None:
    bind = op.get_bind()

    # §11.1 / §17: re-measure the domain precondition BEFORE any DDL. Out-of-domain
    # rows mean "clean the data so the constraint fits" — exactly what BE-030 forbids
    # — so abort with no DDL rather than add a CHECK that would fail or force a cleanup.
    offenders = _out_of_domain_rows(bind)
    if offenders:
        raise EnforcementPreconditionFailed(
            f"cannot add {CHECK_NAME}: {offenders} audit_ledger_events rows carry an "
            "event_type outside AUDIT_EVENT_TYPES. BE-030 §11.1 forbids cleaning data "
            "to fit the constraint; stop and reconcile as a separate incident.")

    # Idempotence guards: refuse to double-install objects someone may have added by
    # hand, so the round trip is honest rather than silently destructive.
    if _trigger_exists(bind) or _function_exists(bind):
        raise EnforcementPreconditionFailed(
            f"{TRIGGER_NAME}/{FUNCTION_NAME} already present; this revision expects to "
            "create them. Refusing to guess what a hand-fixed database should become.")
    if _check_exists(bind):
        raise EnforcementPreconditionFailed(
            f"{CHECK_NAME} already present; refusing to re-add it.")

    # Order (§11.4): the enforcement trigger first, then the CHECK. ADD CONSTRAINT
    # takes a brief exclusive lock and validates every existing row.
    bind.execute(text(FUNCTION_SQL))
    bind.execute(text(TRIGGER_SQL))
    op.create_check_constraint(
        CHECK_NAME, TABLE, f"event_type IN ({_event_type_in_list()})")


def downgrade() -> None:
    bind = op.get_bind()

    # Reverse order: drop the CHECK, then the trigger, then the function (§7.6).
    if _check_exists(bind):
        op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    if _trigger_exists(bind):
        bind.execute(text(f"DROP TRIGGER {TRIGGER_NAME} ON public.{TABLE}"))
    # CREATE OR REPLACE made the function ours; drop it only if it is still present.
    if _function_exists(bind):
        bind.execute(text(f"DROP FUNCTION public.{FUNCTION_NAME}()"))
