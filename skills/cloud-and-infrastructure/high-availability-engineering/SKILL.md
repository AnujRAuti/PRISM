---
name: high-availability-engineering
description: Engineer availability with explicit SLOs—redundancy without single points of failure, failover that is tested, graceful degradation, and error-budget-driven decisions.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# High Availability Engineering

## 1. Purpose

Meet a stated availability target with architecture that actually fails over, and know when to stop spending on it. Availability work goes wrong when targets are aspirational rather than defined, when "multi-AZ" hides a single shared dependency, and when failover has never been executed. This skill covers SLO definition, redundancy design, failover mechanics, graceful degradation, and the error-budget policy that turns availability into an engineering decision.

**Scope:** systems you operate. Failover drills and traffic shifts affect real users: schedule them, notify stakeholders, verify rollback, and never test a regional failover on production without an approved change window.

## 2. Activation Conditions

- Defining or renegotiating an availability target.
- Repeated outages traced to a single dependency or AZ.
- Preparing for regional resilience or a major traffic event.
- Failover runbooks exist but have never been executed.
- Keywords: high availability, SLO, SLA, error budget, failover, multi-AZ, multi-region, redundancy, health check, circuit breaker, graceful degradation, active-active, active-passive, RTO, RPO, chaos.

## 3. When Not to Use

- Backup and disaster recovery for data loss (use disaster-recovery-and-backup; HA does not replace backups).
- Capacity planning for a launch (use performance-and-load-testing).
- Fault injection strategy as a whole program (this skill covers the mechanics you need).

## 4. Required Context

1. Business requirement: downtime cost, contractual SLAs, and hours-of-operation sensitivity.
2. Current architecture: dependencies, state, and failure domains.
3. Measured availability and incident history (where time was lost).
4. Budget available for redundancy.
5. Deployment and traffic management capabilities (DNS, LB, service mesh).

## 5. Operating Procedure

1. **Define SLIs and an SLO** in user terms: availability = successful requests / valid requests, measured at the edge over a rolling 28 days (e.g. 99.9% = 40 min/month).
2. **Derive the error budget** (0.1% = ~40 min) and write the policy: at >50% budget consumed, freeze risky changes; at 100%, prioritize reliability work over features.
3. **Map every dependency and its failure domain**: AZ, region, database, DNS, certificate, third-party. Any single instance of these with no fallback is an SPOF.
4. **Eliminate SPOFs that matter**, in order of budget consumed in past incidents — not by architecture aesthetics.
5. **Design redundancy at each layer**: multiple AZs for compute and data, replicated load balancers, redundant NAT/egress per AZ, replicated DNS zones, and independent certificate renewal paths.
6. **Make state highly available deliberately**: multi-AZ managed databases with automatic failover, replicas for read scaling, and a clear statement of what happens to in-flight writes during failover.
7. **Design graceful degradation**: circuit breakers, timeouts, bounded retries with jitter, cached/stale responses, feature shedding (disable recommendations, not checkout), and queues to absorb bursts.
8. **Make health checks correct**: liveness vs. readiness, deep vs. shallow, and health checks that do not cascade failures (a DB blip must not remove every instance from the pool at once).
9. **Test failover on a schedule**: kill an instance, fail over the database, drop an AZ, and (for tier 1) shift a region — measuring user-visible impact each time.
10. **Alert on SLO burn rate**, not on every individual symptom: multi-window burn-rate alerts catch both fast outages and slow degradation.
11. **Review every incident against the design**: each outage that consumed more than 10% of the budget should produce a change to the architecture or the runbook.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Load balancing | ALB/NLB, GCP load balancer, Envoy, NGINX, service mesh (Istio/Linkerd) |
| Data HA | Multi-AZ RDS/Aurora, Patroni, Cloud SQL HA, DynamoDB global tables |
| Multi-region | Route 53 health checks + failover/weighted routing, Global Accelerator, CloudFront |
| Resilience patterns | Circuit breakers (resilience4j, `pybreaker`), retries with jitter, bulkheads |
| Chaos testing | AWS FIS, Chaos Mesh, Gremlin, manual game days |
| SLO tooling | Sloth, Pyrra, OpenSLO, burn-rate alert rules |
| Verification | synthetic monitors (`curl`/Playwright), RUM, dependency health probes |

## 7. Practical Implementation

**SLO definition and burn-rate alerting (Prometheus):**

