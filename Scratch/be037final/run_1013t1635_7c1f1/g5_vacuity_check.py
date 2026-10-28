"""BE-037 G5 vacuity check (scratch, outside the repository).

Installs the OLD hook body (call the service with ``analysis_job_id``, catch
everything) next to the NEW one and runs both against the scenario the G5 unit
tests assert on: a completed job that no reprocessing request delegates.

Under the old code the service raises ``LookupError`` for that case and the
blanket ``except`` logs an ERROR with a traceback, which is precisely the
assertion the new tests make. If the old body produced no ERROR, the new tests
would be vacuous.
"""

import logging
import sys
from uuid import uuid4

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

import backend.workers.analysis_worker as aw
from backend.repositories import governance as governance_repo
from backend.services import governance as governance_service


class Job:
    def __init__(self) -> None:
        self.id = uuid4()


def old_hook_body(db, job):
    """Verbatim pre-fix implementation, including the wrong comment's intent."""
    try:
        governance_service.complete_reprocessing(
            db, analysis_job_id=str(job.id), completed_by=None
        )
    except Exception:
        aw.logger.exception("reprocessing completion hook failed job_id=%s", job.id)


def run(hook, label):
    records = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Collect(level=logging.DEBUG)
    aw.logger.addHandler(handler)
    previous = aw.logger.level
    aw.logger.setLevel(logging.DEBUG)
    try:
        hook(object(), Job())
    finally:
        aw.logger.removeHandler(handler)
        aw.logger.setLevel(previous)

    errors = [r for r in records if r.levelno >= logging.ERROR]
    with_tb = [r for r in records if r.exc_info]
    print(
        f"{label}: records={len(records)} "
        f"levels={[logging.getLevelName(r.levelno) for r in records]} "
        f"errors={len(errors)} with_traceback={len(with_tb)}"
    )
    return errors


# An unlinked job: the linkage query finds no request. The real service answers
# that with LookupError, so the fake reproduces the service's own behaviour.
governance_repo.lock_pending_reprocessing_for_job = lambda db, job_id: None


def service_raising_like_the_real_one(db, **kwargs):
    raise LookupError("Reprocessing request not found")


governance_service.complete_reprocessing = service_raising_like_the_real_one

old_errors = run(old_hook_body, "OLD hook (unlinked job)")
new_errors = run(aw._complete_reprocessing_hook, "NEW hook (unlinked job)")

# The old service call did not check linkage, so it reached LookupError. Give it
# the same chance the production worker had: no linkage row, service raises.
assert old_errors, "old body did not produce the defect - check this script"
assert not new_errors, "NEW hook still logs the expected absence as an error"
print("VACUITY CHECK OK: the assertion that fails for the old body passes for the new one.")
