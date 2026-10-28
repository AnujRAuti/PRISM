"""Delete the five-row orphan set the HEAD-proof run left in the disposable suite DB.

The exact rows are listed by orphan_inventory.py first; these are the ids it
printed (one api_client + its credential, one external_system, two projects,
three organizations, five users). They exist only because HEAD allowed the
cross-scope create that the fixed code refuses, and the test aborted at its
assertion before registering them for cleanup.

Target is poa_disp_suite on the disposable cluster -- never pofa_dev/pofa_test.
"""
import sys

sys.path.insert(0, r"D:/CODING/Scratch/deploy1")
import armfull  # noqa: E402

assert armfull.SUITE_DB not in armfull.PROTECTED_NAMES, "refusing a protected database"

CLIENTS = ["1033674e-a966-4c18-87a3-4b711cb5575b"]
SYSTEMS = ["df2ba8d7-79ef-4019-a847-189306bb2577"]
PROJECTS = ["e02f681e-b7ab-446f-8872-8ec7dc822080", "707568bf-34c1-4c71-8a05-904a08e1e28e"]
ORGS = ["39358082-e16c-4f91-aa3a-5b7a15d66264", "b467cbb2-cade-4fe8-b5c3-d9d61b11ef75",
        "60cc40e2-8a02-4e48-9812-329b85594179"]
USERS = ["c487f489-3825-4fe4-96ac-656ca0887447", "8bb6e3f4-974d-4775-8336-db4315be98b7",
         "aaaf2205-cc31-4d31-a214-e5c16288cc0a", "15a3228f-4dcd-45fb-9be3-6711c3808e52",
         "315575e2-5341-4887-91bf-f125180ca2f3"]


def in_list(ids: list[str]) -> str:
    return ", ".join(f"'{i}'" for i in ids)


STEPS = [
    ("credentials under those clients",
     f"DELETE FROM api_credentials WHERE client_id IN ({in_list(CLIENTS)})"),
    ("api_clients", f"DELETE FROM api_clients WHERE id IN ({in_list(CLIENTS)})"),
    ("external_systems", f"DELETE FROM external_systems WHERE id IN ({in_list(SYSTEMS)})"),
    # Assignments carry project_id/organization_id foreign keys, so they go
    # before the scopes they point at.
    ("role assignments",
     f"DELETE FROM user_role_assignments WHERE user_id IN ({in_list(USERS)})"),
    ("projects", f"DELETE FROM projects WHERE id IN ({in_list(PROJECTS)})"),
    ("organizations", f"DELETE FROM organizations WHERE id IN ({in_list(ORGS)})"),
    ("users", f"DELETE FROM users WHERE id IN ({in_list(USERS)})"),
]

for label, sql in STEPS:
    armfull.psql(armfull.SUITE_DB, sql)
    print(f"deleted {label}")

CHECKS = [
    ("api_clients", f"SELECT count(*) FROM api_clients WHERE id IN ({in_list(CLIENTS)})"),
    ("external_systems", f"SELECT count(*) FROM external_systems WHERE id IN ({in_list(SYSTEMS)})"),
    ("projects", f"SELECT count(*) FROM projects WHERE id IN ({in_list(PROJECTS)})"),
    ("organizations", f"SELECT count(*) FROM organizations WHERE id IN ({in_list(ORGS)})"),
    ("users", f"SELECT count(*) FROM users WHERE id IN ({in_list(USERS)})"),
    ("any be019 row left", "SELECT count(*) FROM users WHERE username LIKE 'be019-%'"),
]
for label, sql in CHECKS:
    print(f"remaining {label}: {armfull.psql(armfull.SUITE_DB, sql)}")
