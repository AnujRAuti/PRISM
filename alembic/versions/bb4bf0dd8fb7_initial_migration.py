"""initial migration

Revision ID: bb4bf0dd8fb7
Revises: 
Create Date: 2026-09-13 15:46:37.612627

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry


# revision identifiers, used by Alembic.
revision: str = 'bb4bf0dd8fb7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('username', sa.String(length=128), nullable=False),
        sa.Column('email', sa.String(length=256), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('owner_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'activities',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('actor_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('verb', sa.String(length=128), nullable=False),
        sa.Column('details', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'claims',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('claimant_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'evidence',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('claim_id', sa.String(length=36), sa.ForeignKey('claims.id'), nullable=True),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('content_type', sa.String(length=128)),
        sa.Column('location', Geometry(geometry_type='POINT', srid=4326)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'evidence_metadata',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('evidence_id', sa.String(length=36), sa.ForeignKey('evidence.id'), nullable=False),
        sa.Column('metadata', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'analysis_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('evidence_id', sa.String(length=36), sa.ForeignKey('evidence.id'), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'analysis_results',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('job_id', sa.String(length=36), sa.ForeignKey('analysis_jobs.id'), nullable=False),
        sa.Column('result', sa.JSON),
        sa.Column('embedding', sa.ARRAY(sa.Float)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'anomalies',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('evidence_id', sa.String(length=36), sa.ForeignKey('evidence.id'), nullable=False),
        sa.Column('score', sa.Integer),
        sa.Column('details', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'duplicate_matches',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('evidence_id', sa.String(length=36), sa.ForeignKey('evidence.id'), nullable=False),
        sa.Column('matched_evidence_id', sa.String(length=36), sa.ForeignKey('evidence.id'), nullable=False),
        sa.Column('similarity', sa.Integer),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'review_decisions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('evidence_id', sa.String(length=36), sa.ForeignKey('evidence.id'), nullable=False),
        sa.Column('reviewer_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('decision', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('event_type', sa.String(length=128), nullable=False),
        sa.Column('actor_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('payload', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes and constraints
    op.create_index('ix_users_username', 'users', ['username'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_index('ix_projects_owner', 'projects', ['owner_id'])
    op.create_index('ix_evidence_project', 'evidence', ['project_id'])
    op.create_index('ix_evidence_claim', 'evidence', ['claim_id'])


def downgrade() -> None:
    op.drop_index('ix_evidence_claim', table_name='evidence')
    op.drop_index('ix_evidence_project', table_name='evidence')
    op.drop_index('ix_projects_owner', table_name='projects')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_username', table_name='users')

    op.drop_table('audit_events')
    op.drop_table('review_decisions')
    op.drop_table('duplicate_matches')
    op.drop_table('anomalies')
    op.drop_table('analysis_results')
    op.drop_table('analysis_jobs')
    op.drop_table('evidence_metadata')
    op.drop_table('evidence')
    op.drop_table('claims')
    op.drop_table('activities')
    op.drop_table('projects')
    op.drop_table('users')
