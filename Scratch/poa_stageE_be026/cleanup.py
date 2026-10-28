"""Remove every row one Stage E run created, by LABEL alone.

A crashed probe loses its in-process tracking list, so cleanup has to be
derivable from the labels the run wrote. Audit ledger rows are never touched.
"""

import os
import sys

from sqlalchemy import create_engine, text

LABEL = os.environ.get("LABEL") or sys.exit("LABEL required")
engine = create_engine(os.environ["DATABASE_URL"])

USERS = f"se-{LABEL}-%"
ORGS = f"se-{LABEL}-%"
PROJECTS = f"SE {LABEL} %"
CLIENTS = f"se {LABEL} %"


def main():
    with engine.begin() as c:
        p = {"u": USERS, "pr": PROJECTS, "o": ORGS, "cl": CLIENTS}
        ops = c.execute(text("delete from field_capture_operations where user_id in"
                             " (select id from users where username like :u)"), p).rowcount
        sess = c.execute(text("delete from field_sessions where user_id in"
                              " (select id from users where username like :u)"
                              " or project_id in (select id from projects where name like :pr)"),
                         p).rowcount
        assign = c.execute(text("delete from field_assignments where user_id in"
                                " (select id from users where username like :u)"
                                " or project_id in (select id from projects where name like :pr)"),
                           p).rowcount
        # quarantine objects belonging to this run's evidence
        keys = [r[0] for r in c.execute(
            text("select storage_key from evidence where project_id in"
                 " (select id from projects where name like :pr)"
                 " and storage_key is not null"), p)]
        c.execute(text("delete from evidence_metadata where evidence_id in"
                       " (select id from evidence where project_id in"
                       " (select id from projects where name like :pr))"), p)
        c.execute(text("delete from analysis_results where job_id in"
                       " (select id from analysis_jobs where evidence_id in"
                       " (select id from evidence where project_id in"
                       " (select id from projects where name like :pr)))"), p)
        aj = c.execute(text("delete from analysis_jobs where evidence_id in"
                            " (select id from evidence where project_id in"
                            " (select id from projects where name like :pr))"), p).rowcount
        ev = c.execute(text("delete from evidence where project_id in"
                            " (select id from projects where name like :pr)"), p).rowcount
        act = c.execute(text("delete from activities where project_id in"
                             " (select id from projects where name like :pr)"), p).rowcount
        cl = c.execute(text("delete from claims where project_id in"
                            " (select id from projects where name like :pr)"), p).rowcount
        pr = c.execute(text("delete from user_role_assignments where project_id in"
                            " (select id from projects where name like :pr)"), p).rowcount
        pr2 = c.execute(text("delete from projects where name like :pr"), p).rowcount
        units = c.execute(text("delete from user_role_assignments where"
                               " organizational_unit_id in (select id from organizational_units"
                               " where code like :o)"), p).rowcount
        un = c.execute(text("delete from organizational_units where code like :o"), p).rowcount
        orgs = c.execute(text("delete from user_role_assignments where organization_id in"
                              " (select id from organizations where code like :o)"), p).rowcount
        og = c.execute(text("delete from organizations where code like :o"), p).rowcount
        usr = c.execute(text("delete from user_role_assignments where user_id in"
                             " (select id from users where username like :u)"), p).rowcount
        us = c.execute(text("delete from users where username like :u"), p).rowcount
        clients = c.execute(text("delete from api_clients where name like :cl"), p).rowcount
    removed = {"operations": ops, "sessions": sess, "assignments": assign,
               "evidence": ev, "analysis_jobs": aj, "activities": act, "claims": cl,
               "role_rows(projects/units/orgs/users)": (pr, units, orgs, usr),
               "projects": pr2, "units": un, "orgs": og, "users": us, "clients": clients}
    print("removed:", removed)
    if keys:
        from backend.core.config import settings
        import boto3
        s3 = boto3.client("s3", endpoint_url=settings.s3_endpoint,
                          aws_access_key_id=settings.s3_access_key,
                          aws_secret_access_key=settings.s3_secret_key)
        for key in keys:
            s3.delete_object(Bucket=settings.s3_quarantine_bucket, Key=key)
        print(f"quarantine objects deleted: {len(keys)}")
    leftover = {}
    with engine.connect() as c:
        p = {"u": USERS, "pr": PROJECTS, "o": ORGS}
        for name, sql in (
            ("field_capture_operations",
             "select count(*) from field_capture_operations where user_id in"
             " (select id from users where username like :u)"),
            ("field_sessions", "select count(*) from field_sessions where user_id in"
             " (select id from users where username like :u)"),
            ("field_assignments", "select count(*) from field_assignments where user_id in"
             " (select id from users where username like :u)"),
            ("evidence", "select count(*) from evidence where project_id in"
             " (select id from projects where name like :pr)"),
            ("projects", "select count(*) from projects where name like :pr"),
            ("users", "select count(*) from users where username like :u"),
            ("orgs", "select count(*) from organizations where code like :o"),
        ):
            leftover[name] = c.execute(text(sql), p).scalar()
    print("leftover:", leftover)
    return 0 if not any(leftover.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
