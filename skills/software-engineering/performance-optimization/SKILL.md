---
name: performance-optimization
description: Measure-first performance engineering—profiling, bottleneck identification, algorithmic and I/O fixes, caching, and validated before/after results.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: medium
---

# Performance Optimization

## 1. Purpose

Make software faster using measurement rather than intuition. This skill enforces a loop: define the metric and target, reproduce the workload, profile, fix the dominant cost, re-measure, and guard with a regression test. It covers CPU, I/O, allocation, query, and network bottlenecks and when each optimization is worth its complexity cost.

## 2. Activation Conditions

- Latency or throughput targets are missed (p95/p99 SLO breach).
- A hot path is suspected but not proven.
- Cloud bill or resource usage grows unexpectedly.
- Before/after a major change must be reported to stakeholders.
- Keywords: performance, latency, throughput, slow, optimize, profile, benchmark, p95, flamegraph, N+1, caching, hot path.

## 3. When Not to Use

- No reproducible workload or measurement harness exists—build that first.
- User experience issue caused by layout/asset loading (use frontend-performance).
- Memory-specific issues (use memory-optimization) though overlap is expected.
- When correctness is at risk—fix correctness first.
- Micro-optimizing cold paths (< 1% of runtime).

## 4. Required Context

1. The SLO/target: e.g. "p95 < 200 ms at 500 RPS".
2. Workload shape: request mix, payload sizes, read/write ratio, concurrency.
3. Environment: hardware, container limits, noisy-neighbor effects, production vs. test parity.
4. Current metrics and where they come from (APM, logs, Prometheus).
5. Profiling permissions (some profilers need `perf` capabilities or `SYS_PTRACE`).

## 5. Operating Procedure

1. **Define the metric and target** in one sentence. Include the percentile and the measurement point (server-side vs. client-observed).
2. **Build a reproducible benchmark.** Fixed dataset size, warm-up, ≥ 30 s per run, multiple runs, report median and spread.
3. **Establish baseline** with the same workload you will use after the change.
4. **Profile, do not guess.** CPU profile for compute-bound; off-CPU/tracing for I/O waits; heap profile for alloc pressure; DB `EXPLAIN (ANALYZE, BUFFERS)` for queries.
5. **Find the dominant cost.** Use the flame graph's widest stack; compute % of total runtime.
6. **Choose the fix by cost/benefit:**
   - Algorithmic (O(n²) → O(n log n)) — biggest wins.
   - Fewer round trips (batching, N+1 elimination).
   - Caching (with invalidation plan).
   - Data structure/allocation reduction.
   - Parallelism (only for independent work; watch contention).
   - Compiler/runtime flags — smallest, do last.
7. **Change one thing at a time**; re-measure immediately.
8. **Validate under realistic concurrency** (a single-thread benchmark lies about lock contention).
9. **Add a regression benchmark** to CI with an alert threshold.
10. **Document** the change, evidence, and any new operational risk (cache staleness, memory growth).

## 6. Tools and Technologies

| Scope | Tools |
|---|---|
| Python | `cProfile`, `py-spy`, `scalene`, `pyinstrument`, `memray`, `pytest-benchmark` |
| Node/TS | `node --cpu-prof`, `0x`, `clinic`, `autocannon`, `k6` |
| Java | async-profiler, JMH, JFR |
| Go | `pprof` (cpu/heap/block/mutex), `go test -bench -benchmem` |
| Rust | `cargo flamegraph`, `criterion` |
| C/C++ | `perf`, `valgrind --tool=callgrind`, `gprof` |
| System | `perf stat`, `strace -c`, `bpftrace`, `iostat` |
| Web/API | `k6`, `wrk`, `hey`, `vegeta`, Chrome DevTools |
| DB | `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements` |
| Tracing | OpenTelemetry spans, Jaeger/Tempo |

## 7. Practical Implementation

**Python CPU profile + flame graph:**

```bash
python -m cProfile -o prof.out app.py
pip install snakeviz && snakeviz prof.out     # interactive
py-spy record -o flame.svg --pid $(pgrep -f app.py) --duration 30
```

**Fix an N+1 (before/after):**

```python
# Before: 1 + N queries
orders = session.execute(select(Order).limit(100)).scalars().all()
for o in orders:
    print(o.customer.name)   # lazy load per order

# After: 2 queries total
orders = session.execute(
    select(Order).options(selectinload(Order.customer)).limit(100)
).scalars().all()
```

