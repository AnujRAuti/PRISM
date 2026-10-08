"""Objects that belong to a PostgreSQL extension, not to the application schema.

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
"""

from __future__ import annotations

#: Tables installed by PostgreSQL extensions in the public schema.
#: ``spatial_ref_sys`` comes from ``CREATE EXTENSION postgis`` and holds the
#: SRID registry (8,500 rows in this project's PostGIS 3.4.2 image).
EXTENSION_OWNED_TABLES = frozenset({"spatial_ref_sys"})


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Alembic ``include_object`` hook: keep extension-owned tables out of the diff."""
    if type_ == "table" and name in EXTENSION_OWNED_TABLES:
        return False
    return True
