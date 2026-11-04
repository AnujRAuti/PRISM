---
name: aws-engineering
description: Build on AWS with least-privilege IAM, private networking, encrypted stateful services, and guardrails that prevent the expensive mistakes.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# AWS Engineering

## 1. Purpose

Provision AWS infrastructure that is secure by default, cost-aware, and reproducible. The recurring AWS failures are known: `Action: "*"` IAM policies, public S3 buckets, security groups open to `0.0.0.0/0` on management ports, unencrypted volumes, no budget alarms, and resources created by hand that nobody can explain. This skill covers account structure, IAM, VPC design, stateful services, logging, and the guardrails that catch mistakes before they become incidents.

**Scope:** AWS accounts you own or administer. Every action in this skill creates billable resources and changes access control: require explicit authorization for anything touching production, never delete or modify resources you did not create without owner approval, and always work through IaC with reviewed plans rather than ad-hoc console changes. Never use root credentials; never store access keys in code.

## 2. Activation Conditions

- New account, environment, or service landing on AWS.
- Security review found IAM, network, or storage exposure.
- Cost surprises or untracked resources.
- Migrating from manual console work to IaC.
- Keywords: AWS, IAM, VPC, S3, RDS, ECS, EKS, Lambda, CloudTrail, GuardDuty, KMS, Organizations, SCP, budget alarm, least privilege, private subnet, VPC endpoint.

## 3. When Not to Use

- Multi-cloud abstraction design (use infrastructure-automation or a cloud-agnostic skill).
- Kubernetes workload design on EKS (use kubernetes-administration plus this for cloud primitives).
- Vendor/region selection research (use technical-research-reports).

## 4. Required Context

1. Account topology and Organizations structure.
2. Workload requirements: compute, storage, latency, compliance, region/residency.
3. Existing IaC tooling and state backend.
4. Security requirements: encryption, logging, retention, network isolation.
5. Budget and cost owners.

## 5. Operating Procedure

1. **Separate accounts by blast radius** (prod, staging, dev, security-log-archive) under AWS Organizations, with SCPs denying risky actions (`iam:CreateUser`, disabling CloudTrail, leaving the org).
2. **Never use the root user** for daily work: secure it with MFA, no access keys, and an alarmed break-glass procedure.
3. **Use IAM roles everywhere**: workload identity via IRSA/EKS Pod Identity, EC2 instance profiles, OIDC federation for CI, no long-lived access keys.
4. **Default-deny networks**: private subnets for workloads and data, public subnets only for load balancers/NAT, security groups referencing other security groups rather than CIDR where possible.
5. **Keep data services private**: RDS/ElastiCache/OpenSearch in private subnets with `publicly_accessible = false`, encrypted, with automated backups and deletion protection in production.
6. **Encrypt with customer-managed KMS keys** where key rotation, separation of duties, or cross-account access matters; enable S3 default encryption and block public access at the account level.
7. **Use VPC endpoints** (gateway for S3/DynamoDB, interface for others) so traffic to AWS APIs never traverses the internet.
8. **Turn on the security baseline**: CloudTrail organization trail to a locked archive account, GuardDuty, Security Hub, Config rules, and VPC flow logs to a central bucket.
9. **Everything through IaC** with remote state (S3 + DynamoDB lock or native locking), plan review, and drift detection.
10. **Tag everything** (`owner`, `environment`, `cost-center`, `data-classification`) and enforce with SCPs/Config rules.
11. **Set budget alarms** with forecasted thresholds and anomaly detection before the first workload ships.
12. **Define a deletion policy**: protect stateful resources, prefer snapshot-before-delete, and require approval for destroying data stores.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| IaC | Terraform/OpenTofu, AWS CDK, CloudFormation, Pulumi |
| Identity | IAM Identity Center (SSO), roles, OIDC for GitHub Actions |
| Network | VPC, subnets, route tables, NAT gateway, VPC endpoints, Transit Gateway |
| Compute | ECS Fargate, EKS, Lambda, EC2 Auto Scaling |
| Data | RDS/Aurora, DynamoDB, S3, ElastiCache, OpenSearch |
| Security | KMS, Secrets Manager, GuardDuty, Security Hub, Config, CloudTrail, IAM Access Analyzer |
| Cost | Budgets, Cost Anomaly Detection, Cost Explorer, Savings Plans |
| Policy testing | `iam-policy-simulator`, `policy_sentry`, `checkov`, `tfsec`/`trivy` |

## 7. Practical Implementation

