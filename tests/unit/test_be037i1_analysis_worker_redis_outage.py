"""BE-037 I1: the analysis worker waits out a Redis outage instead of dying.

Root cause measured in Phase B: ``run_worker`` called ``queue.dequeue`` and
``process_message`` with no exception handling, and ``__main__`` caught only
``KeyboardInterrupt``. Any transient Redis failure (restart, network blip,
``LOADING``) therefore escaped the loop and terminated the process — under
Docker that is an exit-1 crash loop, and in every deployment it strands the
messages the worker could not acknowledge.

These tests pin the replacement contract with fakes: no Redis, no database, no
network. The live outage scenario runs against the disposable stack separately.
"""

import signal

import pytest
import redis

import backend.workers.analysis_worker as aw
from backend.core.config import settings


class Stop:
    """Scripted dequeue result that asks the loop to wind down."""


class FakeRedisClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeQueue:
    """Scripted dequeue/processing/recovery behaviour plus call accounting.

    ``dequeue_results`` items are values returned by ``dequeue``, exception
    instances it raises, or a ``Stop`` sentinel (sets the shutdown flag and
    returns no message). ``process_behaviour`` items are returned by, or raised
    by, the replaced ``process_message``. ``recover_behaviour`` items are
    returned by, or raised by, ``recover_abandoned``; once exhausted the
    recovery simply reports that nothing was found.
    """

    def __init__(self, dequeue_results, process_behaviour=None,
                 recover_behaviour=None) -> None:
        self.client = FakeRedisClient()
        self._dequeue = list(dequeue_results)
        self._process = list(process_behaviour or [])
        self._recover = list(recover_behaviour or [])
        self.dequeue_calls = 0
        self.dequeue_timeouts = []
        self.recover_calls = 0
        self.acknowledged = []
        self.retried = []
        self.processed = []

    def recover_abandoned(self, session) -> int:
        self.recover_calls += 1
        if self._recover:
            item = self._recover.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        return 0

    def dequeue(self, timeout: int = 0):
        self.dequeue_calls += 1
        self.dequeue_timeouts.append(timeout)
        assert self._dequeue, "dequeue called more times than scripted"
        item = self._dequeue.pop(0)
        if isinstance(item, Stop):
            aw._shutdown_requested = True
            return None
        if isinstance(item, BaseException):
            raise item
        return item

    def acknowledge(self, message) -> None:
        self.acknowledged.append(message)

    def retry(self, message) -> None:
        self.retried.append(message)

    def process(self, message, queue) -> str:
        assert self._process, "process_message called more times than scripted"
        item = self._process.pop(0)
        if isinstance(item, BaseException):
            raise item
        self.processed.append(message)
        return item


@pytest.fixture
def shutdown_flag_restored():
    original = aw._shutdown_requested
    aw._shutdown_requested = False
    yield
    aw._shutdown_requested = original


@pytest.fixture
def harness(monkeypatch, shutdown_flag_restored):
    """run_worker with Redis, the database and the waits replaced by fakes."""

    def build(dequeue_results, process_behaviour=None, recover_behaviour=None):
        queue = FakeQueue(dequeue_results, process_behaviour, recover_behaviour)
        engine = FakeEngine()
        sessions: list[FakeSession] = []
        waits: list[float] = []

        def fake_sleep(seconds: float) -> bool:
            waits.append(seconds)
            return aw._shutdown_requested

        def new_session():
            session = FakeSession()
            sessions.append(session)
            return session

        monkeypatch.setattr(aw, "AnalysisQueue", lambda: queue)
        monkeypatch.setattr(aw, "get_session", new_session)
        monkeypatch.setattr(aw, "get_engine", lambda: engine)
        monkeypatch.setattr(aw, "process_message", queue.process)
        monkeypatch.setattr(aw, "_interruptible_sleep", fake_sleep)
        # Deterministic backoff: the jitter half contributes nothing unless a
        # test says otherwise.
        monkeypatch.setattr(aw.random, "uniform", lambda _low, _high: 0.0)
        return queue, engine, sessions, waits

    return build


def outage() -> redis.exceptions.ConnectionError:
    return redis.exceptions.ConnectionError("Connection refused")


def half(step: int = 1) -> float:
    """The jitter-free backoff for the ``step``-th consecutive failure."""
    return min(
        settings.analysis_retry_backoff_max_seconds,
        settings.analysis_retry_backoff_base_seconds * (2 ** (step - 1)),
    ) / 2


# ---------------------------------------------------------------------------
# the outage path
# ---------------------------------------------------------------------------

