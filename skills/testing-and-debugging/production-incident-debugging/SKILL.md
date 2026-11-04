---
name: production-incident-debugging
description: Diagnose live production issues safely—stabilize first, gather evidence read-only, correlate telemetry, and avoid changes that deepen the outage.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: high
---

# Production Incident Debugging

## 1. Purpose

Restore service fast and learn the truth about what happened, without making it worse. Production debugging differs from local debugging in three ways: the system is live, the data is real, and every command has consequences. This skill covers the stabilization-first sequence, read-only evidence gathering, symptom-to-cause correlation using metrics/traces/logs, safe mitigation (rollback, flag off, scale), and the handoff into a blameless postmortem.

**Scope:** production systems you operate. Every action on production requires authorization under your incident process: destructive operations (dropping data, force-deleting queues, killing database sessions, restarting stateful services) need explicit incident-commander approval. Read-only first, always.

## 2. Activation Conditions

- Error rate, latency, or saturation breaches an SLO.
- Users report failures; a deploy or config change just landed.
- Data integrity question in production (wrong totals, missing records).
- Partial outage across a dependency.
- Keywords: incident, outage, on-call, rollback, mitigation, runbook, SLO, error budget, postmortem, RCA, 5xx spike, latency spike, saturation, feature flag, kill switch.

## 3. When Not to Use

- Pre-production debugging (use debugging-techniques).
- Post-incident deep analysis with no live risk (do it in staging with production-shaped data).
- Capacity planning before an incident (use performance-and-load-testing).

## 4. Required Context

1. Incident severity definitions and the paging/escalation path.
2. Current deploy state: version, recent changes, flags, config.
3. Dashboards: traffic, errors by class, latency percentiles, saturation, dependencies.
4. Runbooks for the affected services and their dependencies.
5. Authorization model for production actions and who holds incident command.

## 5. Operating Procedure

1. **Declare and assign**: state severity, open an incident channel, name an incident commander, and set a check-in cadence. One person decides; others investigate.
2. **Stabilize before diagnosing.** Prefer the fastest reversible mitigation: roll back the last deploy, disable the feature flag, shed non-critical load, fail over, or scale out.
3. **Ask "what changed?" first**: deploys, config, feature flags, cron schedule, traffic pattern, dependency status, certificate/credential expiry, DNS.
4. **Gather evidence read-only**: dashboards, trace samples, log queries, `pg_stat_activity`, `EXPLAIN` on reads only, `kubectl describe/logs`, provider status pages.
5. **Localize the failure**: which route/dependency/tenant/region/version? Slice metrics by those dimensions rather than staring at aggregates.
6. **Check the boundaries first**: database connection pool, cache availability, queue depth/age, DNS, TLS expiry, third-party API errors and rate limits.
7. **Form one hypothesis and test it with a reversible action**, recording what you did in the timeline with timestamps.
8. **Communicate on a cadence** even without new information; include impact, current mitigation, and next update time.
9. **Verify recovery with the same signal that detected the problem**, not just "looks better".
10. **Preserve evidence before cleanup**: snapshot logs, metrics windows, trace IDs, and the exact versions/configs involved.
11. **Write the timeline while it is fresh**; then run a blameless postmortem with concrete action items and owners.
12. **Remove temporary mitigations deliberately**: a burned-in `sleep`, an enlarged pool, or a disabled check becomes permanent debt if unowned.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Metrics/dashboards | Prometheus + Grafana, Datadog, CloudWatch, OTel metrics |
| Traces | Tempo, Jaeger, Honeycomb, Datadog APM |
| Logs | Loki, Elastic, CloudWatch Logs Insights |
| DB | `pg_stat_activity`, `pg_stat_statements`, replication lag queries |
| Kubernetes | `kubectl get/describe/logs`, `kubectl top`, events |
| Feature control | LaunchDarkly, Unleash, config service |
| Status | Dependency status pages, `dig`/`curl` probes |
| Comms | Incident channel, status page, PagerDuty/Opsgenie |

## 7. Practical Implementation

**First five minutes: read-only triage commands**

