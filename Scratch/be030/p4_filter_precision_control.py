"""Precision control for the BE-030 §15 filter: only the named pair may drop.

Feeds the real process_revision_directives hook a MigrationScript built from
genuine Alembic op objects, produced the same way autogenerate produces them
(*ConstraintOp.from_constraint). No database is touched.

Ops are identified by a stable key -- the diff kind Alembic itself reports plus
the op's own table_name/constraint_name -- because op.to_diff_tuple() allocates
a fresh SQLAlchemy object on every call, so reprs are not comparable.
"""

import sys

sys.path.insert(0, r"D:/CODING/Projects/Proof-Of-Action-Final")

from alembic.operations import ops
from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    MetaData,
    Table,
    UniqueConstraint,
)

from backend.db.schema_drift_policy import (
    is_nulls_not_distinct_artifact,
    process_revision_directives,
)

md = MetaData()
ura = Table("user_role_assignments", md, Column("a", Integer), Column("b", Integer))
other = Table("other_table", md, Column("a", Integer), Column("b", Integer))

uq_artifact = UniqueConstraint(
    "a", "b", name="uq_user_role_scoped", postgresql_nulls_not_distinct=True
)
ura.append_constraint(uq_artifact)
ck_scope = CheckConstraint("a > 0", name="ck_assignment_scope")
ura.append_constraint(ck_scope)
uq_other_name = UniqueConstraint("a", name="uq_something_else")
ura.append_constraint(uq_other_name)
uq_other_table = UniqueConstraint("a", "b", name="uq_user_role_scoped")
other.append_constraint(uq_other_table)


def build():
    """A fresh op tree: distinct objects, so upgrade and downgrade share no state."""
    return ops.UpgradeOps(
        ops=[
            ops.ModifyTableOps(
                "user_role_assignments",
                ops=[
                    # --- THE TWO OPS THAT MUST BE DROPPED ---
                    ops.DropConstraintOp.from_constraint(uq_artifact),
                    ops.CreateUniqueConstraintOp.from_constraint(uq_artifact),
                    # --- same table, other constraints: must survive ---
                    ops.DropConstraintOp.from_constraint(ck_scope),
                    ops.CreateUniqueConstraintOp.from_constraint(uq_other_name),
                    # --- same table, indexes: must survive ---
                    ops.CreateIndexOp(
                        "ix_assignments_user", "user_role_assignments", ["a"]
                    ),
                    ops.DropIndexOp("ix_other", "user_role_assignments"),
                ],
            ),
            # --- same constraint NAME, different table: must survive ---
            ops.ModifyTableOps(
                "other_table",
                ops=[
                    ops.DropConstraintOp.from_constraint(uq_other_table),
                    ops.CreateUniqueConstraintOp.from_constraint(uq_other_table),
                ],
            ),
            # --- top-level op outside any container: must survive ---
            ops.DropConstraintOp.from_constraint(ck_scope),
        ]
    )


def key(op):
    kind = op.to_diff_tuple()[0]
    name = getattr(op, "constraint_name", None) or getattr(op, "index_name", None)
    return (kind, getattr(op, "table_name", None), name)


def leaves(container, out=None):
    out = [] if out is None else out
    for op in container.ops:
        if hasattr(op, "ops"):
            leaves(op, out)
        else:
            out.append(op)
    return out


upgrade = build()
downgrade = ops.DowngradeOps(ops=build().ops)
directives = [
    ops.MigrationScript(rev_id="x", upgrade_ops=upgrade, downgrade_ops=downgrade)
]

before_up = sorted(key(o) for o in leaves(upgrade))
before_dg = sorted(key(o) for o in leaves(downgrade))
artifact_before = sum(is_nulls_not_distinct_artifact(o) for o in leaves(upgrade))

process_revision_directives(None, ("rev",), directives)

after_up = sorted(key(o) for o in leaves(upgrade))
after_dg = sorted(key(o) for o in leaves(downgrade))

print("UPGRADE   %d leaf ops -> %d" % (len(before_up), len(after_up)))
print("DOWNGRADE %d leaf ops -> %d" % (len(before_dg), len(after_dg)))
print("\nREMOVED (upgrade):")
for k in sorted(set(before_up) - set(after_up)):
    print("   ", k)
print("SURVIVORS (upgrade):")
for k in after_up:
    print("   ", k)

removed = sorted(set(before_up) - set(after_up))
assert artifact_before == 2, artifact_before
assert removed == [
    ("add_constraint", "user_role_assignments", "uq_user_role_scoped"),
    ("remove_constraint", "user_role_assignments", "uq_user_role_scoped"),
], removed
assert len(before_up) - len(after_up) == 2, "exactly two ops may go"
assert len(before_dg) - len(after_dg) == 2, "downgrade stream not pruned too"

for must in (
    ("remove_constraint", "user_role_assignments", "ck_assignment_scope"),
    ("add_constraint", "user_role_assignments", "uq_something_else"),
    ("add_index", "user_role_assignments", "ix_assignments_user"),
    ("remove_index", "user_role_assignments", "ix_other"),
    ("remove_constraint", "other_table", "uq_user_role_scoped"),
    ("add_constraint", "other_table", "uq_user_role_scoped"),
):
    assert must in after_up, f"OVER-FILTERED: {must} was dropped"
assert (
    after_up.count(("remove_constraint", "user_role_assignments", "ck_assignment_scope"))
    == 2
)

print(
    "\nPASS: exactly the 2 named artifact ops were removed from each stream;\n"
    "      every other constraint, index, top-level op and same-named-other-table\n"
    "      op survived."
)