def test_outage_on_dequeue_is_retried_without_losing_the_loop(harness):
    """Redis down at first, then a message arrives: the worker keeps working."""
    message = object()
    queue, engine, _, waits = harness([outage(), message, Stop()], ["completed"])

    aw.run_worker()

    assert queue.processed == [message]
    assert waits == [half(1)]
    # Startup pass plus the post-outage reclassification pass.
    assert queue.recover_calls == 2
    assert engine.disposed is True


def test_outage_during_acknowledgement_never_acks_early(harness):
    """A job whose ack cannot reach Redis stays unacknowledged, not lost."""
    message = object()
    queue, engine, _, waits = harness(
        [message, None, Stop()],
        process_behaviour=[outage()],
    )

    aw.run_worker()

    # The payload is left in the processing list: no early acknowledgement and
    # no second requeue, which is what would duplicate the job.
    assert queue.acknowledged == []
    assert queue.retried == []
    assert queue.processed == []
    assert waits == [half(1)]
    assert queue.recover_calls == 2
    assert engine.disposed is True


def test_repeated_failures_grow_bounded_and_touch_no_payload(harness):
    message = object()
    queue, _, _, waits = harness(
        [outage(), outage(), outage(), message, Stop()],
        process_behaviour=["completed"],
    )

    aw.run_worker()

    assert waits == [half(1), half(2), half(3)]
    assert queue.retried == []
    assert queue.acknowledged == []
    assert queue.processed == [message]


def test_failure_counter_resets_after_a_clean_message(harness):
    """A reconnect must not leave the next outage at the previous backoff."""
    message = object()
    queue, _, _, waits = harness(
        [outage(), outage(), message, outage(), Stop()],
        process_behaviour=["completed"],
    )

    aw.run_worker()

    assert waits == [half(1), half(2), half(1)]


def test_healthy_loop_recovers_only_at_startup(harness):
    queue, engine, sessions, waits = harness([None, None, Stop()])

    aw.run_worker()

    assert queue.recover_calls == 1
    assert waits == []
    assert engine.disposed is True
    assert all(session.closed for session in sessions)


def test_startup_outage_is_backed_off_instead_of_crashing_the_worker(harness):
    """Redis down at process start must not escape the guarded loop.

    The startup recovery pass used to run before the try/loop, so an outage
    that begins while the process is starting raised straight out of
    ``run_worker`` and the container exited non-zero without ever polling
    again.
    """
    queue, engine, sessions, waits = harness(
        [Stop()], recover_behaviour=[outage(), 0])

    aw.run_worker()

    assert waits == [half(1)]
    # First (failed) pass plus the retry after the backoff.
    assert queue.recover_calls == 2
    assert queue.dequeue_calls == 1
    assert engine.disposed is True
    assert all(session.closed for session in sessions)


def test_non_transient_redis_error_still_propagates(harness):
    """A programming/configuration fault must fail loudly, not be retried."""
    queue, engine, _, waits = harness(
        [redis.exceptions.ResponseError("WRONGTYPE Operation against a key")]
    )

    with pytest.raises(redis.exceptions.ResponseError):
        aw.run_worker()

    assert waits == []
    assert queue.recover_calls == 1
    assert engine.disposed is True


# ---------------------------------------------------------------------------
# WS-C: which Redis failures are an outage and which are a broken deployment
# ---------------------------------------------------------------------------

def stalled() -> redis.exceptions.TimeoutError:
    """What a frozen server now raises once the queue client has a deadline.

    Measured on redis-py 4.6.0: ``TimeoutError`` is a sibling of
    ``ConnectionError`` under ``RedisError``, so listing only the latter leaves a
    stalled read to escape the loop exactly like the pre-I1 crash did.
    """
    return redis.exceptions.TimeoutError("Timeout reading from socket")


def test_a_stalled_socket_is_waited_out_like_any_other_outage(harness):
    message = object()
    queue, engine, _, waits = harness([stalled(), message, Stop()], ["completed"])

    aw.run_worker()

    assert queue.processed == [message]
    assert waits == [half(1)]
    assert queue.recover_calls == 2
    assert engine.disposed is True


def test_repeated_stalls_back_off_without_touching_the_payload(harness):
    queue, _, _, waits = harness([stalled(), stalled(), Stop()])

    aw.run_worker()

    assert waits == [half(1), half(2)]
    assert queue.acknowledged == []
    assert queue.retried == []


def test_bad_credentials_propagate_even_though_they_subclass_connection_error(
    harness
):
    """AuthenticationError is a ``ConnectionError`` subclass, and not an outage.

    Waiting it out would keep a misconfigured worker polling forever with the
    queue looking alive; the deployment has to fail loudly instead.
    """
    queue, engine, _, waits = harness(
        [redis.exceptions.AuthenticationError("invalid password")]
    )

    with pytest.raises(redis.exceptions.AuthenticationError):
        aw.run_worker()

    assert waits == []
    assert queue.dequeue_calls == 1
    assert engine.disposed is True