```bash
# What is deployed, and when did it change?
kubectl -n prod rollout history deploy/orders-api | tail -5
kubectl -n prod get pods -l app=orders-api -o wide
kubectl -n prod get events --sort-by=.lastTimestamp | tail -20

# Error rate by route (PromQL)
# sum by (route) (rate(http_requests_total{status=~"5.."}[5m]))

# Are we saturated or erroring?
kubectl -n prod top pods | sort -k3 -hr | head
kubectl -n prod logs deploy/orders-api --since=15m --tail=200 | grep -iE "error|exception|timeout" | head -40
```

**Database read-only diagnostics**

```sql
-- Who is running what, and for how long?
SELECT pid, usename, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 100) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC
LIMIT 20;

-- Connections vs. limit (pool exhaustion is the most common cause)
SELECT (SELECT count(*) FROM pg_stat_activity) AS used,
       current_setting('max_connections')::int AS max;

-- Blocking chains
SELECT blocked.pid AS blocked_pid, blocking.pid AS blocking_pid,
       left(blocked.query, 60) AS blocked_query
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocking
  ON blocking.pid = ANY(pg_blocking_pids(blocked.pid));

-- Cache hit ratio (a sudden drop means cold cache or missing index)
SELECT sum(blks_hit) * 100.0 / nullif(sum(blks_hit + blks_read), 0) AS hit_pct
FROM pg_stat_database;
```

Never `pg_terminate_backend` or `pg_cancel_backend` without incident-commander approval; killing a writer mid-transaction can leave inconsistent state.

**Trace-first localization (instead of reading 10k log lines):**

```text
Filter: service.name = "orders-api" AND http.status_code >= 500
Group by: http.route, k8s.pod.name, version
Look for: the span where latency/error originates (db.query vs. http.client vs. handler)
Then: pull one trace_id and read the exact failing span's attributes and events
```

**Log query that answers a specific question:**

```text
{service="orders-api", version="2.14.1"}
  | json
  | error_code != ""
  | line_format "{{.ts}} {{.error_code}} {{.order_id}} {{.duration_ms}}"
```

```sql
-- CloudWatch Logs Insights equivalent
fields @timestamp, error_code, order_id, duration_ms
| filter error_code like /PAYMENT/
| stats count() by error_code, bin(5m)
```

**Rollback as the default mitigation:**

```bash
# Deploy rollback (platform-specific; verify in a runbook before you need it)
kubectl -n prod rollout undo deploy/orders-api
kubectl -n prod rollout status deploy/orders-api --timeout=180s

# Feature flag kill switch (preferred when the change is flag-gated)
curl -sS -X PATCH "$FLAG_API/flags/checkout_v2" \
  -H "Authorization: Bearer $FLAG_TOKEN" -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Traffic shedding under overload (reversible, bounded):**

```nginx
# Temporarily cap expensive search traffic at the edge, keep checkout healthy
limit_req_zone $binary_remote_addr zone=search:10m rate=2r/s;
location /v1/search {
    limit_req zone=search burst=5 nodelay;
    limit_req_status 429;
    proxy_pass http://search_backend;
}
```

```python
# Application-level: serve degraded but correct responses instead of failing
if circuit.is_open("recommendations"):
    return {"items": [], "degraded": True}      # never fabricate data as if real