```yaml
# SLI: proportion of good requests at the edge over 28 days
# SLO: 99.9% availability, 99% of requests faster than 400 ms
groups:
  - name: orders-slo
    interval: 30s
    rules:
      - record: slo:orders_availability:ratio_28d
        expr: |
          sum(rate(http_requests_total{job="edge",route="/v1/orders*",code!~"5.."}[28d]))
          /
          sum(rate(http_requests_total{job="edge",route="/v1/orders*"}[28d]))

      # Fast burn: 14.4x over 1h consumes 2% of the monthly budget
      - alert: OrdersAvailabilityFastBurn
        expr: |
          (1 - (sum(rate(http_requests_total{job="edge",code!~"5.."}[1h]))
                / sum(rate(http_requests_total{job="edge"}[1h])))) > (14.4 * 0.001)
        for: 2m
        labels: {severity: critical, slo: orders}
        annotations:
          summary: "orders availability burning 14.4x budget"
          runbook: "https://runbooks.example.com/orders-availability"

      # Slow burn: 6x over 6h catches sustained degradation
      - alert: OrdersAvailabilitySlowBurn
        expr: |
          (1 - (sum(rate(http_requests_total{job="edge",code!~"5.."}[6h]))
                / sum(rate(http_requests_total{job="edge"}[6h])))) > (6 * 0.001)
        for: 30m
        labels: {severity: warning, slo: orders}
```

**Multi-AZ application with independent egress and health-check discipline:**

```hcl
resource "aws_lb_target_group" "orders" {
  name                 = "orders-api"
  port                 = 8080
  protocol             = "HTTP"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30            # let in-flight requests finish

  health_check {
    path                = "/healthz/ready"     # readiness, not liveness
    interval            = 10
    timeout             = 3
    healthy_threshold   = 2
    unhealthy_threshold = 3                    # tolerate a transient blip
    matcher             = "200"
  }

  stickiness { enabled = false }               # stateless app; no pinned sessions
}

resource "aws_autoscaling_group" "orders" {
  min_size            = 6
  max_size            = 24
  desired_capacity    = 6
  vpc_zone_identifier = aws_subnet.app[*].id   # spread across 3 AZs
  health_check_type   = "ELB"

  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 75              # never below 75% during a refresh
      instance_warmup        = 60
    }
  }
}
```

**Circuit breaker and timeout budget (Python):**

```python
import time
from dataclasses import dataclass, field

@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout: float = 30.0
    _failures: int = 0
    _opened_at: float = 0.0

    def allow(self) -> bool:
        if self._failures < self.failure_threshold:
            return True
        if time.monotonic() - self._opened_at > self.reset_timeout:
            self._failures = 0          # half-open: allow a probe
            return True
        return False

    def record(self, ok: bool) -> None:
        if ok:
            self._failures = 0
        else:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()

recommendations_breaker = CircuitBreaker()

async def get_recommendations(user_id: str) -> list[dict]:
    if not recommendations_breaker.allow():
        return []                       # degrade: empty list, page still renders
    try:
        items = await recommendations_client.fetch(user_id, timeout=0.8)  # budget < total 2 s
        recommendations_breaker.record(True)
        return items
    except Exception:
        recommendations_breaker.record(False)
        return []                       # never fail checkout because recs are slow
```

**Retry with jitter and a strict budget (prevents retry storms):**

```python
import asyncio, random

async def call_with_retry(fn, *, attempts: int = 3, base: float = 0.05, cap: float = 1.0):
    for i in range(attempts):
        try:
            return await fn()
        except TransientError:
            if i == attempts - 1:
                raise
            await asyncio.sleep(min(cap, base * 2 ** i) * random.uniform(0.5, 1.5))
    # total added latency ≤ ~1.1 s; the caller's deadline (2 s) always wins
```

**Data-layer failover expectations documented (not assumed):**

```markdown
| Component | Failure | Automated behavior | User impact | Max duration |
|---|---|---|---|---|
| RDS primary (Multi-AZ) | instance/AZ failure | automatic failover to standby | 30–90 s of failed writes; reads may fail | ~2 min |
| Aurora reader | reader loss | endpoint removes reader | none | < 30 s |
| Redis primary | node failure | replica promotion | in-flight sessions may be lost; fallback to Postgres | ~30 s |
| NAT gateway (one AZ) | AZ loss | other AZs have their own NAT | none (cross-AZ egress) | 0 |
| DNS | zone outage | secondary zone on another provider | resolution delays up to TTL | TTL (60 s) |
```

**Failover drill (staging first, production with approval):**

