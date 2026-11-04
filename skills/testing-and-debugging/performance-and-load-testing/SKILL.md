---
name: performance-and-load-testing
description: Measure and validate performance under realistic load—workload modeling, k6/Gatling scenarios, percentile analysis, bottleneck attribution, and CI-regression guards.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: medium
---

# Performance and Load Testing

## 1. Purpose

Answer "will it hold?" with numbers instead of opinions. Load testing fails when the workload is unrealistic (only one endpoint, uniform traffic, no think time), when results are reported as averages, or when the environment differs so much from production that the conclusion is worthless. This skill covers workload modeling, scenario design, metric interpretation (p50/p95/p99, error budget, saturation), bottleneck attribution, and keeping performance from regressing.

**Scope:** load testing targets systems you own or have explicit written authorization to test. Never load-test third-party services, production without approval, or shared infrastructure during business hours without coordination—a load test is indistinguishable from a denial-of-service attack.

## 2. Activation Conditions

- Launch, campaign, or traffic spike expected.
- Capacity planning or cost/instance sizing.
- Latency SLOs at risk; p99 growing release over release.
- After a major architecture change (new cache, new database).
- Keywords: load testing, stress testing, soak test, spike test, k6, Gatling, Locust, JMeter, throughput, latency percentiles, saturation, bottleneck, capacity planning, SLO.

## 3. When Not to Use

- Single-request profiling on a dev laptop (use a profiler).
- Frontend perceived performance (use frontend-performance).
- Database query tuning on one statement (use sql-query-optimization).

## 4. Required Context

1. SLOs: target latency percentiles, error rate, and throughput.
2. Traffic model: endpoint mix, request sizes, think time, peak/off-peak ratios.
3. Environment: staging parity with production (instance sizes, DB, network).
4. Isolation: dedicated environment or approved window with stakeholders notified.
5. Observability: metrics, traces, and DB stats available during the test.

## 5. Operating Procedure

1. **Write the SLOs and the question first**: "sustain 300 rps at p95 < 250 ms and error rate < 0.5% for 30 min."
2. **Model traffic from real data**: top endpoints by request share, payload sizes, and user think time. Use production access logs (or RPS by route) rather than guessing.
3. **Build scenarios with ramping stages**: warm-up, steady state, peak, and recovery. Include a soak stage for leak detection.
4. **Parameterize and randomize data** so caches and unique constraints behave realistically.
5. **Run against production-like infrastructure**; record versions, config, dataset size, and the load generator's own limits.
6. **Monitor everything during the run**: app latency percentiles, error classes, CPU/memory/GC, DB connections and slow queries, cache hit rate, queue depth.
7. **Find saturation first, then tune.** Identify which resource hits 100% (CPU, DB connections, network, IOPS) before changing code.
8. **Report percentiles and error rates, never averages.** Include the throughput achieved and the failure modes under overload.
9. **Distinguish closed vs. open models**: closed-loop tests underestimate queueing; use constant-arrival-rate executors for realistic arrival patterns.
10. **Record a baseline and add a regression guard**: a smaller smoke load in CI (or nightly) that fails on >20% p95 regression.
11. **Teardown**: stop load, verify recovery to baseline, and clean generated data.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Load generators | k6, Gatling, Locust, JMeter, vegeta |
| Distributed load | k6 operator, Gatling Enterprise, multiple generators |
| Profiling under load | py-spy, async-profiler, pprof, Chrome tracing |
| Metrics | Prometheus + Grafana, OpenTelemetry |
| DB visibility | `pg_stat_statements`, `pg_stat_activity`, `pgwatch` |
| Resource analysis | `pidstat`, `iostat`, `node_exporter` |
| CI regression | k6 thresholds + `--summary-export`, GitHub Actions nightly |

## 7. Practical Implementation

**k6 scenario with realistic stages and thresholds:**

