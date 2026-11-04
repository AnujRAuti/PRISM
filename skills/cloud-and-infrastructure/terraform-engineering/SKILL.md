---
name: terraform-engineering
description: Manage infrastructure as code with Terraform/OpenTofu—module design, remote state and locking, plan review, drift detection, and safe apply discipline.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# Terraform Engineering

## 1. Purpose

Make infrastructure changes reviewable, reproducible, and recoverable. Terraform's power is also its danger: a plan can delete a database, a state file can leak every secret in the account, and a manually changed resource can silently drift until an apply "fixes" it by destroying data. This skill covers module boundaries, state isolation, plan review discipline, provider and secret hygiene, drift management, and import/migration procedures.

**Scope:** infrastructure you own. `terraform apply` and `destroy` change real systems: require an approved plan for production, never apply a plan you did not read, protect stateful resources from destruction, and never `terraform state rm` or `force-unlock` without confirming no other process is running.

## 2. Activation Conditions

- New infrastructure or a migration from manual provisioning.
- Shared state problems, lock contention, or state in git.
- Plans that are huge, unreviewable, or unexpectedly destructive.
- Drift between code and reality.
- Keywords: Terraform, OpenTofu, state, backend, remote state, locking, modules, plan, apply, drift, import, moved blocks, workspaces, provider, tflint, checkov, Terragrunt, Atlantis.

## 3. When Not to Use

- Application deployment inside a cluster (use kubernetes-administration / cicd-pipeline-engineering).
- One-off local scripts.
- Provider-specific deep configuration (use aws-engineering etc. for what to provision).

## 4. Required Context

1. Cloud/provider(s) and account/region topology.
2. State backend options available (S3 + lock, GCS, Terraform Cloud).
3. Team workflow: PR-based applies or local applies.
4. Existing modules and naming conventions.
5. Change cadence and who approves production changes.

## 5. Operating Procedure

1. **Separate state by blast radius, not by convenience**: one state per account/environment/component (e.g. `prod/network`, `prod/data`, `prod/app`). A single state for everything makes every change risky.
2. **Use a remote backend with locking and encryption**; never commit state or plan files. Enable versioning on the state bucket for recovery.
3. **Pin versions**: Terraform/OpenTofu version, provider versions, and module sources with refs; commit the lock file.
4. **Design modules around a purpose, with narrow inputs**: required variables explicit, no account IDs or environment names hard-coded inside, and outputs only what consumers need.
5. **Review plans as code**: CI posts the plan; reviewers check for `destroy`/`replace` on stateful resources, unexpected changes to unrelated resources, and count diffs.
6. **Protect stateful resources** with `lifecycle { prevent_destroy = true }`, deletion protection in the provider, and `ignore_changes` only with a documented reason.
7. **Apply only from CI** in a controlled job with the same version, backend, and credentials — not from laptops.
8. **Never edit state by hand**: use `terraform import`, `moved` blocks for refactors, `state mv` only with a plan showing no destruction.
9. **Detect drift on a schedule** (`terraform plan -detailed-exitcode` in a nightly job) and reconcile deliberately.
10. **Scan for misconfiguration in CI** (`tflint`, `checkov`, `trivy config`) and block high-severity findings.
11. **Document rollback**: for each change, know whether reverting the code restores the prior state and what data changes are irreversible.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Engines | Terraform (≥1.6), OpenTofu |
| Backends | S3 + DynamoDB (or `use_lockfile`), GCS, Azure Blob, Terraform Cloud |
| Module sources | Registry, git refs, local paths |
| Plan automation | Atlantis, Spacelift, env0, GitHub Actions + `terraform-plan` comment |
| Lint/scan | `terraform fmt -check`, `tflint`, `checkov`, `trivy config`, `terraform validate` |
| Testing | `terraform test` (native), Terratest, `kitchen-terraform` |
| Drift | scheduled `plan -detailed-exitcode`, CloudQuery/Config comparison |
| Refactoring | `moved` blocks, `import` blocks (1.5+), `removed` blocks (1.7+) |

## 7. Practical Implementation

**Remote backend with locking and versioning:**

```hcl
terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
  backend "s3" {
    bucket         = "acme-tfstate-prod"
    key            = "prod/data/terraform.tfstate"
    region         = "ap-south-1"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:ap-south-1:111122223333:key/..."
    dynamodb_table = "acme-tfstate-locks"     # or use_lockfile = true on 1.10+
  }
}
```

