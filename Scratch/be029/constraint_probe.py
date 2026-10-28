"""Post-migration behavioural check on real migrated dev data.

pofa_dev (post-BE-029) was cloned into pofa_be029_devpost, so this exercises
the new unique indexes against real production-shaped user rows rather than
test fixtures. Every insert runs in a SAVEPOINT that is rolled back, and the
outer transaction is rolled back too.
"""
import sys

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")

import sqlalchemy as sa

URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_be029_devpost"
INSERT = sa.text(
    "INSERT INTO users (id, username, email, status, identity_provider)"
    " VALUES (gen_random_uuid(), :u, :e, 'ACTIVE', 'local')"
)

engine = sa.create_engine(URL)
problems = []

with engine.connect() as conn:
    db = conn.execute(sa.text("SELECT current_database()")).scalar()
    if db != "pofa_be029_devpost":
        raise SystemExit(f"refusing to run: connected to {db}, not the clone")
    print("current_database():", db)

    before = int(conn.execute(sa.text("SELECT count(*) FROM users")).scalar())
    print("users rows before:", before)

    source = conn.execute(sa.text(
        "SELECT username, email FROM users WHERE identity_provider = 'local'"
        " ORDER BY created_at LIMIT 1")).fetchone()

    def attempt(username, email):
        """Returns 'accepted' or 'rejected (<postgres exception class>)'."""
        savepoint = conn.begin_nested()
        try:
            conn.execute(INSERT, {"u": username, "e": email})
            outcome = "accepted"
        except Exception as exc:  # noqa: BLE001
            outcome = f"rejected ({type(getattr(exc, 'orig', exc)).__name__})"
        savepoint.rollback()
        return outcome

    checks = [
        ("duplicate an existing username", attempt(source.username,
                                                   "probe-only-unused@probe.invalid"), "rejected"),
        ("duplicate an existing email", attempt("probe-only-unused-username",
                                                source.email), "rejected"),
        ("brand-new username + email", attempt("probe-only-unused-username-b",
                                               "probe-only-unused-b@probe.invalid"), "accepted"),
    ]
    conn.rollback()

    for label, result, expected in checks:
        ok = result.startswith(expected)
        print(f"  {label}: {result}  [expected {expected}]  {'OK' if ok else 'MISMATCH'}")
        if not ok:
            problems.append(f"{label}: expected {expected}, got {result}")

    after = int(conn.execute(sa.text("SELECT count(*) FROM users")).scalar())
    print("users rows after:", after)
    if after != before:
        problems.append(f"probe changed the row count ({before} -> {after})")

print("\nVERDICT:", "unique identity constraint behaves as designed against real"
      " migrated dev rows" if not problems else "PROBLEMS: " + "; ".join(problems))
engine.dispose()
sys.exit(0 if not problems else 1)
