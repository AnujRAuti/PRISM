"""Align legacy JSON columns with the JSONB model contract.

Revision ID: x4y5z6a7b034
Revises: w3x4y5z6a033
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "x4y5z6a7b034"
down_revision: Union[str, Sequence[str], None] = "w3x4y5z6a033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSON_COLUMNS = (
    ("activities", "details"),
    ("analysis_results", "result"),
    ("anomalies", "details"),
    ("api_clients", "scopes"),
    ("audit_events", "payload"),
    ("audit_ledger_events", "metadata"),
    ("audit_ledger_events", "payload"),
    ("case_generation_configurations", "configuration"),
    ("case_generation_runs", "input_snapshot"),
    ("duplicate_matches", "signals"),
    ("evidence_metadata", "metadata"),
    ("evidence_request_events", "metadata"),
    ("explanation_runs", "summary"),
    ("fusion_configurations", "priority"),
    ("fusion_configurations", "signals"),
    ("fusion_configurations", "thresholds"),
    ("fusion_configurations", "weights"),
    ("fusion_runs", "input_snapshot"),
    ("fusion_signals", "details"),
    ("fusion_signals", "raw_value"),
    ("graph_relationships", "provenance"),
    ("integrity_assessments", "signal_summary"),
    ("notification_outbox", "payload"),
    ("retention_operations", "details"),
    ("retention_policy_versions", "rules"),
)


def upgrade() -> None:
    for table_name, column_name in JSON_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.JSON(),
            type_=postgresql.JSONB(),
            postgresql_using=f'"{column_name}"::jsonb',
        )


def downgrade() -> None:
    for table_name, column_name in reversed(JSON_COLUMNS):
        op.alter_column(
            table_name,
            column_name,
            existing_type=postgresql.JSONB(),
            type_=sa.JSON(),
            postgresql_using=f'"{column_name}"::json',
        )
