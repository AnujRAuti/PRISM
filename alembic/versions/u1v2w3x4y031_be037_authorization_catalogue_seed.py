"""seed the BE-016 authorization catalogue

Revision ID: u1v2w3x4y031
Revises: t0u1v2w3x030

The baseline roles, permissions and role grants are Python constants
(``backend/db/models.py``) that reached the database only through
``authorization.ensure_default_catalogue`` — and nothing in the application or in
any migration ever called it. ``alembic upgrade head`` therefore produced a
structurally complete database with an empty catalogue, where authentication
resolves permissions from the ``role_permissions`` TABLE and every authenticated
request is denied with 403 NO_PERMISSION.

Seeding is placed here rather than in application start-up because it is data,
not behaviour: start-up seeding would write on every API process, every worker
process and every test client, and would race across replicas on first boot. This
puts the baseline behind the one documented bootstrap step
(``docker compose run --rm migrate``).

Each statement upserts on a constraint the schema already declares, so the seed is
idempotent: a database already populated by ``ensure_default_catalogue`` (what the
test fixtures call) re-runs as a no-op and keeps its existing row ids, and row ids
here are derived from each row's name rather than random so a fresh seed converges
on the same values wherever it runs. One-time by nature: a permission added to the
constants later needs its own seed revision, exactly as a column addition needs its
own schema revision.
"""

from typing import Sequence, Union

from alembic import op

from backend.db.models import AUTH_PERMISSIONS, AUTH_ROLE_PERMISSIONS, AUTH_ROLES

revision: str = "u1v2w3x4y031"
down_revision: Union[str, Sequence[str], None] = "t0u1v2w3x030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _quoted(value: str) -> str:
    """One SQL string literal. The catalogue holds identifiers, not prose."""
    return "'" + value.replace("'", "''") + "'"


def _one_column_rows(names) -> str:
    return ", ".join(f"({_quoted(name)})" for name in names)


def _pair_rows(pairs) -> str:
    return ", ".join(
        f"({_quoted(role)}, {_quoted(permission)})" for role, permission in pairs
    )


def upgrade() -> None:
    op.execute(
        "INSERT INTO roles (id, name, status) "
        "SELECT md5('poa-catalogue:role:' || r.name)::uuid, r.name, 'ACTIVE' "
        f"FROM (VALUES {_one_column_rows(AUTH_ROLES)}) AS r(name) "
        "ON CONFLICT (name) DO NOTHING"
    )
    op.execute(
        "INSERT INTO permissions (id, name) "
        "SELECT md5('poa-catalogue:permission:' || p.name)::uuid, p.name "
        f"FROM (VALUES {_one_column_rows(AUTH_PERMISSIONS)}) AS p(name) "
        "ON CONFLICT (name) DO NOTHING"
    )
    pairs = [
        (role, permission)
        for role, permissions in AUTH_ROLE_PERMISSIONS.items()
        for permission in permissions
    ]
    op.execute(
        "INSERT INTO role_permissions (id, role_id, permission_id) "
        "SELECT md5('poa-catalogue:grant:' || r.name || ':' || p.name)::uuid, "
        "       r.id, p.id "
        f"FROM (VALUES {_pair_rows(pairs)}) AS t(role_name, permission_name) "
        "JOIN roles r ON r.name = t.role_name "
        "JOIN permissions p ON p.name = t.permission_name "
        "ON CONFLICT (role_id, permission_id) DO NOTHING"
    )


def downgrade() -> None:
    # The seed is baseline configuration, not a schema change: role assignments
    # and every authorization decision in the database reference these rows, so
    # deleting them would silently revoke live grants rather than undo a
    # structural change. Data this consequential is not destroyed on rollback.
    pass
