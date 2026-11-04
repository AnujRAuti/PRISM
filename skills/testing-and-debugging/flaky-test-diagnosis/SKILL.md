---
name: flaky-test-diagnosis
description: Track down nondeterministic test failures—reproduce with seeds and repetition, isolate shared state, eliminate timing and ordering assumptions, and enforce a quarantine SLA.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Flaky Test Diagnosis

## 1. Purpose

Turn "it fails sometimes" into a fixed test with a recorded root cause. Flakiness is almost never random: it is shared state, time, concurrency, network, or ordering. Retries hide the problem and train the team to ignore red builds. This skill provides a systematic diagnostic process, the common root-cause catalogue with fixes, and the measurement and governance that keeps flake rate below 1%.

**Scope:** your own test suites and CI. Do not "fix" flakiness by widening timeouts or adding retries without recording the underlying cause.

## 2. Activation Conditions

- A test fails intermittently in CI or locally.
- Flake rate above 1% or retries masking failures.
- Tests pass alone but fail in a suite or in parallel.
- Tests fail only on CI, or only on a specific OS/browser.
- Keywords: flaky test, nondeterministic, race condition, test isolation, ordering, retry, quarantine, seed, pytest-randomly, trace viewer, async timing, shared state.

## 3. When Not to Use

- Consistently failing tests (ordinary debugging; use the language debugger and logs).
- Performance regressions (use performance-and-load-testing).
- Environment outages (check infrastructure first).

## 4. Required Context

1. Failure rate and history (is it recent, or long-standing?).
2. Whether it fails locally, in CI, or both, and with which parallelism.
3. Test level: unit, integration, E2E.
4. Artifacts available: logs, traces, screenshots, seeds.
5. Recent changes to the test, the code, or the environment.

## 5. Operating Procedure

1. **Quantify it**: find the failure rate in CI history (`gh run list`, JUnit XML history). A test at 2% over 500 runs is a repeatable signal, not noise.
2. **Reproduce by repetition**: run the single test 50–200 times in a loop before doing anything else; note the failure rate.
3. **Reproduce with randomization**: randomize test order and run in parallel with different worker counts — most "flaky" tests are order- or parallelism-dependent.
4. **Classify the failure**: assertion mismatch, timeout, exception, or environment error. The class narrows the cause immediately.
5. **Check the four usual suspects**: shared mutable state, wall-clock/timezone, async timing/races, and external variability (network, DNS, third-party sandbox).
6. **Read the artifacts** (trace, DOM snapshot, server logs, query log) rather than guessing; in E2E the trace usually reveals the exact race.
7. **Fix the cause, not the symptom**: replace sleeps with condition waits, isolate data per test, inject a clock, seed randomness, or make the assertion deterministic.
8. **Verify the fix by repetition**: 200 consecutive passes in the same configuration that failed before.
9. **Record the root cause** in a short note attached to the test or the PR, so the pattern is recognizable next time.
10. **Enforce a quarantine SLA**: quarantine (skip with owner + expiry) if unfixable today, and require a fix or deletion within two weeks.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Repetition | `pytest --count`, `for i in $(seq 200)`, Playwright `--repeat-each` |
| Randomization | pytest-randomly, jest `--randomize`, vitest `sequence.shuffle` |
| Parallelism | pytest-xdist (`-n`), Playwright `--workers`, jest `--maxWorkers` |
| E2E artifacts | Playwright trace viewer, video, screenshots |
| Time control | freezegun, `vi.useFakeTimers`, `page.clock` |
| CI history | JUnit XML → dashboard, `gh api` run history, BuildPulse/Datadog CI Visibility |
| Network control | `respx`, `page.route`, toxiproxy |
| Detecting shared state | per-test unique IDs, DB snapshot diffing |

## 7. Practical Implementation

**Reproduce a flaky unit test with repetition and randomization:**

```bash
# 200 runs of one test
pytest tests/unit/test_refunds.py::test_refund_window -q --count=200

# random order + parallel, the usual trigger
pytest -p randomly -n 4 tests/unit -q --count=20

# isolate: does it fail alone?
pytest tests/unit/test_refunds.py::test_refund_window -q
```

