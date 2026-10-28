import os
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev"
os.environ.setdefault("ENVIRONMENT", "development")
from backend.db.session import get_session
from backend.services import audit_ledger as svc
from backend.services.audit_integrity_baseline import POFA_DEV_HISTORICAL_BASELINE
s = get_session()
try:
    r = svc.verify_chain_classified(s, POFA_DEV_HISTORICAL_BASELINE.name)
    c = r["classification"]
    print("valid=", r.get("valid"))
    print("status=", c["status"])
    print("degraded=", c["degraded"])
    print("known_historical_gaps=", len(c["known_historical_gaps"]))
    print("new_gaps=", len(c["new_gaps"]))
    print("hard_anomalies=", len(c["hard_anomalies"]))
    print("baseline=", c["baseline_name"], "v", c["baseline_version"])
finally:
    s.close()