**Postgres: prove the index works**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, total_cents FROM orders
WHERE tenant_id = '6f2c...' AND status = 'pending'
ORDER BY created_at DESC LIMIT 20;

-- Seq Scan + Sort  → add a covering index
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_created
  ON orders (tenant_id, status, created_at DESC)
  INCLUDE (total_cents);
```

**Go benchmark:**

```go
func BenchmarkParse(b *testing.B) {
    data := loadFixture(b)
    b.ResetTimer()
    b.ReportAllocs()
    for i := 0; i < b.N; i++ {
        if _, err := parse(data); err != nil { b.Fatal(err) }
    }
}
```

```bash
go test -run '^$' -bench . -benchmem -count 5 ./pkg/parser
```

**Load test with thresholds (k6):**

```js
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: { steady: { executor: 'constant-arrival-rate', rate: 500, timeUnit: '1s', duration: '2m', preAllocatedVUs: 100 } },
  thresholds: { http_req_duration: ['p(95)<200'], http_req_failed: ['rate<0.01'] },
};

export default function () {
  const res = http.get('http://localhost:8000/v1/orders?limit=20');
  check(res, { 'status 200': (r) => r.status === 200 });
}
```

**Cache with explicit invalidation (Redis):**

```python
import json, redis

r = redis.Redis(decode_responses=True)

def get_catalog(tenant_id: str, fetch):
    key = f"catalog:{tenant_id}:v3"
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    data = fetch(tenant_id)
    r.set(key, json.dumps(data), ex=300)  # 5-minute TTL, version in key
    return data
```

## 8. Quality Standards

- Every optimization has a before/after measurement on the same workload.
- Dominant cost is identified as % of total before changing code.
- No caching without a documented invalidation strategy and staleness bound.
- Benchmarks run ≥ 3 times; results report median and p95.
- p99 is checked, not just average; averages hide tail pain.
- Regression benchmarks are in CI with an explicit threshold.
- Complexity added for speed is justified by the measured gain.

## 9. Verification and Testing

```bash
k6 run --vus 200 --duration 2m load.js
hey -z 30s -c 50 http://localhost:8000/v1/orders
ab -n 10000 -c 100 http://localhost:8000/health   # legacy but still usable
pgbench -c 20 -j 4 -T 60 -f query.sql mydb
```

Report a table: metric | baseline | after | change %, plus resource usage (CPU, RSS) to prove no regressions elsewhere.

## 10. Security Considerations

- Profilers can dump memory containing secrets; restrict access and delete artifacts.
- Never benchmark against production without authorization; use anonymized production-shaped data.
- Do not disable security features for speed (TLS offloading without re-encryption, deleting auth checks, disabling rate limits).
- Caching auth decisions for speed can cause privilege persistence after revocation—bound the TTL.
- Load tests can look like DoS attacks: coordinate with network teams and use allowlisted source IPs.
- Watch for timing side channels when replacing constant-time comparisons for speed.

## 11. Failure Handling

- **No improvement:** the profile pointed at the wrong layer (e.g. waiting on DB while you optimized CPU). Re-profile end-to-end with distributed tracing.
- **Faster locally, slower in prod:** environment mismatch (CPU limits, connection pool size, cold cache). Replicate limits.
- **Cache stamps after a fix:** invalidation bug; add versioned keys and test invalidation paths.
- **Parallelism made it slower:** lock contention or memory bandwidth; measure with `perf stat` and reduce shared state.
- **Benchmark flakiness:** pin CPU (`taskset`), disable turbo where possible, run multiple counts, compare medians.

## 12. Expected Deliverables

1. Metric definition and target.
2. Benchmark harness committed to the repo.
3. Baseline profile artifacts (flame graph, query plans).
4. Prioritized list of bottlenecks with % of runtime.
5. Implemented fixes with diffs.
6. Before/after results table with percentiles.
7. CI regression guard.
8. Operational notes (cache TTLs, memory, new failure modes).

## 13. References

- Brendan Gregg, *Systems Performance*, 2nd ed. — https://www.brendangregg.com/systems-performance-2nd-edition-book.html
- Brendan Gregg, "Flame Graphs" — https://www.brendangregg.com/flamegraphs.html
- PostgreSQL `EXPLAIN` documentation — https://www.postgresql.org/docs/current/using-explain.html
- k6 documentation — https://k6.io/docs/
- py-spy — https://github.com/benfred/py-spy
- Go pprof — https://pkg.go.dev/net/http/pprof
- OpenTelemetry — https://opentelemetry.io/docs/
