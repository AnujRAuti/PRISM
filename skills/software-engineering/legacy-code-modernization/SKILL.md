---
name: legacy-code-modernization
description: Bring untested, outdated systems forward safely—characterization tests, seam identification, strangler migrations, dependency upgrades, and risk-managed cutover.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: high
---

# Legacy Code Modernization

## 1. Purpose

Modernize systems that cannot be safely changed: no tests, dead frameworks, undocumented behavior, and business logic encoded in 15-year-old code. This skill provides the disciplined path—characterize before changing, create seams, migrate incrementally (strangler fig), keep the old system live until proven, then decommission with evidence. It avoids the two failure modes: endless paralysis ("we can't touch it") and catastrophic big-bang rewrites.

## 2. Activation Conditions

- Framework/language end-of-life (Python 2, Java 8 EOL, .NET Framework, AngularJS, PHP 5).
- Unsafe dependencies, CVE backlogs, or inability to run on current OS.
- Business rules only known by one person or embedded in code.
- Need to add features to a system that has no tests.
- Keywords: legacy, modernization, migration, upgrade, strangler, monolith split, technical renovation, EOL, deprecated runtime.

## 3. When Not to Use

- The system will be retired within 6 months—plan decommission instead.
- Small isolated modules with modern tooling; use code-refactoring.
- When there is no business case or budget for dual-running during migration.
- When "modernization" means adopting new tech for its own sake—require a concrete driver.

## 4. Required Context

1. Business criticality: revenue path, users, SLA, regulatory obligations.
2. Runtime inventory: language versions, frameworks, OS, database, deployment method.
3. Test coverage reality and how the system is verified today (manual QA scripts?).
4. Data volume and complexity; migrations cost.
5. Interfaces: who calls it, what it calls, file exchanges, DB links.
6. Team knowledge distribution and available time.
7. Constraints: no-downtime requirement, freeze windows, compliance.

## 5. Operating Procedure

1. **Inventory and classify** every capability by risk: business value × change frequency × technical risk. Pick the smallest high-value, low-risk slice to start.
2. **Establish a test harness** at the outermost boundary: record real requests/responses (sanitized) and replay. Add smoke tests for critical journeys.
3. **Characterize behavior** with golden-master tests around the slice you will change, including quirks and error messages.
4. **Identify seams**: HTTP boundaries, DB views, message queues, file interfaces. Prefer seams you can intercept without editing the legacy code.
5. **Choose migration pattern**:
   - Strangler fig (route traffic gradually to new implementation).
   - Branch by abstraction (interface in front of legacy, swap implementation).
   - Extract-then-rewrite (lift a module out, then rewrite in isolation).
   - Re-host/re-platform (same code, new runtime) when logic is fine.
6. **Build the new slice** behind a router/feature flag with shadow traffic; compare outputs continuously.
7. **Dual-run and diff.** Log differences; treat any unexpected diff as a finding, not noise.
8. **Migrate data** with a reversible plan: dual-write or CDC, backfill with verification, then cut reads over, then stop dual-write.
9. **Cut over progressively**: internal users → 5% → 50% → 100%, each with a rollback trigger (error rate, latency, business metric).
10. **Decommission the old slice** only after a stability window (e.g. 2 weeks at 100%), then remove routing and delete code.
11. **Repeat per slice**; never start a second slice before the first is closed out.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Traffic capture/replay | Envoy/nginx mirroring, GoReplay, `mitmproxy` |
| Golden master | approvaltests, snapshot testing, custom diff harness |
| Feature flags | Unleash, LaunchDarkly, config-based flags |
| Data sync | Debezium CDC, logical replication, dual-write with outbox |
| Routing | nginx, Envoy, API gateway |
| Legacy runtimes | Containers/VMs to freeze old environment safely |
| Static analysis of legacy | SonarQube, `jdeps`, `grep`-based inventories |
| Documentation recovery | EventStorming, code reading sessions, call-graph tools |

## 7. Practical Implementation

**Golden-master harness (Python, HTTP boundary):**

```python
# tests/golden/test_legacy_parity.py
import json, pathlib, httpx, pytest

CASES = json.loads(pathlib.Path("tests/golden/cases.json").read_text())

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_new_matches_legacy(case):
    legacy = httpx.post("http://legacy:8080/quote", json=case["request"], timeout=10)
    new = httpx.post("http://new:8080/v1/quote", json=case["request"], timeout=10)
    assert new.status_code == legacy.status_code
    assert normalize(new.json()) == normalize(legacy.json())

def normalize(body: dict) -> dict:
    # drop fields that legitimately differ: timestamps, request ids
    return {k: v for k, v in body.items() if k not in {"request_id", "generated_at"}}
```

**Traffic shadowing with nginx:**

```nginx
location /api/quote {
    mirror /mirror_quote;
    mirror_request_body on;
    proxy_pass http://legacy_upstream;
}
location = /mirror_quote {
    internal;
    proxy_pass http://new_upstream$request_uri;
}
```

