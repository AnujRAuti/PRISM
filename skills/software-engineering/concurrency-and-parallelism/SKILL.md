---
name: concurrency-and-parallelism
description: Design correct concurrent code—threads, async I/O, locks, channels, atomics—and prove absence of races, deadlocks, and lost updates under load.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: high
---

# Concurrency and Parallelism

## 1. Purpose

Make concurrent code correct, then fast. This skill separates concurrency (structuring for multiple in-flight tasks) from parallelism (executing simultaneously on cores), maps each to the right primitive in each language, and enforces a verification loop with race detectors, stress tests, and deadlock analysis. It prevents the classic failures: lost updates, check-then-act races, deadlocks from inconsistent lock ordering, and async blocking the event loop.

## 2. Activation Conditions

- Shared mutable state accessed by multiple threads/tasks/processes.
- Adding workers, thread pools, `asyncio`, `tokio`, goroutines, or `CompletableFuture`.
- Symptoms: intermittent wrong results, stalls under load, CPU below 100% while latency climbs.
- Designing background job processing or high-throughput servers.
- Keywords: race condition, deadlock, mutex, semaphore, thread pool, async, await, goroutine, channel, atomic, lock-free, backpressure.

## 3. When Not to Use

- Single-threaded request handlers with no shared state.
- Problems solvable by using a database transaction or queue instead of in-process synchronization.
- When the workload is I/O-bound and a simpler sequential loop meets the SLO.
- Before correctness is established—parallelizing buggy code multiplies bugs.

## 4. Required Context

1. Language and runtime concurrency model (GIL, event loop, OS threads, green threads).
2. Where state is shared: module globals, singletons, caches, connection pools.
3. Failure modes already observed and how often.
4. Deployment: process model (gunicorn workers, Kubernetes replicas) — multiple processes do not share memory, which changes the design.
5. Available CPU/memory and whether the runtime is inside a container with a CPU quota.

## 5. Operating Procedure

1. **Draw the concurrency model**: tasks, shared resources, and the ordering guarantees required.
2. **Eliminate sharing first.** Prefer immutable data, per-task state, and message passing over locks. Most lock bugs disappear when there is nothing to lock.
3. **Classify the workload** (CPU-bound vs I/O-bound) to select the mechanism:
   - I/O-bound: async/await or threads.
   - CPU-bound: processes or native threads without a GIL (Go/Rust/Java), or native extensions that release the GIL.
4. **Choose primitives deliberately**: mutex for mutual exclusion, RW-lock for read-heavy, semaphore for resource caps, channel/queue for handoff, atomic for single-variable counters.
5. **Define lock ordering** globally when > 1 lock exists, and document it. Never acquire locks in loops with external calls inside.
6. **Keep critical sections minimal**; never perform I/O, logging with locks, or callback invocation while holding a lock.
7. **Bound concurrency**: worker pools with fixed size, bounded queues, and explicit backpressure (block, reject, or shed).
8. **Handle cancellation and timeouts** so tasks cannot hang forever.
9. **Make idempotency explicit** for retried tasks.
10. **Stress test**: high concurrency × many iterations; run race detectors.
11. **Measure**: throughput vs. concurrency curve; find the knee where contention dominates.

## 6. Tools and Technologies

| Language | Primitives / tools |
|---|---|
| Python | `threading`, `asyncio`, `concurrent.futures`, `multiprocessing`, `queue.Queue`, `anyio`, race risk: `threading.Lock` + GIL caveats |
| Go | goroutines, `chan`, `sync.Mutex/RWMutex`, `sync/atomic`, `errgroup`, `-race` |
| Java | `ExecutorService`, `CompletableFuture`, `ReentrantLock`, `StampedLock`, `java.util.concurrent`, `AtomicLong`, JFR |
| Rust | `std::thread`, `tokio`, `rayon`, `Arc<Mutex<T>>`, `crossbeam`, `loom` for model checking |
| C/C++ | `pthreads`, `std::thread`, `std::atomic`, `std::mutex`, TSan, helgrind |
| JS/TS | event loop, `Promise.all`, `worker_threads`, `p-limit` |
| Load/verification | `hey`, `k6`, `pytest-xdist`, `go test -race -count`, TSan, `loom` |

## 7. Practical Implementation

**Python: bounded thread pool for I/O**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx

def fetch(client: httpx.Client, url: str) -> int:
    r = client.get(url, timeout=5.0)
    return r.status_code

with httpx.Client() as client, ThreadPoolExecutor(max_workers=16) as pool:
    futures = {pool.submit(fetch, client, u): u for u in urls}
    for fut in as_completed(futures):
        try:
            status = fut.result()
        except Exception as exc:
            print(f"{futures[fut]} failed: {exc}")
```

**Python: fix check-then-act with a lock or an atomic DB update**

```python
import threading

# WRONG: read-modify-write race
counter = 0
def inc_bad():
    global counter
    counter += 1

# RIGHT: lock, or better, push atomicity into the datastore
_lock = threading.Lock()
def inc_ok():
    global counter
    with _lock:
        counter += 1

# BEST for services: single atomic SQL statement
# UPDATE counters SET value = value + 1 WHERE id = $1 RETURNING value;
```

**Python asyncio: never block the loop**

```python
import asyncio

