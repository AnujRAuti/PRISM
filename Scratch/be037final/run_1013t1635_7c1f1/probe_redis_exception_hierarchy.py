"""BE-037 WS-C: the redis-py 4.6.0 exception hierarchy, measured not recalled.

Prints each class's MRO and the subclass relations the worker's
TRANSIENT_REDIS_ERRORS tuple depends on, plus the version it came from.
"""

import inspect
import sys

sys.path.insert(0, r"D:\CODING\Projects\Proof-Of-Action-Final")

import redis
from redis import exceptions as ex

print("redis-py version:", redis.__version__, redis.__file__)

for name in ("ConnectionError", "TimeoutError", "BusyLoadingError",
             "AuthenticationError", "ResponseError", "DataError", "RedisError"):
    cls = getattr(ex, name)
    print(f"{name}: MRO={[c.__name__ for c in cls.__mro__]}")

print()
pairs = [
    ("TimeoutError", "ConnectionError"),
    ("BusyLoadingError", "ConnectionError"),
    ("AuthenticationError", "ConnectionError"),
    ("ConnectionError", "RedisError"),
    ("TimeoutError", "RedisError"),
    ("ResponseError", "RedisError"),
    ("ResponseError", "ConnectionError"),
]
for child, parent in pairs:
    print(f"issubclass({child}, {parent}) = "
          f"{issubclass(getattr(ex, child), getattr(ex, parent))}")

print()
print("Connection.__init__ timeout-related defaults:")
sig = inspect.signature(ex.Connection.__init__ if hasattr(ex, "Connection") else object)
from redis.connection import AbstractConnection

params = inspect.signature(AbstractConnection.__init__).parameters
for key in ("socket_timeout", "socket_connect_timeout", "health_check_interval",
            "retry_on_timeout", "socket_keepalive"):
    print(f"  {key} = {params[key].default!r}")
