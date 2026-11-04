---
name: cloud-migration
description: Move workloads to the cloud or between providers—portfolio assessment, 6Rs strategy, landing zone, wave planning, cutover, and rollback.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# Cloud Migration

## 1. Purpose

Move systems to a new platform without a multi-day outage or a permanent cost surprise. Migrations fail for organizational more than technical reasons: no inventory, no owner per application, "lift and shift" of workloads that needed re-architecture, cutovers with no rollback, and no data-validation criteria. This skill covers portfolio assessment, strategy selection (the 6Rs), landing-zone prerequisites, wave planning, data migration with validation, cutover, and decommissioning.

**Scope:** systems and data you own. Migration involves copying and cutting over production data: require written authorization per wave, verify legal/contractual constraints on data movement (residency, third-party terms), never delete source systems until the retention and validation period has passed, and always have a tested rollback.

## 2. Activation Conditions

- Datacenter exit, provider change, or acquisition consolidation.
- Compliance or residency requirement driving relocation.
- Cost or scalability forcing a platform change.
- Keywords: cloud migration, lift and shift, 6Rs, rehost, replatform, refactor, wave planning, landing zone, cutover, dual-run, data migration, rollback, decommission, TCO.

## 3. When Not to Use

- Greenfield builds (use the relevant cloud engineering skill).
- Single-service moves within one provider (treat as a standard change).
- Disaster recovery planning (use disaster-recovery-and-backup).

## 4. Required Context

1. Application portfolio: owners, dependencies, criticality tiers, data volumes.
2. Current costs and performance baselines.
3. Target platform and landing zone readiness.
4. Compliance constraints: residency, encryption, audit, contractual.
5. Business calendar: freeze periods, peak seasons.

## 5. Operating Procedure

1. **Build the portfolio inventory**: every application, owner, tier, dependency graph, data store, integration, batch job, and interface. Unknown dependencies are the top cause of failed cutovers.
2. **Assign a strategy per application (6Rs)** with rationale: retire, retain, rehost, replatform, refactor, repurchase. Most portfolios are 60–70% retire/rehost/replatform; reserve refactor for apps where the business case is explicit.
3. **Retire first**: decommissioning 15–20% of a portfolio is the cheapest migration win and shrinks everything downstream.
4. **Sequence into waves by dependency and value**, not by department: early waves should be low-risk and build the migration muscle (internal tools → supporting services → revenue paths).
5. **Prepare the target landing zone before wave 1**: accounts, network, identity, logging, guardrails, IaC, CI/CD, and cost allocation (see aws-engineering and terraform-engineering).
6. **Baseline performance and cost per application** on the source so you can prove parity after cutover.
7. **Design the cutover per wave**: coexistence period, data sync mechanism, DNS/traffic switch, validation criteria, and rollback trigger with a time limit.
8. **Migrate data with validation, not hope**: row counts, checksums, referential integrity, and application-level reconciliation; run dual-write/CDC where the RPO demands it.
9. **Dual-run where the risk justifies it**: shadow traffic or a canary slice for a defined period, comparing outputs.
10. **Cut over with a written runbook and a decision log**: who decides go/no-go, what the abort criteria are, and who can call a rollback.
11. **Decommission deliberately** after a 30-day stability window: revoke access, delete data per retention policy, update the CMDB/service catalogue, and close the cost line.
12. **Report per wave**: migrated scope, parity evidence, incidents, cost delta, and lessons that change the next wave.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Discovery | CMDB, network flow analysis, `lsof`/`ss` inventories, application dependency mapping tools |
| Server migration | AWS MGN, Azure Migrate, GCP Migrate to VMs |
| Database migration | AWS DMS, `pg_dump`/`pg_restore`, logical replication, `pglogical` |
| Storage sync | `rclone`, `aws s3 sync`, DataSync, `rsync` |
| Replatform targets | RDS instead of self-managed DB, ECS/EKS instead of VMs, S3 instead of NFS |
| IaC/landing zone | Terraform, Control Tower, org-level SCPs |
| Cutover | Route 53 weighted routing, feature flags, load-balancer weighted target groups |
| Validation | reconciliation scripts, checksums, business metric comparison |

## 7. Practical Implementation

**Portfolio inventory and strategy table (the planning artifact):**

```markdown
| App | Owner | Tier | Strategy | Target | Wave | Depends on | Data (GB) | Cutover risk |
|---|---|---|---|---|---|---|---|---|
| internal-wiki | @it | 3 | repurchase | SaaS | 1 | SSO | 40 | low |
| legacy-crm | @sales-ops | 3 | retire | — | 1 | reporting-db | 200 | low (archive) |
| reporting-db | @data | 2 | replatform | RDS Postgres | 2 | orders-db (read) | 800 | medium |
| orders-api | @payments | 1 | replatform | EKS + RDS | 3 | payments provider, Redis | 300 | high |
| batch-billing | @finance | 1 | refactor | Lambda + SQS | 4 | orders-api | 50 | high |
| image-store | @platform | 2 | replatform | S3 + CloudFront | 2 | none | 4000 | low |
```

