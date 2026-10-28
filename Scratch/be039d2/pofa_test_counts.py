"""Read-only catalogue counts on pofa_test, after the seed revision ran there."""

from __future__ import annotations

import sys

import psycopg2

sys.path.insert(0, r"D:/CODING/Scratch/be039d2")
from arm import owner_dsn  # noqa: E402

from sqlalchemy.engine.url import make_url  # noqa: E402

url = make_url(owner_dsn())
connection = psycopg2.connect(
    host=url.host, port=url.port, user=url.username, password=url.password,
    dbname=url.database,
)
with connection.cursor() as cursor:
    cursor.execute("SELECT current_user, current_database(), "
                   "(SELECT version_num FROM alembic_version)")
    print("identity/revision:", cursor.fetchone())
    for table in ("roles", "permissions", "role_permissions"):
        cursor.execute(f"SELECT count(*) FROM {table}")
        print(f"  {table}: {cursor.fetchone()[0]}")
    cursor.execute("SELECT r.name, count(*) FROM role_permissions rp "
                   "JOIN roles r ON r.id = rp.role_id "
                   "JOIN permissions p ON p.id = rp.permission_id "
                   "GROUP BY r.name ORDER BY r.name")
    print("  grants per role (name must join to a real permission):",
          cursor.fetchall())
connection.rollback()
connection.close()