**Branch by abstraction (Java):**

```java
public interface QuoteEngine {
    Quote quote(QuoteRequest request);
}

@Component
@ConditionalOnProperty(name = "quote.engine", havingValue = "legacy", matchIfMissing = true)
class LegacyQuoteEngine implements QuoteEngine { /* delegates to old code */ }

@Component
@ConditionalOnProperty(name = "quote.engine", havingValue = "v2")
class V2QuoteEngine implements QuoteEngine { /* new implementation */ }
```

**Data migration with verification (SQL):**

```sql
-- 1. dual-write period: application writes both tables
-- 2. backfill in batches, keyed and resumable
WITH batch AS (
  SELECT id FROM orders_old
  WHERE id > $1 ORDER BY id LIMIT 1000
)
INSERT INTO orders_new (id, customer_id, total_cents, created_at)
SELECT id, customer_id, total_cents, created_at FROM orders_old WHERE id IN (SELECT id FROM batch)
ON CONFLICT (id) DO NOTHING
RETURNING id;

-- 3. verification query run continuously
SELECT count(*) FROM orders_old o
LEFT JOIN orders_new n USING (id)
WHERE n.id IS NULL OR n.total_cents <> o.total_cents;
```

**Cutover plan table:**

| Stage | Traffic to new | Duration | Rollback trigger |
|---|---|---|---|
| Shadow | 0% (mirrored) | 2 weeks, diff rate < 0.1% | Any unexplained diff |
| Canary | 5% | 3 days | Error rate > 1% or p95 +20% |
| Ramp | 50% | 3 days | Business metric drop > 2% |
| Full | 100% | 2 weeks stability | Any SEV-2 |

## 8. Quality Standards

- No behavior change without a test that proves the change was intended.
- Every migrated slice has parity evidence (diff rate, sample size, time window).
- Rollback is possible at every stage and rehearsed at least once.
- Data migration is resumable, idempotent, and verified with counts plus checksums.
- Decommissioning includes removing routes, flags, and dead code—not just stopping traffic.
- Business rules discovered during the work are documented in the repo.

## 9. Verification and Testing

```bash
# parity diff report
pytest tests/golden -q --maxfail=5
python scripts/diff_report.py --legacy http://legacy:8080 --new http://new:8080 --n 2000
# data verification
psql "$DB" -f scripts/verify_migration.sql
# canary health
kubectl top pods -n quote && curl -s http://new/healthz
```

Acceptance evidence: diff rate below threshold with sample size stated; migration verification returns zero rows; error budget and latency in range during ramp; rollback drill completed with timestamps.

## 10. Security Considerations

- Legacy systems often run unsupported runtimes with known CVEs: isolate them on a private network segment, restrict egress, and keep them patched to the last available version.
- Do not copy insecure patterns (string-concatenated SQL, MD5 passwords, disabled TLS verification) into the new code; explicitly list them as non-portable.
- Captured production traffic contains PII and secrets: sanitize before storing, encrypt at rest, and delete after use.
- Preserve security controls during migration—authz checks must move intentionally, not disappear with old middleware.
- Audit logging must continue across both systems; correlate by request ID during dual-run.
- Shadow traffic doubles load on downstream payment/notification systems—use sandbox endpoints or suppress side effects.

## 11. Failure Handling

- **Parity diffs too many to analyze:** bucket by endpoint and error type, fix the largest bucket first; temporarily exclude known-benign fields with documented justification.
- **Legacy behavior turns out wrong:** do not silently "fix" it during migration—record it as a behavior change with approval and a separate test.
- **Data inconsistency after backfill:** stop cutover, reconcile from source of truth, and add continuous verification before resuming.
- **Performance regression in new system:** compare with the same workload; often missing indexes or chatty calls—fix before ramping.
- **Business rules unknown:** run code-reading sessions and add characterization tests; consult users for expected outcomes.
- **Team reverts to big-bang:** re-scope into smaller slices with independent value.

## 12. Expected Deliverables

1. System inventory and risk-ranked slice list.
2. Test harness and characterization tests.
3. Chosen migration pattern per slice with rationale.
4. Shadow/diff results with thresholds.
5. Data migration and verification scripts.
6. Cutover plan with rollback triggers and rehearsal record.
7. Decommission checklist and final report on what was retired.

## 13. References

- Michael Feathers, *Working Effectively with Legacy Code*.
- Martin Fowler, "StranglerFigApplication" — https://martinfowler.com/bliki/StranglerFigApplication.html
- Martin Fowler, "BranchByAbstraction" — https://martinfowler.com/bliki/BranchByAbstraction.html
- Sam Newman, *Monolith to Microservices*.
- Debezium documentation — https://debezium.io/documentation/
- GoReplay — https://github.com/buger/goreplay
- ApprovalTests — https://approvaltests.com/
