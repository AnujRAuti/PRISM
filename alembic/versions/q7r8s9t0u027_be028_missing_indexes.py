"""BE-028: the three indexes the models declared but no migration created.

Revision ID: q7r8s9t0u027
Revises: p6q7r8s9t026

Drift inventory (BE-028 §13, category D): ``AnalysisJob.status``,
``EvidenceMetadata.evidence_id`` and ``Project.name`` all declare ``index=True``
in ``backend/db/models.py``, but no revision in the chain ever created the
corresponding index, so every migrated database is missing three objects the
application says it has.

Purely additive: each ``CREATE INDEX`` takes a brief write lock on a small table
(measured during BE-028: ``analysis_jobs`` 32/36 rows, ``evidence_metadata``
102/43, ``projects`` 584/1053 in ``pofa_dev``/``pofa_test``), touches no data,
and changes no column. Downgrade drops exactly the three indexes it created.

Deliberately NOT included here: the ``unique=True`` on ``users.username`` /
``users.email``. That difference is unsafe until the duplicate identities it
would collide with are resolved (BE-028 §11/§39 — see the B-1 blocker and the
remediation plan in docs/BE-028 Schema Integrity and Drift Containment
Results.md).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "q7r8s9t0u027"
down_revision: Union[str, Sequence[str], None] = "p6q7r8s9t026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MISSING_INDEXES = (
    ("analysis_jobs", "ix_analysis_jobs_status", "status"),
    ("evidence_metadata", "ix_evidence_metadata_evidence_id", "evidence_id"),
    ("projects", "ix_projects_name", "name"),
)


def upgrade() -> None:
    for table, name, column in MISSING_INDEXES:
        op.create_index(name, table, [column], unique=False)


def downgrade() -> None:
    for table, name, column in reversed(MISSING_INDEXES):
        op.drop_index(name, table_name=table)
