import os
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/poa_b033_clone"
os.environ.setdefault("ENVIRONMENT", "development")
from backend.db.session import get_session
from backend.services import audit_ledger as svc
from backend.services.audit_integrity_baseline import POFA_DEV_HISTORICAL_BASELINE
s = get_session()
try:
    # Without baseline: every gap counts as new (default-deny).
    dn = svc.verify_chain_classified(s)
    print("no-baseline status=", dn["classification"]["status"],
          "new_gaps=", len(dn["classification"]["new_gaps"]),
          "hard=", len(dn["classification"]["hard_anomalies"]))
    r = svc.verify_chain_classified(s, POFA_DEV_HISTORICAL_BASELINE.name)
    c = r["classification"]
    print("with-baseline valid=", r.get("valid"), "status=", c["status"],
          "degraded=", c["degraded"], "known=", len(c["known_historical_gaps"]),
          "new=", len(c["new_gaps"]), "hard=", len(c["hard_anomalies"]),
          "checkpoint_rows=", (r.get("checkpoint") or {}).get("rows"))
finally:
    s.close()
