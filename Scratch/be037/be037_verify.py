import sys
sys.path.insert(0, r"D:/CODING/Projects/Proof-Of-Action-Final")
from sqlalchemy import text, create_engine
from backend.db.session import get_session
from backend.services import audit_ledger as al

print("== RUNTIME IDENTITY (poa_runtime, from app .env) — read-only ==")
db = get_session()
print("identity:", db.execute(text("select current_database(), current_user")).one())
print("ledger:", db.execute(text("select count(*) rows, min(sequence_number) mn, max(sequence_number) mx from audit_ledger_events")).one())
priv = db.execute(text("select "
    "has_table_privilege(current_user,'audit_ledger_events','SELECT') sel,"
    "has_table_privilege(current_user,'audit_ledger_events','INSERT') ins,"
    "has_table_privilege(current_user,'audit_ledger_events','UPDATE') upd,"
    "has_table_privilege(current_user,'audit_ledger_events','DELETE') del,"
    "has_table_privilege(current_user,'audit_ledger_events','TRUNCATE') trn,"
    "has_table_privilege(current_user,'alembic_version','SELECT') av_sel")).one()
print("privs(sel,ins,upd,del,trunc,alembic_sel):", tuple(priv))
res = al.verify_chain_classified(db, "pofa-dev-pre-be030-test-cleanup")
print("verify.valid =", res.get("valid"), "checked =", res.get("checked_events"),
      "failures =", len(res.get("failures", [])), "writer_policy =", res.get("writer_policy"))
cp = res.get("checkpoint") or {}
print("verify.checkpoint rows/min_seq/tail_hash =", cp.get("rows"), cp.get("min_sequence"), (cp.get("tail_event_hash") or "")[:12])
cls = res.get("classification") or {}
print("classification.status =", cls.get("status"))
print("classification.degraded =", cls.get("degraded"))
print("classification known_gaps =", len(cls.get("known_historical_gaps", [])),
      "new_gaps =", len(cls.get("new_gaps", [])),
      "hard_anomalies =", len(cls.get("hard_anomalies", [])))
print("classification keys:", sorted(cls.keys()))
print("baseline:", cls.get("baseline_name"), "@", cls.get("baseline_version"))
db.close()

print("\n== OWNER IDENTITY (read-only) — migration bookkeeping the runtime cannot see ==")
eng = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_dev")
with eng.connect() as c:
    print("owner:", c.execute(text("select current_database(), current_user")).one())
    print("alembic version_num:", c.execute(text("select version_num from alembic_version")).scalars().all())
    print("is_trusted/rolemembers(poarta?):", c.execute(text("select rolname, rolsuper, rolcanlogin from pg_roles where rolname in ('postgres','poa_runtime') order by 1")).all())
eng.dispose()