**Account guardrails with SCPs (deny dangerous actions):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyRootUserActions",
      "Effect": "Deny",
      "Action": "*",
      "Resource": "*",
      "Condition": {"StringLike": {"aws:PrincipalArn": "arn:aws:iam::*:root"}}
    },
    {
      "Sid": "DenyDisablingSecurityServices",
      "Effect": "Deny",
      "Action": [
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail",
        "guardduty:DeleteDetector",
        "securityhub:DisableSecurityHub",
        "config:DeleteConfigurationRecorder"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyLeavingOrganization",
      "Effect": "Deny",
      "Action": "organizations:LeaveOrganization",
      "Resource": "*"
    }
  ]
}
```

**Least-privilege workload role (scoped to a bucket prefix and a KMS key):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadWriteOrdersPrefix",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::acme-documents-prod/tenant/*"
    },
    {
      "Sid": "ListBucketScoped",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::acme-documents-prod",
      "Condition": {"StringLike": {"s3:prefix": ["tenant/*"]}}
    },
    {
      "Sid": "UseDocumentsKey",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:ap-south-1:111122223333:key/9f2c...",
      "Condition": {"StringEquals": {"kms:ViaService": "s3.ap-south-1.amazonaws.com"}}
    }
  ]
}
```

**CI to AWS without static keys (GitHub Actions OIDC):**

```yaml
permissions:
  id-token: write
  contents: read

- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::111122223333:role/gh-deploy-orders
    role-session-name: gh-${{ github.run_id }}
    aws-region: ap-south-1
```

Trust policy pinned to the repository and branch:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": "repo:acme/orders:ref:refs/heads/main"}
    }
  }]
}
```

**Terraform: private RDS with encryption, backups, and deletion protection:**

```hcl
resource "aws_db_instance" "orders" {
  identifier                      = "orders-prod"
  engine                          = "postgres"
  engine_version                  = "16.4"
  instance_class                  = "db.r7g.large"
  allocated_storage               = 200
  max_allocated_storage           = 1000

  db_name                         = "orders"
  username                        = "app"
  manage_master_user_password     = true          # password in Secrets Manager, auto-rotated

  db_subnet_group_name            = aws_db_subnet_group.private.name
  vpc_security_group_ids          = [aws_security_group.db.id]
  publicly_accessible             = false

  storage_encrypted               = true
  kms_key_id                      = aws_kms_key.data.arn
  backup_retention_period         = 14
  backup_window                   = "18:00-19:00"
  maintenance_window              = "sun:19:00-sun:20:00"
  copy_tags_to_snapshot           = true
  deletion_protection             = true
  skip_final_snapshot             = false
  final_snapshot_identifier       = "orders-prod-final"

  performance_insights_enabled    = true
  monitoring_interval             = 30

  tags = {
    owner               = "payments-platform"
    environment         = "prod"
    "data-classification" = "confidential"
  }
}
```

**Private subnet networking with endpoints (no internet egress for data):**

```hcl
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.ap-south-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = ["s3:GetObject", "s3:PutObject"]
      Resource  = "arn:aws:s3:::acme-documents-prod/*"
      Condition = {"StringEquals" : {"aws:PrincipalOrgID" : "o-example123"}}
    }]
  })
}

resource "aws_security_group" "db" {
  name   = "orders-db"
  vpc_id = aws_vpc.main.id
  # ingress only from the app security group, never from a CIDR
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  egress { from_port = 0; to_port = 0; protocol = "-1"; cidr_blocks = [] }
}
```

**S3 bucket hardened (public access blocked, encrypted, versioned, TLS-only):**

```hcl
resource "aws_s3_bucket" "documents" { bucket = "acme-documents-prod" }

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_policy" "documents_tls_only" {
  bucket = aws_s3_bucket.documents.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = ["${aws_s3_bucket.documents.arn}", "${aws_s3_bucket.documents.arn}/*"]
      Condition = {"Bool" : {"aws:SecureTransport" : "false"}}
    }]
  })
}
```

**Security baseline and logging:**

```hcl
resource "aws_cloudtrail" "org" {
  name                          = "org-trail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail.id
  is_organization_trail         = true
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true
  kms_key_id                    = aws_kms_key.logs.arn
}