```python
# pytest-repeat provides --count; add it to dev dependencies
# pip install pytest-repeat pytest-randomly
```

**Shared-state diagnosis: the classic culprit**

```python
# BAD: module-level cache shared across tests; order-dependent
_CACHE: dict[str, Price] = {}

def get_price(sku: str) -> Price:
    if sku not in _CACHE:
        _CACHE[sku] = _load_price(sku)
    return _CACHE[sku]

# Fix 1: inject the cache so tests can supply a fresh one
class PriceService:
    def __init__(self, repo: PriceRepo, cache: MutableMapping[str, Price] | None = None) -> None:
        self._repo, self._cache = repo, cache if cache is not None else {}

# Fix 2: autouse fixture clears global state between tests (for third-party globals)
@pytest.fixture(autouse=True)
def reset_globals(monkeypatch):
    monkeypatch.setattr("app.pricing._CACHE", {}, raising=True)
```

**Time-dependent test**

```python
# BAD: depends on the real clock and the machine timezone
def test_trial_expired():
    user = make_user(trial_started=datetime.now() - timedelta(days=15))
    assert user.trial_expired()

# GOOD: inject a clock; the test owns time
def test_trial_expired_at_fourteen_days():
    clock = FixedClock(datetime(2026, 11, 4, 12, tzinfo=timezone.utc))
    user = make_user(trial_started=clock.now() - timedelta(days=14), clock=clock)
    assert user.trial_expired()
```

```python
# When the code cannot be changed, freeze time and pin the timezone
@pytest.fixture(autouse=True)
def frozen_time(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    with time_machine.travel("2026-11-04T12:00:00Z", tick=False):
        yield
```

**Async race (test asserts before the write commits)**

```python
# BAD: fire-and-forget with a sleep
await service.enqueue_export(order_id)
await asyncio.sleep(0.5)
assert await repo.export_exists(order_id)

# GOOD: await the completion signal the production code provides
await service.enqueue_export(order_id)
await queue.join()                       # or await eventual_assert(...) with a bound
assert await repo.export_exists(order_id)
```

```python
async def eventually(predicate, *, timeout: float = 5.0, interval: float = 0.05):
    """Bounded polling for genuinely asynchronous side effects; fails with a clear message."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")
```

**Parallelism collision (two workers, same unique key)**

```python
# BAD: fixed identifiers collide across workers
def test_create_customer(client):
    r = client.post("/customers", json={"email": "test@example.com"})
    assert r.status_code == 201

# GOOD: per-test unique identifiers
import uuid

@pytest.fixture
def unique_email() -> str:
    return f"t-{uuid.uuid4().hex[:12]}@example.test"
```

**E2E: replace arbitrary waits with condition-based waits**

```ts
// BAD: racy in CI, always passes locally (fast machine)
await page.getByRole("button", {name: "Save"}).click();
await page.waitForTimeout(1000);
expect(await page.getByTestId("status").textContent()).toBe("Saved");

// GOOD: web-first assertion with the real condition
await page.getByRole("button", {name: "Save"}).click();
await expect(page.getByRole("status")).toHaveText("Saved");
```

```ts
// Repeat each test 20 times to reproduce
// npx playwright test e2e/checkout.spec.ts --repeat-each=20 --workers=4
```

**Network variability**

```python
# Integration tests must never depend on a real third party
import respx

@respx.mock
def test_inventory_sync(monkeypatch):
    respx.get("https://api.warehouse.test/v1/stock").mock(
        return_value=respx.MockResponse(200, json={"available": 5})
    )
    ...
```

```bash
# For local services, inject latency and failures deliberately to expose races
toxiproxy-cli toxic add redis -t latency -a latency=200
```

**Flake tracking query (CI history):**

```bash
gh run list --workflow=test.yml --limit 100 --json conclusion,headSha,createdAt \
  | jq '[.[] | {sha: .headSha, ok: (.conclusion == "success")}] | group_by(.sha)' 
```