def test_the_blocking_dequeue_wait_comes_from_settings(harness, monkeypatch):
    """The value the socket-deadline invariant is written against."""
    monkeypatch.setattr(settings, "analysis_dequeue_block_seconds", 7)
    queue, _, _, _ = harness([Stop()])

    aw.run_worker()

    assert queue.dequeue_timeouts == [7]


# ---------------------------------------------------------------------------
# the wait itself
# ---------------------------------------------------------------------------

def test_backoff_is_exponential_and_bounded(monkeypatch):
    monkeypatch.setattr(settings, "analysis_retry_backoff_base_seconds", 1.0)
    monkeypatch.setattr(settings, "analysis_retry_backoff_max_seconds", 8.0)
    monkeypatch.setattr(aw.random, "uniform", lambda _low, high: high)

    samples = [aw._backoff_delay(failures) for failures in range(1, 13)]

    assert samples[:4] == [1.0, 2.0, 4.0, 8.0]
    assert samples[4:] == [8.0] * 8
    assert max(samples) <= settings.analysis_retry_backoff_max_seconds


def test_jitter_is_taken_from_the_upper_half_of_the_delay(monkeypatch):
    monkeypatch.setattr(settings, "analysis_retry_backoff_base_seconds", 4.0)
    monkeypatch.setattr(settings, "analysis_retry_backoff_max_seconds", 60.0)
    seen = []

    def capture(low, high):
        seen.append((low, high))
        return high

    monkeypatch.setattr(aw.random, "uniform", capture)

    assert aw._backoff_delay(1) == 4.0
    assert seen == [(0.0, 2.0)]


def test_interruptible_sleep_wakes_when_shutdown_is_requested(monkeypatch,
                                                              shutdown_flag_restored):
    """A SIGTERM during a backoff wait must stop the worker, not after it."""
    slices = []

    def fake_sleep(seconds: float) -> None:
        slices.append(seconds)
        if len(slices) == 2:
            aw._shutdown_requested = True

    monkeypatch.setattr(aw.time, "sleep", fake_sleep)
    monkeypatch.setattr(settings, "analysis_shutdown_poll_seconds", 0.25)

    assert aw._interruptible_sleep(30.0) is True
    assert len(slices) == 2
    assert all(seconds <= 0.25 for seconds in slices)


def test_interruptible_sleep_returns_false_when_the_wait_completes(
    monkeypatch, shutdown_flag_restored
):
    slept: list[float] = []

    monkeypatch.setattr(aw.time, "sleep", slept.append)
    monkeypatch.setattr(settings, "analysis_shutdown_poll_seconds", 5.0)
    times = iter([0.0, 0.0, 4.0])
    monkeypatch.setattr(aw.time, "monotonic", lambda: next(times))

    assert aw._interruptible_sleep(1.0) is False
    assert aw._shutdown_requested is False
    assert slept == [1.0]


def test_shutdown_during_backoff_stops_the_loop_and_releases_resources(
    harness, monkeypatch
):
    queue, engine, sessions, waits = harness([outage()])
    monkeypatch.setattr(aw, "_interruptible_sleep", lambda _seconds: True)

    aw.run_worker()

    assert waits == []
    assert queue.dequeue_calls == 1
    assert queue.client.closed is True
    assert engine.disposed is True
    assert all(session.closed for session in sessions)


def test_sigint_still_raises_and_releases_resources(harness):
    """The pre-existing Ctrl-C contract is unchanged by the outage handling."""
    queue, engine, _, _ = harness([KeyboardInterrupt()])

    with pytest.raises(KeyboardInterrupt):
        aw.run_worker()

    assert queue.client.closed is True
    assert engine.disposed is True


def test_handler_only_flips_the_flag(monkeypatch, shutdown_flag_restored):
    """The signal handler stays work-free, including during an outage wait."""
    monkeypatch.setattr(aw, "_shutdown_requested", False)

    def explode(*args, **kwargs):
        raise AssertionError("signal handler performed work")

    monkeypatch.setattr(aw, "get_session", explode)
    monkeypatch.setattr(aw, "get_engine", explode)
    monkeypatch.setattr(aw, "AnalysisQueue", explode)
    monkeypatch.setattr(aw, "_await_redis_retry", explode)

    assert aw._request_shutdown(signal.SIGTERM, None) is None
    assert aw._shutdown_requested is True