resource "aws_guardduty_detector" "main" { enable = true }
resource "aws_securityhub_account" "main" {}
```

**Budget alarm with forecast and anomaly detection:**

```hcl
resource "aws_budgets_budget" "monthly" {
  name         = "acme-monthly-total"
  budget_type  = "COST"
  limit_amount = "500000"
  limit_unit   = "INR"
  time_unit    = "MONTHLY"

  cost_filter { name = "TagKeyValue"; values = ["user:environment$prod"] }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = ["finops@example.com"]
  }
}
```

**Policy validation before merge:**

```bash
checkov -d . --framework terraform --compact
trivy config .
terraform validate && tflint
# Verify what a principal can actually do (simulate, do not guess)
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::111122223333:role/orders-api \
  --action-names s3:PutObject kms:Decrypt \
  --resource-arns arn:aws:s3:::acme-documents-prod/tenant/42/inv.pdf
```

## 8. Quality Standards

- No long-lived IAM access keys; workloads and CI assume roles.
- No `Action: "*"` on `Resource: "*"` in workload policies; permissions scoped to ARNs and conditions.
- Root user MFA-locked with no access keys and an alarm on root sign-in.
- Workload and data subnets are private; databases not publicly accessible; management ports never open to `0.0.0.0/0`.
- Encryption at rest with KMS on all data stores; TLS enforced on all buckets and endpoints.
- CloudTrail (org, multi-region), GuardDuty, Security Hub, and Config enabled in every account.
- All infrastructure is IaC with remote state, locking, and reviewed plans; no console-created production resources.
- Every resource carries `owner`, `environment`, `cost-center`, and `data-classification` tags.
- Budget and anomaly alarms exist before workloads go live.
- Deletion protection and final snapshots on production data stores.

## 9. Verification and Testing

- `aws iam simulate-principal-policy` for the workload's critical actions (allowed and denied cases).
- IAM Access Analyzer findings reviewed; unused permissions removed (`GenerateServiceLastAccessedDetails`).
- `checkov`/`trivy config` clean of high/critical findings in CI.
- Anonymous access test against every S3 bucket (`curl` a presigned-less object URL → `403`).
- Confirm no security group allows `0.0.0.0/0` on 22/3389/5432 and that flow logs are arriving.
- Restore test: snapshot → restore into an isolated account/VPC and verify data.
- Budget alarm test: lower the threshold in a sandbox and confirm notification delivery.

## 10. Security Considerations

- Treat the AWS account as a trust boundary: cross-account access only via roles with explicit external IDs and scoped trust policies.
- Never store secrets in user data scripts, Lambda env vars in plaintext, or Terraform state without encryption; use Secrets Manager/SSM with rotation.
- Terraform state contains sensitive values: encrypt the S3 backend, restrict access, and enable versioning + access logging.
- Enable MFA delete or Object Lock on the log archive bucket; logs are evidence and must be tamper-evident.
- Guard against SSRF to instance metadata: enforce IMDSv2 (`http_tokens = "required"`) and limit hop limit to 1.
- Public IPs on instances and open ingress are attack surface; prefer load balancers and private workloads.
- Least privilege applies to humans too: use IAM Identity Center with short-lived sessions and permission sets, not shared users.
- Deleting a KMS key is irreversible — require a waiting period (7–30 days) and an approval record.

## 11. Failure Handling

- **Destroy blocked by deletion protection or non-empty bucket:** expected — remove protection and empty the bucket deliberately with approval, after confirming backups.
- **Terraform state lock stuck:** identify the lock owner from the DynamoDB entry; never force-unlock without confirming no apply is running.
- **Cost spike:** check Cost Anomaly Detection and CloudTrail for the creating principal, then tag and stop the resource; add a budget action if recurring.
- **Access denied after a policy change:** use IAM Policy Simulator and CloudTrail `AccessDenied` events to find the missing action or condition before broadening anything.
- **Region capacity errors:** retry in another AZ, request quota increases early, and avoid hard-coding instance types that are capacity-constrained.

## 12. Expected Deliverables

1. Account topology and SCP guardrails.
2. IAM role inventory with trust and permission policies.
3. VPC/subnet/endpoint design and security group rules.
4. Encrypted stateful services with backup and retention configuration.
5. Security baseline (CloudTrail, GuardDuty, Security Hub, Config, flow logs).
6. Tagging standard and SCP/Config enforcement.
7. Budget alarms and cost allocation.
8. Policy validation and restore-test evidence.

## 13. References

- AWS IAM best practices — https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
- AWS Well-Architected Framework — https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html
- AWS security best practices (Organizations, SCPs) — https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html
- VPC endpoints — https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html
- S3 Block Public Access — https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html
- IMDSv2 — https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html
- GuardDuty — https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html
- AWS Budgets — https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html
- Terraform AWS provider — https://registry.terraform.io/providers/hashicorp/aws/latest/docs
