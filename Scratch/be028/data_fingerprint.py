"""BE-028 §33: data-state fingerprint for one database (read-only).

Produces the numbers the task file requires before and after a migration:
row counts (per affected table and a whole-schema total), primary-key and
foreign-key counts, null counts on the columns the BE-028 indexes cover, and
the duplicate counts that make B-1 a blocker. Nothing here writes.
"""
import sys

from sqlalchemy import create_engine, text

AFFECTED = ["analysis_jobs", "evidence_metadata", "projects", "users"]

SQL = {
    "exact_rows": "SELECT count(*) FROM {table}",
    "pk_count": "SELECT count(*) FROM pg_constraint WHERE contype='p'",
    "fk_count": "SELECT count(*) FROM pg_constraint WHERE contype='f'",
    "uq_count": "SELECT count(*) FROM pg_constraint WHERE contype='u'",
    "nulls": """
        SELECT
          (SELECT count(*) FROM users WHERE username IS NULL)      AS u_username_null,
          (SELECT count(*) FROM users WHERE email IS NULL)        AS u_email_null,
          (SELECT count(*) FROM projects WHERE name IS NULL)      AS p_name_null,
          (SELECT count(*) FROM analysis_jobs WHERE status IS NULL) AS aj_status_null,
          (SELECT count(*) FROM evidence_metadata WHERE evidence_id IS NULL) AS em_evidence_null
    """,
    "duplicates": """
        SELECT
          (SELECT count(*) FROM (SELECT email FROM users GROUP BY email HAVING count(*) > 1) d) AS email_groups,
          (SELECT coalesce(sum(c),0) FROM (SELECT count(*) AS c FROM users GROUP BY email HAVING count(*) > 1) d) AS email_rows,
          (SELECT count(*) FROM (SELECT username FROM users GROUP BY username HAVING count(*) > 1) d) AS username_groups,
          (SELECT coalesce(sum(c),0) FROM (SELECT count(*) AS c FROM users GROUP BY username HAVING count(*) > 1) d) AS username_rows
    """,
    "index_presence": """
        SELECT indexname FROM pg_indexes
        WHERE schemaname='public' AND indexname = ANY(:t)
        ORDER BY indexname
    """,
    "alembic_version": "SELECT version_num FROM alembic_version",
}

BE028_INDEXES = [
    "ix_analysis_jobs_status",
    "ix_evidence_metadata_evidence_id",
    "ix_projects_name",
]


def main(url: str, label: str) -> None:
    engine = create_engine(url)
    print(f"=== {label} ===")
    with engine.connect() as c:
        print("schema        ", c.execute(text(SQL["alembic_version"])).scalars().one_or_none())
        for t in AFFECTED:
            print(f"rows {t:<20}", c.execute(text(SQL["exact_rows"].format(table=t))).scalar())
        print("indexes present", [r for (r,) in c.execute(text(SQL["index_presence"]), {"t": BE028_INDEXES})])
        print("pk/fk/uq      ", [c.execute(text(SQL[k])).scalar() for k in ("pk_count", "fk_count", "uq_count")])
        print("nulls         ", dict(c.execute(text(SQL["nulls"])).mappings().first()))
        print("duplicates    ", dict(c.execute(text(SQL["duplicates"])).mappings().first()))
    engine.dispose()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