```js
// load/checkout.js
import http from "k6/http";
import {check, sleep} from "k6";
import {Trend, Rate} from "k6/metrics";

const checkoutLatency = new Trend("checkout_latency_ms", true);
const checkoutErrors = new Rate("checkout_error_rate");

export const options = {
  scenarios: {
    browse: {
      executor: "ramping-arrival-rate",       // open model: fixed arrival rate
      startRate: 20,
      timeUnit: "1s",
      stages: [
        {target: 100, duration: "2m"},        // warm-up
        {target: 300, duration: "5m"},        // steady state
        {target: 450, duration: "3m"},        // peak
        {target: 0,   duration: "2m"},        // ramp down
      ],
      preAllocatedVUs: 100,
      maxVUs: 800,
    },
    soak: {
      executor: "constant-arrival-rate",
      rate: 150, timeUnit: "1s", duration: "30m",
      preAllocatedVUs: 80, maxVUs: 200,
      startTime: "13m",
    },
  },
  thresholds: {
    "http_req_duration{scenario:browse}": ["p(95)<250", "p(99)<600"],
    "http_req_failed": ["rate<0.005"],
    checkout_latency: ["p(95)<800"],
    checkout_error_rate: ["rate<0.01"],
  },
};

const BASE = __ENV.BASE_URL;

export default function () {
  const roll = Math.random();

  if (roll < 0.60) {
    const res = http.get(`${BASE}/v1/products?limit=20&cursor=${__ENV.CURSOR ?? ""}`,
                         {tags: {route: "products_list"}});
    check(res, {"products 200": (r) => r.status === 200});
  } else if (roll < 0.90) {
    const id = Math.floor(Math.random() * 50_000) + 1;   // spread across the catalog
    const res = http.get(`${BASE}/v1/products/${id}`, {tags: {route: "product_detail"}});
    check(res, {"product 200 or 404": (r) => [200, 404].includes(r.status)});
  } else {
    const payload = JSON.stringify({product_id: Math.floor(Math.random() * 50_000) + 1,
                                    quantity: 1});
    const res = http.post(`${BASE}/v1/cart/items`, payload, {
      headers: {"Content-Type": "application/json", Authorization: `Bearer ${__ENV.API_TOKEN}`},
      tags: {route: "cart_add"},
    });
    checkoutLatency.add(res.timings.duration);
    checkoutErrors.add(res.status >= 500);
    check(res, {"cart add accepted": (r) => r.status === 201});
  }

  sleep(Math.random() * 3 + 1);            // think time: 1-4 s, jittered
}
```

```bash
k6 run load/checkout.js \
  -e BASE_URL=https://staging.example.com \
  -e API_TOKEN="$LOAD_TEST_TOKEN" \
  --summary-export=load/results-$(date +%F-%H%M).json
```

**Reading results correctly:**

```text
http_req_duration........: avg=118ms min=4ms med=96ms max=2.4s
  p(90)=180ms p(95)=240ms p(99)=590ms
http_req_failed..........: 0.31%  ✓ 234 out of 75k
http_reqs................: 75,412  418.9/s
vus......................: 120 min=0 max=640
iteration_duration.......: avg=2.3s
```

Reported as: "At 419 rps sustained, p95 = 240 ms and p99 = 590 ms met the SLO; error rate 0.31% was below 0.5%. Failures were 502s from the database connection pool at peak, which is the first saturation point."

**Saturation identification (measure before tuning):**

```bash
# During the run, on the app host
pidstat -u -r -p "$(pgrep -f 'uvicorn app.main:app')" 5
iostat -xz 5 3
ss -s | head

# Database: who is waiting?
psql -c "SELECT state, wait_event_type, wait_event, count(*) FROM pg_stat_activity GROUP BY 1,2,3 ORDER BY 4 DESC;"
psql -c "SELECT count(*), max(now() - query_start) FROM pg_stat_activity WHERE state = 'active';"
```

```python
# App-side: pool wait time is often the real bottleneck, not CPU
POOL_WAIT = Histogram("db_pool_wait_seconds", "Time waiting for a DB connection",
                      buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5))
```

**Spike test (recovery matters more than the spike):**

```javascript
export const options = {
  scenarios: {
    spike: {
      executor: "ramping-arrival-rate",
      startRate: 50, timeUnit: "1s",
      stages: [
        {target: 50,  duration: "1m"},
        {target: 900, duration: "10s"},   // 18x spike
        {target: 900, duration: "1m"},
        {target: 50,  duration: "30s"},
        {target: 50,  duration: "3m"},    // observe recovery
      ],
      preAllocatedVUs: 200, maxVUs: 2000,
    },
  },
};
```

Observe: does the system recover without intervention, or does the pool stay exhausted, the queue stay backed up, or the circuit breaker stay open?

**Soak test for leaks (30–120 min at steady state):**

```javascript
export const options = {
  scenarios: {soak: {
    executor: "constant-arrival-rate", rate: 150, timeUnit: "1s", duration: "60m",
    preAllocatedVUs: 100, maxVUs: 300,
  }},
  thresholds: {"http_req_failed": ["rate<0.005"], "http_req_duration": ["p(99)<800"]},
};
```

Watch RSS memory, open file descriptors, connection counts, and GC pause time for monotonic growth.

**Nightly CI regression guard (small, fast, deterministic):**