```python
# Aggregate JUnit XML from many runs into a per-test failure rate
import glob
from collections import Counter
import xml.etree.ElementTree as ET

runs, fails = Counter(), Counter()
for path in glob.glob("reports/**/*.xml", recursive=True):
    for case in ET.parse(path).iter("testcase"):
        key = f"{case.get('classname')}::{case.get('name')}"
        runs[key] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            fails[key] += 1

for key, n in fails.most_common(20):
    print(f"{fails[key]/runs[key]:6.1%}  {fails[key]:3d}/{runs[key]:3d}  {key}")
```

**Quarantine with expiry (from testing-strategy, enforced):**

```python
FLAKY = {"tests/e2e/test_export.py::test_large_export": ("order-export", date(2026, 11, 20))}
```

Any quarantine past its expiry fails collection, forcing a fix or a deletion.

## 8. Quality Standards

- No retries in the suite without a recorded reason and an owner (retries are for surfacing flake, not for passing).
- Every fixed test has a root-cause note: cause, reproduction command, fix, verification count.
- Tests never depend on wall-clock time, execution order, shared mutable state, or real third parties.
- Unique data per test; no fixed identifiers for unique constraints.
- E2E tests use condition-based waits exclusively.
- Flake rate is measured weekly from CI history, target < 1%.
- Quarantined tests have an owner and a hard expiry.

## 9. Verification and Testing

- 200 consecutive passes with the original triggering configuration (parallelism, random order, shards).
- Run with `-n 8` and random order for 20 iterations.
- Run on a deliberately slow machine or under CPU throttling to expose timing assumptions.
- Confirm the fix fails when reverted (the test still catches the bug it was written for).
- Verify the flake did not simply move to a different test that shares the same state.

## 10. Security Considerations

- Flaky security tests are dangerous: an intermittently failing authz test trains people to re-run and merge. Treat any authz/security test flake as a P1.
- Do not loosen a failing security assertion (e.g. accepting 200 and 403) to make it deterministic — fix the nondeterminism.
- Reproducing with real external services can send traffic to third parties; use fakes and sandboxes.
- Shared test accounts across parallel workers can trigger rate limits or lockouts that look like flakiness and can mask an attack.
- CI logs and traces from flaky runs may contain tokens; scrub before sharing in tickets.

## 11. Failure Handling

- **Cannot reproduce locally:** CI-only parallelism or resource limits. Get a trace artifact, run with the same worker count, and add `--repeat-each`.
- **Failure rate too low to sample:** run 500 iterations in a nightly job to catch one occurrence with artifacts enabled.
- **Fix appears to work but flake returns:** another instance of the same pattern exists in the suite (same global, same helper). Search for the pattern, not just the test.
- **Third-party sandbox is the flake:** replace with a fake at the HTTP boundary; keep one contract test against the sandbox that is allowed to be retried.
- **Quarantine list grows:** stop accepting new quarantines without deleting an equivalent test; flake debt compounds.

## 12. Expected Deliverables

1. Flake inventory with failure rates.
2. Reproduction commands and configuration.
3. Root-cause classification per test.
4. Fixes (isolation, inert time, condition waits, fakes).
5. Verification evidence (200 consecutive passes).
6. Quarantine list with owners and expiry dates.
7. Weekly flake-rate report.

## 13. References

- Google Testing Blog, "Flaky Tests at Google and How We Mitigate Them" — https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
- pytest-randomly — https://github.com/pytest-dev/pytest-randomly
- pytest-repeat — https://github.com/pytest-dev/pytest-repeat
- pytest-xdist — https://pytest-xdist.readthedocs.io/
- Playwright retries and trace viewer — https://playwright.dev/docs/test-retries
- Playwright `--repeat-each` — https://playwright.dev/docs/test-cli#all-options
- time-machine — https://time-machine.readthedocs.io/
- Toxiproxy — https://github.com/Shopify/toxiproxy
- "Software Engineering at Google", Ch. 11 (flaky tests) — https://abseil.io/resources/swe-book/html/ch11.html
