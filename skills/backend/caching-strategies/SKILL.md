---
name: caching-strategies
description: Add caching without breaking correctness—cache-aside patterns, TTL and invalidation, Redis key design, stampede protection, and cache-consistency testing.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# Caching Strategies

## 1. Purpose

Reduce latency and database load with caches that do not serve stale or wrong data. Most caching incidents are consistency incidents: keys that never expire, invalidation hooks that miss a path, and thundering herds when a hot key expires. This skill covers pattern selection, key design, TTL policy, invalidation ownership, stampede control, and the tests that prove a cache is safe.

**Scope:** your own caches. A cache is a copy of data with weaker access control—never cache per-user sensitive data under a shared key, and treat cache contents as untrusted input when reading them back.

## 2. Activation Conditions

- Read-heavy endpoints hitting the database repeatedly for the same rows.
- p95 latency dominated by a slow query or external call.
- Traffic spikes overwhelm the database at cache expiry.
- Need to decide between in-process, Redis, or CDN caching.
- Keywords: cache, Redis, Memcached, cache-aside, TTL, invalidation, stampede, thundering herd, write-through, CDN, ETag, single-flight.

## 3. When Not to Use

- Data changes on every read (a cache guarantees staleness with no benefit).
- Strong consistency is mandatory and invalidation cannot be made reliable.
- The bottleneck is CPU in the app process, not data access.

## 4. Required Context

1. Read/write ratio per entity and tolerance for staleness (seconds? minutes?).
2. Data ownership: which service writes each entity.
3. Access patterns: hot keys, cardinality, payload sizes.
4. Available infrastructure (Redis, Memcached, CDN).
5. Failure behavior desired when the cache is down (fail open to DB or fail closed).

## 5. Operating Procedure

1. **Decide the pattern**:
   - Cache-aside (lazy): app reads cache, on miss reads DB and populates. Default choice.
   - Write-through: write cache and DB together — simpler consistency, higher write latency.
   - Write-behind: async flush — risks data loss; avoid for critical data.
   - Read-through: cache library loads on miss (same semantics as aside).
2. **Name keys with a version prefix and full identity**: `v3:order:{order_id}:detail`. Include tenant where data is scoped.
3. **Set an explicit TTL always** (no unbounded keys), and a shorter TTL for volatile data.
4. **Assign an owner for invalidation**: the writer deletes or updates the key after a successful commit, not before.
5. **Protect against stampedes**: single-flight per key (in-process lock), jittered TTLs, and stale-while-revalidate for high-traffic keys.
6. **Add negative caching** for repeated misses (e.g. `404` for 30 s) with a short TTL to prevent penetration.
7. **Size and bound values** (compress large payloads, cap at ~100 kB); never cache unbounded lists.
8. **Instrument hit rate, latency, and errors**; alert when hit rate drops or Redis latency rises.
9. **Design degradation**: on cache failure, log and fall through to the source of truth with a circuit breaker if the DB is also strained.
10. **Test consistency explicitly**: write then read through the cache; verify no stale value survives the invalidation path.

## 6. Tools and Technologies

| Layer | Options |
|---|---|
| In-process | `functools.lru_cache`, `cachetools`, `node-cache` |
| Shared | Redis, Valkey, Memcached |
| HTTP | `Cache-Control`, `ETag`, `Vary`, CDN (Cloudflare, Fastly) |
| Client libs | `redis-py` (async), `ioredis`, `go-redis` |
| Patterns | single-flight, `cachetools` TTLCache, `pytest-redis` |
| Observability | Redis `INFO stats`, `SLOWLOG`, OpenTelemetry spans |

## 7. Practical Implementation

**Cache-aside with versioned keys and TTL:**

