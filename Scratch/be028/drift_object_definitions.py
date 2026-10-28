"""BE-028 §13: real definitions of every object alembic check wants to touch.

Run against a PRISTINE scratch database migrated from base -> head, so what we
see is exactly what the migration chain produces (no manual pokes).
"""
from sqlalchemy import create_engine, text

URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be028_scratch"

INDEXES = """
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='public'
  AND indexname = ANY(:names)
ORDER BY tablename, indexname
"""

CONSTRAINTS = """
SELECT c.relname AS table_name, con.conname, con.contype,
       pg_get_constraintdef(con.oid) AS def
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname='public'
  AND con.conname = ANY(:names)
ORDER BY c.relname, con.conname
"""

# every unique constraint/index per table, to see what the chain really created
ALL_UNIQUE = """
SELECT c.relname AS table_name, con.conname, pg_get_constraintdef(con.oid) AS def
FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND con.contype='u'
  AND c.relname = ANY(:tables)
UNION ALL
SELECT i.tablename, i.indexname, i.indexdef
FROM pg_indexes i
WHERE i.schemaname='public' AND i.indexdef ILIKE '%UNIQUE%'
  AND i.tablename = ANY(:tables)
ORDER BY 1,2
"""

CHECKED_INDEXES = [
    "ix_evidence_claim", "ix_evidence_project", "ix_projects_owner",
    "uq_graph_relationships_dedupe_active", "uq_review_case_active_run",
    "ix_users_username", "ix_users_email", "ix_analysis_jobs_status",
    "ix_evidence_metadata_evidence_id", "ix_projects_name",
]
CHECKED_TABLES = [
    "duplicate_matches", "user_role_assignments", "evidence", "projects",
    "graph_relationships", "review_cases", "analysis_jobs", "evidence_metadata",
    "users",
]

e = create_engine(URL)
with e.connect() as c:
    print("== 1. definitions of the specific index objects in the drift list ==")
    for row in c.execute(text(INDEXES), {"names": CHECKED_INDEXES}):
        print(f"  {row[0]}.{row[1]}\n      {row[2]}")
    print("\n  (missing from the above = not created by the migration chain)")
    found = {r[1] for r in c.execute(text(INDEXES), {"names": CHECKED_INDEXES})}
    for n in CHECKED_INDEXES:
        if n not in found:
            print(f"   ABSENT: {n}")

    print("\n== 2. named unique constraints in the drift list ==")
    for row in c.execute(text(CONSTRAINTS), {"names": [
        "uq_duplicate_matches_pair", "uq_user_role_assignment_scope",
        "user_role_assignments_user_id_role_id_scope_type_organization_id_organi"
        "zational_unit_id_pro_key",
    ]}):
        print(f"  {row[0]} :: {row[1]} :: {row[3]}")

    print("\n== 3. every unique object on the affected tables (what the chain made) ==")
    for row in c.execute(text(ALL_UNIQUE), {"tables": CHECKED_TABLES}):
        print(f"  {row[0]} | {row[1]}\n      {row[2]}")

    print("\n== 4. spatial_ref_sys origin ==")
    print("  ", c.execute(text(
        "SELECT count(*) FROM information_schema.tables WHERE table_name='spatial_ref_sys'"
    )).scalar(), "row(s); srids:", c.execute(text("SELECT count(*) FROM spatial_ref_sys")).scalar())

    print("\n== 5. non-unique indexes the chain made on evidence/projects ==")
    for row in c.execute(text("""
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname='public' AND tablename = ANY(:t)
          AND indexdef NOT ILIKE '%UNIQUE%'
        ORDER BY tablename, indexname
    """), {"t": ["evidence", "projects", "analysis_jobs", "evidence_metadata"]}):
        print(f"  {row[0]}.{row[1]} :: {row[2]}")
e.dispose()
