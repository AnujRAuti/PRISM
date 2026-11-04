---
name: cloud-cost-optimization
description: Reduce cloud spend without breaking reliability—allocation and tagging, waste elimination, commitment planning, and unit-cost tracking with owner accountability.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: medium
---

# Cloud Cost Optimization

## 1. Purpose

Cut waste and align spend with value, permanently. Cost problems are usually allocation problems: nobody knows which team owns a line item, so nobody acts. The durable sequence is tag and allocate, find waste, right-size, then commit to discounts — in that order. This skill covers cost visibility, common waste classes, commitment strategy, storage lifecycle, and unit economics.

**Scope:** cloud accounts you own. Cost work involves deleting and resizing resources: require owner confirmation before terminating anything, verify backups for stateful systems, and never delete resources to hit a budget without a change record.

## 2. Activation Conditions

- Bill grew faster than traffic; forecast exceeds budget.
- Large untagged spend or shared costs nobody claims.
- Before signing a commitment (Savings Plans/Reserved Instances).
- FinOps review or funding conversation.
- Keywords: FinOps, cost optimization, tagging, cost allocation, right-sizing, Savings Plans, Reserved Instances, spot, idle resources, storage lifecycle, unit economics, anomaly detection, budget.

## 3. When Not to Use

- Performance tuning that ignores cost (do both, together).
- Vendor selection (use technical-research-reports).
- Cutting spend by reducing reliability without an explicit risk decision.

## 4. Required Context

1. Billing accounts, organization structure, and cost-allocation strategy.
2. Top spend services and fastest-growing line items.
3. Workload ownership (tags, service catalogue).
4. Commitment coverage today and expiry dates.
5. Growth forecast and revenue/usage metric for unit economics.

## 5. Operating Procedure

1. **Make cost visible per owner** first: enforce a tagging standard (`owner`, `environment`, `service`, `cost-center`, `data-classification`), activate cost allocation tags, and split shared costs (network, observability, support) by a documented rule.
2. **Establish the baseline**: last 3 months by service, account, and tag; plus unit cost (₹ per 1,000 orders, per active user, per GB processed).
3. **Hunt waste in a fixed order** — idle, orphaned, oversized, over-replicated, over-retained:
   - Unattached EBS volumes, unused Elastic IPs, idle load balancers, old snapshots/AMIs.
   - Underutilized instances (p95 CPU < 10% and low memory) and over-provisioned node groups.
   - Non-production environments running 24/7 (schedule them off).
   - Log/metric retention longer than policy; debug logs at INFO in production.
   - Data transfer: cross-AZ chatter, NAT gateway processing, internet egress.
4. **Right-size with data**: use CloudWatch/vendor recommendations and 2–4 weeks of utilization, change in small steps, and verify SLOs after each change.
5. **Use the cheapest correct purchase option**: Spot for fault-tolerant batch, Savings Plans for steady baseline compute, Reserved Instances for steady databases; never commit to more than the proven baseline.
6. **Apply storage lifecycle policies**: S3/object storage tiering, snapshot retention, log retention by class, and deletion of temp data.
7. **Right-size non-production**: smaller instance classes, single-AZ where acceptable, scheduled shutdown outside working hours, and ephemeral preview environments that expire.
8. **Attribute savings to owners** in a monthly report with the change, the measured delta, and the residual risk accepted.
9. **Set guardrails so waste does not return**: budget alarms, anomaly detection, tag-on-create policies, quotas in non-prod, and periodic idle-resource reports.
10. **Track unit cost, not just total cost**: total spend can rise while unit economics improve — report both.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Cost visibility | AWS Cost Explorer, CUR + Athena, GCP Billing export + BigQuery, Azure Cost Management |
| Allocation | Cost allocation tags, account splitting, shared-cost split rules |
| Recommendations | Compute Optimizer, Trusted Advisor, GCP Recommender |
| Anomalies | AWS Cost Anomaly Detection, budgets with actions |
| Commitments | Savings Plans / RI purchase analysis, coverage and utilization reports |
| Scheduling | Instance Scheduler, Kubernetes CronJobs, cron + autoscaling to zero |
| Tag enforcement | SCPs denying create without tags, Config rules, `terraform` validation |
| Unit economics | CUR → warehouse → dashboard with a business metric |

## 7. Practical Implementation

