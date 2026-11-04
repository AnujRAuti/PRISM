"""Regression tests for the audit-ledger static guard (BE-023 §14).

The guard is the thing standing between a future test author and
permanent corruption of append-only audit history. A guard that silently
stops working is worse than no guard, so its behaviour is pinned here
against synthetic sources -- including the cases it must NOT flag, so it
cannot be "fixed" into uselessness by over-blocking.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.audit_guard import scan_source, scan_test_tree  # noqa: E402

# BE-023 §14: this module is part of the verification-hardening suite, so it is
# selectable with `-m be023`. Applied at module level to avoid touching the
# signature or semantics of any individual test.
pytestmark = pytest.mark.be023


def kinds(violations) -> set[str]:
    return {v.kind for v in violations}


# --------------------------------------------------------------------------
# Must be DETECTED
# --------------------------------------------------------------------------

def test_detects_orm_delete():
    src = """
from backend.db.models import AuditLedgerEvent
def cleanup(session, ids):
    session.query(AuditLedgerEvent).filter(
        AuditLedgerEvent.resource_id.in_(ids)
    ).delete()
"""
    assert "orm_delete" in kinds(scan_source(src, "t.py"))


def test_detects_orm_delete_in_governance_shape():
    """The exact predicate that caused the historical contamination."""
    src = """
from backend.db.models import AuditLedgerEvent
def cleanup(session, all_ids, user_ids, project_ids):
    session.query(AuditLedgerEvent).filter(
        AuditLedgerEvent.resource_id.in_(all_ids)
        | AuditLedgerEvent.actor_id.in_(user_ids)
        | AuditLedgerEvent.project_id.in_(project_ids)
    ).delete(synchronize_session=False)
"""
    assert "orm_delete" in kinds(scan_source(src, "t.py"))


def test_detects_core_construct_delete():
    """The spelling that used to slip past the guard (BE-029 Phase G).

    A test written as ``delete(AuditLedgerEvent).where(...)`` removes ledger
    rows exactly as surely as ``query(...).delete()``, but matched none of the
    original string-and-method patterns, so the violating test passed the
    guard. Coverage must not depend on which spelling an author picked.
    """
    src = """
from sqlalchemy import delete
from backend.db.models import AuditLedgerEvent
def probe(session, row):
    session.execute(delete(AuditLedgerEvent).where(
        AuditLedgerEvent.id == row.id))
"""
    assert "core_delete" in kinds(scan_source(src, "t.py"))


def test_detects_module_qualified_core_delete():
    src = """
import sqlalchemy as sa
from backend.db.models import AuditLedgerEvent
def probe(session, row):
    session.execute(sa.delete(AuditLedgerEvent))
"""
    assert "core_delete" in kinds(scan_source(src, "t.py"))


def test_core_delete_has_no_rollback_exception():
    """Rolling back does not license removing a row: DELETE is unconditional."""
    src = """
from sqlalchemy import delete
from backend.db.models import AuditLedgerEvent
def test_tamper_detection_with_rollback(session, row):
    session.execute(delete(AuditLedgerEvent).where(
        AuditLedgerEvent.id == row.id))
    session.rollback()
"""
    assert "core_delete" in kinds(scan_source(src, "t.py"))


def test_detects_core_construct_update_outside_a_guarded_test():
    src = """
from sqlalchemy import update
from backend.db.models import AuditLedgerEvent
def sweep(session):
    session.execute(update(AuditLedgerEvent).values(action='rewritten'))
"""
    assert "core_update" in kinds(scan_source(src, "t.py"))


def test_core_delete_on_an_unrelated_table_is_not_flagged():
    """The guard must not over-block: an unrelated table is not the ledger."""
    src = """
from sqlalchemy import delete
from backend.db.models import Project
def cleanup(session):
    session.execute(delete(Project))
"""
    assert scan_source(src, "t.py") == []


def test_detects_raw_sql_delete():
    src = """
def cleanup(session):
    session.execute("DELETE FROM audit_ledger_events")
"""
    assert "raw_delete" in kinds(scan_source(src, "t.py"))


def test_detects_raw_sql_delete_lowercase_and_spacing():
    src = """
def cleanup(session):
    session.execute("delete   from    audit_ledger_events")
"""
    assert "raw_delete" in kinds(scan_source(src, "t.py"))


def test_detects_truncate():
    src = """
def cleanup(session):
    session.execute("TRUNCATE TABLE audit_ledger_events")
"""
    assert "truncate" in kinds(scan_source(src, "t.py"))


def test_detects_truncate_lowercase():
    src = """
def cleanup(session):
    session.execute("truncate audit_ledger_events restart identity")
"""
    assert "truncate" in kinds(scan_source(src, "t.py"))


def test_detects_bulk_update_as_destructive():
    """Bulk .update() is a cleanup sweep, not controlled tamper testing."""
    src = """
from backend.db.models import AuditLedgerEvent
def cleanup(session, ids):
    session.query(AuditLedgerEvent).filter(
        AuditLedgerEvent.resource_id.in_(ids)
    ).update({AuditLedgerEvent.payload: {}})
