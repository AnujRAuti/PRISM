---
name: observability-and-monitoring
description: Instrument systems with metrics, logs, and traces—define SLIs/SLOs, build actionable alerts, and design dashboards that shorten detection and diagnosis.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# Observability and Monitoring

## 1. Purpose

Make the system's internal state observable from the outside, and alert on symptoms users feel—not on every metric that moves. This skill covers the three pillars (metrics, logs, traces), SLI/SLO definition with error budgets, alert design that avoids fatigue, dashboard structure for on-call, and cost control for telemetry. It solves both failure modes: no visibility during incidents, and so much noise that real alerts are ignored.

**Scope:** telemetry from systems you operate. Logs and traces contain user data—apply retention and redaction policies.

## 2. Activation Conditions

- Standing up monitoring for a new service.
- Alert fatigue, missed incidents, or slow detection (MTTD).
- An SLO discussion or reliability target is required.
- Grafana/Prometheus/Loki/Tempo stack design or migration.
- Keywords: observability, monitoring, SLO, SLI, alert, Prometheus, Grafana, OpenTelemetry, tracing, logging, dashboard, on-call, error budget.

## 3. When Not to Use

- One-shot batch jobs with no service level.
- Deep single-process profiling (use performance-optimization).
- Security event monitoring (use incident-response/SIEM), though telemetry overlaps.

## 4. Required Context

1. Services and their user-facing endpoints; criticality tiers.
2. Existing tooling and ingestion budget (storage cost per GB/day).
3. Current alerts: count, firing frequency, false-positive rate.
4. Data classification and retention requirements for logs/traces.
5. On-call structure and escalation policy.

## 5. Operating Procedure

1. **Define SLIs per user journey**: availability (successful requests / total), latency (p95/p99 under threshold), correctness (business invariant), freshness (data age).
2. **Set SLOs with a window** (28 days rolling): e.g. 99.9% availability, p95 < 300 ms. Derive the error budget (0.1% = ~40 min/month).
3. **Instrument the application** with OpenTelemetry: RED metrics (Rate, Errors, Duration) for services and USE (Utilization, Saturation, Errors) for resources.
4. **Standardize labels**: `service`, `env`, `version`, `route`, `status_class`. Never use unbounded values (user IDs, raw URLs) as labels—cardinality explosion kills Prometheus.
5. **Propagate trace context** across services (W3C `traceparent`); sample at the head for volume and at the tail for error-focused sampling.
6. **Structure logs as JSON** with `timestamp`, `level`, `service`, `trace_id`, `span_id`, `message`, and stable field names; no PII.
7. **Alert on symptoms with SLO burn rates**, not on causes: page when the error budget burns fast (multi-window burn rate), ticket on slow burn.
8. **Write runbooks per alert** with what it means, first checks, and escalation.
9. **Design dashboards by audience**: on-call overview (SLO + top errors + saturation), service detail, dependency health, business metrics.
10. **Control cost**: metric retention tiers, log sampling, trace sampling, and drop debug logs in production.
11. **Review monthly**: alert precision, pages per shift, SLO compliance, and dashboard usefulness.

## 6. Tools and Technologies

| Pillar | Tools |
|---|---|
| Metrics | Prometheus, VictoriaMetrics, Mimir, CloudWatch, Grafana Cloud |
| Dashboards | Grafana, Perses |
| Logs | Loki, Elasticsearch/OpenSearch, CloudWatch Logs |
| Traces | Tempo, Jaeger, OpenTelemetry Collector |
| Instrumentation | OpenTelemetry SDKs, Prometheus client libraries |
| Alerting | Alertmanager, Grafana Alerting, PagerDuty/Opsgenie |
| SLO tooling | Sloth, Pyrra, Grafana SLO |
| Synthetic | Blackbox exporter, Playwright synthetic checks |

## 7. Practical Implementation

