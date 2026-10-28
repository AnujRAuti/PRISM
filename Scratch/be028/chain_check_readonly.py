"""BE-028 §31: re-validate the audit chain on the real databases, read-only.

verify_chain() only SELECTs, so this is safe against pofa_test and pofa_dev.
Prints the ledger size, sequence span and validity, so "audit integrity did not
change" is a measurement instead of an assumption.
"""
import sys

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.services import audit_ledger as audit_service  # noqa: E402

for url in sys.argv[1:]:
    engine = create_engine(url)
    with Session(bind=engine) as session:
        rows = session.execute(text("SELECT count(*) FROM audit_ledger_events")).scalar()
        span = session.execute(
            text("SELECT min(sequence_number), max(sequence_number) FROM audit_ledger_events")
        ).first()
        schema = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        result = audit_service.verify_chain(session)
        failures = result.get("failures") or []
        print(f"--- {url.rsplit('/', 1)[-1]} ---")
        print(f"  schema={schema} ledger rows={rows} sequence span={span}")
        print(f"  verify_chain: valid={result['valid']} failures={len(failures)}")
        for failure in failures[:3]:
            print("   ", dict(failure) if hasattr(failure, "keys") else failure)
    engine.dispose()
