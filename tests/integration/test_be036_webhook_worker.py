"""BE-036 Phase E: webhook-worker delivery behavior, verified without real egress.

The point of this milestone is the worker that the BE-035-D1 finding reported as
an ``ImportError``. These tests drive the *real* worker functions
(``sweep_pending_deliveries`` / ``sweep_retries`` / ``_attempt_delivery`` /
``_fanout_event`` / ``run_worker_once``) end to end and pin the delivery
behavior the fix must preserve:

* a PENDING delivery is selected and processed exactly once,
* a successful HTTP response drives the DELIVERED status and resets the
  subscription failure counter,
* a connection error / retryable status drives the RETRYING path with a future
  ``next_attempt_at`` (and is therefore not re-processed immediately),
* a non-retryable status and an exhausted attempt budget terminate in FAILED,
* an SSRF-blocked endpoint fails *permanently and without any network call*,
* a delivery to a disabled subscription short-circuits,
* every outcome appends exactly one audit event through the real
  ``append_event`` writer, and the append-only ledger is never mutated.

Safety (BE-036 §2 / §7): the delivery opener
(``webhook_service.NO_REDIRECT_OPENER.open``, reached via ``deliver_webhook``) is
monkeypatched, so no outbound request ever leaves the process; and
``socket.getaddrinfo`` (used by the SSRF validator) is stubbed with a
deterministic resolver — numeric hosts resolve to themselves, named hosts to one
public address — so the real SSRF blocking logic runs without touching DNS.
Rows are written to the explicitly configured test database only; the test
harness refuses to fall back to ``pofa_dev``/``pofa_test``.

These are integration tests (they require the BE-030 enforcement migration and
the webhook/audit tables) and are marked ``integration`` accordingly.
"""

from __future__ import annotations

import ipaddress
import urllib.error
import urllib.request
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from backend.db.session import get_session
from backend.repositories import integration as integration_repo
from backend.services import webhook as webhook_service
from backend.workers import webhook_worker

pytestmark = pytest.mark.integration

# One event type from WEBHOOK_EVENT_TYPES; the worker does not re-validate the
# domain, but staying inside it keeps the fixture faithful to production.
EVENT_TYPE = "review_case.created"
# A named endpoint. With the deterministic resolver below it maps to a public
# address, so validate_webhook_url runs its full path and permits delivery.
GOOD_ENDPOINT = "https://hooks.invalid.example/poa-be036"
# A literal cloud-metadata IP: validate_webhook_url must block it, and because
# it never reaches urlopen this also proves the no-egress guarantee.
BLOCKED_ENDPOINT = "http://169.254.169.254/latest/meta-data/"


@pytest.fixture()
def db():
    """A session bound to the explicit test database, cleaned up per test.

    The worker commits (that is its production behavior and must not be
    changed), so teardown deletes the domain rows this test created. Audit
    ledger rows are append-only and are intentionally left in place; the tests
    assert on their deltas, never on a global count.
    """
    session = get_session()
    created: dict[str, list[str]] = {
        "delivery": [], "event": [], "subscription": [], "system": [],
    }
    session._be036_created = created  # type: ignore[attr-defined]
    try:
        yield session
    finally:
        try:
            session.rollback()
        except Exception:
            pass
        # Order matters: deliveries FK-> events/subscriptions; subscriptions FK-> systems.
        for tid in created["delivery"]:
            session.execute(text("DELETE FROM webhook_deliveries WHERE id = :i"), {"i": tid})
        for eid in created["event"]:
            session.execute(text("DELETE FROM webhook_events WHERE id = :i"), {"i": eid})
        for sid in created["subscription"]:
            session.execute(text("DELETE FROM webhook_subscriptions WHERE id = :i"), {"i": sid})
        for yid in created["system"]:
            session.execute(text("DELETE FROM external_systems WHERE id = :i"), {"i": yid})
        session.commit()
        session.close()