```python
import json
from redis.asyncio import Redis
from app.domain.order import Order
from app.repositories.orders import OrderRepository

CACHE_VERSION = "v3"

def order_key(order_id: str) -> str:
    return f"{CACHE_VERSION}:order:{order_id}:detail"

class CachedOrderRepository:
    def __init__(self, repo: OrderRepository, redis: Redis, ttl: int = 300) -> None:
        self._repo, self._redis, self._ttl = repo, redis, ttl

    async def get(self, order_id: str) -> Order | None:
        key = order_key(order_id)
        try:
            raw = await self._redis.get(key)
        except Exception:
            raw = None                       # cache failure degrades to source of truth
        if raw is not None:
            return Order(**json.loads(raw))  # validate on read: cache is untrusted input

        order = await self._repo.get(order_id)
        if order is None:
            await self._redis.set(key, "null", ex=30, nx=True)   # negative cache
            return None
        await self._redis.set(key, json.dumps(order.model_dump(mode="json")), ex=self._ttl)
        return order

    async def save(self, order: Order) -> None:
        await self._repo.save(order)                  # commit first
        await self._redis.delete(order_key(order.id)) # invalidate after commit
```

Note: deleting after commit can still race with a concurrent reader that repopulates stale data. For strict needs, use a short TTL plus version-bumped keys, or write-through with a database transaction id in the key.

**Single-flight to prevent a stampede:**

```python
import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")
_locks: dict[str, asyncio.Lock] = {}

async def single_flight(key: str, load: Callable[[], Awaitable[T]]) -> T:
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        return await load()
```

For multi-instance stampede protection, use a Redis lock (`SET key val NX PX 5000`) so only one process recomputes while others wait briefly and then read the cache or fall back.

**Jittered TTL:**

```python
import random

def jittered_ttl(base: int, spread: float = 0.15) -> int:
    return max(1, int(base * (1 + random.uniform(-spread, spread))))
```

**Stale-while-revalidate (serve stale, refresh in background):**

```python
async def get_with_swr(redis: Redis, key: str, loader, *, fresh: int = 60, stale: int = 600):
    raw = await redis.get(key)
    if raw is not None:
        ttl = await redis.ttl(key)
        if ttl is not None and ttl < 0:
            pass
        if ttl is not None and ttl > 0:
            return json.loads(raw)
        if ttl is not None and ttl <= 0:
            asyncio.create_task(_refresh(redis, key, loader, fresh))
            return json.loads(raw)
    value = await loader()
    await redis.set(key, json.dumps(value), ex=fresh + stale)
    return value

async def _refresh(redis: Redis, key: str, loader, fresh: int) -> None:
    value = await loader()
    await redis.set(key, json.dumps(value), ex=fresh)
```

**HTTP/CDN caching with correct headers:**

```python
@router.get("/catalog/{category}")
async def catalog(category: str, response: Response, svc: CatalogService = Depends(get_svc)):
    data = await svc.category(category)
    response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    response.headers["ETag"] = f'W/"{data.version}"'
    response.headers["Vary"] = "Accept-Encoding"
    return data
```

Never mark authenticated, per-user responses `public`: use `Cache-Control: private, no-store` for account pages.

**In-process LRU for hot, rarely changing lookups:**

```python
from functools import lru_cache

@lru_cache(maxsize=2048)
def currency_exponent(code: str) -> int:
    # static reference data loaded at startup; invalidated by process restart
    return CURRENCY_EXPONENTS[code]
```

**Bulk read to avoid per-item round trips:**

```python
async def get_many(redis: Redis, ids: list[str]) -> dict[str, dict]:
    keys = [order_key(i) for i in ids]
    values = await redis.mget(keys)
    return {i: json.loads(v) for i, v in zip(ids, values) if v not in (None, "null")}
```

**Metrics to emit:**

```python
from prometheus_client import Counter

CACHE = Counter("cache_requests_total", "Cache requests", ["cache", "result"])
CACHE.labels("order_detail", "hit").inc()
CACHE.labels("order_detail", "miss").inc()
```

**Test: writes invalidate reads:**

