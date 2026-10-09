"""BE-029 (2/2): make users.username / users.email unique in the database.

Revision ID: s9t0u1v2w029
Revises: r8s9t0u1v028

Closes BE-028 blocker B-1 and drift category E: ``backend/db/models.py`` has
always declared ``unique=True`` on both columns and no revision ever enforced
it, so the model overstated the database contract and ``testuser`` /
``test@example.com`` could be inserted repeatedly.

Product policy (BE-029 §4, owner decision OQ-1 = Option A): username and email
are identity attributes, therefore the database must refuse duplicates. The
authoritative external identity key ``uq_user_identity_subject`` is untouched.

Why the ordinary CREATE UNIQUE INDEX and not CONCURRENTLY
---------------------------------------------------------
``users`` measured 2,098 rows in ``pofa_test`` and 1,094 in ``pofa_dev`` at the
time of writing (BE-029 §34), i.e. a sub-millisecond build. ``CONCURRENTLY``
also cannot be used here: it may not run inside a transaction block and Alembic
wraps each revision in one. Lock duration is therefore a non-issue at this size;
if the table ever grows enough for it to matter, the rebuild has to move out of
Alembic's transactional wrapper rather than being bolted on here.

Order of operations
-------------------
1. §19 pre-constraint validation: duplicate detection over the live rows must
   find zero groups. If it finds any, this revision aborts with no DDL at all,
   because "create the constraint anyway" is exactly what BE-029 forbids.
2. Verify the existing indexes are the plain non-unique ones BE-028 documented,
   so a database that someone already fixed by hand is not silently rebuilt.
3. Drop and recreate both indexes under their existing names
   (``ix_users_username``, ``ix_users_email``) with UNIQUE, which is the object
   the ORM's ``unique=True, index=True`` declaration describes.

``downgrade()`` restores the non-unique pair. It does not re-add duplicates.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "s9t0u1v2w029"
down_revision: Union[str, Sequence[str], None] = "r8s9t0u1v028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (index name, column) — names kept from the initial migration so no layer has
#: to be renamed and the ORM's automatic names continue to match.
IDENTITY_INDEXES = (
    ("ix_users_username", "username"),
    ("ix_users_email", "email"),
)


class UniquenessPreconditionFailed(RuntimeError):
    """Raised when the data is not ready for a unique index."""


def _duplicate_groups(bind, column: str) -> int:
    return int(bind.execute(text(
        f"SELECT count(*) FROM (SELECT {column} FROM users"
        f" GROUP BY {column} HAVING count(*) > 1) d"
    )).scalar())


def _is_unique(bind, index_name: str) -> bool:
    row = bind.execute(text(
        "SELECT i.indisunique FROM pg_index i"
        " JOIN pg_class c ON c.oid = i.indexrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE c.relname = :name AND n.nspname = 'public'"
    ), {"name": index_name}).fetchone()
    if row is None:
        raise UniquenessPreconditionFailed(
            f"{index_name} does not exist; the identity index pair is not in "
            "the shape BE-028 documented, so this revision refuses to guess")
    return bool(row[0])


def upgrade() -> None:
    bind = op.get_bind()

    # §19: the data precondition, checked before any DDL.
    for column in ("username", "email"):
        groups = _duplicate_groups(bind, column)
        if groups:
            raise UniquenessPreconditionFailed(
                f"cannot make users.{column} unique: {groups} duplicate group(s)"
                " remain. BE-029 §19 forbids creating the constraint on top of"
                " unremediated data.")

    for index_name, column in IDENTITY_INDEXES:
        if _is_unique(bind, index_name):
            raise UniquenessPreconditionFailed(
                f"{index_name} is already UNIQUE; this revision expects to "
                f"convert the plain index on users.{column}")

    for index_name, column in IDENTITY_INDEXES:
        op.drop_index(index_name, table_name="users")
        op.create_index(index_name, "users", [column], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    for index_name, column in IDENTITY_INDEXES:
        if not _is_unique(bind, index_name):
            raise UniquenessPreconditionFailed(
                f"{index_name} is not UNIQUE; refusing to drop an index that"
                " this revision did not create")
        op.drop_index(index_name, table_name="users")
        op.create_index(index_name, "users", [column], unique=False)
