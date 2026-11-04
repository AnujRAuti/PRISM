"""Drift exclusions that ``alembic/env.py`` and the schema-drift gate share.

Alembic compares the live database against ``Base.metadata``. Anything created
by ``CREATE EXTENSION`` is therefore invisible to the model and shows up as an
object to *delete*: ``alembic check`` on a freshly migrated database proposes
``DropTableOp(spatial_ref_sys)``, and ``alembic revision --autogenerate`` would
write that into a real migration. Applying one would break every PostGIS
function that resolves an SRID.

This module is the single source of truth for that exclusion so ``alembic/env.py``
and the schema-drift gate cannot disagree. It excludes by exact object name and
kind only: a new application table, index or constraint is still compared, so
this is not a way to hide drift.

It also carries the reviewed, named autogenerate filter for the one
*tooling* artifact Alembic cannot express -- the ``uq_user_role_scoped``
nulls-not-distinct pair, documented at
:data:`NULLS_NOT_DISTINCT_ARTIFACT_OPS` below. That filter runs only on the
revision-generation path (``process_revision_directives``); the drift gate keeps
measuring the pair, because the gate's whole purpose is to notice when it moves.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger("alembic.schema_drift_policy")

#: Tables installed by PostgreSQL extensions in the public schema.
#: ``spatial_ref_sys`` comes from ``CREATE EXTENSION postgis`` and holds the
#: SRID registry (8,500 rows in this project's PostGIS 3.4.2 image).
EXTENSION_OWNED_TABLES = frozenset({"spatial_ref_sys"})


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Alembic ``include_object`` hook: keep extension-owned tables out of the diff."""
    if type_ == "table" and name in EXTENSION_OWNED_TABLES:
        return False
    return True


#: --- BE-030 §15: the nulls-not-distinct autogenerate artifact ---------------
#:
#: What this removes, and only this:
#:
#: * ``remove_constraint`` on ``user_role_assignments.uq_user_role_scoped``
#: * ``add_constraint``    on ``user_role_assignments.uq_user_role_scoped``
#:
#: Why the pair is permanent. The model declares the constraint with
#: ``postgresql_nulls_not_distinct=True`` (``backend/db/models.py``, the
#: ``UniqueConstraint`` in ``UserRoleAssignment.__table_args__``), and the live
#: database really does have it -- ``pg_get_constraintdef`` reads
#: ``UNIQUE NULLS NOT DISTINCT (user_id, role_id, scope_type, organization_id,
#: organizational_unit_id, project_id)``. But SQLAlchemy's reflection hands
#: Alembic that flag while Alembic's own rebuild path throws it away:
#: ``alembic/autogenerate/compare.py::_make_unique_constraint()`` reconstructs
#: the reflected side from column names and name alone, so the two sides of the
#: comparison differ only by ``('nulls_not_distinct', True)`` and every
#: autogenerate pass proposes to drop and re-add a constraint that is already
#: correct. ``alembic check`` therefore fails *by construction* on a schema that
#: matches its model.
#:
#: Measurement: ``docs/BE-029 User Identity Constraint Remediation Results.md``
#: §14.6-§14.7 established the mechanism and the permanence of the pair; BE-030
#: §15 re-measured it before and after this filter, and that before/after
#: ``alembic check`` transcript is carried in the BE-030 results record.
#:
#: Why *this* mechanism and not editing the model. Deleting
#: ``postgresql_nulls_not_distinct`` from the model would make the pair vanish
#: too, by silently downgrading a NULLS NOT DISTINCT constraint to NULLS
#: DISTINCT -- two rows with the same user/role/scope and a NULL scope column
#: would start colliding, then start *not* colliding, in whichever direction the
#: next migration drifted. The fix belongs in the tool that is wrong, not in the
#: contract it is describing.
#:
#: Why it does not weaken the gate. ``tests/integration/test_schema_drift_gate.py``
#: calls ``alembic.autogenerate.compare_metadata()`` directly, which never
#: reaches ``process_revision_directives``. The pair stays in
#: ``tests/schema_drift_baseline.py`` and the gate still fails if it changes
#: shape or disappears. This filter only trims the noise from revision
#: generation and from ``alembic check``'s verdict.
NULLS_NOT_DISTINCT_TABLE = "user_role_assignments"
NULLS_NOT_DISTINCT_CONSTRAINT = "uq_user_role_scoped"

