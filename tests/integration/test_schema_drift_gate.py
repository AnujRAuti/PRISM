"""BE-028 §19-§21: the schema-drift containment gate.

This is the mechanism that was missing when BE-027 found 16 unexplained
differences between the models, the migrations and the database and nothing in
the repository noticed.

What it guarantees:

* ``Base.metadata`` and the migrated schema agree, except for the operations
  individually investigated and documented in
  ``tests/schema_drift_baseline.py``.
* New drift fails the suite, with the unexplained operations named.
* Drift that *disappears* also fails the suite, because the baseline would now
  be describing a problem that no longer exists; clearing an entry is a
  deliberate edit made in the same change that resolves it.
* The gate cannot pass by being broken: one test injects a model change with no
  migration and asserts the gate reports it, and another asserts the PostGIS
  exclusion really is the only reason ``spatial_ref_sys`` is absent from the
  diff (and that the table is still there).

It deliberately uses Alembic's own comparison engine, configured exactly like
``alembic/env.py``, so what this test checks is what ``alembic check`` reports.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Index, text

from backend.db.models import Base
from backend.db.schema_drift_policy import (
    EXTENSION_OWNED_TABLES,
    NULLS_NOT_DISTINCT_CONSTRAINT,
    NULLS_NOT_DISTINCT_TABLE,
    include_object,
)
from backend.db.session import get_engine
from tests.schema_drift_baseline import ACCEPTED_SIGNATURES, compare, signature

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.integration


def collect_drift(connection) -> list[str]:
    """Signature list for every operation `alembic check` would report."""
    ctx = MigrationContext.configure(
        connection,
        opts={
            "target_metadata": Base.metadata,
            "include_object": include_object,
        },
    )
    signatures = [signature(entry) for entry in compare_metadata(ctx, Base.metadata)]
    known_comparator_artifacts = {
        f"add_constraint|{NULLS_NOT_DISTINCT_TABLE}|{NULLS_NOT_DISTINCT_CONSTRAINT}",
        f"remove_constraint|{NULLS_NOT_DISTINCT_TABLE}|{NULLS_NOT_DISTINCT_CONSTRAINT}",
    }
    return [item for item in signatures if item not in known_comparator_artifacts]


def script_head() -> str:
    """The head the revision files claim, independent of any database."""
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"expected one head, found {heads}"
    return heads[0]


def database_version(connection) -> str | None:
    return connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalars().one_or_none()


@pytest.fixture(scope="module")
def drift() -> list[str]:
    """Drift signatures for the test database, which must be at head."""
    engine = get_engine()
    with engine.connect() as connection:
        head, current = script_head(), database_version(connection)
        if head != current:
            pytest.fail(
                "The drift gate cannot judge a database that is not at the "
                f"migration head: schema is at {current!r}, revisions end at "
                f"{head!r}. Run "
                "`python -m alembic upgrade head` against this database, then "
                "re-run. Refusing to compare, because drift measured against a "
                "stale schema is meaningless."
            )
        return collect_drift(connection)


def test_drift_is_exactly_the_documented_baseline(drift):
    """§20: fail on unexpected schema change, in both directions."""
    verdict = compare(drift)
    assert verdict.clean, (
        "Schema drift is not fully accounted for.\n"
        f"UNEXPLAINED (new since the baseline was written): {list(verdict.new)}\n"
        f"NO LONGER PRESENT (the baseline is stale): {list(verdict.resolved)}\n"
        "Explain a new operation by classifying it (BE-028 §13) and adding it "
        "to tests/schema_drift_baseline.py with a reason, or fix it with a "
        "migration. If one has been resolved, delete its baseline entry in the "
        "same change."
    )


def test_baseline_entries_are_all_observed(drift):
    """Every accepted operation must still be real, or the file is fiction."""
    observed = set(drift)
    missing = sorted(ACCEPTED_SIGNATURES - observed)
    assert not missing, (
        f"tests/schema_drift_baseline.py accepts operations that no longer "
        f"occur: {missing}. Remove them; an outdated baseline hides future "
        "drift by making the check look intentional."
    )


def test_a_baseline_entry_that_stops_being_true_also_fails():
    """Prove the second direction: a stale baseline is not a passing state.

    Pure comparison, no database: if someone resolves documented drift and
    leaves the entry behind, `compare()` must report it as `resolved` and the
    verdict must be unclean. Without this, the baseline could grow into a
    suppression list that quietly tolerates whatever it once described.

    When the reviewed baseline is empty, use a synthetic entry so this test
    still proves the comparison's stale-entry behavior rather than requiring
    production drift to exist solely to exercise the guard.
    """
    stale = (
        sorted(ACCEPTED_SIGNATURES)[0]
        if ACCEPTED_SIGNATURES
        else "add_index|schema_drift_gate_probe|ix_stale_baseline_probe"
    )
    observed = sorted(ACCEPTED_SIGNATURES - {stale})
    verdict = compare(observed, baseline={stale})
    assert verdict.resolved == (stale,), (
        f"Dropping {stale!r} from the observed drift did not register as a "
        "stale baseline entry. The check would then be one-directional."
    )
    assert not verdict.clean


def test_the_gate_detects_a_model_change_with_no_migration(drift):
    """The gate must be capable of failing: prove it on an injected change.

    Adds an index to a model that no migration creates, re-runs the comparison,
    and requires the new operation to show up as unexplained. Reverted in a
    finally block, so the run leaves the metadata (and the database) untouched.
    """
    table = Base.metadata.tables["projects"]
    probe = Index("ix_be028_gate_probe_marker", table.c.created_at)
    try:
        with get_engine().connect() as connection:
            injected = collect_drift(connection)
        verdict = compare(injected)
        assert "add_index|projects|ix_be028_gate_probe_marker" in verdict.new, (
            "The drift gate did not notice a model declaration with no "
            "migration. A gate that cannot see new drift is not containment."
        )
    finally:
        table.indexes.remove(probe)
    assert "ix_be028_gate_probe_marker" not in {i.name for i in table.indexes}, (
        "The injected index survived the test and now pollutes Base.metadata."
    )


def test_extension_owned_objects_are_excluded_not_suppressed(drift):
    """The PostGIS exclusion is narrow: named objects only, nothing else."""
    assert not [d for d in drift if d.startswith("remove_table|")], (
        "The comparison wants to drop a table. If it is spatial_ref_sys, the "
        "include_object hook has stopped working and an autogenerated "
        "migration would destroy the PostGIS SRID registry."
    )
    # And the object it protects is genuinely present and populated.
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT count(*) FROM spatial_ref_sys")
        ).scalar()
    assert rows > 0, "spatial_ref_sys is empty or missing: PostGIS is not usable"
    assert EXTENSION_OWNED_TABLES == {"spatial_ref_sys"}, (
        "The exclusion list grew. Every added name must be justified as "
        "extension-owned, or the gate is becoming a suppression switch."
    )


def test_the_assignment_constraint_is_still_nulls_not_distinct():
    """Guard the object the accepted artifact is about, independently.

    The baseline tolerates Alembic proposing to rebuild uq_user_role_scoped.
    That is only safe because the database already matches the model, so the
    definition is asserted here from the catalog rather than via Alembic's
    reflection, which is the component that cannot see the flag.
    """
    with get_engine().connect() as connection:
        definition = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'uq_user_role_scoped'"
            )
        ).scalar()
    assert definition is not None, "uq_user_role_scoped has been dropped"
    assert "NULLS NOT DISTINCT" in definition, (
        f"uq_user_role_scoped is no longer nulls-not-distinct: {definition}. "
        "BE-025's scope matrix depends on NULLs comparing as equal here."
    )
