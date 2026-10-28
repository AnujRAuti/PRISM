"""add BE-016 authentication and authorization foundation

Revision ID: i9d0e1f2g016
Revises: h8c9d0e1f015
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "i9d0e1f2g016"
down_revision: Union[str, Sequence[str], None] = "h8c9d0e1f015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_STATUSES = "'ACTIVE', 'SUSPENDED', 'DISABLED'"
SCOPES = "'GLOBAL', 'ORGANIZATION', 'ORGANIZATIONAL_UNIT', 'PROJECT'"


def upgrade() -> None:
    # Existing users: extend identity without touching established rows.
    op.add_column("users", sa.Column("external_subject", sa.String(length=512), nullable=True))
    op.add_column(
        "users",
        sa.Column("identity_provider", sa.String(length=128), nullable=False,
                  server_default="local"),
    )
    op.add_column("users", sa.Column("display_name", sa.String(length=256), nullable=True))
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    # Deterministic backfill: local identity derived from the stable row id.
    op.execute(
        "UPDATE users SET external_subject = id::text "
        "WHERE external_subject IS NULL"
    )
    op.execute(
        "UPDATE users SET display_name = username WHERE display_name IS NULL"
    )
    op.create_unique_constraint("uq_user_identity_subject", "users",
                                ["identity_provider", "external_subject"])
    op.create_check_constraint("ck_user_status", "users",
                               f"status IN ({USER_STATUSES})")

    # Existing projects stay unscoped (nullable) and behave as before.
    # NOTE: the organization/unit foreign keys are added after those
    # tables are created below.
    op.add_column(
        "projects",
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("organizational_unit_id", UUID(as_uuid=False), nullable=True),
    )

    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"status IN ({USER_STATUSES})", name="ck_organization_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_organizations_code"),
    )
    op.create_index("ix_organizations_code", "organizations", ["code"])

    op.create_table(
        "organizational_units",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"status IN ({USER_STATUSES})", name="ck_org_unit_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_org_unit_code"),
    )
    op.create_index("ix_org_units_org", "organizational_units", ["organization_id"])

    op.create_foreign_key("fk_projects_organization", "projects",
                          "organizations", ["organization_id"], ["id"])
    op.create_foreign_key("fk_projects_org_unit", "projects",
                          "organizational_units", ["organizational_unit_id"], ["id"])

    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"status IN ({USER_STATUSES})", name="ck_role_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_index("ix_roles_name", "roles", ["name"])

    op.create_table(
        "permissions",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_permissions_name"),
    )
    op.create_index("ix_permissions_name", "permissions", ["name"])

    op.create_table(
        "role_permissions",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("role_id", UUID(as_uuid=False), nullable=False),
        sa.Column("permission_id", UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role", "role_permissions", ["role_id"])

    op.create_table(
        "user_role_assignments",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", UUID(as_uuid=False), nullable=False),
        sa.Column("role_id", UUID(as_uuid=False), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=False), nullable=True),
        sa.Column("organizational_unit_id", UUID(as_uuid=False), nullable=True),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"scope_type IN ({SCOPES})", name="ck_assignment_scope"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["organizational_unit_id"], ["organizational_units.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "role_id", "scope_type", "organization_id",
            "organizational_unit_id", "project_id",
            name="uq_user_role_scoped",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_assignments_user", "user_role_assignments", ["user_id"])
    op.create_index("ix_assignments_project", "user_role_assignments", ["project_id"])
    op.create_index("ix_assignments_org", "user_role_assignments", ["organization_id"])

    op.create_table(
        "api_clients",
        sa.Column("id", UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("project_id", UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.CheckConstraint(f"status IN ({USER_STATUSES})", name="ck_api_client_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_api_clients_name"),
    )
    op.create_index("ix_api_clients_name", "api_clients", ["name"])


def downgrade() -> None:
    op.drop_constraint("fk_projects_org_unit", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_organization", "projects", type_="foreignkey")
    op.drop_index("ix_api_clients_name", table_name="api_clients")
    op.drop_table("api_clients")
    op.drop_index("ix_assignments_org", table_name="user_role_assignments")
    op.drop_index("ix_assignments_project", table_name="user_role_assignments")
    op.drop_index("ix_assignments_user", table_name="user_role_assignments")
    op.drop_table("user_role_assignments")
    op.drop_index("ix_role_permissions_role", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_permissions_name", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_org_units_org", table_name="organizational_units")
    op.drop_table("organizational_units")
    op.drop_index("ix_organizations_code", table_name="organizations")
    op.drop_table("organizations")
    op.drop_column("projects", "organizational_unit_id")
    op.drop_column("projects", "organization_id")
    op.drop_constraint("ck_user_status", "users", type_="check")
    op.drop_constraint("uq_user_identity_subject", "users", type_="unique")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "status")
    op.drop_column("users", "display_name")
    op.drop_column("users", "identity_provider")
    op.drop_column("users", "external_subject")