#: The two Alembic diff kinds that make up the artifact pair.
NULLS_NOT_DISTINCT_ARTIFACT_OPS = frozenset(
    {"remove_constraint", "add_constraint"}
)


def _artifact_diff_kind(op) -> str | None:
    """Alembic's own diff-kind string for one generated op, or ``None``.

    ``UpgradeOps.as_diffs()`` (``alembic/operations/ops.py``) reports each op as
    ``op.to_diff_tuple()``, and ``alembic check`` prints exactly that. Deriving
    the kind the same way keeps this filter in word-for-word agreement with what
    ``alembic check`` shows and with the ``kind|table|object`` signatures the
    drift baseline uses, instead of inventing a second vocabulary.

    Non-constraint ops (and every ``OpContainer``) either lack
    ``constraint_name`` or raise from ``to_diff_tuple``; both return ``None``, so
    this can never match an index, table or column op.
    """
    if getattr(op, "constraint_name", None) is None:
        return None
    try:
        return op.to_diff_tuple()[0]
    except (IndexError, KeyError, NotImplementedError, TypeError):
        return None


def is_nulls_not_distinct_artifact(op) -> bool:
    """True for exactly one op: a uq_user_role_scoped add/drop of the artifact pair."""
    if getattr(op, "table_name", None) != NULLS_NOT_DISTINCT_TABLE:
        return False
    if getattr(op, "constraint_name", None) != NULLS_NOT_DISTINCT_CONSTRAINT:
        return False
    return _artifact_diff_kind(op) in NULLS_NOT_DISTINCT_ARTIFACT_OPS


def _drop_artifact_ops(container) -> None:
    """Remove the named artifact ops from one OpContainer, in place.

    Alembic does not put constraint ops at the top of ``upgrade_ops.ops``: it
    wraps them in ``ModifyTableOps(table_name='user_role_assignments', ops=[
    DropConstraintOp, CreateUniqueConstraintOp])``. So this descends into any op
    that has ``.ops`` -- the same test Alembic's own ``_ops_as_diffs`` uses --
    and filters at the leaves. An emptied ``ModifyTableOps`` renders as nothing
    (``alembic/autogenerate/render.py::_render_modify_table``), so the container
    itself is left where it is.
    """
    kept = []
    for op in container.ops:
        if hasattr(op, "ops"):
            _drop_artifact_ops(op)
            kept.append(op)
        elif is_nulls_not_distinct_artifact(op):
            _LOGGER.info(
                "schema_drift_policy: suppressed known Alembic autogenerate "
                "artifact %s on %s.%s -- Alembic discards nulls_not_distinct "
                "when it rebuilds this constraint (BE-030 task 15; reason text "
                "and measurement pointer: backend/db/schema_drift_policy.py)",
                _artifact_diff_kind(op),
                NULLS_NOT_DISTINCT_TABLE,
                NULLS_NOT_DISTINCT_CONSTRAINT,
            )
        else:
            kept.append(op)
    container.ops[:] = kept


def process_revision_directives(context, revision, directives) -> None:
    """Alembic ``process_revision_directives`` hook for the revision path.

    Wired into both ``context.configure(...)`` calls in ``alembic/env.py``.
    Alembic calls it after ``compare._populate_migration_script()`` has filled
    the ops and before ``alembic check`` reads ``upgrade_ops.as_diffs()``
    (``alembic/autogenerate/api.py``), which is why trimming ops here is what
    ``alembic check`` reports -- and why it is *not* seen by the drift gate.

    Only ops that ``is_nulls_not_distinct_artifact()`` accepts are dropped:
    the two diff kinds in ``NULLS_NOT_DISTINCT_ARTIFACT_OPS``, on
    ``NULLS_NOT_DISTINCT_TABLE``, for ``NULLS_NOT_DISTINCT_CONSTRAINT`` -- and
    nothing else. If that leaves the stream empty it stays empty; no other
    object's diff is suppressed here, and an empty autogenerated revision
    renders as ``pass``.
    """
    for script in directives:
        # *_ops_list, not .upgrade_ops: the singular property raises when a
        # revision does multiple autogenerate passes (multidb templates).
        for container in list(script.upgrade_ops_list) + list(
            script.downgrade_ops_list
        ):
            _drop_artifact_ops(container)
