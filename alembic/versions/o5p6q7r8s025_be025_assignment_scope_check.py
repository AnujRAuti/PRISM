"""BE-025: database-enforced assignment scope/ID matrix (M1).

Revision ID: o5p6q7r8s025
Revises: n4o5p6q7r022

Additive CHECK constraint mirroring the validation already guaranteed by
``backend.services.authorization.assign_role``. Existing rows were created
exclusively through that path and satisfy the constraint.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "o5p6q7r8s025"
down_revision: Union[str, Sequence[str], None] = "n4o5p6q7r022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCOPE_MATRIX = (
    "(scope_type = 'GLOBAL' AND organization_id IS NULL"
    " AND organizational_unit_id IS NULL AND project_id IS NULL)"
    " OR (scope_type = 'ORGANIZATION' AND organization_id IS NOT NULL"
    " AND organizational_unit_id IS NULL AND project_id IS NULL)"
    " OR (scope_type = 'ORGANIZATIONAL_UNIT' AND organizational_unit_id IS NOT NULL"
    " AND organization_id IS NULL AND project_id IS NULL)"
    " OR (scope_type = 'PROJECT' AND project_id IS NOT NULL"
    " AND organization_id IS NULL AND organizational_unit_id IS NULL)"
)


def upgrade() -> None:
    op.create_check_constraint(
        "ck_assignment_scope_matrix", "user_role_assignments", SCOPE_MATRIX)


def downgrade() -> None:
    op.drop_constraint(
        "ck_assignment_scope_matrix", "user_role_assignments", type_="check")
