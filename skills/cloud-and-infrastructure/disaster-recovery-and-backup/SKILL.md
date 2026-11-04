---
name: disaster-recovery-and-backup
description: Plan and prove recovery—RTO/RPO targets, backup design with immutability, restore drills, failover runbooks, and data-integrity verification.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# Disaster Recovery and Backup

## 1. Purpose

Survive the loss of data, a region, or an account, and prove it before it happens. Disaster recovery fails in two ways: the backup was never tested (so it is not a backup), and the recovery plan exists only in someone's head. Ransomware and accidental deletion additionally require immutability and out-of-band access. This skill covers target-setting, backup architecture, restore drills, failover procedures, and the integrity checks that make recovery real.

**Scope:** systems you own. Restore drills consume resources and restore sensitive data into environments: use isolated accounts/projects, restrict access to restored data, and destroy it after verification. Never run destructive restore tests against production, and never delete backups without checking retention obligations.

## 2. Activation Conditions

- New critical service or datastore without a tested recovery path.
- Audit, compliance, or insurer request for DR evidence.
- Region/account-level dependency risk identified.
- Ransomware or insider-deletion risk assessment.
- Keywords: disaster recovery, backup, RTO, RPO, restore drill, failover, multi-region, immutable backup, object lock, cross-account, point-in-time recovery, PITR, business continuity, tabletop exercise.

## 3. When Not to Use

- Routine database administration (use sql-query-optimization / database-schema-design).
- High-availability design for a single AZ failure within one region (complementary but separate).
- Individual file restore requests (follow the restore procedure from this skill).

## 4. Required Context

1. Systems and their criticality tiers, with owners.
2. Business requirements: RTO (time to restore) and RPO (tolerable data loss) per tier.
3. Current backup configuration and where backups live.
4. Threat model: accidental deletion, ransomware, region outage, account compromise.
5. Compliance retention requirements and legal hold obligations.

## 5. Operating Procedure

1. **Set RTO/RPO per system tier with the business**, not by engineering preference. Tier 1 (money/identity): RTO 1 h, RPO 5 min. Tier 2: RTO 8 h, RPO 1 h. Tier 3: RTO 72 h, RPO 24 h.
2. **Design backups to satisfy RPO**: continuous WAL/binlog archiving for databases (PITR), scheduled snapshots for volumes and file stores, and object versioning for buckets.
3. **Make backups immutable and isolated**: object lock / WORM where available, a separate account (or project) with different credentials, and no delete permissions for the workload role.
4. **Encrypt backups** with keys the workload cannot delete; keep key custody separate from data access.
5. **Record what is NOT backed up** (caches, derived indexes, ephemeral queues) and how each is rebuilt.
6. **Write the restore procedure as a runbook** with exact commands, prerequisites, expected durations, and verification queries.
7. **Drill on a schedule**: quarterly for Tier 1, twice a year for Tier 2. A drill is restore-to-isolated-environment plus verification, executed by someone other than the author.
8. **Measure actual RTO/RPO in drills** and compare to targets; publish both, including misses.
9. **Verify integrity, not just existence**: row counts, checksums, referential constraints, application-level smoke tests against restored data.
10. **Plan failover for region loss** where Tier 1 demands it: warm standby with replicated data, DNS/global accelerator cutover, and a documented decision authority to invoke it.
11. **Test the whole chain**: credentials, DNS, KMS keys, IaC, and monitoring all restored, not just the database.
12. **Keep the plan accessible offline**: a copy of the runbook and contact tree outside the systems that may be down.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| DB PITR | RDS automated backups + PITR, Aurora backtrack, Postgres WAL-G/pgBackRest, MySQL binlog |
| Snapshots | EBS snapshots, AWS Backup with vault lock, GCP snapshot schedules |
| Object immutability | S3 Object Lock (compliance mode), versioning + MFA delete |
| Cross-account | AWS Backup cross-account copy, org-level policies |
| Replication | Aurora Global Database, Postgres logical/physical replication, DynamoDB global tables |
| IaC restore | Terraform/CloudFormation from version control, bootstrap runbook |
| Verification | `pg_restore --list`, checksums, `pg_dump --schema-only` diff, application smoke tests |
| Orchestration | AWS Elastic Disaster Recovery, Azure Site Recovery, custom runbooks |

## 7. Practical Implementation

**Tiered recovery objectives (the document that drives everything):**

```markdown
| Tier | Systems | RTO | RPO | Strategy | Drill cadence | Evidence |
|---|---|---|---|---|---|---|
| 1 | orders-db, auth, payments | 1 h | 5 min | PITR + cross-region replica + warm standby | quarterly | drill report, RTO measured |
| 2 | reporting-db, document store | 8 h | 1 h | PITR + cross-account backup copy | twice yearly | restore log |
| 3 | internal tools, dev data | 72 h | 24 h | nightly snapshot | annually | snapshot exists |
| n/a | caches, search indexes, queues | rebuild | rebuild | rebuild from source | — | rebuild runbook |
```

