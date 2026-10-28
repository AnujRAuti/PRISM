"""BE-029 pre-live: run the production audit-chain verifier against one database.

Usage: python chain_probe.py <postgres-url>
Read-only: the SQLAlchemy connection is put in a READ ONLY session before
verify_chain() runs, and verify_chain() itself only SELECTs.
"""
import sys

from alembic.config import Config  # noqa: F401  (import check for env sanity)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "D:/CODING/Projects/Proof-Of-Action-Final")
from backend.services.audit_ledger import verify_chain  # noqa: E402

URL = sys.argv[1].replace("postgresql://", "postgresql+psycopg2://")
engine = create_engine(URL)
with engine.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    db = sessionmaker(bind=conn)()
    result = verify_chain(db)
    database = db.execute(text("SELECT current_database()")).scalar_one()
    rows = db.execute(text("SELECT count(*), min(sequence_number), max(sequence_number) "
                           "FROM audit_ledger_events")).one()

print(f"database={database} rows={rows[0]} span={rows[1]}..{rows[2]}")
print(f"valid={result['valid']} checked={result['checked_events']} "
      f"failures={len(result['failures'])}")
for failure in result["failures"][:12]:
    print("  -", failure)
