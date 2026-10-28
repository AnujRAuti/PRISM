"""Read-only inventory of rows left behind by the HEAD-proof run of the BE-019 write tests.

On HEAD the cross-scope creates were ALLOWED, so the route wrote rows; the test
then failed at its assertion before registering them for cleanup, and the fixture
teardown hit a foreign key. This script only SELECTs and prints.
"""
import sys

sys.path.insert(0, r"D:/CODING/Scratch/deploy1")
import armfull  # noqa: E402

QUERIES = {
    "api_clients": (
        "SELECT id, name, project_id FROM api_clients WHERE name LIKE 'be019-%' ORDER BY created_at"
    ),
    "external_systems": (
        "SELECT id, name, code, organization_id FROM external_systems "
        "WHERE code LIKE 'be019%' OR name LIKE 'be019 %' ORDER BY created_at"
    ),
    "projects": (
        "SELECT id, name, owner_id FROM projects WHERE name LIKE 'be019 %' ORDER BY created_at"
    ),
    "organizations": (
        "SELECT id, name, code FROM organizations WHERE code LIKE 'BE019-%' ORDER BY created_at"
    ),
    "users": "SELECT id, username FROM users WHERE username LIKE 'be019-%' ORDER BY username",
}

for table, sql in QUERIES.items():
    out = armfull.psql(armfull.SUITE_DB, sql)
    print(f"=== {table} ===\n{out}")
