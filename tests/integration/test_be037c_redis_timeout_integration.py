"""BE-037 WS-C: the Redis timeout strategy proven against a real server.

The unit module (`tests/unit/test_be037c_analysis_queue_timeouts.py`) pins the
client's configured bounds. Configuration is not behaviour: the claim under test
here is that a real stalled or vanished server produces a *bounded* failure the
worker treats as an outage, instead of a read that never returns.

This module never touches the shared stack. It is armed by environment and
refuses the protected resources by name:

  POA_DISPOSABLE_REDIS_URL        a redis:// URL for THIS run's disposable
                                  Redis (host ports such as 16379). Every test
                                  that needs a live server skips without it; only
                                  the closed-port case still runs, because it
                                  dials loopback port 1 and can never reach a
                                  server it does not own.
  POA_DISPOSABLE_REDIS_CONTAINER  the disposable Redis container name, required
                                  by the two injections that need a real server
                                  fault: ``pause`` for the blackhole read (no
                                  clean TCP disconnect) and ``stop``/``start``
                                  for the dead-server acknowledgement. A name
                                  belonging to the protected stack is a hard
                                  error, not a skip.

Cleanup is scoped to keys this module created (a unique queue name per run), and
the container is always restored (unpaused, or started) in a finally block.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from typing import Iterator

import pytest
import redis

from backend.core.config import settings
from backend.services.analysis_queue import AnalysisQueue
from backend.workers.analysis_worker import TRANSIENT_REDIS_ERRORS

DISPOSABLE_REDIS_URL_ENV = "POA_DISPOSABLE_REDIS_URL"
DISPOSABLE_REDIS_CONTAINER_ENV = "POA_DISPOSABLE_REDIS_CONTAINER"

#: The protected pofa_redis publishes the standard port on the host. Nothing in
#: this module may dial it, and nothing may pause a protected container.
PROTECTED_REDIS_HOST_PORT = ":6379"
PROTECTED_CONTAINER_PREFIXES = ("pofa_", "proof-of-action")

# Generous upper bounds: the point is "finite and small", not an exact timing
# promise. The configured values are deliberately tiny so a stalled read is
# distinguishable from a hang inside a couple of seconds.
SOCKET_TIMEOUT = 4.0
CONNECT_TIMEOUT = 2.0
DEQUEUE_BLOCK = 1


def _disposable_url() -> str:
    url = os.environ.get(DISPOSABLE_REDIS_URL_ENV, "").strip()
    if not url:
        pytest.skip(
            f"{DISPOSABLE_REDIS_URL_ENV} is unset: this module needs a disposable "
            "Redis, and the repository's own stack is protected from test traffic."
        )
    if PROTECTED_REDIS_HOST_PORT in url:
        pytest.fail(
            f"{DISPOSABLE_REDIS_URL_ENV} points at the protected Redis port; "
            "re-arm it with this run's disposable server."
        )
    return url


@pytest.fixture
def queue(monkeypatch) -> Iterator[AnalysisQueue]:
    monkeypatch.setattr(settings, "redis_url", _disposable_url())
    monkeypatch.setattr(settings, "analysis_queue_name", f"poa-wsc-it:{uuid.uuid4()}")
    monkeypatch.setattr(settings, "analysis_redis_socket_timeout_seconds", SOCKET_TIMEOUT)
    monkeypatch.setattr(settings, "analysis_redis_socket_connect_timeout_seconds", CONNECT_TIMEOUT)
    monkeypatch.setattr(settings, "analysis_redis_health_check_interval_seconds", 1.0)
    monkeypatch.setattr(settings, "analysis_dequeue_block_seconds", DEQUEUE_BLOCK)
    q = AnalysisQueue()
    try:
        yield q
    finally:
        q.clear()
        q.client.close()


def _container() -> str:
    name = os.environ.get(DISPOSABLE_REDIS_CONTAINER_ENV, "").strip()
    if not name:
        pytest.skip(
            f"{DISPOSABLE_REDIS_CONTAINER_ENV} is unset: a network blackhole can "
            "only be produced by freezing this run's own disposable container."
        )
    if name.startswith(PROTECTED_CONTAINER_PREFIXES):
        pytest.fail(
            f"{name} is not this run's container; the protected stack must never "
            "be frozen, restarted or reconfigured from a test."
        )
    return name


def _docker(*args: str) -> None:
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {proc.stderr.strip()[:200]}")


def test_server_is_reachable_and_queue_starts_empty(queue: AnalysisQueue) -> None:
    """Guard: the armed URL really is a live, empty disposable server."""
    assert queue.client.ping() is True
    assert queue.client.llen(queue.queue_name) == 0


def test_healthy_idle_blocking_dequeue_returns_none_without_looking_like_an_outage(
    queue: AnalysisQueue,
) -> None:
    """The invariant's real-world consequence.

    A blocked read that simply has nothing to return must come back as "no
    message" inside its own wait, not as a connection failure. If the socket
    deadline sat at or below the block, every idle poll would read as an outage
    and a healthy worker would back off forever.
    """
    started = time.monotonic()
    message = queue.dequeue(timeout=DEQUEUE_BLOCK)
    elapsed = time.monotonic() - started

    assert message is None
    assert elapsed < SOCKET_TIMEOUT, "an idle poll must not reach the socket deadline"


def test_vanished_server_fails_fast_as_a_transient_error(
    monkeypatch,
) -> None:
    """A connection that cannot be established is an outage, and it is bounded.

    Port 1 on loopback is closed by construction: nothing is dialled beyond the
    local host, and the attempt cannot succeed. The old unbounded client would
    have sat in connect forever.

    Measured on this host, redis-py reports a failed connect as its own
    ``TimeoutError("Timeout connecting to server")`` rather than as
    ``ConnectionError``. Both are members of the worker's transient set and both
    are refused, so the assertion is on the documented pair: the point is that
    the fault is a *connection-class* error the worker backs off from, not that
    it carries one specific class name.
    """
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(settings, "analysis_queue_name", f"poa-wsc-it:{uuid.uuid4()}")
    monkeypatch.setattr(settings, "analysis_redis_socket_timeout_seconds", SOCKET_TIMEOUT)
    monkeypatch.setattr(settings, "analysis_redis_socket_connect_timeout_seconds", CONNECT_TIMEOUT)
    monkeypatch.setattr(settings, "analysis_redis_health_check_interval_seconds", 1.0)
    monkeypatch.setattr(settings, "analysis_dequeue_block_seconds", DEQUEUE_BLOCK)

    q = AnalysisQueue()
    started = time.monotonic()
    with pytest.raises(TRANSIENT_REDIS_ERRORS) as raised:
        q.dequeue(timeout=DEQUEUE_BLOCK)
    elapsed = time.monotonic() - started

    q.client.close()
    assert elapsed <= CONNECT_TIMEOUT + 3.0, (
        f"connect attempt took {elapsed:.1f}s against a closed port"
    )
    assert isinstance(
        raised.value,
        (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError),
    ), f"unexpected fault class: {type(raised.value).__name__}: {raised.value}"


def test_frozen_server_is_bounded_by_the_socket_timeout(queue: AnalysisQueue) -> None:
    """The case the fix exists for: no disconnect, just silence.

    A warm connection is frozen mid-life, so the failure cannot come from a
    refused connect; it has to come from the read deadline.
    """
    container = _container()
    queue.client.ping()  # establish the socket that will then go silent
    _docker("pause", container)
    try:
        started = time.monotonic()
        with pytest.raises(TRANSIENT_REDIS_ERRORS):
            queue.dequeue(timeout=DEQUEUE_BLOCK * 3)
        elapsed = time.monotonic() - started
    finally:
        _docker("unpause", container)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if queue.client.ping():
                    break
            except redis.exceptions.RedisError:
                time.sleep(0.5)
        else:
            pytest.fail("disposable Redis did not come back after unpause")

    # Bounded by the read deadline (or the pre-command health check against it),
    # never by the server's own silence.
    assert elapsed <= SOCKET_TIMEOUT + 3.0, f"frozen read took {elapsed:.1f}s"


def _wait_reachable(client: redis.Redis, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if client.ping():
                return
        except redis.exceptions.RedisError:
            time.sleep(0.5)
    pytest.fail("disposable Redis did not come back")


def test_failed_acknowledgement_never_loses_or_early_acknowledges_the_job(
    queue: AnalysisQueue,
) -> None:
    """The ordering the worker relies on, on a real server.

    The dequeue moves the payload into the processing list, so an acknowledgement
    that cannot reach Redis has to leave the work visible and recoverable: never
    dropped, never reported as done.

    This uses a stopped server, not a frozen one. Measured in this run's evidence:
    against a *paused* container the guest kernel still accepts and buffers the
    ``LREM``, so an acknowledgement the client already gave up on lands when the
    process resumes and the payload disappears -- the freeze cannot isolate the
    command. A stopped server takes the buffered command down with it, which is
    the failure the guarantee is actually about. It is also the reason the worker
    treats delivery as at-least-once and re-runs recovery classification after
    every outage instead of trusting one acknowledgement.
    """
    job_id = str(uuid.uuid4())
    queue.enqueue(job_id)
    message = queue.dequeue(timeout=DEQUEUE_BLOCK)
    assert message is not None and message.job_id == job_id
    assert queue.client.lrange(queue.processing_name, 0, -1) == [message.payload]

    container = _container()
    _docker("stop", container)
    try:
        ack_failed = False
        try:
            queue.acknowledge(message)
        except TRANSIENT_REDIS_ERRORS:
            ack_failed = True
        assert ack_failed, "acknowledging a dead server must not silently succeed"
    finally:
        _docker("start", container)
        _wait_reachable(queue.client)

    assert queue.client.lrange(queue.processing_name, 0, -1) == [message.payload], (
        "the un-acknowledged payload must survive in the processing list"
    )
    assert queue.client.lrange(queue.queue_name, 0, -1) == [], (
        "a failed ack must not have requeued the job either; recovery owns that"
    )

    queue.acknowledge(message)
    assert queue.client.lrange(queue.processing_name, 0, -1) == []
    assert json.loads(message.payload)["job_id"] == job_id