**Wave plan with entry and exit criteria:**

```markdown
## Wave 2 — supporting services (2 weeks)
**Entry criteria:** landing zone live; IaC modules published; on-call rota covers new stack;
DNS TTLs lowered to 60 s for all in-scope names.
**Scope:** reporting-db, image-store.
**Exit criteria:** 14 days with no Sev-1/Sev-2; p95 within 10% of baseline; cost delta within
±15% of the model; source read-only for 7 days then decommissioned.

## Rollback policy per wave
- Redeploy the source stack (kept warm for 14 days after cutover).
- Repoint DNS/LB weights back to the source (≤ 5 min once the decision is made).
- Data: source remains authoritative until dual-write is disabled (day 14).
- Abort triggers: error rate > 2× baseline, p95 > 2× baseline, any data-validation mismatch.
```

**Database migration with logical replication (minimal downtime):**

```bash
# 1. Provision target and create schema from migrations (never from a dump of a live DB)
alembic upgrade head    # against the target RDS instance

# 2. Establish replication from source to target
psql "host=$SOURCE dbname=orders user=repl" -c \
  "SELECT pg_create_logical_replication_slot('migrate_orders', 'pgoutput');"
psql "host=$SOURCE dbname=orders user=repl" -c \
  "CREATE PUBLICATION migrate_pub FOR ALL TABLES;"
psql "host=$TARGET dbname=orders" -c \
  "CREATE SUBSCRIPTION migrate_sub CONNECTION 'host=$SOURCE dbname=orders user=repl' PUBLICATION migrate_pub;"

# 3. Monitor replication lag until it is stable near zero
psql "$TARGET" -c "SELECT subname, received_lsn, latest_end_lsn,
  now() - latest_end_time AS lag FROM pg_stat_subscription;"

# 4. Validate continuously before cutover
./scripts/reconcile.sh --source "$SOURCE" --target "$TARGET" --tables order,order_line,payment
```

```bash
#!/usr/bin/env bash
# scripts/reconcile.sh — compare counts and checksums; non-zero exit blocks cutover
set -euo pipefail
for t in order order_line payment; do
  src=$(psql "$SOURCE" -tAc "SELECT count(*), coalesce(sum(hashtext(x::text)),0) FROM (SELECT t.*::text AS x FROM \"$t\" t) s")
  dst=$(psql "$TARGET" -tAc "SELECT count(*), coalesce(sum(hashtext(x::text)),0) FROM (SELECT t.*::text AS x FROM \"$t\" t) s")
  if [ "$src" != "$dst" ]; then
    echo "MISMATCH $t: source=$src target=$dst" >&2
    exit 1
  fi
  echo "ok $t: $src"
done
```

**Cutover runbook (staged, reversible):**

```markdown
# Cutover: orders-api → EKS + RDS (Wave 3)

T-7 days
- [ ] Rehearsal completed in staging with production-like traffic
- [ ] DNS TTL = 60 s; both targets healthy in the load balancer
- [ ] Rollback rehearsed and timed (< 5 min)

T-0 (02:00 IST, change window approved by @payments-lead)
1. [ ] Enable maintenance banner for non-critical surfaces (checkout stays live)
2. [ ] Stop batch jobs writing to the source database
3. [ ] Confirm replication lag < 1 s and reconcile passes
4. [ ] Shift 5% of traffic (weighted target group) → watch 15 min
        go/no-go: 5xx ≤ baseline, p95 ≤ 1.2× baseline
5. [ ] Shift 50% → watch 15 min, same criteria
6. [ ] Shift 100%; keep the source running read-only for rollback
7. [ ] Run business smoke tests: create order, pay, refund, export invoice
8. [ ] Announce completion with the new endpoints and dashboards

Rollback (decision by incident commander, ≤ 10 min)
- [ ] Shift weights back to the source target group
- [ ] Reverse replication or discard target writes made after T-0 (documented data policy)
- [ ] Confirm source traffic is healthy; keep the target available for analysis

T+1 day: verify reconciliation again; disable source writes entirely.
T+14 days: decommission source (snapshot, revoke access, close cost line).
```

**Dual-run validation for a hard-to-reverse migration:**

