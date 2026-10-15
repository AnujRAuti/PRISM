"""BE-030 §13 pure contract tests (no database).

Two couplings that must not silently drift:

* the model's event-type ``CHECK`` and the migration's ``CHECK`` are both
  generated from ``AUDIT_EVENT_TYPES``; if either stops being generated from it,
  they diverge and the enforced vocabulary no longer matches the Python one;
* the application-side hatch GUC name must equal the one the trigger reads, or
  ``sanctioned_ledger_mutation`` would set a flag the trigger never checks.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from backend.db.models import AUDIT_EVENT_TYPES
from backend.services import audit_ledger as audit_service

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATION = (REPO_ROOT / "alembic" / "versions"
             / "t0u1v2w3x030_be030_ledger_append_only.py")


def _load_migration():
    spec = importlib.util.spec_from_file_location("be030_ledger_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_event_type_vocabulary_is_exactly_96_members():
    assert len(AUDIT_EVENT_TYPES) == 96


def test_model_and_migration_check_share_the_vocabulary():
    migration = _load_migration()
    expected = ", ".join(f"'{value}'" for value in sorted(AUDIT_EVENT_TYPES))

    # Migration side.
    assert migration._event_type_in_list() == expected

    # Model side: pull the generated CHECK's SQL text off the mapped table.
    check = next(
        c for c in
        __import__("backend.db.models", fromlist=["AuditLedgerEvent"])
        .AuditLedgerEvent.__table__.constraints
        if c.name == "ck_audit_ledger_event_type_domain"
    )
    sqltext = str(check.sqltext)
    assert sqltext == f"event_type IN ({expected})"


def test_hatch_guc_matches_the_migration_constant():
    migration = _load_migration()
    assert audit_service.HATCH_GUC == migration.HATCH_GUC == "poa.ledger_mutation_exception"


def test_migration_is_a_single_linear_child_of_the_be029_head():
    migration = _load_migration()
    assert migration.revision == "t0u1v2w3x030"
    assert migration.down_revision == "s9t0u1v2w029"


def test_migration_and_model_agree_on_object_names():
    migration = _load_migration()
    assert migration.CHECK_NAME == "ck_audit_ledger_event_type_domain"
    assert migration.FUNCTION_NAME == "audit_ledger_refuse_mutation"
    assert migration.TRIGGER_NAME == "trg_audit_ledger_append_only"
    # The refusal function body must be % -free (feasibility §2b: SQLAlchemy's
    # psycopg2 dialect doubles a bare %).
    assert "%" not in migration.FUNCTION_SQL