```yaml
- name: Load smoke
  run: |
    k6 run load/smoke.js \
      -e BASE_URL="$STAGING_URL" \
      --quiet --summary-export=smoke.json
  # smoke.js: 30 s at 50 rps with thresholds p95<250ms, error rate <1%
- name: Compare baseline
  run: python scripts/compare_p95.py smoke.json baseline.json --max-regression 0.20
```

```python
# scripts/compare_p95.py
import json, sys

def main(current_path, baseline_path, max_regression):
    cur = json.load(open(current_path))["metrics"]["http_req_duration"]["values"]["p(95)"]
    base = json.load(open(baseline_path))["metrics"]["http_req_duration"]["values"]["p(95)"]
    delta = (cur - base) / base
    print(f"p95 current={cur:.0f}ms baseline={base:.0f}ms delta={delta:+.1%}")
    sys.exit(1 if delta > max_regression else 0)
```

**Load-test safety checklist:**

```text
[ ] Written approval and a change ticket for the target environment
[ ] Stakeholders notified; support aware of expected error spikes
[ ] Rate limits and WAF rules verified so the test is not silently blocked
[ ] Production: only with a cap, a kill switch, and off-peak window
[ ] Test data created in a separate tenant; generated rows tagged for cleanup
[ ] Kill switch verified before the run starts (k6 Ctrl-C / abort script)
```

## 8. Quality Standards

- Every test states its question and SLO before running.
- Workload mix and think time derive from measured traffic, not guesses.
- Open-model executors are used for arrival-rate questions; closed-loop only when modeling a fixed user pool.
- Results are reported with p50/p95/p99, throughput, and error classes.
- Environment parity is documented (instance types, dataset size, versions).
- The first saturated resource is identified and named as the bottleneck.
- Tests are reproducible (fixed seed, committed script, recorded config).
- A regression guard exists that fails on material p95 degradation.

## 9. Verification and Testing

- Run the same scenario twice: results within ±10% (otherwise the environment or data is unstable).
- Validate the load generator itself: confirm the generator is not CPU-bound and that `dropped_iterations` is zero.
- Confirm monitoring captured the run window (dashboards, traces, DB stats).
- Reproduce a known bottleneck deliberately (e.g. shrunken pool) to prove the harness detects it.
- After teardown, verify the system returns to baseline latency within the documented window.

## 10. Security Considerations

- Written authorization is mandatory for load testing; unauthorized load against third-party or production systems is abusive traffic.
- Never use production customer credentials or real personal data in load scripts.
- Load tests can mask a real attack or trigger incident response—announce them and use a recognizable header (`X-Load-Test: k6`).
- Rate-limit/WAF bypasses used for testing must be temporary, scoped, and removed immediately after.
- Test tokens must be scoped to test tenants and revoked after the run.
- Generated test data must be tagged and cleaned; unlabeled synthetic rows in production are a data-quality and privacy problem.
- Do not test against systems where failure could affect safety, payments, or regulated workloads without explicit sign-off.

## 11. Failure Handling

- **Generator cannot reach the target rate:** too few VUs or generator CPU-bound. Scale generators or increase `maxVUs`/`preAllocatedVUs`.
- **Latency cliff at a specific rate:** saturation. Identify the resource (`pg_stat_activity`, pool wait, CPU) and raise capacity or reduce work per request.
- **Errors only under load:** connection pool exhaustion, file descriptor limits, or lock contention — not "slow code".
- **Results unreproducible:** shared environment, data drift, or autoscaling. Pin capacity and reset the dataset.
- **Passes in staging, fails in production:** parity gap in instance size, dataset size, or cache warmth. Document the gap and test the difference.
- **Soak shows memory growth:** confirm with a heap profile; often unbounded caches or connection leaks.

## 12. Expected Deliverables

1. SLOs and the question the test answers.
2. Traffic model from real data.
3. Committed load scripts and scenario configuration.
4. Run log: environment, versions, dataset size, duration.
5. Results table with percentiles, throughput, and error breakdown.
6. Bottleneck analysis with evidence.
7. Capacity recommendation and next saturation point.
8. CI regression guard and baseline.

## 13. References

- Grafana k6 documentation — https://grafana.com/docs/k6/latest/
- k6 executors (arrival-rate models) — https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/
- k6 thresholds — https://grafana.com/docs/k6/latest/using-k6/thresholds/
- Gatling documentation — https://docs.gatling.io/
- Locust documentation — https://docs.locust.io/
- Google SRE Book, "Handling Overload" — https://sre.google/sre-book/handling-overload/
- Brendan Gregg, "The USE Method" — https://www.brendangregg.com/usemethod.html
- PostgreSQL `pg_stat_activity` — https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW
