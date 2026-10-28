"""BE-034 runtime-identity append probe.

Drives the application's OWN append path (services.audit_ledger.append_event, the
function every endpoint and worker calls) while the process connects to the
disposable clone as the non-owner poa_runtime identity. Proves: reads work, an
authorized append succeeds and chains, the whole-chain classifier still reports
known_historical_only, and a direct tamper is refused. Never targets a protected DB.
"""
import sys
from sqlalchemy import text

from backend.core.config import settings

target = settings.database_url.rsplit("/", 1)[-1]
assert "poa_b034_clone" in settings.database_url, f"WRONG TARGET: {target}"
print(f"connected_target={target} environment={settings.environment}")

from backend.db import session as dbsess
from backend.services import audit_ledger as al

db = dbsess.get_session()
who = db.execute(text("SELECT current_user")).scalar()
before = db.execute(text("SELECT count(*) FROM audit_ledger_events")).scalar()
print(f"current_user={who} ledger_before={before}")

row = al.append_event(
    db,
    event_type="ANALYSIS_COMPLETED",
    action="BE034_RUNTIME_IDENTITY_APPEND_PROBE",
    resource_type="cutover_probe",
    payload={"milestone": "BE-034", "identity": str(who)},
    commit=True,
)
after = db.execute(text("SELECT count(*) FROM audit_ledger_events")).scalar()
print(f"appended_seq={row.sequence_number} event_type={row.event_type} ledger_after={after}")

# Read the appended row back through the same runtime session.
rb = db.execute(
    text("SELECT sequence_number, event_type, action, event_hash IS NOT NULL FROM "
         "audit_ledger_events WHERE sequence_number = :s"),
    {"s": row.sequence_number},
).first()
print(f"read_back={rb}")

res = al.verify_chain_classified(db, "pofa-dev-pre-be030-test-cleanup")
cls = res["classification"]
print(
    "classify: "
    f"valid={res.get('valid')} status={cls['status']} degraded={cls['degraded']} "
    f"known={len(cls['known_historical_gaps'])} new={len(cls['new_gaps'])} "
    f"hard={len(cls['hard_anomalies'])} writer_policy={res.get('writer_policy')}"
)

# A direct historical tamper through the runtime identity must be refused.
try:
    db.execute(
        text("UPDATE audit_ledger_events SET action = :a WHERE sequence_number = :s"),
        {"a": "TAMPER", "s": row.sequence_number},
    )
    db.commit()
    print("TAMPER_RESULT=ALLOWED (UNEXPECTED)")
except Exception as exc:  # noqa: BLE001
    db.rollback()
    print(f"TAMPER_RESULT=REFUSED {type(exc).__name__}: {str(exc).splitlines()[0][:120]}")

db.close()
print("DONE")