```hcl
# S3 backend bucket hardening (bootstrap stack, applied once by a human)
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

**Module with a narrow interface:**

```hcl
# modules/service-bucket/variables.tf
variable "name" {
  type        = string
  description = "Bucket base name; environment suffix is appended by the caller."
}

variable "environment" {
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "kms_key_arn" {
  type        = string
  description = "CMK used for SSE-KMS; must be in the same region as the bucket."
}

variable "force_destroy" {
  type        = bool
  default     = false
  description = "Allow destruction of non-empty buckets. Only for ephemeral environments."
}
```

```hcl
# modules/service-bucket/main.tf
resource "aws_s3_bucket" "this" {
  bucket        = "${var.name}-${var.environment}"
  force_destroy = var.force_destroy

  # Production data must never be destroyed by a plan
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
  }
}

output "bucket" { value = aws_s3_bucket.this.bucket }
output "arn"    { value = aws_s3_bucket.this.arn }
```

**Composition root per environment:**

```hcl
# environments/prod/data/main.tf
locals {
  environment = "prod"
  tags = {
    environment         = local.environment
    owner               = "payments-platform"
    "cost-center"       = "cc-4412"
    "data-classification" = "confidential"
  }
}

module "documents_bucket" {
  source      = "../../../modules/service-bucket"
  name        = "acme-documents"
  environment = local.environment
  kms_key_arn = module.kms.data_key_arn
}

module "orders_db" {
  source              = "../../../modules/postgres"
  identifier          = "orders-${local.environment}"
  instance_class      = "db.r7g.large"
  subnet_group        = data.terraform_remote_state.network.outputs.db_subnet_group
  deletion_protection = true
  backup_retention    = 14
}
```

**Refactor without destroying (moved block):**

```hcl
# Before: inline bucket named "orders_docs" in root module
# After: resource moved into module.documents; tell Terraform instead of recreating it
moved {
  from = aws_s3_bucket.orders_docs
  to   = module.documents_bucket.aws_s3_bucket.this
}
```

**Adopt existing resources with import blocks (1.5+), reviewable in a plan:**

```hcl
import {
  to = module.orders_db.aws_db_instance.this
  id = "orders-prod"
}
```

```bash
terraform plan -generate-config-out=generated.tf   # then edit and commit; never apply blindly
```

**CI: plan on PR, apply on merge, with a readable summary:**

```yaml
- run: terraform fmt -check -recursive
- run: terraform init -input=false
- run: terraform validate
- run: tflint --recursive
- run: checkov -d . --framework terraform --soft-fail-on LOW --compact
- id: plan
  run: |
    set +e
    terraform plan -input=false -lock-timeout=5m -out=tfplan -detailed-exitcode
    code=$?
    set -e
    [ $code -eq 0 ] && echo "changed=false" >> "$GITHUB_OUTPUT"
    [ $code -eq 2 ] && echo "changed=true"  >> "$GITHUB_OUTPUT"
    [ $code -eq 1 ] && exit 1
- run: terraform show -no-color tfplan > plan.txt   # posted to the PR for review
```

```yaml
# Separate apply job, gated by environment approval, applying the exact saved plan
- run: terraform apply -input=false -auto-approve tfplan
  environment: production        # requires reviewer approval in GitHub
```

**Destructive-change guard before apply:**

```bash
terraform show -json tfplan > plan.json
python3 - <<'PY'
import json, sys

plan = json.load(open("plan.json"))
dangerous = []
for rc in plan.get("resource_changes", []):
    actions = rc["change"]["actions"]
    if "delete" in actions and rc["type"] in {"aws_db_instance", "aws_s3_bucket",
                                              "aws_kms_key", "aws_dynamodb_table",
                                              "aws_elasticache_cluster"}:
        dangerous.append(f'{rc["address"]}: {actions}')

print("BLOCKED: destructive change to stateful resources" if dangerous else "no stateful deletions")
for d in dangerous:
    print(" -", d)
sys.exit(1 if dangerous else 0)
PY
```

**Nightly drift detection:**

```bash
terraform plan -detailed-exitcode -lock=false -refresh=true >/dev/null 2>&1
case $? in
  0) echo "no drift" ;;
  2) echo "DRIFT DETECTED — posting to #platform-alerts" ;;
  *) echo "plan error — investigate"; exit 1 ;;