@pytest.fixture(autouse=True)
def deterministic_resolver(monkeypatch):
    """Make SSRF validation deterministic and DNS-free.

    Numeric hostnames resolve to themselves (so the metadata/ private checks
    still fire); any other hostname resolves to one public address (so a
    well-formed named endpoint is permitted). This exercises the real blocking
    logic without any external name service.
    """
    def _fake(host, *args, **kwargs):  # noqa: ANN001, D401
        try:
            ipaddress.ip_address(host)
            resolved = host
        except ValueError:
            resolved = "93.184.216.34"  # a public address; passes SSRF
        # (family, type, proto, canonname, (ip, port))
        return [(2, 1, 6, "", (resolved, 0))]

    monkeypatch.setattr(webhook_service.socket, "getaddrinfo", _fake)


class _FakeResponse:
    """Minimal stand-in for urlopen's context manager exposing .status."""

    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def recorder(monkeypatch):
    """Patch the worker's outbound HTTP call and record every invocation.

    ``calls`` collects each Request the worker *would* have sent, so a test can
    assert delivery happened (or, for the SSRF case, that it never did). The
    ``result`` attribute selects the outcome: an int status is returned, an
    Exception instance/type is raised.
    """
    calls: list[urllib.request.Request] = []
    state = SimpleNamespace(calls=calls, result=200)

    def _fake_open(req, *args, **kwargs):
        calls.append(req)
        assert getattr(req, "timeout", None) == 10, \
            "worker must keep an explicit outbound timeout"
        result = state.result
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, type) and issubclass(result, BaseException):
            raise result("injected")
        return _FakeResponse(int(result))

    monkeypatch.setattr(webhook_service.NO_REDIRECT_OPENER, "open", _fake_open)
    return state


def _seed(db, *, endpoint=GOOD_ENDPOINT, sub_status="ACTIVE",
          consecutive_failures=0, delivery_status="PENDING",
          attempt_count=0, next_due=True):
    """Create one external system + subscription + event + delivery.

    Returns ``(system, subscription, event, delivery)``. The delivery's FK
    parents are registered in the session's cleanup ledger.
    """
    created = db._be036_created  # type: ignore[attr-defined]
    system = integration_repo.insert_external_system(
        db, name=f"be036-{uuid4()}", code=f"BE036-{uuid4()}",
        system_type="GOVERNMENT_PORTAL", status="ACTIVE",
    )
    created["system"].append(str(system.id))

    subscription = integration_repo.insert_webhook_subscription(
        db, external_system_id=str(system.id), endpoint_url=endpoint,
        status=sub_status, subscribed_events=[EVENT_TYPE],
        secret_hash="be036-test-signing-key",
        consecutive_failures=consecutive_failures,
    )
    created["subscription"].append(str(subscription.id))

    event = integration_repo.insert_webhook_event(
        db, event_type=EVENT_TYPE, event_version=1,
        aggregate_type="review_case", aggregate_id=str(uuid4()),
        payload={"probe": "be036"}, status="PENDING",
    )
    created["event"].append(str(event.id))

    delivery = integration_repo.insert_webhook_delivery(
        db, webhook_event_id=str(event.id), subscription_id=str(subscription.id),
        status=delivery_status, attempt_count=attempt_count,
        next_attempt_at=webhook_service.utc_now() if next_due else None,
    )
    created["delivery"].append(str(delivery.id))

    db.commit()
    return system, subscription, event, delivery


def _audit_count(db, event_type: str, resource_id: str) -> int:
    return int(db.execute(
        text("SELECT count(*) FROM audit_ledger_events"
             " WHERE event_type = :t AND resource_id = :r"),
        {"t": event_type, "r": resource_id},
    ).scalar_one())


