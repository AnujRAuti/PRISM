---
name: memory-optimization
description: Diagnose and reduce memory footprint and leaks—heap profiling, allocation reduction, object lifetime control, and GC tuning validated by measured RSS/heap before and after.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: medium
---

# Memory Optimization

## 1. Purpose

Control memory usage: eliminate leaks, reduce steady-state footprint, cut allocation churn, and tune garbage collection only after the first two are done. The skill distinguishes leaks (unbounded growth), bloat (large steady state), and churn (high allocation rate causing GC pressure), because each needs different tools and fixes. It produces measured evidence, not hopeful changes.

## 2. Activation Conditions

- OOM kills (`exit code 137`), container restarts, or rising RSS over time.
- GC pauses causing latency spikes; allocation rate dominating CPU.
- Loading large datasets or files into memory.
- Memory limits in Kubernetes require a guarantee, not a guess.
- Keywords: memory leak, OOM, RSS, heap, GC, allocation, out of memory, memory limit, malloc, retain cycle, memray, valgrind.

## 3. When Not to Use

- Pure latency/throughput problems with flat memory (use performance-optimization).
- When the footprint is acceptable and stable—do not optimize without a target.
- Before verifying the host container limit; if the limit is misconfigured, fixing code will not help.
- Tuning GC flags before finding the leak—you may just delay the OOM.

## 4. Required Context

1. Observed memory curve over time (flat, sawtooth, monotonic increase).
2. Container/host limits and runtime version (`python --version`, `java -version`, `node -v`).
3. Workload characteristics: request sizes, batch sizes, concurrency.
4. Whether restarts correlate with specific endpoints or jobs.
5. Access to heap dumps/profiles in an environment that mirrors load.

## 5. Operating Procedure

1. **Classify** the problem: monotonic growth after GC → leak; high plateau → bloat; sawtooth with short period → churn.
2. **Measure baseline**: RSS via `ps`/`docker stats`; heap via runtime tooling; record under fixed load.
3. **Confirm the limit** (`cat /sys/fs/cgroup/memory.max` in cgroup v2; `memory.stat` for breakdown).
4. **For suspected leaks**, take two heap snapshots separated by sustained load and diff retainer paths.
5. **Fix the root cause**: unbounded caches, listener/observer leaks, growing collections, thread-locals, closures capturing large objects, unclosed resources.
6. **For bloat**, reduce per-item cost: use compact representations (arrays of structs vs. dicts, `__slots__`, `dataclass(slots=True)`, primitives over boxed types), stream instead of load, and page large results.
7. **For churn**, reduce allocations in hot paths: reuse buffers, avoid intermediate copies, prefer generators/iterators, pool where profiling shows allocation cost.
8. **Set explicit cache bounds** (max entries + TTL + eviction) and verify eviction happens.
9. **Tune GC only after 5–8**, and only with measurements: heap size ratio, young-gen size, pause target.
10. **Validate** with a soak test (≥ 1 h) at target load; RSS must plateau.
11. **Add a memory regression test** and alert on RSS growth slope.

## 6. Tools and Technologies

| Runtime | Tools |
|---|---|
| Python | `tracemalloc`, `memray`, `objgraph`, `gc.get_objects`, `resource.getrusage` |
| Node.js | `--inspect` + Chrome DevTools heap snapshots, `--max-old-space-size`, `clinic heapprofiler` |
| Java/JVM | `jcmd GC.heap_dump`, Eclipse MAT, JFR, async-profiler `-e alloc`, `-Xmx`, G1/ZGC |
| Go | `runtime/pprof` heap profile, `GODEBUG=gctrace=1`, `go tool pprof -inuse_space` |
| Rust | `heaptrack`, `valgrind --tool=massif`, jemalloc stats |
| C/C++ | `valgrind --leak-check=full`, ASan `-fsanitize=address`, `massif` |
| System | `smem`, `pmap -x`, `docker stats`, cgroup `memory.stat` |

## 7. Practical Implementation

**Python: tracemalloc snapshot diff**

```python
import tracemalloc, linecache

tracemalloc.start(25)
snap1 = tracemalloc.take_snapshot()

run_workload()

snap2 = tracemalloc.take_snapshot()
for stat in snap2.compare_to(snap1, "traceback")[:10]:
    print(stat)
    for line in stat.traceback.format():
        print("   ", line)
```

**Python: memray flame graph of allocations**

```bash
pip install memray
python -m memray run -o mem.bin app.py
memray flamegraph mem.bin -f -o mem.html
memray summary mem.bin
```

**Fix an unbounded cache (Python):**