**Postgres PITR with WAL archiving to an immutable bucket (self-managed):**

```bash
# postgresql.conf
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /var/lib/pgbackrest/archive/%f && aws s3 cp %p s3://acme-db-archive/%f --sse aws:kms'
archive_timeout = 60s
```

```bash
# Base backup + retention via pgBackRest
pgbackrest --stanza=orders --type=full backup
pgbackrest --stanza=orders --type=incr backup
pgbackrest --stanza=orders info            # verify the archive chain is complete

# Restore to a point in time into an isolated instance
pgbackrest --stanza=orders --delta \
  --type=time --target="2026-11-04 09:47:00+00" \
  --target-action=promote restore
```

**RDS automated backups with PITR and cross-region copy:**

```hcl
resource "aws_db_instance" "orders" {
  identifier                  = "orders-prod"
  backup_retention_period     = 14            # PITR window
  backup_window               = "18:00-19:00"
  deletion_protection         = true
  copy_tags_to_snapshot       = true
  final_snapshot_identifier    = "orders-prod-final"
  storage_encrypted           = true
  kms_key_id                  = aws_kms_key.data.arn
  # Cross-region replica for regional failure
  replicate_source_db         = null
}

resource "aws_db_instance" "orders_replica_dr" {
  provider             = aws.dr_region
  identifier           = "orders-dr"
  replicate_source_db  = aws_db_instance.orders.arn
  instance_class       = "db.r7g.large"
  skip_final_snapshot  = false
}
```

**Cross-account, vault-locked backups (ransomware/deletion defense):**

```hcl
resource "aws_backup_vault" "primary" {
  name = "acme-backups-primary"
  kms_key_arn = aws_kms_key.backup.arn
}

resource "aws_backup_vault_lock_configuration" "primary" {
  backup_vault_name   = aws_backup_vault.primary.name
  changeable_for_days = 3                 # grace for mistakes, then immutable
  min_retention_days  = 30
  max_retention_days  = 365
}

resource "aws_backup_plan" "tier1" {
  name = "tier1-daily"

  rule {
    rule_name         = "daily-35d"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 18 * * ? *)"
    lifecycle { delete_after = 35 }
    copy_action {
      destination_vault_arn = "arn:aws:backup:ap-south-1:444455556666:vault/acme-backups-dr"
      lifecycle { delete_after = 365 }
    }
  }
}

resource "aws_backup_selection" "tier1" {
  name         = "tier1-resources"
  iam_role_arn = aws_iam_role.backup.arn
  plan_id      = aws_backup_plan.tier1.id
  resources    = ["arn:aws:rds:ap-south-1:111122223333:db:orders-prod"]
}
```

The workload role must **not** hold `backup:DeleteBackupVault` or `backup:DeleteRecoveryPoint` in the destination account — separation of duties is the control.

**S3 versioning + Object Lock for document stores:**

```hcl
resource "aws_s3_bucket" "documents" {
  bucket              = "acme-documents-prod"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_object_lock_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    default_retention {
      mode = "COMPLIANCE"          # cannot be shortened or deleted, even by root
      days = 30
    }
  }
}
```

**Restore runbook (database, written to be executed under pressure):**

```markdown
# Runbook: restore orders-db to a point in time

**Trigger:** data loss/corruption confirmed; incident commander approval recorded.
**Target RTO:** 1 h. **Never** restore in place over the production instance.

### 1. Preconditions (2 min)
- [ ] IC approval + incident ticket number
- [ ] Confirm the target timestamp (UTC) from logs; record the latest known-good event
- [ ] Identify the DR account: `111122223333` (prod), `444455556666` (dr)

### 2. Restore into an isolated instance (20–35 min)
```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier orders-prod \
  --target-db-instance-identifier orders-restore-$(date +%Y%m%d%H%M) \
  --restore-time 2026-11-04T09:47:00Z \
  --db-subnet-group-name restore-isolated \
  --vpc-security-group-ids sg-restore-only \
  --no-publicly-accessible --region ap-south-1
aws rds wait db-instance-available --db-instance-identifier <target>
```

### 3. Verify data integrity (10 min)
```sql
SELECT count(*) FROM "order" WHERE created_at > now() - interval '1 day';
SELECT sum(total_cents) FROM "order" WHERE status = 'paid' AND created_at::date = '2026-11-04';
SELECT count(*) FROM order_line l LEFT JOIN "order" o ON o.id = l.order_id WHERE o.id IS NULL; -- expect 0
```
- [ ] Counts within expected range (±0.5% of the pre-incident baseline)
- [ ] No orphan rows; foreign keys valid
- [ ] Application smoke test against the restored instance (read + write in a throwaway schema)

### 4. Cut over (15 min)
- [ ] Put the app in maintenance/read-only mode
- [ ] Repoint the application secret/DNS to the restored instance
- [ ] Run smoke tests; confirm error rate returns to baseline
- [ ] Notify stakeholders with the data-loss window (RPO actual)

### 5. Aftermath
- [ ] Delete the temporary restore instance after 7 days (retention policy)
- [ ] Record actual RTO/RPO in the incident ticket
- [ ] File follow-ups for any gap found during the restore
```

