"""BE-035 Phase F/G worker+ledger smoke against a DISPOSABLE clone as poa_runtime.

Targets only the named clone DB (asserted). Never pofa_dev/pofa_test.
"""
import os, sys

REPO = r"D:\CODING\Projects\Proof-Of-Action-Final"
sys.path.insert(0, REPO)

CLONE = "poa_b035_restore"
assert CLONE in os.environ["DATABASE_URL"], "refusing: not pointed at the disposable clone"

from backend.core.config import settings  # noqa: E402
assert CLONE in settings.database_url, f"settings.url={settings.database_url}"

from sqlalchemy import text  # noqa: E402
from backend.db.session import build_guarded_engine  # noqa: E402
from backend.services import audit_ledger as audit_service  # noqa: E402

eng = build_guarded_engine(settings.database_url)

with eng.connect() as c:
    ident = c.execute(text("SELECT current_user, session_user")).one()
    print("IDENTITY", ident[0], ident[1])
    pre = c.execute(text("SELECT count(*) FROM public.audit_ledger_events")).scalar()
    print("LEDGER_COUNT_PRE", pre)

# Baseline classification (read-only) BEFORE append
from backend.db import session as sess  # noqa: E402
sess._engine = eng
sess._SessionLocal = None
db = sess.get_session()
cls_pre = audit_service.verify_chain_classified(db, "pofa-dev-pre-be030-test-cleanup")
k = cls_pre["classification"]
print("CLASSIFY_PRE", k["status"], "known=", len(k["known_historical_gaps"]),
      "new=", len(k["new_gaps"]), "hard=", len(k["hard_anomalies"]),
      "writer_policy=", cls_pre["writer_policy"])
db.close()

# Legitimate append through the REAL app path (event_type from AUDIT_EVENT_TYPES)
from backend.db.models import AUDIT_EVENT_TYPES  # noqa: E402
etype = sorted(AUDIT_EVENT_TYPES)[0]
import uuid  # noqa: E402
rid = str(uuid.uuid4())
db = sess.get_session()
try:
    ev = audit_service.append_event(
        db, event_type=etype, action="verify", resource_type="be035_smoke",
        resource_id=rid, actor_id=None, project_id=None,
        payload={"note": "BE-035 clone append smoke"}, source="be035_probe",
        commit=True,
    )
    print("APPEND_OK", "seq=", ev.sequence_number, "event_type=", ev.event_type,
          "hash=", str(ev.event_hash)[:16])
except Exception as e:
    print("APPEND_FAIL", type(e).__name__, str(e)[:200])
finally:
    db.close()

# After append: count + classification (must stay known_historical_only, no new gaps)
db = sess.get_session()
with eng.connect() as c:
    post = c.execute(text("SELECT count(*) FROM public.audit_ledger_events")).scalar()
cls_post = audit_service.verify_chain_classified(db, "pofa-dev-pre-be030-test-cleanup")
kp = cls_post["classification"]
print("LEDGER_COUNT_POST", post)
print("CLASSIFY_POST", kp["status"], "known=", len(kp["known_historical_gaps"]),
      "new=", len(kp["new_gaps"]), "hard=", len(kp["hard_anomalies"]))
db.close()

# Denial checks: UPDATE/DELETE/TRUNCATE on the ledger must be refused (append-only).
for label, sql in [
    ("UPDATE", "UPDATE public.audit_ledger_events SET action='tamper' WHERE sequence_number=1"),
    ("DELETE", "DELETE FROM public.audit_ledger_events WHERE sequence_number=1"),
    ("TRUNCATE", "TRUNCATE TABLE public.audit_ledger_events"),
]:
    try:
        with eng.connect() as c:
            c.execute(text(sql))
            c.commit()
        print(f"DENIAL_{label}", "NOT-DENIED(!)")
    except Exception as e:
        print(f"DENIAL_{label}", "DENIED", type(e).__name__, str(e).splitlines()[0][:80])

# Ordinary-table write must be permitted (workers mutate ordinary tables).
try:
    with eng.connect() as c:
        c.execute(text("UPDATE public.users SET updated_at = updated_at WHERE id = "
                       "(SELECT id FROM public.users ORDER BY id LIMIT 1)"))
        c.commit()
    print("ORDINARY_WRITE", "PERMITTED")
except Exception as e:
    print("ORDINARY_WRITE", "FAIL", type(e).__name__, str(e).splitlines()[0][:80])

# Elevation must be refused.
try:
    with eng.connect() as c:
        c.execute(text("SET ROLE postgres"))
    print("SET_ROLE_POSTGRES", "ALLOWED(!)")
except Exception as e:
    print("SET_ROLE_POSTGRES", "DENIED", str(e).splitlines()[0][:80])

eng.dispose()
print("SMOKE_DONE")
