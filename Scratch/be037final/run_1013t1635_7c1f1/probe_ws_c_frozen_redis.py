"""BE-037 WS-C baseline: what the queue client really does to a frozen Redis.

Measured against this run's disposable Redis only (be037fin7c1f1_redis,
127.0.0.1:16379). Nothing here touches pofa_redis. Every observation is bounded
by a wall-clock budget so the probe cannot hang the session, and the container
is unpaused in a finally block.

Questions this answers, from the task's WS-C list:
  * does the blocking command have a finite socket timeout as configured today?
  * does health_check_interval rescue a frozen connection?
  * can a stall without a clean disconnect block the worker indefinitely?
"""

import json
import socket
import subprocess
import sys
import time

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

import redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from backend.services.analysis_queue import AnalysisQueue

CONTAINER = "be037fin7c1f1_redis"
URL = "redis://127.0.0.1:16379/0"
BUDGET_SECONDS = 45.0

results: dict = {"budget_seconds": BUDGET_SECONDS}


def timed(fn, budget):
    """Run fn in a daemon thread and report either its value or 'hung > budget'."""
    holder = {}

    def target():
        try:
            holder["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - reporting is the point
            holder["error"] = exc

    thread = __import__("threading").Thread(target=target, daemon=True)
    start = time.monotonic()
    thread.start()
    thread.join(budget)
    elapsed = round(time.monotonic() - start, 3)
    if thread.is_alive():
        return {"elapsed": elapsed, "outcome": "HUNG past the budget", "thread": "daemon, abandoned"}
    if "error" in holder:
        exc = holder["error"]
        return {
            "elapsed": elapsed,
            "outcome": type(exc).__name__,
            "mro": [c.__name__ for c in type(exc).__mro__][:5],
            "message": str(exc)[:200],
        }
    return {"elapsed": elapsed, "outcome": "returned", "value": repr(holder["value"])[:200]}


def control(state):
    return subprocess.run(
        ["docker", state, CONTAINER], capture_output=True, text=True, timeout=60
    ).returncode


try:
    # Isolation assertion first: the protected pofa_redis answers on 6379 and
    # must never be the target of an outage injection.
    from backend.core.config import settings as _settings

    results["redis_url_in_use"] = _settings.redis_url
    assert ":16379" in _settings.redis_url, (
        f"refusing to run: REDIS_URL points at {_settings.redis_url!r}, not this "
        "run's disposable Redis on port 16379"
    )

    # 0. the exception hierarchy the worker's tuple is built on
    results["timeouterror_is_subclass_of_connectionerror"] = issubclass(
        RedisTimeoutError, RedisConnectionError
    )
    results["both_under_rediserror"] = issubclass(
        RedisTimeoutError, redis.exceptions.RedisError
    )

    # 1. healthy baseline: the blocking dequeue honours its own 5s block timeout
    queue = AnalysisQueue()
    results["client_kwargs_as_configured"] = {
        "socket_timeout": queue.client.connection_pool.connection_kwargs.get(
            "socket_timeout"
        ),
        "socket_connect_timeout": queue.client.connection_pool.connection_kwargs.get(
            "socket_connect_timeout"
        ),
        "health_check_interval": queue.client.connection_pool.connection_kwargs.get(
            "health_check_interval"
        ),
    }
    results["healthy_blocking_dequeue"] = timed(lambda: queue.dequeue(timeout=5), 20.0)
    queue.client.close()

    # 2. freeze the container: no RST, no FIN, the socket just stops answering
    results["pause_returncode"] = control("pause")
    frozen_started = time.monotonic()

    if results["pause_returncode"] != 0:
        results["frozen_probes"] = "SKIPPED: docker pause failed"
    else:
        fresh = AnalysisQueue()
        results["frozen_new_connection_ping"] = timed(
            lambda: fresh.client.ping(), BUDGET_SECONDS
        )
        results["frozen_blocking_dequeue"] = timed(
            lambda: fresh.dequeue(timeout=5), BUDGET_SECONDS
        )
        results["frozen_raw_socket_check"] = timed(
            lambda: socket.create_connection(("127.0.0.1", 16379), timeout=5)
            .sendall(b"PING\r\n")
            or socket.socket().close(),
            15.0,
        )
        fresh.client.close()

    results["frozen_observation_seconds"] = round(time.monotonic() - frozen_started, 1)
finally:
    results["unpause_returncode"] = control("unpause")
    time.sleep(1)
    resumed = redis.Redis.from_url(URL)
    results["redis_reachable_after_unpause"] = resumed.ping()
    resumed.close()
    print(json.dumps(results, indent=2, default=str))