async def handle(req):
    # BLOCKING — stalls all tasks
    # data = requests.get(url).text

    # CORRECT
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(url)
        return resp.json()

async def main():
    sem = asyncio.Semaphore(50)          # backpressure
    async def bounded(url):
        async with sem:
            return await handle(url)
    results = await asyncio.gather(*(bounded(u) for u in urls), return_exceptions=True)
```

**Go: worker pool with errgroup and cancellation**

```go
func processAll(ctx context.Context, items []Item, workers int) error {
    g, ctx := errgroup.WithContext(ctx)
    ch := make(chan Item)
    g.Go(func() error {
        defer close(ch)
        for _, it := range items {
            select {
            case ch <- it:
            case <-ctx.Done():
                return ctx.Err()
            }
        }
        return nil
    })
    var mu sync.Mutex
    for i := 0; i < workers; i++ {
        g.Go(func() error {
            for it := range ch {
                if err := process(ctx, it); err != nil {
                    return err
                }
                mu.Lock(); done++; mu.Unlock()
            }
            return nil
        })
    }
    return g.Wait()
}
```

**Go: race detection**

```bash
go test -race -count=10 ./...        # must be clean before merge
go run -race ./cmd/server
```

**Java: correct shared counter**

```java
private final AtomicLong processed = new AtomicLong();

public void onMessage(Msg m) {
    // ...
    processed.incrementAndGet();
}
```

**Rust: shared state with explicit locking scope**

```rust
use std::sync::{Arc, Mutex};

let state = Arc::new(Mutex::new(Vec::<Job>::new()));
let s2 = Arc::clone(&state);
std::thread::spawn(move || {
    let mut jobs = s2.lock().expect("mutex poisoned");
    jobs.push(Job::new());
}); // lock released here
```

## 8. Quality Standards

- Every shared mutable value has a documented synchronization strategy.
- No I/O or user callbacks while holding a lock.
- All locks acquired in a single global order; verified by code review or a lint rule.
- Concurrency bounded everywhere (pools, queues, semaphores); unbounded spawning is a defect.
- Cancellation and timeouts implemented for all long-running operations.
- Race detector clean in CI for Go/Rust/C++ builds.
- Async code contains no blocking calls on the event loop thread.

## 9. Verification and Testing

```bash
go test -race -count=50 ./pkg/...
RUSTFLAGS="-Z sanitizer=thread" cargo +nightly test    # nightly TSan for Rust
gcc -fsanitize=thread -g app.c -o app && ./app          # C/C++
pytest -q -n 8 tests/test_concurrency.py
python -X dev -m pytest -q                              # dev mode surfaces warnings
```

Stress pattern: 10× expected concurrency for 5 minutes; assert zero lost updates (final counter == expected), no deadlock (all workers complete), and stable latency. Use `py-spy dump --pid` or `jstack`/`SIGQUIT` to capture stack traces during a suspected deadlock.

## 10. Security Considerations

- Races can be security bugs: check-then-act on permissions (TOCTOU) allows privilege escalation. Enforce authorization inside the same transaction/lock as the action.
- DoS via unbounded concurrency: attacker-triggered task explosion exhausts memory/threads. Cap per-principal and global concurrency.
- Rate limiters and lockout counters must be atomic and shared (Redis `INCR` + TTL), not per-process.
- Avoid predictable randomness in concurrent security decisions; use CSPRNG.
- Thread dumps/stacks can reveal secrets in locals; treat as sensitive artifacts.
- Be careful with `fork()` after acquiring locks—child processes inherit locked mutexes and may deadlock; prefer `spawn` or re-init locks in workers.

## 11. Failure Handling

- **Intermittent wrong results:** look for check-then-act and non-atomic increments; add a race detector run and a stress test that asserts invariants.
- **Hang with no CPU usage:** suspected deadlock. Capture stack traces of all threads, check lock ordering, and look for lock acquired twice (non-reentrant mutex).
- **Throughput drops as concurrency rises:** contention or pool exhaustion. Profile lock wait times (`pprof -contentions`, JFR `jdk.JavaMonitorEnter`).
- **Event loop stalled:** a blocking call is in the path. Search for `requests.`, `time.sleep`, `subprocess.run` without `await`, and heavy JSON parsing in async handlers; move to a threadpool.
- **Memory growth under load:** tasks queueing unboundedly. Add a bounded queue and reject with 429/503.

## 12. Expected Deliverables

- Concurrency model diagram (tasks, shared state, synchronization).
- Primitive inventory with justification per lock/channel/atomic.
- Bounded pools/queues with explicit limits.
- Race-detector-clean test runs; stress test asserting invariants.
- Throughput-vs-concurrency measurement identifying the knee.
- Notes on cancellation, timeouts, and backpressure behavior.

## 13. References

- Python `asyncio` docs — https://docs.python.org/3/library/asyncio.html
- Go memory model — https://go.dev/ref/mem
- Go race detector — https://go.dev/doc/articles/race_detector
- Java `java.util.concurrent` — https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html
- Rust `tokio` — https://tokio.rs/
- Rustonomicon (concurrency) — https://doc.rust-lang.org/nomicon/
- Linux `pthreads(7)` man page — https://man7.org/linux/man-pages/man7/pthreads.7.html
- Herb Sutter, "Atomic Weapons" talks (C++ memory model).