**Tag policy enforced at the API (SCP) and in IaC:**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "RequireCostTagsOnCreate",
    "Effect": "Deny",
    "Action": ["ec2:RunInstances", "rds:CreateDBInstance", "s3:CreateBucket"],
    "Resource": "*",
    "Condition": {
      "Null": {
        "aws:RequestTag/owner": "true",
        "aws:RequestTag/cost-center": "true",
        "aws:RequestTag/environment": "true"
      }
    }
  }]
}
```

```hcl
# Provider default_tags: every resource gets the tags without repetition
provider "aws" {
  region = "ap-south-1"
  default_tags {
    tags = {
      owner         = "payments-platform"
      environment   = "prod"
      "cost-center" = "cc-4412"
      "managed-by"  = "terraform"
    }
  }
}
```

**Idle-resource audit (read-only; nothing deleted automatically):**

```bash
# Unattached EBS volumes
aws ec2 describe-volumes --filters Name=status,Values=available \
  --query 'Volumes[].[VolumeId,Size,CreateTime,Tags[?Key==`owner`].Value|[0]]' --output table

# Unassociated Elastic IPs (charged per hour)
aws ec2 describe-addresses --query 'Addresses[?AssociationId==null].[PublicIp,AllocationId]' --output table

# Idle load balancers: no requests in 14 days (check CloudWatch RequestCount)
aws cloudwatch get-metric-statistics --namespace AWS/ApplicationELB \
  --metric-name RequestCount --dimensions Name=LoadBalancer,Value=app/orders/50dc6c495c0c9188 \
  --start-time "$(date -u -d '-14 days' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
  --period 86400 --statistics Sum --query 'sort_by(Datapoints,&Timestamp)[].Sum'

# Snapshots older than retention policy
aws ec2 describe-snapshots --owner-ids self \
  --query "Snapshots[?StartTime<='$(date -u -d '-90 days' +%FT%TZ)'].[SnapshotId,VolumeSize,StartTime]" \
  --output table
```

**Right-sizing evidence before changing an instance:**

```text
orders-api on m6i.2xlarge (8 vCPU, 32 GiB), 90-day data:
  CPU p95 = 8%, p99 = 22%, memory p95 = 31%
  Decision: move to m6i.large (2 vCPU, 8 GiB) initially → m6i.xlarge if p95 CPU > 60%.
  Risk: peak-season burst; mitigate with autoscaling group min 2 / max 8 and a load test.
  Expected saving: ₹41,000/month per instance; 4 instances → ₹164,000/month.
```

**Savings Plan analysis before committing:**

```bash
# What is the steady-state baseline we can safely commit to?
aws ce get-savings-plans-purchase-recommendation \
  --savings-plans-type COMPUTE_SP --term-in-years ONE_YEAR \
  --payment-option NO_UPFRONT --lookback-period-in-days SIXTY_DAYS \
  --query 'SavingsPlansPurchaseRecommendation.SavingsPlansPurchaseRecommendationDetails[0].{
    hourlyCommitment: HourlyCommitmentToPurchase,
    estimatedMonthlySavings: EstimatedMonthlySavingsAmount,
    utilization: EstimatedAverageUtilization}'
```

```text
Rule: commit to no more than the p10 of the last 90 days of hourly on-demand spend,
in increments, starting with a 1-year no-upfront Compute Savings Plan.
A 3-year all-upfront commitment is only justified for a proven, flat baseline.
```

**Non-production scheduling (cut 65% of a 24/7 dev environment):**

```yaml
# Kubernetes CronJob that scales dev workloads to zero overnight
apiVersion: batch/v1
kind: CronJob
metadata: {name: scale-dev-down, namespace: dev}
spec:
  schedule: "0 20 * * 1-5"         # 20:00 IST weekdays
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: dev-scaler
          containers:
            - name: kubectl
              image: bitnami/kubectl:1.31
              command:
                - /bin/sh
                - -c
                - kubectl -n dev scale deploy --all --replicas=0
          restartPolicy: OnFailure
```

**Storage lifecycle (object storage + snapshots + logs):**

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    id     = "tier-and-expire"
    status = "Enabled"
    filter { prefix = "tenant/" }
    transition { days = 30  storage_class = "STANDARD_IA" }
    transition { days = 120 storage_class = "GLACIER_IR" }
    expiration { days = 2555 }              # 7 years, per records policy
    noncurrent_version_expiration { noncurrent_days = 90 }
  }
  rule {
    id = "expire-temp"
    status = "Enabled"
    filter { prefix = "tmp/" }
    expiration { days = 2 }
  }
}
```

```bash
# CloudWatch log retention: find groups with no retention (never expire)
aws logs describe-log-groups --query 'logGroups[?retentionInDays==null].[logGroupName,storedBytes]' --output table
aws logs put-retention-policy --log-group-name /aws/lambda/orders-worker --retention-in-days 30
```

