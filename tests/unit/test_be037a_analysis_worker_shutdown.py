"""BE-037A-D3: the analysis worker must stop cleanly on SIGTERM.

Root cause measured in the container: the worker runs as PID 1, where the kernel
does not act on default-action signals, so an unhandled SIGTERM was ignored until
Docker escalated to SIGKILL (exit 137). These tests pin the replacement contract
without touching a database, Redis, or the network.
"""

import signal

import pytest

import backend.workers.analysis_worker as aw


class FakeRedisClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeQueue:
    def __init__(self, dequeue_results):
        self.client = FakeRedisClient()
        self._dequeue_results = list(dequeue_results)
        self.dequeue_calls = 0

    def recover_abandoned(self, session):
        return 0

    def dequeue(self, timeout: int = 0):
        self.dequeue_calls += 1
        if not self._dequeue_results:
            raise AssertionError("dequeue called more times than scripted")
        result = self._dequeue_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def shutdown_flag_restored():
    original = aw._shutdown_requested
    aw._shutdown_requested = False
    yield
    aw._shutdown_requested = original


@pytest.fixture
def harness(monkeypatch, shutdown_flag_restored):
    """run_worker with its external dependencies replaced by fakes."""

    def build(dequeue_results, process_result="completed"):
        queue = FakeQueue(dequeue_results)
        engine = FakeEngine()
        session = FakeSession()
        processed = []

        def fake_process_message(message, q):
            processed.append(message)
            return process_result

        monkeypatch.setattr(aw, "AnalysisQueue", lambda: queue)
        monkeypatch.setattr(aw, "get_session", lambda: session)
        monkeypatch.setattr(aw, "get_engine", lambda: engine)
        monkeypatch.setattr(aw, "process_message", fake_process_message)
        return queue, engine, session, processed

    return build


def test_install_registers_sigterm_and_leaves_sigint_alone(monkeypatch):
    """Only SIGTERM is claimed; SIGINT keeps raising KeyboardInterrupt."""
    registered = {}

    def fake_signal(signum, handler):
        registered[signum] = handler

    monkeypatch.setattr(aw.signal, "signal", fake_signal)

    aw.install_shutdown_handlers()

    assert registered == {signal.SIGTERM: aw._request_shutdown}
    assert signal.SIGINT not in registered


def test_import_does_not_install_a_handler(monkeypatch):
    """Importing the module must not mutate process-wide signal state."""
    assert signal.getsignal(signal.SIGTERM) is not aw._request_shutdown


def test_handler_only_flips_the_flag(monkeypatch):
    """No work in the handler: it can fire inside an open transaction."""
    monkeypatch.setattr(aw, "_shutdown_requested", False)

    def explode(*args, **kwargs):
        raise AssertionError("signal handler performed work")

    monkeypatch.setattr(aw, "get_session", explode)
    monkeypatch.setattr(aw, "get_engine", explode)
    monkeypatch.setattr(aw, "AnalysisQueue", explode)

    assert aw._request_shutdown(signal.SIGTERM, None) is None
    assert aw._shutdown_requested is True
    # A second signal (e.g. stop retried by the orchestrator) must be a no-op.
    assert aw._request_shutdown(signal.SIGTERM, None) is None
    assert aw._shutdown_requested is True


def test_loop_exits_on_flag_and_releases_resources(harness):
    """SIGTERM during a blocking dequeue stops the loop within one iteration."""
    queue, engine, session, _ = harness(
        dequeue_results=[None, None],
    )

    def second_dequeue_then_stop(timeout: int = 0):
        queue.dequeue_calls += 1
        aw._shutdown_requested = True
        return None

    queue.dequeue = second_dequeue_then_stop

    aw.run_worker()

    assert aw._shutdown_requested is True
    assert queue.client.closed is True
    assert engine.disposed is True
    assert session.closed is True


def test_in_flight_message_completes_before_shutdown(harness):
    """A stop requested mid-job is honoured only after that job returns."""
    message = object()
    queue, engine, _, processed = harness(dequeue_results=[message])
    original_dequeue = queue.dequeue

    def dequeue_then_request_stop(timeout: int = 0):
        result = original_dequeue(timeout=timeout)
        aw._shutdown_requested = True
        return result

    queue.dequeue = dequeue_then_request_stop

    aw.run_worker()

    assert len(processed) == 1
    assert engine.disposed is True
    assert queue.client.closed is True


def test_no_message_loop_exits_immediately_when_flag_already_set(harness):
    queue, engine, _, _ = harness(dequeue_results=[])
    aw._shutdown_requested = True

    aw.run_worker()

    assert queue.dequeue_calls == 0
    assert engine.disposed is True


def test_keyboard_interrupt_propagates_and_still_releases_resources(harness):
    """Ctrl-C behaviour is preserved: run_worker raises, cleanup still runs."""
    queue, engine, session, _ = harness(
        dequeue_results=[KeyboardInterrupt()],
    )

    with pytest.raises(KeyboardInterrupt):
        aw.run_worker()

    assert queue.client.closed is True
    assert engine.disposed is True
    assert session.closed is True