**Prometheus scrape config:**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files: [/etc/prometheus/rules/*.yml]

scrape_configs:
  - job_name: orders-api
    metrics_path: /metrics
    static_configs:
      - targets: ["orders-api-1:8080", "orders-api-2:8080"]
        labels: {service: orders-api, env: prod}
```

**Application metrics (Python, prometheus_client):**

```python
from prometheus_client import Counter, Histogram, start_http_server
import time

REQUESTS = Counter(
    "http_requests_total", "HTTP requests",
    ["service", "route", "method", "status_class"],
)
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP latency",
    ["service", "route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

def observe(route: str, method: str, status: int, started: float) -> None:
    LATENCY.labels("orders-api", route).observe(time.perf_counter() - started)
    REQUESTS.labels("orders-api", route, method, f"{status // 100}xx").inc()

if __name__ == "__main__":
    start_http_server(9090)   # bind to a private interface in production
```

**SLO burn-rate alerts (Prometheus rules):**

```yaml
groups:
  - name: slo-orders
    rules:
      - record: slo:orders_error_ratio:5m
        expr: |
          sum(rate(http_requests_total{service="orders-api",status_class="5xx"}[5m]))
          /
          sum(rate(http_requests_total{service="orders-api"}[5m]))
      - alert: OrdersErrorBudgetFastBurn
        expr: |
          (slo:orders_error_ratio:5m > (14.4 * 0.001))
          and
          (slo:orders_error_ratio:1h > (14.4 * 0.001))
        for: 2m
        labels: {severity: page, service: orders-api}
        annotations:
          summary: "orders-api burning error budget 14.4x (SLO 99.9%)"
          runbook_url: "https://runbooks.example.com/orders-api/error-budget"
      - alert: OrdersErrorBudgetSlowBurn
        expr: slo:orders_error_ratio:6h > (6 * 0.001)
        for: 30m
        labels: {severity: ticket, service: orders-api}
        annotations:
          summary: "orders-api slow burn; investigate within the business day"
```

**Latency SLO recording rule:**

```yaml
- record: slo:orders_latency_p95:5m
  expr: |
    histogram_quantile(0.95,
      sum by (le) (rate(http_request_duration_seconds_bucket{service="orders-api"}[5m])))
```

**Structured logging (Node/TypeScript):**

```ts
import pino from 'pino';

export const log = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  base: {service: 'orders-api', env: process.env.NODE_ENV},
  redact: {
    paths: ['req.headers.authorization', '*.password', '*.token', 'req.headers.cookie'],
    censor: '[redacted]',
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});
```

**OpenTelemetry tracing setup (Python):**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

provider = TracerProvider(resource=Resource.create({"service.name": "orders-api"}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://otel-collector:4317", insecure=True)))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("orders")
with tracer.start_as_current_span("charge_card") as span:
    span.set_attribute("payment.provider", "stripe")
    span.set_attribute("order.id", order_id)   # bounded, business-relevant, not PII
```

**Cardinality guard (Prometheus):**

```promql
# Top label cardinality offenders
topk(10, count by (__name__, route) ({__name__=~".+"}))
# Never label by user_id/email/URL with query strings.
```

**On-call dashboard layout:**

```text
Row 1: SLO status (availability, latency p95/p99), error budget remaining, active incidents
Row 2: Traffic (RPS by route), errors (5xx ratio by route), saturation (CPU/mem/conn pool)
Row 3: Dependencies (DB latency, cache hit ratio, external API error rate)
Row 4: Deploy markers and version, recent alert history
```

## 8. Quality Standards

- Every service has at least one SLI/SLO with an owner and a window.
- Alerts reference a runbook and have a severity (page vs. ticket).
- Page volume is low enough to stay meaningful (< ~2 per on-call shift).
- Label cardinality is bounded and monitored.
- Logs are structured JSON, redacted, and sampled consistently.
- Traces propagate across all hops; sampling policy is documented.
- Dashboards load in < 5 s and answer "is the service healthy?" at a glance.
- Retention and cost are explicit per signal type.

## 9. Verification and Testing

```bash
promtool check rules /etc/prometheus/rules/*.yml
promtool query instant http://localhost:9090 'slo:orders_error_ratio:5m'
curl -s http://127.0.0.1:9090/-/healthy
curl -s http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets[] | {job, health}'
amtool check-config /etc/alertmanager/alertmanager.yml
# Alert simulation
amtool alert add service=orders-api severity=page alertname=TestPage --annotation=summary="test"
```

Expected evidence: recording rules evaluate, targets are `up`, a synthetic error rate increase fires the burn-rate alert within minutes, and the alert resolves automatically.

## 10. Security Considerations

- Metrics endpoints and Grafana must not be public; bind to private interfaces and require auth.
- Logs frequently contain tokens and PII: redact at the source and enforce retention.
- Telemetry pipelines cross trust boundaries (collector → backend): use TLS and authentication.
- Cardinality abuse is a DoS vector: never accept label values from untrusted input.
- Access control: production dashboards and traces reveal architecture; restrict by role.
- Audit who can silence alerts; silences hide outages.
- Keep exporters patched; `node_exporter` and friends have had auth bypass issues.

## 11. Failure Handling

- **Prometheus out of memory:** high cardinality—find the offending metric (`count by (__name__)({__name__=~".+"})`), drop or relabel it, and enforce limits.
- **Alerts fire constantly:** raise thresholds, use `for:` durations, and convert cause-based alerts to symptom-based SLO alerts.
- **Missing data during incidents:** check scrape targets, collector queue, and remote-write lag; add a "metrics stale" alert.
- **Log volume explodes:** sampling/dropping in the collector, and a rate-limited alert on log ingestion.
- **Trace sampling misses errors:** switch to tail sampling retaining error and slow traces.
- **Dashboard slow:** reduce time range, increase step, precompute recording rules.

## 12. Expected Deliverables

1. SLI/SLO specification with windows and owners.
2. Instrumentation code and metric naming conventions.
3. Alert rules with runbook links and severities.
4. Dashboard JSON/provisioning files.
5. Logging schema and redaction config.
6. Trace propagation and sampling configuration.
7. Cost/retention policy and monthly review process.

## 13. References

- Google SRE Book — Monitoring Distributed Systems — https://sre.google/sre-book/monitoring-distributed-systems/
- SRE Workbook — Alerting on SLOs — https://sre.google/workbook/alerting-on-slos/
- OpenTelemetry documentation — https://opentelemetry.io/docs/
- Prometheus best practices — https://prometheus.io/docs/practices/naming/
- Alertmanager — https://prometheus.io/docs/alerting/latest/alertmanager/
- Grafana documentation — https://grafana.com/docs/
- Sloth (SLO generator) — https://sloth.dev/