```bash
# 1. Baseline
kubectl -n payments get pods -o wide | awk '{print $7}' | sort | uniq -c   # pods per node
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" https://staging.example.com/v1/orders/health

# 2. Inject failure (managed fault injection: instance termination of one AZ's nodes)
aws fis start-experiment --experiment-template-id EXT... --tags Name=az-failure-drill

# 3. Observe during the fault
watch -n2 'curl -s -o /dev/null -w "code=%{http_code} t=%{time_total}s\n" https://staging.example.com/v1/orders'

# 4. Measure: error rate, p99, time to full recovery, alerts fired
# 5. Record in the drill log, including any alert that did NOT fire
```

**Degradation ladder (decide before the incident, not during):**

```text
Level 0 — normal
Level 1 — recommendations/search disabled, cached results served (checkout unaffected)
Level 2 — non-essential writes queued (analytics, emails), synchronous path preserved
Level 3 — read-only mode for non-critical surfaces; checkout still allowed
Level 4 — static maintenance page with status link (only when data integrity is at risk)
Owner decides at each level; the trigger metric and the rollback for each level are pre-agreed.
```

## 8. Quality Standards

- Each user-facing service has documented SLIs, an SLO, and an error-budget policy.
- No single-instance dependency remains in the critical path for a service claiming multi-AZ.
- Health checks are readiness-based for traffic and shallow for liveness; thresholds prevent flapping.
- Timeouts and retries form a bounded budget; no unbounded retry loops.
- Every critical dependency has a defined degradation behavior.
- Failover is tested at a documented cadence with measured, user-visible impact.
- SLO burn-rate alerts exist with multi-window rules and linked runbooks.
- Architecture decisions state which failures are accepted (and their cost).

## 9. Verification and Testing

- Kill one instance of each tier in staging: no user-visible errors, no dropped requests.
- Force a database failover during a load test; measure error count and recovery time against the documented expectation.
- Simulate an AZ failure (remove that AZ's nodes/NAT) and confirm capacity remains within SLO.
- Verify DNS failover with a health check: take the primary endpoint unhealthy and measure propagation time.
- Confirm alerting fires on a synthetic 5% error injection within the intended burn window.
- Review the last 90 days of incidents: each contributed to a design change or a documented acceptance.

## 10. Security Considerations

- Failover must not weaken security: replica databases and standby regions need the same encryption, IAM, and network controls as primary.
- Health-check endpoints must not leak internals; return minimal status, no version strings or dependency details.
- Circuit breakers and fallbacks must not silently bypass authorization or validation — degrade features, never controls.
- Multi-region replication carries data-residency obligations; confirm the standby region is permitted.
- Break-glass failover credentials must be tightly scoped, audited, and rotated; the power to fail over is the power to cause an outage.
- Chaos experiments need authorization, a blast-radius limit, an abort switch, and notification to on-call.

## 11. Failure Handling

- **Failover works but capacity does not:** the surviving AZ cannot absorb the load — size for N+1 AZ and test at full traffic.
- **Health checks cascade:** every instance fails readiness because they all check the same dependency; use shallow readiness plus dependency-specific degradation.
- **Retry storm during an outage:** clients retry aggressively; add jitter, caps, and server-side load shedding.
- **Split brain in stateful failover:** confirm the fencing/quorum mechanism; never run two primaries accepting writes.
- **SLO breach with no obvious incident:** slow burn from a degraded dependency; inspect the burn-rate dashboard by route and dependency.

## 12. Expected Deliverables

1. SLI/SLO definitions per user-facing service with error-budget policy.
2. Failure-domain map and SPOF inventory with remediation status.
3. Redundancy configuration per tier (AZ spread, replicas, redundant egress, DNS).
4. Degradation ladder with triggers and owners.
5. Failover runbooks and drill reports with measured impact.
6. Burn-rate alert rules and dashboards.
7. Post-incident architecture changes linked to budget consumption.

## 13. References

- Google SRE Book — "Embracing Risk" and "Service Level Objectives" — https://sre.google/sre-book/embracing-risk/
- Google SRE Workbook — "Alerting on SLOs" — https://sre.google/workbook/alerting-on-slos/
- AWS Well-Architected — Reliability Pillar — https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html
- AWS Fault Injection Service — https://docs.aws.amazon.com/fis/latest/userguide/what-is.html
- Route 53 health checks and failover routing — https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover.html
- resilience4j (circuit breakers) — https://resilience4j.readme.io/
- Chaos Mesh — https://chaos-mesh.org/
- OpenSLO specification — https://openslo.com/