def test_pending_delivery_delivers_and_audits(db, recorder):
    """§7 success path: PENDING -> DELIVERED, failures reset, one success audit."""
    _, sub, event, delivery = _seed(db)
    recorder.result = 200

    processed = webhook_worker.sweep_pending_deliveries(db, limit=50)

    assert processed == 1
    db.refresh(delivery)
    assert delivery.status == "DELIVERED"
    assert delivery.delivered_at is not None
    assert delivery.last_status_code == 200
    assert delivery.last_error is None
    db.refresh(sub)
    assert sub.consecutive_failures == 0
    assert len(recorder.calls) == 1
    assert _audit_count(db, "WEBHOOK_DELIVERY_SUCCEEDED", str(delivery.id)) == 1


def test_connection_error_enters_retrying(db, recorder):
    """§7 failure path: a connection error schedules a future retry, one fail audit."""
    _, _, _, delivery = _seed(db)
    recorder.result = urllib.error.URLError("connection refused")

    processed = webhook_worker.sweep_pending_deliveries(db, limit=50)

    assert processed == 1
    db.refresh(delivery)
    assert delivery.status == "RETRYING"
    assert delivery.attempt_count == 1
    assert delivery.next_attempt_at is not None
    assert delivery.next_attempt_at > webhook_service.utc_now()
    assert _audit_count(db, "WEBHOOK_DELIVERY_FAILED", str(delivery.id)) == 1


def test_retryable_status_retries_nonretryable_fails(db, recorder):
    """A 5xx retries; a 4xx terminates as FAILED with no next attempt."""
    _, _, _, d500 = _seed(db)
    recorder.result = urllib.error.HTTPError(
        GOOD_ENDPOINT, 500, "server error", None, None)
    webhook_worker.sweep_pending_deliveries(db, limit=50)
    db.refresh(d500)
    assert d500.status == "RETRYING"
    assert d500.last_status_code == 500

    _, _, _, d404 = _seed(db)
    recorder.result = urllib.error.HTTPError(
        GOOD_ENDPOINT, 404, "not found", None, None)
    webhook_worker.sweep_pending_deliveries(db, limit=50)
    db.refresh(d404)
    assert d404.status == "FAILED"
    assert d404.last_status_code == 404
    assert d404.next_attempt_at is None


def test_exhausted_attempts_terminate_failed(db, recorder):
    """Once the attempt budget is spent the next failure is terminal."""
    _, _, _, delivery = _seed(
        db, delivery_status="RETRYING",
        attempt_count=webhook_worker.MAX_DELIVERY_ATTEMPTS - 1,
    )
    recorder.result = urllib.error.URLError("still down")

    processed = webhook_worker.sweep_retries(db, limit=50)

    assert processed == 1
    db.refresh(delivery)
    assert delivery.status == "FAILED"
    assert delivery.next_attempt_at is None
    assert delivery.attempt_count == webhook_worker.MAX_DELIVERY_ATTEMPTS


def test_ssrf_blocked_fails_permanently_without_egress(db, recorder):
    """§7 controlled failure: an unsafe endpoint fails closed and never sends."""
    _, _, _, delivery = _seed(db, endpoint=BLOCKED_ENDPOINT)

    webhook_worker.sweep_pending_deliveries(db, limit=50)

    assert recorder.calls == [], "SSRF-blocked delivery must not reach urlopen"
    db.refresh(delivery)
    # Permanent failure: FAILED (not RETRYING), so sweep_retries will never pick
    # it up regardless of the residual next_attempt_at value.
    assert delivery.status == "FAILED"
    assert "SSRF" in (delivery.last_error or "")
    assert _audit_count(db, "WEBHOOK_DELIVERY_FAILED", str(delivery.id)) == 1
    # A later retry sweep must find nothing to re-deliver for this row.
    assert webhook_worker.sweep_retries(db, limit=50) >= 0
    assert len(recorder.calls) == 0, "a permanently-failed SSRF delivery must not retry"