"""
    assert "bulk_update" in kinds(scan_source(src, "t.py"))


def test_detects_raw_update_outside_tamper_test():
    src = """
def cleanup(session):
    session.execute("UPDATE audit_ledger_events SET payload = '{}'")
"""
    assert "raw_update" in kinds(scan_source(src, "t.py"))


def test_detects_orm_delete_in_multiline_string_sql():
    src = '''
def cleanup(session):
    session.execute("""
        DELETE FROM audit_ledger_events
        WHERE resource_id = ANY(ids)
    """)
'''
    assert "raw_delete" in kinds(scan_source(src, "t.py"))


# --------------------------------------------------------------------------
# Must NOT be flagged
# --------------------------------------------------------------------------

def test_does_not_flag_legitimate_tamper_update_with_rollback():
    """The real tamper test shape: UPDATE + explicit rollback. Allowed."""
    src = """
from sqlalchemy import text
def test_tamper_detection_with_rollback():
    session = get_session()
    try:
        session.execute(
            text("UPDATE audit_ledger_events SET payload = :p WHERE id = :i"),
            {"p": '{"probe": "EVIL"}', "i": row_id},
        )
        assert verify(session)["valid"] is False
    finally:
        session.rollback()
        session.close()
"""
    assert scan_source(src, "t.py") == []


def test_does_not_flag_broken_link_tamper_test():
    src = """
from sqlalchemy import text
def test_broken_link_detection_with_rollback():
    session = get_session()
    try:
        session.execute(
            text("UPDATE audit_ledger_events SET previous_hash = :p WHERE id = :i"),
            {"p": "tampered", "i": second_id},
        )
        assert verify(session)["valid"] is False
    finally:
        session.rollback()
        session.close()
"""
    assert scan_source(src, "t.py") == []


def test_does_not_flag_comment_containing_example_code():
    """§14: the guard must not be fooled by comments."""
    src = """
def cleanup(session):
    # NEVER do this: session.query(AuditLedgerEvent).delete()
    # nor: DELETE FROM audit_ledger_events
    # nor: TRUNCATE audit_ledger_events
    pass
"""
    assert scan_source(src, "t.py") == []


def test_does_not_flag_docstring_containing_example_code():
    """§14: docstrings describing the forbidden pattern are not violations."""
    src = '''
def explain():
    """Never run DELETE FROM audit_ledger_events or TRUNCATE audit_ledger_events.

    The ledger is append-only; cleanup must not remove rows.
    """
    return "ok"
'''
    assert scan_source(src, "t.py") == []


def test_does_not_flag_module_docstring_mentioning_delete():
    src = '''
"""Test helper. It would be wrong to DELETE FROM audit_ledger_events here."""
def helper():
    return 1
'''
    assert scan_source(src, "t.py") == []


def test_does_not_flag_unrelated_table_deletes():
    src = """
from backend.db.models import Evidence, User
def cleanup(session, ids):
    session.query(Evidence).filter(Evidence.id.in_(ids)).delete()
    session.query(User).filter(User.id == ids[0]).delete()
    session.execute("DELETE FROM evidence WHERE id = 1")
"""
    assert scan_source(src, "t.py") == []


def test_does_not_flag_ledger_reads_and_assertions():
    src = """
from backend.db.models import AuditLedgerEvent
def assert_event(session, rid, etype):
    rows = session.query(AuditLedgerEvent).filter(
        AuditLedgerEvent.event_type == etype
    ).count()
    assert rows == 1
"""
    assert scan_source(src, "t.py") == []


def test_tamper_update_without_rollback_is_flagged():
    """Allowlisting is conditional on a real rollback, not the name alone."""
    src = """
def test_tamper_detection_with_rollback():
    session.execute("UPDATE audit_ledger_events SET payload = 'x'")
    assert True
"""
    assert "raw_update" in kinds(scan_source(src, "t.py"))


# --------------------------------------------------------------------------
# Whole-tree behaviour
# --------------------------------------------------------------------------

def test_current_test_tree_has_no_violations():
    """The live suite must be clean, excluding this file's own fixtures."""
    tests_root = Path(__file__).resolve().parent.parent
    violations = scan_test_tree(tests_root, skip_files=frozenset({"test_audit_guard.py"}))
    assert violations == [], "destructive audit operations found:\n" + "\n".join(
        str(v) for v in violations
    )


def test_scan_test_tree_detects_injected_violation(tmp_path: Path):
    """End-to-end: the tree scanner catches a planted ORM delete."""
    (tmp_path / "test_bad.py").write_text(
        "from backend.db.models import AuditLedgerEvent\n"
        "def cleanup(session, ids):\n"
        "    session.query(AuditLedgerEvent).filter(\n"
        "        AuditLedgerEvent.resource_id.in_(ids)).delete()\n"
    )
    violations = scan_test_tree(tmp_path)
    assert any(v.kind == "orm_delete" for v in violations)


def test_scan_test_tree_ignores_skipped_files(tmp_path: Path):
    (tmp_path / "test_audit_guard.py").write_text(
        "def f():\n    session.execute('DELETE FROM audit_ledger_events')\n"
    )
    assert scan_test_tree(tmp_path, skip_files=frozenset({"test_audit_guard.py"})) == []
