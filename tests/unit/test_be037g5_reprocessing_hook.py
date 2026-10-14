"""BE-037 G5: the reprocessing-completion hook stops manufacturing errors.

Root cause measured in Phase B: every completed analysis job produced an ERROR
with a traceback. ``_complete_reprocessing_hook`` called
``governance_service.complete_reprocessing(db, analysis_job_id=...)``, and that
service raises ``LookupError("Reprocessing request not found")`` whenever no
reprocessing request delegates the job — the normal case, because most jobs come
straight from the evidence pipeline. The hook's blanket ``except`` logged that
expected absence as a failure, so genuine governance faults were
indistinguishable from steady-state noise.

These tests pin the replacement contract with fakes: the linkage check decides
whether there is any work to do, an unlinked job is quiet, and only a real fault
reaches the error log — exactly once, with its traceback, and never escaping
into the analysis pipeline.
"""

import logging
from uuid import uuid4

import pytest

import backend.workers.analysis_worker as aw
from backend.repositories import governance as governance_repo
from backend.services import governance as governance_service


class Job:
    def __init__(self) -> None:
        self.id = uuid4()


class Request:
    def __init__(self) -> None:
        self.id = uuid4()


@pytest.fixture
def calls():
    """Every collaboration the hook is permitted to make, in order."""
    return {"linkage": [], "complete": []}


@pytest.fixture
def link(monkeypatch, calls):
    """Script ``lock_pending_reprocessing_for_job``.

    A callable becomes the query behaviour (it receives the session and job id,
    so it may raise); any other value is returned as the found row or ``None``.
    """

    def apply(result):
        def lock_pending_reprocessing_for_job(db, analysis_job_id):
            calls["linkage"].append((db, analysis_job_id))
            if callable(result):
                return result(db, analysis_job_id)
            return result

        monkeypatch.setattr(
            governance_repo,
            "lock_pending_reprocessing_for_job",
            lock_pending_reprocessing_for_job,
        )

    return apply


@pytest.fixture
def complete(monkeypatch, calls):
    """Replace the governance completion call and record how it was invoked."""

    def apply(behaviour=None):
        def fake_complete_reprocessing(db, **kwargs):
            calls["complete"].append(kwargs)
            if isinstance(behaviour, BaseException):
                raise behaviour
            if callable(behaviour):
                return behaviour(db, kwargs)
            return "COMPLETED"

        monkeypatch.setattr(
            governance_service, "complete_reprocessing", fake_complete_reprocessing
        )

    return apply


@pytest.fixture
def run_hook(caplog):
    """Run the hook and return only the worker logger's own records.

    Captured from DEBUG so a quiet path is proven quiet rather than merely
    filtered out by the handler's level.
    """

    def run(job=None, db=None):
        job = job or Job()
        with caplog.at_level(logging.DEBUG, logger=aw.logger.name):
            # Contract: the hook is failure-isolated, so this must never raise.
            aw._complete_reprocessing_hook(db if db is not None else object(), job)
        return [r for r in caplog.records if r.name == aw.logger.name], job

    return run


def test_unlinked_job_is_a_quiet_no_op(link, complete, run_hook, calls):
    """The expected absence must not look like a failure."""
    link(None)
    complete()

    records, _ = run_hook()

    assert calls["complete"] == []
    assert [r for r in records if r.levelno >= logging.WARNING] == []
    assert not any(r.exc_info for r in records)


def test_unlinked_job_is_reported_at_debug_with_the_job_id(link, complete, run_hook):
    """Diagnosing "why was my request not completed" needs one traceable line."""
    link(None)
    complete()

    records, job = run_hook()

    assert [r.levelno for r in records] == [logging.DEBUG]
    message = records[0].getMessage()
    assert "governance hook skipped" in message
    assert f"job_id={job.id}" in message


def test_linkage_is_measured_with_the_job_id_as_a_string(link, complete, run_hook, calls):
    """The absence is queried from the database, not inferred from the job."""
    db = object()
    job = Job()
    link(None)
    complete()

    run_hook(job=job, db=db)

    assert calls["linkage"] == [(db, str(job.id))]


def test_linked_job_completes_the_delegating_request(link, complete, run_hook, calls):
    """A real delegation is closed out, addressed by its own id."""
    request = Request()
    link(request)
    complete()

    records, job = run_hook()

    assert calls["complete"] == [
        {"reprocessing_id": str(request.id), "completed_by": None}
    ]
    assert [r for r in records if r.levelno >= logging.WARNING] == []


@pytest.mark.parametrize(
    "fault",
    [
        RuntimeError("governance service exploded"),
        ValueError("Only PENDING reprocessing requests can complete (current: CANCELLED)"),
        LookupError("Reprocessing request not found"),
    ],
    ids=["runtime", "state-machine", "lookup"],
)
def test_completion_failure_is_logged_once_with_a_traceback(
    link, complete, run_hook, fault
):
    """Genuine faults stay observable and never reach the caller."""
    link(Request())
    complete(fault)

    records, job = run_hook()

    errors = [r for r in records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, "the hook must not duplicate the failure log"
    assert errors[0].exc_info[1] is fault
    assert f"job_id={job.id}" in errors[0].getMessage()
    assert not any(r.levelno >= logging.ERROR for r in records[1:])


def test_linkage_query_failure_is_logged_and_skips_completion(
    link, complete, run_hook, calls
):
    """A database fault is a genuine failure, not the expected no-op."""
    fault = RuntimeError("connection lost")

    def explode(db, analysis_job_id):
        raise fault

    link(explode)
    complete()

    records, _ = run_hook()

    assert calls["complete"] == []
    errors = [r for r in records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info[1] is fault
    assert "linkage lookup failed" in errors[0].getMessage()


def test_repeated_hook_calls_stay_quiet_and_idempotent(link, complete, run_hook, calls):
    """Re-running after the request is already COMPLETED adds no noise.

    The service owns the idempotency (it returns the completed row unchanged),
    so the hook must keep calling it and keep silent about it.
    """
    request = Request()
    link(request)
    complete()

    first, _ = run_hook()
    second, _ = run_hook()

    assert len(calls["complete"]) == 2
    assert [r for r in first + second if r.levelno >= logging.WARNING] == []