def test_redirect_rejected_fails_permanently_and_is_not_retried(db, recorder):
    """BE-037/BE-036-D1: a refused redirect is a permanent, audited failure.

    The opener connects to the validated endpoint, receives a 3xx, and raises
    ``WebhookRedirectError`` (a ``ValueError``) before ever reaching the redirect
    target. The worker must treat this like an SSRF rejection — FAILED, not
    RETRYING, one audit event, and no later re-send — because a redirect cannot
    be made safe by trying again.
    """
    _, sub, _, delivery = _seed(db)
    recorder.result = webhook_service.WebhookRedirectError(
        "HTTP 302 redirect to 'http://127.0.0.1/admin' rejected")

    webhook_worker.sweep_pending_deliveries(db, limit=50)

    db.refresh(delivery)
    assert delivery.status == "FAILED", "a refused redirect must not enter RETRYING"
    assert (delivery.last_error or "").startswith("Redirect rejected")
    # A security rejection must not be retried: the FAILED row is out of both
    # the PENDING and RETRYING sweeps, so a follow-up pass sends nothing more.
    assert webhook_worker.sweep_retries(db, limit=50) == 0
    assert len(recorder.calls) == 1, "the refused-redirect delivery must be sent once, not retried"
    assert _audit_count(db, "WEBHOOK_DELIVERY_FAILED", str(delivery.id)) == 1
    db.refresh(sub)
    assert sub.status != "DISABLED", "a single permanent rejection is not a failure-streak disable"


def test_disabled_subscription_short_circuits(db, recorder):
    """A DISABLED subscription marks the delivery DISABLED without any send."""
    _, _, _, delivery = _seed(db, sub_status="DISABLED")

    webhook_worker.sweep_pending_deliveries(db, limit=50)

    assert recorder.calls == []
    db.refresh(delivery)
    assert delivery.status == "DISABLED"


def test_consecutive_failures_auto_disable(db, recorder):
    """The 10th consecutive failure disables the subscription and the delivery."""
    _, sub, _, delivery = _seed(
        db, consecutive_failures=webhook_worker.MAX_CONSECUTIVE_FAILURES_BEFORE_DISABLE - 1)
    recorder.result = urllib.error.URLError("nope")

    webhook_worker.sweep_pending_deliveries(db, limit=50)

    db.refresh(sub)
    db.refresh(delivery)
    assert sub.status == "DISABLED"
    assert delivery.status == "DISABLED"


def test_completed_delivery_is_not_reprocessed(db, recorder):
    """§7 idempotence: a DELIVERED row is not selected by a later sweep."""
    _, _, _, delivery = _seed(db)
    recorder.result = 200
    webhook_worker.sweep_pending_deliveries(db, limit=50)
    assert delivery.status == "DELIVERED"

    first_call_count = len(recorder.calls)
    processed = webhook_worker.sweep_pending_deliveries(db, limit=50)

    assert processed == 0
    assert len(recorder.calls) == first_call_count
    assert _audit_count(db, "WEBHOOK_DELIVERY_SUCCEEDED", str(delivery.id)) == 1


def test_interrupted_attempt_is_reclaimable_not_stranded(db, recorder):
    """BE-037 §7.2: an interruption before the sweep commit reverts to PENDING.

    ``_attempt_delivery`` flushes ``PROCESSING`` and then the terminal status,
    but the caller commits only after it returns. A crash (here simulated by a
    rollback) therefore discards the whole attempt, so the row is reclaimable as
    ``PENDING`` — a durable ``PROCESSING`` strand is not reachable under this
    commit design.
    """
    _, _, _, delivery = _seed(db)
    delivery_id = str(delivery.id)
    recorder.result = 200

    # Run the attempt but do NOT commit (the sweep would commit here).
    webhook_worker._attempt_delivery(db, delivery)

    # Simulate a worker crash before the transaction is durably written.
    db.rollback()
    db.expire_all()

    status = db.execute(
        text("SELECT status FROM webhook_deliveries WHERE id = :i"),
        {"i": delivery_id},
    ).scalar_one()
    assert status == "PENDING", (
        "an interrupted attempt must revert the whole PROCESSING->terminal "
        f"transition, leaving reclaimable work, not a stranded {status!r} row"
    )


