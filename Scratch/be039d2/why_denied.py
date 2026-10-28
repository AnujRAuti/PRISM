"""Why alembic cannot read alembic_version on pofa_test (read-only)."""

from __future__ import annotations

import sys

import psycopg2

sys.path.insert(0, r"D:/CODING/Scratch/be039d2")
from d2_bootstrap_proof import _resolve  # noqa: E402

import re
from pathlib import Path

COMPOSE = Path(r"D:/CODING/Projects/Proof-Of-Action-Final/docker-compose.yml")
text = COMPOSE.read_text(encoding="utf-8")
values = {}
for key in ("POSTGRES_USER", "POSTGRES_PASSWORD"):
    match = re.search(rf"^\s*{key}:\s*(.+)$", text, re.MULTILINE)
    values[key] = _resolve(match.group(1)) if match else None
print(f"compose POSTGRES_USER={values['POSTGRES_USER']!r} "
      f"password length={len(values['POSTGRES_PASSWORD'] or '')}")

connection = psycopg2.connect(
    host="localhost", port=5432,
    user=values["POSTGRES_USER"], password=values["POSTGRES_PASSWORD"],
    dbname="pofa_test",
)
with connection.cursor() as cursor:
    cursor.execute("SELECT current_user, current_database()")
    print("identity:", cursor.fetchone())
    cursor.execute(
        "SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, "
        "has_table_privilege(current_user, c.oid, 'SELECT') AS can_select "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname IN "
        "('alembic_version', 'roles', 'permissions', 'role_permissions') "
        "ORDER BY c.relname")
    for row in cursor.fetchall():
        print("  ", row)
    cursor.execute("SELECT count(*) FROM information_schema.tables "
                   "WHERE table_schema='public'")
    print("public tables:", cursor.fetchone()[0])
connection.rollback()
connection.close()
