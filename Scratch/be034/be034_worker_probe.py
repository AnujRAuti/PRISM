"""BE-034 worker-identity probe (bounded; no network delivery).

Confirms the pieces the webhook worker needs, under the non-owner poa_runtime
identity on the disposable clone: (1) its audit event types append through the
shared append_event path, and (2) it holds UPDATE on the ordinary delivery-status
table. run_worker_once() is NOT executed because it performs real outbound
webhook HTTP; the ledger/DML permissions are what the F-05 identity gate changes.
"""
from sqlalchemy import text

from backend.core.config import settings
from backend.db import session as dbsess
from backend.services import audit_ledger as al

assert "poa_b034_clone" in settings.database_url
db = dbsess.get_session()
who = db.execute(text("SELECT current_user")).scalar()
before = db.execute(text("SELECT count(*) FROM audit_ledger_events")).scalar()

row = al.append_event(
    db,
    event_type="WEBHOOK_DELIVERY_SUCCEEDED",
    action="deliver",
    resource_type="webhook_delivery",
    payload={"milestone": "BE-034", "source": "webhook_worker", "success": True},
    source="webhook_worker",
    commit=True,
)
after = db.execute(text("SELECT count(*) FROM audit_ledger_events")).scalar()
print(f"worker_identity current_user={who} ledger {before}->{after} seq={row.sequence_number} type={row.event_type}")

# The delivery-status table the worker writes to (ordinary DML, not the ledger).
upd = db.execute(
    text("SELECT has_table_privilege(current_user, 'webhook_deliveries', 'UPDATE')")
).scalar()
ins = db.execute(
    text("SELECT has_table_privilege(current_user, 'webhook_deliveries', 'INSERT')")
).scalar()
print(f"webhook_deliveries privilege: insert={ins} update={upd}")

res = al.verify_chain_classified(db, "pofa-dev-pre-be030-test-cleanup")
cls = res["classification"]
print(f"classify valid={res.get('valid')} status={cls['status']} degraded={cls['degraded']} "
      f"known={len(cls['known_historical_gaps'])} new={len(cls['new_gaps'])} hard={len(cls['hard_anomalies'])}")
db.close()
print("DONE")