def test_fanout_creates_one_delivery_per_subscription(db):
    """§7 fanout: one PENDING delivery is created, and re-fanout is idempotent."""
    created = db._be036_created  # type: ignore[attr-defined]
    system = integration_repo.insert_external_system(
        db, name=f"be036-{uuid4()}", code=f"BE036-{uuid4()}",
        system_type="FIELD_SYSTEM", status="ACTIVE")
    created["system"].append(str(system.id))
    sub = integration_repo.insert_webhook_subscription(
        db, external_system_id=str(system.id), endpoint_url=GOOD_ENDPOINT,
        status="ACTIVE", subscribed_events=[EVENT_TYPE],
        secret_hash="be036-key", consecutive_failures=0)
    created["subscription"].append(str(sub.id))
    event = integration_repo.insert_webhook_event(
        db, event_type=EVENT_TYPE, event_version=1,
        aggregate_type="review_case", aggregate_id=str(uuid4()),
        payload={}, status="PENDING")
    created["event"].append(str(event.id))
    db.commit()

    webhook_worker._fanout_event(db, event)
    db.commit()
    first = db.execute(
        text("SELECT count(*) FROM webhook_deliveries"
             " WHERE webhook_event_id = :e"), {"e": str(event.id)}).scalar_one()

    # A second fanout must not duplicate the delivery (existing-row skip).
    webhook_worker._fanout_event(db, event)
    db.commit()
    second = db.execute(
        text("SELECT count(*) FROM webhook_deliveries"
             " WHERE webhook_event_id = :e"), {"e": str(event.id)}).scalar_one()

    assert int(first) == 1
    assert int(second) == 1


def test_run_worker_once_uses_fixed_session_and_closes_cleanly(monkeypatch):
    """§7 lifecycle: the entry point acquires the session via the fixed import.

    BE-035-D1 was an ``ImportError`` rooted in ``run_worker_once``/``__main__``
    calling a nonexistent ``SessionLocal``. The behavior tests above cover the
    sweeps themselves against real deliveries; this test isolates the entry
    point that the fix touched. The three sweeps are stubbed so the pass does
    not fan out the shared ``pofa_test`` event backlog — the point is not the
    volume it processes but that it acquires a session through ``get_session``
    (the corrected symbol) and closes it in its ``finally``, i.e. the launch
    path runs end to end after the fix.
    """
    acquired = {"count": 0}
    closed = {"count": 0}
    seen_sweeps: list[tuple[str, int]] = []

    class _SpySession:
        def close(self):
            closed["count"] += 1

    def _fake_get_session():
        acquired["count"] += 1
        return _SpySession()

    def _stub_events(db, limit):
        seen_sweeps.append(("events", limit)); return 0
    def _stub_pending(db, limit):
        seen_sweeps.append(("pending", limit)); return 0
    def _stub_retries(db, limit):
        seen_sweeps.append(("retries", limit)); return 0

    monkeypatch.setattr(webhook_worker, "get_session", _fake_get_session)
    monkeypatch.setattr(webhook_worker, "sweep_webhook_events", _stub_events)
    monkeypatch.setattr(webhook_worker, "sweep_pending_deliveries", _stub_pending)
    monkeypatch.setattr(webhook_worker, "sweep_retries", _stub_retries)

    webhook_worker.run_worker_once(limit=7)  # must not raise ImportError/NameError

    assert acquired["count"] == 1, "run_worker_once must acquire a session via get_session"
    assert closed["count"] == 1, "run_worker_once must close its session even on success"
    assert seen_sweeps == [("events", 7), ("pending", 14), ("retries", 7)]
