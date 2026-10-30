"""PRISM Phase 3 step 1: map the real reviewer subject onto a least-privileged user.

The mapping is the pair ``backend/security/oidc.py`` resolve_oidc_principal looks up:
``users.identity_provider`` must equal ``AUTH_OIDC_IDENTITY_PROVIDER`` and
``users.external_subject`` must equal the verified token's ``sub``, and the resolved
user must be ACTIVE. There is no auto-provisioning on purpose - a token that verifies
but maps to nobody is refused - so this creates the row the provider token needs.

Least privilege is the point: exactly one user, exactly one PROJECT-scoped REVIEWER
assignment, no ADMINISTRATOR, no GLOBAL grant, and the project is the reviewer's own
so nothing here reaches anyone else's data.

Safety: refuses to run against anything that is not a test or disposable database, and
never against poa_prod or pofa_dev. The subject and email come from a local file that
is gitignored, because they are personal data and must not enter the repository this
mission just cleaned.

    python Scratch/prism2/phase3_provision.py [--apply] <identity_provider> <subject_file>
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.core.config import settings
from backend.db.models import Project, User
from backend.db.session import get_session
from backend.repositories import authorization as auth_repo
from backend.services import authorization as authz

ALLOWED_DATABASES = {"pofa_test", "poa_disp_oidc", "pofa_disp"}
FORBIDDEN = {"poa_prod", "pofa_dev", "poa_owner", "postgres"}
USERNAME = "prism-reviewer"
ROLE_NAME = "REVIEWER"


def database_name() -> str:
    url = str(settings.database_url)
    return url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]


def report_principal(db, user_id: str) -> None:
    """Print what the verifier will resolve, in the same shape /auth/me answers."""
    principal = authz.resolve_user_principal(db, user_id)
    assignments = auth_repo.assignments_for_user(db, user_id)
    role_rows = auth_repo.roles_by_ids(db, sorted({str(a.role_id) for a in assignments}))
    scopes = [
        f"{role_rows[str(a.role_id)].name}@{a.scope_type}"
        + (f":{str(a.project_id)[:8]}" if a.project_id else "")
        for a in assignments if str(a.role_id) in role_rows
    ]
    print(f"principal               : authenticated={principal.authenticated} "
          f"type={principal.principal_type} status={principal.status} "
          f"display={principal.display_name!r}")
    print(f"grants                  : {scopes}")
    print(f"permissions             : {sorted(principal.permissions)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("provider")
    parser.add_argument("subject_file")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    name = database_name()
    if name in FORBIDDEN or name not in ALLOWED_DATABASES:
        print(f"REFUSED: DATABASE_URL points at {name!r}; only {sorted(ALLOWED_DATABASES)} "
              f"are acceptable and {sorted(FORBIDDEN)} are never acceptable.")
        return 2
    if settings.auth_oidc_enabled and args.provider != settings.auth_oidc_identity_provider:
        print(f"REFUSED: the mapping key is the provider name, and this process is "
              f"configured for {settings.auth_oidc_identity_provider!r}, not "
              f"{args.provider!r}. A row keyed to another provider can never resolve.")
        return 2

    with open(args.subject_file, encoding="utf-8") as fh:
        identity = json.load(fh)
    subject, email = identity["external_subject"], identity["email"]

    db = get_session()
    try:
        # Ask the server, not the DSN string: the guard has to hold even if the
        # environment resolved to a different database than it looks like.
        from sqlalchemy import text

        server_db = str(db.execute(text("SELECT current_database()")).scalar_one())
        if server_db in FORBIDDEN or server_db not in ALLOWED_DATABASES:
            print(f"REFUSED: the connected database is {server_db!r}; this script only writes "
                  f"to {sorted(ALLOWED_DATABASES)} and never to {sorted(FORBIDDEN)}.")
            return 2

        role = auth_repo.get_role_by_name(db, ROLE_NAME)
        print(f"database (server-confirmed): {server_db}  [dsn said {name}]")
        print(f"configured provider      : {settings.auth_oidc_identity_provider}")
        print(f"role '{ROLE_NAME}' seeded    : {role.id if role else 'MISSING'}")
        if role is None:
            print("REFUSED: the catalogue is not seeded on this database.")
            return 2

        existing = db.query(User).filter(User.external_subject == subject).one_or_none()
        print(f"rows with this subject   : "
              f"{existing.username + ' / status=' + existing.status + ' / provider=' + existing.identity_provider if existing else 'none'}")
        projects = db.query(Project).order_by(Project.id).all()
        print(f"projects                 : {len(projects)} "
              f"{[str(p.id)[:8] for p in projects[:3]]}")
        if not args.apply:
            print("\nDRY RUN - nothing written. Re-run with --apply.")
            return 0

        user = existing
        if user is None:
            user = authz.create_user(
                db, username=USERNAME, email=email, display_name="PRISM reviewer probe",
                external_subject=subject, identity_provider=args.provider, actor_id=None)
            print(f"created user             : id={user.id} status={user.status}")
        else:
            print(f"reusing user             : id={user.id} status={user.status}")

        owned = [p for p in projects if str(p.owner_id) == str(user.id)]
        if owned:
            project = owned[0]
            print(f"scoping to project       : id={project.id} (already owned)")
        elif projects:
            # Never scope a reviewer onto someone else's project: create their own.
            project = authz.create_project(
                db, name="PRISM reviewer scope", owner_id=str(user.id))
            print(f"created project          : id={project.id} owner={user.id}")
        else:
            org = authz.create_organization(
                db, name="PRISM disposable org", code="prism-disp")
            project = authz.create_project(
                db, name="PRISM reviewer scope", owner_id=str(user.id))
            print(f"created org+project      : org={org.id} project={project.id}")

        assignment, created = authz.assign_role(
            db, user_id=str(user.id), role_name=ROLE_NAME, scope_type="PROJECT",
            project_id=str(project.id), actor_id=None)
        # assign_role deliberately does not commit (backend/services/authorization.py):
        # without this the grant existed only in this session and would have been
        # discarded on close while the lines below still reported success.
        db.commit()
        fresh = get_session()
        try:
            from sqlalchemy import text as _text

            persisted = fresh.execute(
                _text("select count(*) from user_role_assignments where user_id = :u"),
                {"u": str(user.id)}).scalar_one()
        finally:
            fresh.close()
        print(f"granted                  : {ROLE_NAME} at PROJECT scope "
              f"(assignment={assignment.id}, newly_created={created})")
        print(f"persisted assignments    : {persisted} (read back on a new session)")
        if not persisted:
            print("FAILED: the grant did not persist; do not use this identity for the token test.")
            return 1
        report_principal(db, str(user.id))
        print(f"project id for the token test: {project.id}")
        print("\nAPPLIED. Rollback: delete this user's user_role_assignments rows and "
              "the user row printed above, or drop the disposable database.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