**Drill report template (the evidence auditors ask for):**

```markdown
# DR drill — orders-db — 2026-11-04
- Executed by: @arun (not the runbook author)
- Scenario: accidental deletion of `order_line` at 09:47 UTC; restore to 09:46
- Target: RTO 60 min / RPO 5 min
- Measured: RTO **52 min** (restore 31, verify 11, cutover 10); RPO **1 min** (last WAL 09:46:12)
- Result: PASS
- Issues found: (1) restore subnet lacked a KMS grant for the snapshot key — fixed same day;
  (2) runbook step 3 query referenced a dropped column — corrected.
- Follow-ups: add KMS grant to the restore role (done); re-drill 2027-02.
```

**Tabletop exercise scenario list (cheap, catches coordination gaps):**

```text
1. Primary region unavailable for 4 h; who declares, who decides to fail over?
2. Ransomware encrypted the primary account; are backups reachable with out-of-band credentials?
3. KMS key deleted by a departing engineer; can data be decrypted from the DR copy?
4. DNS provider outage: does the API resolve? Is there a secondary zone?
5. Restore works, but the app cannot start: is Terraform/Helm state available and are secrets recoverable?
```

## 8. Quality Standards

- Every Tier 1/2 system has documented RTO/RPO agreed with the business.
- Backups exist in a separate account/region with immutability (object lock/vault lock) and separate credentials.
- The workload identity cannot delete its own backups.
- Restore runbooks exist, are executable by someone other than the author, and include verification queries.
- Drills are executed on schedule and results (including failures) are recorded.
- Actual RTO/RPO is measured, not assumed, and reported against targets.
- Items not backed up are documented with their rebuild procedure.
- Encryption keys are recoverable independently of the systems they protect.
- The plan is available offline (not only in the systems that may be down).

## 9. Verification and Testing

- Restore a database to a point in time in an isolated environment and run integrity checks.
- Delete a file in a versioned bucket, then restore the prior version.
- Confirm a backup cannot be deleted by the workload role (`aws backup delete-recovery-point` → AccessDenied) and that object lock blocks version deletion.
- Time the full drill end to end with a stopwatch; compare with the RTO.
- Failover test: promote the cross-region replica in staging and measure cutover time and data loss.
- Verify key recovery: restore using only the DR account's credentials and keys.

## 10. Security Considerations

- Backups are a copy of all your sensitive data: encrypt at rest, restrict access, and apply the same classification rules.
- Ransomware targets backups first: immutability, separate accounts, and separate credentials are mandatory, not optional.
- Restored environments must not be internet-exposed; they contain production data at a point in time.
- Destroy temporary restore instances promptly after verification, per data-retention policy.
- KMS key deletion is irreversible; use a waiting period and ensure key policy allows DR-account recovery.
- Audit who can restore: restoring sensitive data into a lower-trust environment is an exfiltration path.
- Verify that backups do not include secrets in plaintext (Terraform state, `.env` files in volumes).

## 11. Failure Handling

- **Restore fails on a missing WAL segment:** the archive chain is broken; identify the gap and accept the RPO breach explicitly rather than restoring silently to an older point.
- **Restore takes longer than RTO:** volume size, IOPS, or wrong instance class; pre-provision restore capacity and test with production-sized data.
- **Backup job silently stopped:** alert on backup age, not just on job failure — "no successful backup in 26 h" is the alarm that matters.
- **Restored app cannot start:** credentials, secrets, migrations, or DNS are missing from the plan; the drill must exercise the whole chain.
- **Backup exceeds retention/cost budget:** tier retention by criticality and use cold storage classes for older copies.
- **Object lock blocking a legitimate delete:** compliance-mode locks cannot be shortened by design; use governance mode with documented exceptions if business rules require it.

## 12. Expected Deliverables

1. Tiered RTO/RPO matrix with business sign-off.
2. Backup configuration as code (schedules, retention, immutability, cross-account copy).
3. Rebuild procedures for non-backed-up systems.
4. Restore runbooks per Tier 1/2 system with verification queries.
5. Failover runbook with decision authority and communication plan.
6. Drill schedule, reports, and measured RTO/RPO.
7. Tabletop exercise notes and follow-ups.

## 13. References

- AWS Backup and Vault Lock — https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html
- RDS point-in-time recovery — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html
- S3 Object Lock — https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html
- pgBackRest — https://pgbackrest.org/
- WAL-G — https://github.com/wal-g/wal-g
- NIST SP 800-34 (Contingency Planning Guide) — https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final
- AWS Well-Architected — Reliability Pillar — https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html
- Google SRE Workbook, "Data Integrity: What You Read Is What You Wrote" — https://sre.google/workbook/data-integrity/