```python
# Shadow-mode comparison: send production requests to the new implementation
# with a sampled mirror, compare results, never return the shadow result to the user.
async def handle(request):
    primary = await legacy_impl(request)

    if should_shadow(request):
        shadow = await new_impl(request)
        if not equivalent(primary, shadow):
            metrics.increment("migration.shadow_mismatch",
                              tags={"route": request.route, "field": first_diff(primary, shadow)})
            log.warning("shadow mismatch", extra={"request_id": request.id, "route": request.route})

    return primary
```

**CloudFront/S3 file migration with verification:**

```bash
aws s3 sync /mnt/nfs/images s3://acme-images-prod/ \
  --exclude "*.tmp" --storage-class INTELLIGENT_TIERING --only-show-errors

# Verify by count and total size, then spot-check checksums on a sample
aws s3 ls --recursive --summarize s3://acme-images-prod/ | tail -3
find /mnt/nfs/images -type f -newermt '2020-01-01' | wc -l
```

## 8. Quality Standards

- Every in-scope application has an owner, tier, strategy, and wave before work starts.
- Retire/replace decisions are made before rehosting an app nobody needs.
- Landing zone (accounts, network, identity, logging, guardrails, IaC, CI/CD, cost tags) is live before wave 1.
- Performance and cost baselines exist for every migrated application.
- Data validation is automated and blocks cutover on mismatch.
- Every cutover has written go/no-go criteria, a rollback trigger, and a rehearsed rollback.
- Dual-run or canary periods are used for Tier 1 workloads.
- Decommissioning has a defined stability window, snapshot, access revocation, and catalogue update.
- Per-wave reports capture parity evidence and lessons.

## 9. Verification and Testing

- Full cutover rehearsal in staging with production-shaped data and traffic.
- Reconciliation script passes on all critical tables; run it twice (before and after cutover).
- Business smoke tests executed by a non-migrating person (finance runs the invoice test).
- Rollback rehearsal timed and documented, including the data-handling decision.
- Performance comparison against baseline at p50/p95/p99 and throughput.
- Cost comparison against the TCO model after the first full billing cycle.

## 10. Security Considerations

- The landing zone must meet the target security baseline before data arrives: encryption, logging, network segmentation, IAM, and secret management.
- Data residency and contractual terms may prohibit moving certain data classes; verify per application before wave 1.
- Replication connections must be encrypted and use dedicated least-privilege accounts, removed after cutover.
- Migration tooling and temporary credentials are high-value targets: rotate, scope, and delete them promptly.
- Source systems often run on unsupported software; an interim compensating control is required if the migration slips.
- Do not lower security controls to make the cutover work (e.g. temporarily public databases, disabled WAF); if unavoidable, time-box, log, and revert.
- Decommissioning must include secure data destruction (crypto-shredding or certified wipe) per policy.

## 11. Failure Handling

- **Unknown dependency discovered at cutover:** dependency mapping missed a cron job or a hard-coded IP. Mitigate with flow logs and DNS query logs from the source during the pilot; keep the source running for the coexistence window.
- **Replication lag grows:** large transactions or insufficient IOPS on the target; batch large deletes/updates, increase target capacity, or use a staged bulk load plus CDC.
- **Post-cutover performance regression:** rehosting without right-sizing. Compare against the baseline, adjust instance class/IOPS, and check the new network path (cross-AZ chatter, DNS).
- **Data mismatch after cutover:** writes went to both sides and diverged. Define authority per table before cutover; reconcile and document any accepted loss.
- **Rollback window expired and defects appear:** keep read-only access to the source snapshot; recovery becomes a data operation, not a switch, so plan for it.
- **Cost higher than modeled:** data egress, cross-AZ traffic, or missing commitment discounts; re-run the model with real billing data and apply the cost-optimization skill.

## 12. Expected Deliverables

1. Application portfolio inventory with owners, tiers, and dependencies.
2. 6Rs strategy per application with rationale.
3. Wave plan with entry/exit criteria and business calendar.
4. Landing zone readiness checklist.
5. Per-application runbooks: data migration, cutover, validation, rollback.
6. Reconciliation and parity reports.
7. Wave reports with cost/performance deltas.
8. Decommissioning records and catalogue updates.

## 13. References

- AWS Migration Hub and the 6Rs — https://docs.aws.amazon.com/migrationhub/latest/ug/whatishub.html
- AWS Prescriptive Guidance: migration strategies — https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html
- AWS Database Migration Service — https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html
- PostgreSQL logical replication — https://www.postgresql.org/docs/current/logical-replication.html
- AWS Application Migration Service — https://docs.aws.amazon.com/mgn/latest/ug/what-is-application-migration-service.html
- Google Cloud migration center — https://cloud.google.com/migration-center/docs
- Azure Migrate — https://learn.microsoft.com/azure/migrate/migrate-services-overview
- AWS Well-Architected — Operational Excellence Pillar — https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html