```python
from collections import OrderedDict

class BoundedCache:
    def __init__(self, max_items: int = 10_000):
        self._data: OrderedDict[str, bytes] = OrderedDict()
        self._max = max_items

    def get(self, key: str) -> bytes | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: str, value: bytes) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)   # LRU eviction
```

**Python: slots to cut per-object cost**

```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class Point:
    x: float
    y: float
```

**Go: capture and inspect a heap profile**

```go
import (
    "net/http"
    _ "net/http/pprof"
)

func main() { _ = http.ListenAndServe("127.0.0.1:6060", nil) } // debug only, never public
```

```bash
go tool pprof -inuse_space http://127.0.0.1:6060/debug/pprof/heap
# interactive: top, list FuncName, web
GODEBUG=gctrace=1 ./server     # verify GC cycle behavior
```

**Java: heap dump and analysis**

```bash
jcmd $(pgrep -f myapp) GC.heap_dump /tmp/heap.hprof
# open /tmp/heap.hprof in Eclipse MAT; run "Leak Suspects"
```

**C: catch the leak**

```bash
gcc -g -fsanitize=address,leak app.c -o app && ./app
valgrind --leak-check=full --show-leak-kinds=all ./app
```

**Kubernetes memory limit sanity check**

```bash
kubectl exec deploy/api -- cat /sys/fs/cgroup/memory.max
kubectl exec deploy/api -- cat /sys/fs/cgroup/memory.stat | head
kubectl top pods
```

## 8. Quality Standards

- A memory target is stated (e.g. "steady state < 350 MiB at 200 RPS, no growth over 1 h").
- Leak fixes are proven by a soak test with a flat RSS line.
- Every cache has a bound and an eviction policy; no `dict` used as an unlimited cache.
- Large payloads are streamed, not fully materialized, wherever the API allows.
- GC tuning is documented with before/after pause and throughput numbers.
- Memory regression tests or alerts exist (RSS slope, heap after GC).

## 9. Verification and Testing

```bash
# soak test: apply steady load for 1 hour, sample RSS every 10 s
for i in $(seq 1 360); do ps -o rss= -p $(pgrep -f 'uvicorn|node|java') >> rss.log; sleep 10; done
python - <<'PY'
import statistics
vals = [int(l) for l in open("rss.log")]
first, last = statistics.mean(vals[:30]), statistics.mean(vals[-30:])
print(f"start={first/1024:.0f}MiB end={last/1024:.0f}MiB growth={(last-first)/first*100:.1f}%")
PY
```

Acceptance: growth < 5% across the run, no OOM restart, heap-after-GC stable, p99 latency unchanged.

## 10. Security Considerations

- Heap dumps contain secrets, tokens, and PII: store them encrypted, restrict access, delete after analysis.
- Never expose `/debug/pprof`, JMX, or Node inspector ports publicly; bind to localhost or a protected admin network.
- ASan/valgrind builds may disable other hardening; do not ship them.
- Reducing memory by disabling safety checks (bounds checks, sanitizers) trades security for footprint—do not.
- `mmap`ed files and swap can leak data to disk; consider `mlock` for sensitive buffers and zero memory before free where required.
- Container memory limits protect the host: never run privileged without limits.

## 11. Failure Handling

- **RSS grows but heap is flat:** native/off-heap allocations, thread stacks, memory-mapped files, or allocator fragmentation. Use `pmap -x`, `smem`, `heaptrack`, or jemalloc stats.
- **OOM despite low heap:** container limit too low or a spike in concurrent large requests; add concurrency bounds/backpressure.
- **Leak not reproducible in staging:** the difference is usually workload shape; replay captured traffic (sanitized).
- **Fix made it slower:** allocation savings traded for CPU; re-measure throughput and decide by the stated target.
- **GC tuning did not help:** the allocation rate is the problem, not collector settings; return to churn reduction.

## 12. Expected Deliverables

1. Memory problem classification and target.
2. Baseline measurements (RSS, heap, allocation rate, GC pauses).
3. Profile artifacts and identified root cause with retainer path.
4. Code changes with diffs.
5. Soak-test results showing stable memory.
6. Bounded caches and documented limits.
7. Monitoring/alert recommendation (RSS slope, heap after GC).

## 13. References

- Python `tracemalloc` — https://docs.python.org/3/library/tracemalloc.html
- memray — https://bloomberg.github.io/memray/
- Go `runtime/pprof` — https://pkg.go.dev/runtime/pprof
- Node.js memory diagnostics — https://nodejs.org/en/learn/diagnostics/memory
- Eclipse Memory Analyzer — https://eclipse.dev/mat/
- Valgrind manual — https://valgrind.org/docs/manual/manual.html
- Linux cgroup v2 memory controller — https://docs.kernel.org/admin-guide/cgroup-v2.html