```python
async def test_write_invalidates_cache(cached_repo, redis):
    order = await cached_repo.get("ord_1")                 # populates
    assert await redis.get(order_key("ord_1")) is not None
    updated = order.model_copy(update={"status": "paid"})
    await cached_repo.save(updated)
    assert await redis.get(order_key("ord_1")) is None     # invalidated
    fresh = await cached_repo.get("ord_1")
    assert fresh.status == "paid"
```

## 8. Quality Standards

- Every key has a TTL; no unbounded growth.
- Keys include a version prefix so a schema change can invalidate all at once.
- Cache reads are validated (parse/validate failures are treated as misses, not crashes).
- Invalidation happens after a successful commit and covers every write path (including admin tools and background jobs).
- Stale data tolerance is documented per entity.
- Sensitive per-user data is never cached under a shared key; responses with auth are `private, no-store`.
- Degradation path is defined and tested (cache down → DB path still works).
- Hit rate, latency, and error metrics are monitored with alerts.

## 9. Verification and Testing

- Consistency tests: read → write → read through every path (API, job, admin) and assert freshness.
- Stampede test: expire a hot key under load (e.g. 500 concurrent requests) and confirm the loader runs once (or a bounded number of times).
- Failure injection: make Redis unreachable and verify requests still succeed via the DB path.
- TTL test with a fake clock (`freezegun`, `time-machine`) for expiry behavior.
- Key audit: scan Redis for keys without TTL (`TTL` = -1) in staging.
- Load test to confirm hit rate and p99 improvement.

## 10. Security Considerations

- Cache poisoning: if cache keys are built from user input, validate and canonicalize; never let a user control the key namespace.
- Shared caches must include tenant/user scope in the key, or one tenant can read another's data.
- Cached data inherits the sensitivity of the source: encrypt or avoid caching PII/secrets/tokens.
- Redis must not be internet-exposed; require auth, TLS, and network isolation, and disable dangerous commands (`FLUSHALL`, `CONFIG`) for app users.
- Serialization: prefer JSON over pickle. Never unpickle data from a shared cache — that is remote code execution.
- `Vary` and CDN rules matter: an authenticated response cached publicly is a data breach.
- Cache invalidation on permission change: if a user loses access, cached objects must not remain readable.

## 11. Failure Handling

- **Stale value persists after update:** a write path bypassed invalidation (job, admin, direct SQL). Centralize writes in one repository and add a test per path.
- **Thundering herd on expiry:** single-flight plus jittered TTL plus stale-while-revalidate.
- **Hot key overwhelms one Redis shard:** replicate the key with a random suffix and fan-out reads, or use a local in-process layer for that key.
- **Cache and DB disagree permanently:** add a reconciliation job or version column that lets you detect and repair drift.
- **Redis memory eviction of important keys:** use separate logical databases or instances for critical versus best-effort caches, and set `maxmemory-policy` intentionally.
- **Serialization errors after deploy:** bump the key version prefix so old payloads are ignored.

## 12. Expected Deliverables

1. Cache pattern chosen per entity, with staleness tolerance.
2. Key naming and versioning scheme.
3. TTL table.
4. Invalidation map (writer → keys).
5. Stampede and negative-cache handling.
6. Degradation behavior and metrics.
7. Consistency and failure-injection test suite.

## 13. References

- Redis documentation — https://redis.io/docs/latest/
- Redis key eviction (`maxmemory-policy`) — https://redis.io/docs/latest/develop/reference/eviction/
- AWS caching best practices — https://aws.amazon.com/caching/best-practices/
- MDN HTTP caching — https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching
- `redis-py` asyncio — https://redis-py.readthedocs.io/en/stable/examples/asyncio_examples.html
- "Caching at Scale" (Facebook/Meta engineering blog) — https://engineering.fb.com/2013/06/25/core-data/mcache-facebooks-memcache-system-at-scale/
- `cachetools` — https://cachetools.readthedocs.io/