```

**Dependency health probes:**

```bash
dig +short api.payments.example.com
echo | openssl s_client -servername api.example.com -connect api.example.com:443 2>/dev/null \
  | openssl x509 -noout -dates
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" https://api.payments.example.com/healthz
```

**Incident timeline entry format:**

```markdown
- 14:02 UTC — Alert: orders-api 5xx > 5% for 3 min. IC: @priya. Sev-2 declared.
- 14:04 — Dashboards: 5xx concentrated on POST /v1/orders/{id}/pay; DB pool at 100%.
- 14:05 — Change check: deploy 2.14.1 (14:00) included connection-pool refactor.
- 14:07 — Hypothesis: pool_size reduced 20→5; prediction: reverting restores capacity.
- 14:09 — Rollout undo initiated (approved by IC).
- 14:12 — 5xx back to 0.2%; pool wait < 5 ms. Recovering.
- 14:25 — Stable 20 min. Monitoring. Evidence snapshot saved to inc-4821/.
```

**Evidence preservation checklist:**

```text
[ ] Metrics window exported (JSON/CSV) for the incident period
[ ] Representative trace IDs (10-20) captured, plus one full trace JSON
[ ] Logs for the window saved to the incident bucket (with PII redaction rules)
[ ] Deploy/flag change history with timestamps
[ ] `EXPLAIN` plans and `pg_stat_statements` snapshot from the window
[ ] Dependency provider status and incident IDs
```

## 8. Quality Standards

- Mitigation precedes root-cause analysis whenever a mitigation exists and is reversible.
- All production actions are logged in the timeline with actor and approval.
- Diagnostics are read-only until an approved mitigation; no interactive debuggers or ad-hoc `UPDATE`s.
- Localization uses dimensions (route, tenant, version, dependency) rather than aggregate charts alone.
- Recovery is verified against the detecting signal and held for a stability window (e.g. 20 min).
- Evidence is preserved before cleanup, with PII handled per policy.
- Temporary mitigations have an owner and an expiry ticket.
- A postmortem is completed within the agreed window with action items and owners.

## 9. Verification and Testing

- After mitigation, confirm the alert resolves and the SLO error budget stops burning.
- Run a smoke test on critical journeys (read and write) rather than trusting dashboards alone.
- Compare pre-incident and post-recovery baselines (latency, throughput, pool usage).
- Confirm no data corruption by running integrity checks (`count` deltas, reconciliation job, checksums on affected records).
- Re-run the runbook steps in staging as a drill to keep them accurate.

## 10. Security Considerations

- Production access requires MFA, least-privilege roles, and an audited break-glass path; a real incident is also a common moment for social engineering—verify identities before granting access.
- While firefighting, attackers may exploit weakened controls: do not disable WAF, auth, or rate limits for convenience; if unavoidable, time-box it and re-enable with verification.
- Logs and traces pulled during an incident contain sensitive data; move them to restricted storage with retention limits.
- Do not paste secrets from environment dumps into the incident channel; redact before sharing.
- Any command with `--force`, `--no-verify`, `DELETE`, `DROP`, `TRUNCATE`, `pg_terminate_backend`, or a queue purge requires IC approval and a backup/verification plan.
- Preserve evidence with chain-of-custody notes if the incident may involve a compromise; coordinate with security before deleting anything.

## 11. Failure Handling

- **Mitigation makes it worse:** revert the mitigation immediately; prefer flags so you can flip back in seconds.
- **Alert noise makes the signal invisible:** mute non-critical alerts temporarily and record it; alert on symptoms (SLO burn) not causes.
- **Dashboards show nothing wrong while users complain:** your instrumentation is blind (missing route label, unmonitored dependency). Sample real user requests and check the edge/CDN layer.
- **Rollback is blocked by a migration:** expand/contract migrations keep rollback possible — never ship a destructive migration and a code change in the same deploy.
- **Everyone debugging, nobody communicating:** IC enforces roles; one investigator per hypothesis, one comms owner.
- **Recurrence of the same incident:** postmortem action items were not completed — track them as work items with owners and due dates.

## 12. Expected Deliverables

1. Incident declaration with severity and IC.
2. Live timeline with actions and approvals.
3. Evidence bundle (metrics, traces, logs, plans).
4. Mitigation record and verification.
5. Root cause analysis and contributing factors.
6. Action items with owners and dates.
7. Runbook updates and detections added.

## 13. References

- Google SRE Book — "Managing Incidents" — https://sre.google/sre-book/managing-incidents/
- Google SRE Workbook — "Postmortem Culture" — https://sre.google/workbook/postmortem-culture/
- PagerDuty Incident Response documentation — https://response.pagerduty.com/
- PostgreSQL monitoring statistics — https://www.postgresql.org/docs/current/monitoring.html
- Prometheus alerting practices — https://prometheus.io/docs/practices/alerting/
- OpenTelemetry traces — https://opentelemetry.io/docs/concepts/signals/traces/
- Kubernetes debugging running pods — https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