**Cost anomaly detection with routing:**

```hcl
resource "aws_ce_anomaly_monitor" "service" {
  name              = "service-anomaly-monitor"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "alerts" {
  name      = "finops-alerts"
  frequency = "DAILY"
  monitor_arn_list = [aws_ce_anomaly_monitor.service.arn]
  subscriber { type = "EMAIL"; address = "finops@example.com" }
  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = ["50000"]        # ₹50,000 impact threshold
    }
  }
}
```

**Unit economics query (Athena over CUR, simplified):**

```sql
-- Cost per 1,000 orders, by month
WITH cost AS (
  SELECT date_trunc('month', line_item_usage_start_date) AS month,
         sum(line_item_unblended_cost) AS spend
  FROM cur
  WHERE line_item_product_code IN ('AmazonEC2','AmazonRDS','AmazonS3','AmazonEKS')
  GROUP BY 1
), business AS (
  SELECT date_trunc('month', created_at) AS month, count(*) AS orders
  FROM orders.orders WHERE status = 'paid' GROUP BY 1
)
SELECT c.month, round(c.spend, 0) AS spend, b.orders,
       round(c.spend / nullif(b.orders, 0) * 1000, 2) AS inr_per_1k_orders
FROM cost c JOIN business b USING (month)
ORDER BY c.month DESC;
```

## 8. Quality Standards

- 100% of spend is allocated to an owner (tagged or by account); untagged spend is tracked as a defect.
- Shared costs have a documented, stable split rule (proportional to usage or headcount), not ad-hoc.
- Waste audits run on a schedule and produce an owned list, not a report nobody reads.
- Every right-sizing change cites utilization data over ≥ 14 days and a rollback plan.
- Commitments never exceed the proven baseline; coverage and utilization are monitored monthly.
- Non-production schedules, storage lifecycle, and log retention are enforced by policy where possible.
- Unit cost is reported alongside total spend.
- Anomaly alerts route to an owner with a runbook.

## 9. Verification and Testing

- Compare month-over-month spend for the changed resource; savings must appear in the next bill.
- Run a load test after right-sizing to confirm SLOs hold at peak.
- Verify a scheduled shutdown by checking running instances during off-hours.
- Confirm tag-on-create denial by attempting to create an untagged resource in a sandbox.
- Check Savings Plan utilization (> 95%) and coverage; a utilization below 90% means over-commitment.
- Reconcile the CUR against business metrics monthly to catch attribution errors.

## 10. Security Considerations

- Do not remove logging, WAF, or backup retention to save money without an explicit risk decision — those costs are controls, not waste.
- Deletion is destructive: confirm ownership, verify backups, and use a change record. Never delete a resource you cannot identify.
- Cost dashboards expose service names and usage patterns; restrict access like other internal data.
- Billing export buckets contain account IDs and usage detail: encrypt and restrict.
- Tag values are user-controlled input in reporting — sanitize before rendering in dashboards.
- Commitment purchases are financial contracts: require approval and record terms.

## 11. Failure Handling

- **Savings appear then vanish:** a new untagged workload or non-prod back to 24/7 — fix enforcement, not just the resource.
- **Right-sizing caused latency regressions:** revert to the prior size and re-measure; the utilization window missed a peak.
- **Savings Plan under-utilized:** workloads moved off the covered family/region; adjust the plan mix at the next term and consider exchangeable Compute SPs.
- **Cost spike from data transfer:** cross-AZ or NAT traffic; use private endpoints, same-AZ placement where sensible, and compress payloads.
- **Nobody acts on the waste list:** assign each item an owner and a due date in the ticketing system; report only items that are owned.

## 12. Expected Deliverables

1. Cost-allocation and tagging standard with enforcement.
2. Baseline spend and unit-cost dashboard.
3. Waste inventory with owners and savings estimates.
4. Right-sizing decisions with utilization evidence.
5. Commitment strategy, coverage, and utilization tracking.
6. Lifecycle, retention, and non-prod scheduling policies.
7. Anomaly detection and monthly FinOps report.

## 13. References

- AWS Cost Explorer and CUR — https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html
- AWS Cost Anomaly Detection — https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html
- AWS Savings Plans — https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html
- AWS Compute Optimizer — https://docs.aws.amazon.com/compute-optimizer/latest/ug/what-is-compute-optimizer.html
- S3 lifecycle configuration — https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html
- FinOps Foundation framework — https://www.finops.org/framework/
- Google Cloud cost optimization — https://cloud.google.com/architecture/framework/cost-optimization
- CloudWatch Logs retention — https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html
