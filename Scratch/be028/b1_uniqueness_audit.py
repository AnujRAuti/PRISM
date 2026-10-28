"""BE-028 §7/§8/§9 measurement: users uniqueness, ORM vs DB, duplicates.

Read-only. Never writes. Targets are passed explicitly so there is no chance
of touching an unintended database.
"""
import sys
from sqlalchemy import create_engine, text

TARGETS = {
    "pofa_test": "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test",
    "pofa_dev": "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev",
}

CONSTRAINTS = """
SELECT c.conname, c.contype,
       pg_get_constraintdef(c.oid) AS def
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE n.nspname = 'public' AND c.conrelid = 'public.users'::regclass
ORDER BY c.contype, c.conname
"""

INDEXES = """
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'users'
ORDER BY indexname
"""

COLUMNS = """
SELECT column_name, is_nullable, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_schema='public' AND table_name='users'
ORDER BY ordinal_position
"""

TOTAL = "SELECT count(*) FROM users"

DUP = """
SELECT count(*) AS groups, coalesce(sum(n),0) AS rows_in_groups,
       coalesce(sum(n-1),0) AS redundant_rows
FROM (SELECT {col} AS v, count(*) AS n FROM users GROUP BY {col} HAVING count(*) > 1) t
WHERE v IS NOT NULL
"""

DUPNULL = "SELECT count(*) FROM users WHERE {col} IS NULL"
DUPEMPTY = "SELECT count(*) FROM users WHERE {col} = ''"
DUPWS = "SELECT count(*) FROM users WHERE {col} ~ '^\\s+$'"

CASEDUP = """
SELECT count(*) FROM (
  SELECT lower({col}) AS v, count(*) FROM users
  WHERE {col} IS NOT NULL AND {col} <> ''
  GROUP BY lower({col}) HAVING count(*) > 1
) t
"""

NORMDUP = """
SELECT count(*) FROM (
  SELECT v, count(*) FROM (
    SELECT regexp_replace(lower(trim(email)), '\\+[^@]*', '', 'g') AS v
    FROM users WHERE email IS NOT NULL AND email <> ''
  ) x GROUP BY v HAVING count(*) > 1
) t
"""

print("ORM declares: users.username unique+index NOT NULL, users.email unique+index NOT NULL,")
print("             UniqueConstraint(identity_provider, external_subject) uq_user_identity_subject,")
print("             CheckConstraint status IN (ACTIVE,SUSPENDED,DISABLED) ck_user_status")

for name, url in TARGETS.items():
    if len(sys.argv) > 1 and name not in sys.argv:
        continue
    e = create_engine(url)
    print("\n" + "=" * 78)
    print(f"DATABASE {name}")
    with e.connect() as c:
        print("total users:", c.execute(text(TOTAL)).scalar())
        print("\n-- constraints on users --")
        for row in c.execute(text(CONSTRAINTS)):
            print(f"   {row[1]}  {row[0]}  :: {row[2]}")
        print("\n-- indexes on users --")
        for row in c.execute(text(INDEXES)):
            print(f"   {row[0]} :: {row[1]}")
        print("\n-- columns --")
        for row in c.execute(text(COLUMNS)):
            print(f"   {row[0]:22} null={row[1]:3} {row[2]}({row[3]})")
        for col in ("username", "email"):
            g = c.execute(text(DUP.format(col=col))).mappings().one()
            print(f"\n-- {col} --")
            print(f"   duplicate groups={g['groups']} rows_in_groups={g['rows_in_groups']} "
                  f"redundant={g['redundant_rows']}")
            print(f"   NULL={c.execute(text(DUPNULL.format(col=col))).scalar()} "
                  f"empty={c.execute(text(DUPEMPTY.format(col=col))).scalar()} "
                  f"whitespace={c.execute(text(DUPWS.format(col=col))).scalar()}")
            print(f"   case-insensitive duplicate groups="
                  f"{c.execute(text(CASEDUP.format(col=col))).scalar()}")
        if name != "skip":
            print(f"\n-- email normalised (lower + strip +tag) duplicate groups="
                  f"{c.execute(text(NORMDUP)).scalar()}")
    e.dispose()
