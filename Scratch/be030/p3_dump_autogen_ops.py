"""Read-only probe: replicate alembic.command.check() and dump the raw op tree.

Mirrors alembic/command.py:250-303 exactly (ScriptDirectory -> RevisionContext
-> EnvironmentContext -> run_env()), but instead of raising it prints the
structure that env.py's process_revision_directives hook would receive:
directives[0].upgrade_ops.ops, recursing into OpContainer subclasses.

Performs no DDL: alembic.autogenerate only reflects and compares.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, r"D:/CODING/Projects/Proof-Of-Action-Final")

from alembic import command  # noqa: F401
from alembic.autogenerate import RevisionContext
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.environment import EnvironmentContext

INI = r"D:/CODING/Scratch/be030/alembic_pre030.ini"

collected = {}


def _safe_diff(op):
    if not hasattr(op, "to_diff_tuple"):
        return None
    try:
        return repr(op.to_diff_tuple())[:200]
    except Exception as exc:
        return f"<{type(exc).__name__}>"


def dump(op, depth=0):
    info = {
        "depth": depth,
        "class": type(op).__name__,
        "has_operation": hasattr(op, "operation"),
        "operation": getattr(op, "operation", None),
        "has_args": hasattr(op, "args"),
        "args": repr(getattr(op, "args", None)),
        "has_kw": hasattr(op, "kw"),
        "kw": repr(getattr(op, "kw", None))[:120],
        "constraint_name": getattr(op, "constraint_name", None),
        "table_name": getattr(op, "table_name", None),
        "constraint_type": getattr(op, "constraint_type", None),
        "diff_tuple": _safe_diff(op),
    }
    print(json.dumps(info, indent=2, default=str))
    if hasattr(op, "ops"):
        for child in op.ops:
            dump(child, depth + 1)


config = Config(INI)
script_directory = ScriptDirectory.from_config(config)

command_args = dict(
    message=None,
    autogenerate=True,
    sql=False,
    head="head",
    splice=False,
    branch_label=None,
    version_path=None,
    rev_id=None,
    depends_on=None,
)
revision_context = RevisionContext(config, script_directory, command_args)


def retrieve_migrations(rev, context):
    revision_context.run_autogenerate(rev, context)
    return []


with EnvironmentContext(
    config,
    script_directory,
    fn=retrieve_migrations,
    as_sql=False,
    template_args=revision_context.template_args,
    revision_context=revision_context,
):
    script_directory.run_env()

script = revision_context.generated_revisions[-1]
print("=== type(directives[0]) =", type(script).__name__)
print("=== upgrade_ops class =", type(script.upgrade_ops).__name__)
print("=== len(upgrade_ops.ops) =", len(script.upgrade_ops.ops))
for top in script.upgrade_ops.ops:
    dump(top)
print("=== downgrade_ops.ops ===")
for top in script.downgrade_ops.ops:
    dump(top)
print("=== as_diffs count =", len(script.upgrade_ops.as_diffs()))