esac
```

**State operations with a safety check:**

```bash
terraform state list | grep aws_db_instance        # confirm the address first
terraform plan -refresh-only                       # understand reality before touching state
# Prefer code-level refactors:
#   moved { ... }   for renames
#   removed { ... } for dropping a resource from state without destroying it
```

**Native tests for modules (`terraform test`):**

```hcl
# modules/service-bucket/tests/bucket.tftest.hcl
run "encrypts_with_cmk" {
  command = plan
  variables {
    name        = "test-docs"
    environment = "dev"
    kms_key_arn = "arn:aws:kms:ap-south-1:111122223333:key/test"
  }
  assert {
    condition     = aws_s3_bucket_server_side_encryption_configuration.this.rule[0].apply_server_side_encryption_by_default[0].kms_master_key_id == var.kms_key_arn
    error_message = "Bucket must use the caller-provided CMK."
  }
}
```

## 8. Quality Standards

- State is remote, encrypted, versioned, and locked; never committed, never edited by hand.
- One state per blast radius (account/environment/component).
- Engine, providers, and modules are version-pinned; lock file committed.
- Production applies run only from CI against a reviewed, saved plan.
- Stateful resources carry `prevent_destroy` and provider-level deletion protection.
- Modules have typed inputs with validation, no hard-coded environment values, and documented outputs.
- CI blocks high-severity findings and destructive plans to stateful resources.
- Drift is detected on a schedule and reconciled explicitly.
- Every irreversible change states its rollback path in the PR.

## 9. Verification and Testing

- `terraform validate`, `fmt -check`, `tflint`, `checkov` pass in CI.
- `terraform test` or Terratest covers module invariants (encryption, tagging, networking).
- Apply the same configuration twice: the second plan is empty (idempotence).
- Destroy in an ephemeral environment to verify `prevent_destroy` blocks production-shaped resources appropriately.
- Restore state from an object version in a sandbox to confirm the recovery path works.
- Import test: adopt an existing resource in staging with `import` and confirm a no-op plan afterward.

## 10. Security Considerations

- State files contain secrets and full resource definitions: restrict bucket access, enable access logging, and prefer providers that write secrets to Secrets Manager instead of state.
- `sensitive = true` hides values in output but not in state — plan for that.
- Provider credentials in CI must be OIDC-assumed roles, not long-lived keys; scope the role to the resources the stack manages.
- PR-triggered plans from forks must not receive production credentials; require review or restrict to internal branches.
- Scan for public buckets, open security groups, and unencrypted volumes before they exist, not after.
- Never `terraform destroy` a production state without an approved maintenance window and verified backups.
- Third-party modules execute with your credentials: pin to a commit/tag and review before adopting.

## 11. Failure Handling

- **State lock held:** find the lock owner in DynamoDB; confirm no apply is running before `force-unlock`.
- **Plan wants to replace a database:** a change touched an immutable attribute; use `create_before_destroy` where supported or a deliberate migration path, never apply blind.
- **Drift keeps reappearing:** something else manages the resource (console, autoscaler, another stack). Move ownership explicitly rather than fighting it with `ignore_changes`.
- **Partial apply failure:** the state reflects what succeeded; fix the root cause and re-apply. Never manually create the missing resource.
- **`prevent_destroy` blocks a legitimate removal:** remove the lifecycle block in a reviewed PR with a documented reason, then destroy.
- **Provider version bump breaks the plan:** pin back, read the upgrade guide, and migrate in an isolated environment first.

## 12. Expected Deliverables

1. Repository layout with per-scope state and module structure.
2. Backend bootstrap stack (bucket, locking, encryption) with restricted access.
3. Module interfaces with validation and tests.
4. CI pipeline: fmt/validate/lint/scan/plan post/apply gate.
5. Destructive-change guard for stateful resources.
6. Drift detection job and reconciliation runbook.
7. Import/move/refactor procedures and rollback notes.

## 13. References

- Terraform documentation — https://developer.hashicorp.com/terraform/docs
- OpenTofu documentation — https://opentofu.org/docs/
- S3 backend configuration — https://developer.hashicorp.com/terraform/language/backend/s3
- `moved` blocks — https://developer.hashicorp.com/terraform/language/modules/develop/refactoring
- `import` blocks — https://developer.hashicorp.com/terraform/language/import
- `terraform test` — https://developer.hashicorp.com/terraform/language/tests
- tflint — https://github.com/terraform-linters/tflint
- checkov — https://www.checkov.io/
- Atlantis — https://www.runatlantis.io/
- Terraform state management docs — https://developer.hashicorp.com/terraform/language/state
