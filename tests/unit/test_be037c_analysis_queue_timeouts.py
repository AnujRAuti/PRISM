"""BE-037 WS-C: the queue client's reads have a deadline.

Baseline measured on this run's disposable Redis (final-07): with the redis-py
4.6.0 defaults the queue client had ``socket_timeout=None``,
``socket_connect_timeout=None`` and ``health_check_interval=0``, and freezing the
container left both ``ping`` and the blocking ``brpoplpush`` hanging past a
45-second budget. A worker stuck inside a read reaches neither the outage
handler nor its shutdown check, so no amount of backoff logic helps until the
read itself can fail.

These are configuration-level tests: ``Redis.from_url`` does not connect, so no
server is needed and no server is dialled (the DSN used is port 1, unreachable
by design and never touched).
"""

import redis
import pytest

from backend.core.config import settings
from backend.services.analysis_queue import AnalysisQueue

#: A DSN that is only ever parsed, never dialled.
UNUSED_URL = "redis://127.0.0.1:1/0"


class Injected:
    """Stand-in for a caller-supplied client; proves injection bypasses the pool."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", UNUSED_URL)
    monkeypatch.setattr(settings, "analysis_redis_socket_timeout_seconds", 30.0)
    monkeypatch.setattr(settings, "analysis_redis_socket_connect_timeout_seconds", 10.0)
    monkeypatch.setattr(settings, "analysis_redis_health_check_interval_seconds", 15.0)
    monkeypatch.setattr(settings, "analysis_dequeue_block_seconds", 5)
    return settings


def pool_kwargs(queue: AnalysisQueue) -> dict:
    return queue.client.connection_pool.connection_kwargs


def test_every_read_bound_is_configured(configured):
    """The three values the frozen-server baseline found unset are now set."""
    kwargs = pool_kwargs(AnalysisQueue())

    assert kwargs["socket_timeout"] == configured.analysis_redis_socket_timeout_seconds
    assert (
        kwargs["socket_connect_timeout"]
        == configured.analysis_redis_socket_connect_timeout_seconds
    )
    assert (
        kwargs["health_check_interval"]
        == configured.analysis_redis_health_check_interval_seconds
    )


def test_no_read_bound_is_left_open(configured):
    """The regression itself: ``None``/0 means "block forever", which is the bug."""
    kwargs = pool_kwargs(AnalysisQueue())

    assert kwargs["socket_timeout"], "an unset socket timeout hangs on a stalled server"
    assert kwargs["socket_connect_timeout"]
    assert kwargs["health_check_interval"]


def test_socket_deadline_must_outlast_the_blocking_wait(configured, monkeypatch):
    """An idle ``brpoplpush`` is supposed to return "no message", not raise.

    If the socket deadline were at or below the block wait, every healthy idle
    poll would present as a Redis outage and the worker would back off forever
    while the server was fine.
    """
    monkeypatch.setattr(configured, "analysis_redis_socket_timeout_seconds", 5.0)
    monkeypatch.setattr(configured, "analysis_dequeue_block_seconds", 5)

    with pytest.raises(ValueError, match="must be greater than ANALYSIS_DEQUEUE_BLOCK_SECONDS"):
        AnalysisQueue()


def test_injected_client_bypasses_the_pool_builder(configured, monkeypatch):
    """Tests and callers that supply their own connection keep their own bounds."""
    monkeypatch.setattr(configured, "analysis_redis_socket_timeout_seconds", 1.0)
    injected = Injected()

    queue = AnalysisQueue(client=injected)

    assert queue.client is injected


def test_queue_names_are_unchanged_by_the_timeout_work(configured):
    """The deadline change must not move the keys the worker recovers from."""
    queue = AnalysisQueue()

    assert queue.queue_name == configured.analysis_queue_name
    assert queue.processing_name == f"{configured.analysis_queue_name}:processing"


def test_client_is_a_real_redis_instance_with_the_pinned_hierarchy(configured):
    """Pin the client class the worker's exception tuple was written against.

    The transient/outage split depends on redis-py's hierarchy (TimeoutError and
    ConnectionError as siblings); a different client type would silently change
    what the loop treats as an outage.
    """
    client = AnalysisQueue().client

    assert isinstance(client, redis.Redis)
    assert not issubclass(
        redis.exceptions.TimeoutError, redis.exceptions.ConnectionError
    )
