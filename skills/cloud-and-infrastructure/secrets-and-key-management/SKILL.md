---
name: secrets-and-key-management
description: Manage secrets and encryption keys end to end—secret stores, workload identity, rotation without downtime, KMS key policy, and leak response.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: high
---

# Secrets and Key Management

## 1. Purpose

Keep credentials and keys out of code, logs, and chat, and make rotation routine rather than an incident. Secret management fails through three patterns: secrets spread into environment variables, CI variables, config files, and wikis; long-lived static credentials that are never rotated; and encryption keys whose policies grant more access than the data they protect. This skill covers secret stores, dynamic credentials, rotation, KMS design, and what to do when a secret leaks.

**Scope:** secrets for systems you own. Every action here involves access to production credentials or keys: never print a secret value, never copy production secrets into lower environments, never disable encryption or audit logging "temporarily", and require explicit authorization before rotating a shared credential or changing a KMS key policy (both can cause outages).

## 2. Activation Conditions

- Credentials in code, config, CI variables, or chat.
- No rotation process, or rotation requires an outage.
- Introducing a new database, third-party API, or encryption requirement.
- Suspected or confirmed secret exposure.
- Keywords: secrets manager, Vault, KMS, envelope encryption, key policy, rotation, dynamic credentials, IAM role, workload identity, OIDC, sealed secrets, SOPS, secret scanning, leak response.

## 3. When Not to Use

- Application-level password hashing (use authentication-and-session-management).
- Authorization policy design (use authorization-and-permissions).
- TLS certificate issuance mechanics (covered briefly here; use provider tooling).

## 4. Required Context

1. Inventory of secret types: database credentials, API keys, signing keys, TLS keys, encryption keys.
2. Where each is consumed (services, CI, humans).
3. Cloud provider and available secret/KMS services.
4. Rotation constraints (does the dependency support two valid credentials?).
5. Compliance requirements (key custody, HSM, audit retention).

## 5. Operating Procedure

1. **Inventory and classify first**: list every secret, its owner, consumers, storage location, creation date, and rotation feasibility. You cannot rotate what you cannot find.
2. **Choose the right mechanism per credential type**:
   - Cloud-to-cloud / CI-to-cloud: IAM roles via OIDC — no secret at all.
   - Service-to-database: dynamic credentials from a secret engine (Vault database engine) or managed rotation.
   - Third-party API keys: secret store with rotation + versioning.
   - Encryption: KMS with envelope encryption, never a key in config.
3. **Centralize in a secret manager** with audit logging, versioning, and least-privilege access policies scoped per path.
4. **Inject at runtime, never at build time**: fetch into memory at startup or per use; never bake into images, artifacts, or IaC state.
5. **Design rotation for zero downtime**: two active credentials during transition (or a store that serves "current" and "previous"), consumers reload on change, and a rollback path.
6. **Automate rotation**: 30–90 days for database passwords and API keys; short-lived (minutes–hours) for dynamic credentials; immediate on suspicion.
7. **Use workload identity**: Kubernetes ServiceAccount → cloud role (IRSA/Pod Identity), CI OIDC → cloud role, no static keys in environment variables.
8. **Design KMS key hierarchy**: separate keys per data classification/environment, key policies that grant least privilege, automatic rotation enabled, and `kms:ViaService` conditions.
9. **Prevent leaks structurally**: secret scanning in pre-commit and CI, push protection enabled, deny plaintext secrets in PRs, and log redaction.
10. **Prepare the leak-response runbook** before you need it: revoke → rotate → audit access → notify → validate.
11. **Audit continuously**: alert on secret reads in unusual contexts, on access from unexpected principals, and on keys/policies changes.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Secret stores | AWS Secrets Manager, GCP Secret Manager, Azure Key Vault, HashiCorp Vault, Infisical |
| Dynamic credentials | Vault database/AWS engines, AWS IAM Roles Anywhere |
| Workload identity | EKS Pod Identity / IRSA, GKE Workload Identity, GitHub OIDC |
| Encryption | AWS KMS, GCP KMS, Vault Transit, `age`/SOPS for git-stored config |
| Kubernetes | External Secrets Operator, Secrets Store CSI driver, Sealed Secrets |
| Scanning | gitleaks, trufflehog, GitHub secret scanning + push protection, `detect-secrets` |
| Rotation | Secrets Manager rotation Lambdas, Vault rotation, custom jobs |
| Audit | CloudTrail data events, Vault audit devices, KMS grants audit |

## 7. Practical Implementation

**No secret at all: OIDC workload identity (CI → cloud):**

```yaml
# GitHub Actions: assume a role, no stored credentials
permissions: {id-token: write, contents: read}
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::111122223333:role/gh-orders-deploy
      aws-region: ap-south-1
```

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": "repo:acme/orders:environment:production"}
    }
  }]
}
```

**Runtime retrieval with caching and no logging of values:**

```python
import json, logging, os, time
import boto3
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)
_client = boto3.client("secretsmanager")
_cache: dict[str, tuple[dict, float]] = {}
_TTL = 300.0

def get_secret(name: str) -> dict:
    now = time.monotonic()
    cached = _cache.get(name)
    if cached and now - cached[1] < _TTL:
        return cached[0]
    try:
        raw = _client.get_secret_value(SecretId=name)["SecretString"]
    except ClientError as exc:
        log.error("secret.fetch_failed", extra={"secret": name, "code": exc.response["Error"]["Code"]})
        raise
    value = json.loads(raw)
    _cache[name] = (value, now)
    # never log value, keys of the dict are safe
    log.info("secret.fetched", extra={"secret": name, "fields": sorted(value)})
    return value
```

**Least-privilege secret access policy (path-scoped, environment-tagged):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-south-1:111122223333:secret:prod/orders/db-*",
      "Condition": {
        "StringEquals": {"aws:PrincipalTag/team": "payments"}
      }
    }
  ]
}
```

**Zero-downtime rotation with two-phase credentials:**

```python
"""Rotate a database password without dropping connections.

Phase 1: create a new password, store as AWSPENDING, apply to the database user
         (both old and new work only if the DB supports two passwords; otherwise
         create a new user and migrate).
Phase 2: store as AWSCURRENT; consumers re-read on TTL or on a rotation event.
Phase 3: invalidate AWSPREVIOUS after the consumer TTL has passed.
"""
import boto3, psycopg

sm = boto3.client("secretsmanager")

def rotate(secret_id: str, new_password: str) -> None:
    token = sm.get_secret_value(SecretId=secret_id, VersionStage="AWSPENDING")
    pending = token["SecretString"]

    # Apply the pending credential to the database (idempotent)
    with psycopg.connect(current_admin_dsn()) as conn:
        conn.execute("ALTER ROLE app WITH PASSWORD %s", (pending,))

    sm.update_secret_version_stage(
        SecretId=secret_id, VersionStage="AWSCURRENT",
        MoveToVersionId=token["VersionId"], RemoveFromVersionId=None,
    )
    # Consumers with a 5-minute cache continue using the old value until it expires.
```

```hcl
resource "aws_secretsmanager_secret_rotation" "orders_db" {
  secret_id           = aws_secretsmanager_secret.orders_db.id
  rotation_lambda_arn = aws_lambda_function.rotate_orders_db.arn
  rotation_rules { automatically_after_days = 30 }
}
```

**External Secrets Operator (Kubernetes, store-backed, no values in git):**

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata: {name: orders-db, namespace: payments}
spec:
  refreshInterval: 5m            # picks up rotation without a restart
  secretStoreRef: {name: aws-secretsmanager, kind: ClusterSecretStore}
  target: {name: orders-db, creationPolicy: Owner}
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: prod/orders/db
        property: url
```

**KMS key with a strict key policy and rotation:**

```hcl
resource "aws_kms_key" "data" {
  description             = "Envelope key for orders data (prod)"
  enable_key_rotation     = true          # annual automatic rotation
  deletion_window_in_days = 30           # never 7 without an explicit decision
  multi_region            = false

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "KeyAdmins"
        Effect    = "Allow"
        Principal = {"AWS" : "arn:aws:iam::111122223333:role/kms-admin"}
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "WorkloadUseViaServices"
        Effect    = "Allow"
        Principal = {"AWS" : "arn:aws:iam::111122223333:role/orders-api"}
        Action    = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource  = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = ["s3.ap-south-1.amazonaws.com", "rds.ap-south-1.amazonaws.com"]
          }
        }
      },
      {
        Sid       = "DenyKeyDeletionToNonAdmins"
        Effect    = "Deny"
        Principal = "*"
        Action    = ["kms:ScheduleKeyDeletion", "kms:DisableKey"]
        Resource  = "*"
        Condition = {"StringNotEquals" : {"aws:PrincipalArn" : "arn:aws:iam::111122223333:role/kms-admin"}}
      }
    ]
  })
}
```

Note: key administrators must not be the same principals who can read the data — that separation is the point of customer-managed keys.

**Leak prevention in the toolchain:**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]
```

```bash
gitleaks detect --source . --redact --no-banner          # history scan
gitleaks protect --staged --redact                        # pre-commit
```

Enable GitHub push protection so a detected secret is blocked before it is ever committed.

**Leak response runbook (execute within minutes, not days):**

```markdown
# Runbook: exposed credential

1. **Contain (5 min)** — revoke the credential at the source (rotate key, disable token).
   Do not wait to determine exploitability; revocation is reversible, exposure is not.
2. **Rotate (15 min)** — issue a new credential, update the store, confirm consumers pick it up.
3. **Audit (1 h)** — search provider audit logs (CloudTrail/Vault/API logs) for use of the
   leaked value from unexpected principals, IPs, or times. Export evidence before cleanup.
4. **Assess scope** — what could that credential do? List affected data and systems; if it was
   an encryption key, treat all data it protected as potentially exposed.
5. **Purge** — remove from git history (filter-repo) or, better, assume permanent exposure and
   rotate; also remove from logs, CI variables, wikis, and chat.
6. **Notify** — security owner, affected service owners, and (if personal data) privacy/legal
   per the incident policy.
7. **Prevent** — add a scanner rule/detector for the pattern, add a CI check, and record the
   incident's action items.
```

## 8. Quality Standards

- No secrets in git, container images, IaC state, CI variables (except through OIDC), or logs.
- Human and workload access to secrets is scoped by path/resource and role, with audit logging.
- Every secret has an owner, a rotation interval, and an automated rotation path where feasible.
- Rotation is tested for zero downtime; consumers reload without restarts.
- KMS keys are per classification/environment, with rotation enabled, least-privilege key policies, and separation between key admins and data readers.
- Secret scanning runs pre-commit and in CI, with push protection enabled.
- Dynamic/short-lived credentials are preferred over static keys wherever the platform supports them.
- A leak-response runbook exists, is rehearsed, and has named owners.

## 9. Verification and Testing

- Simulate a rotation in staging: rotate, confirm no errors, confirm consumers use the new value, then confirm the old value is rejected.
- Attempt a read with a principal outside the allowed role/tag; expect `AccessDenied` (and verify the attempt is logged).
- Verify `kms:Decrypt` fails for a principal lacking the key policy entry, and that key deletion is denied to non-admins.
- Run `gitleaks detect` over the full history; confirm zero findings or documented exceptions.
- Check that secret values never appear in application logs: grep a captured log sample for the secret's known test value.
- Test the leak runbook end to end in a sandbox with a dummy credential.

## 10. Security Considerations

- Prefer no-secret designs (OIDC, workload identity, instance roles) over any store; a secret that does not exist cannot leak.
- Environment variables are readable by any process in the container and often dumped in crash reports; prefer file-based or in-memory retrieval where possible.
- Secret managers are high-value targets: enable MFA delete, restrict `PutSecretValue`, and alert on policy changes.
- KMS key deletion is irreversible after the window; require dual approval and a long deletion window.
- Encrypt secrets at rest and in transit; a "secret" store without TLS is just a list.
- Backups and snapshots contain encrypted data but the keys may be separate — verify the recovery path includes key availability.
- Rotation must include anything cached: connections pools, sidecars, clients with in-memory credentials.
- Do not log secret names that reveal architecture to untrusted parties in public-facing error messages.

## 11. Failure Handling

- **Rotation breaks the app:** consumers cached the old value past invalidation, or the database rejected the new password — keep the previous version available until all consumers refresh, then retire it.
- **Secret not found at startup:** fail fast with a clear error and alert; a service running with a missing secret is worse than a service that refuses to start.
- **KMS access denied after a policy change:** check `kms:ViaService` conditions and the caller's role; do not loosen the policy to `"*"` as a fix.
- **Leak found in git history:** rotate first; rewriting history is secondary and cannot undo exposure.
- **Rotation automation runs but the secret is unchanged:** the Lambda lacks permission to `PutSecretValue` on the pending stage or the rotation step failed silently; add metrics/alerts on rotation failures.

## 12. Expected Deliverables

1. Secret inventory with owners, consumers, and rotation intervals.
2. Secret store design with path/permission model.
3. Workload identity mapping (no static keys).
4. Rotation implementation and zero-downtime procedure.
5. KMS key hierarchy with policies and rotation settings.
6. Scanning configuration (pre-commit, CI, push protection).
7. Leak-response runbook with owners and rehearsal record.

## 13. References

- AWS Secrets Manager rotation — https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html
- AWS KMS key policies — https://docs.aws.amazon.com/kms/latest/developerguide/key-policies.html
- AWS KMS automatic key rotation — https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html
- EKS Pod Identity — https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html
- HashiCorp Vault — https://developer.hashicorp.com/vault/docs
- External Secrets Operator — https://external-secrets.io/
- gitleaks — https://github.com/gitleaks/gitleaks
- GitHub secret scanning and push protection — https://docs.github.com/en/code-security/secret-scanning
- NIST SP 800-57 (Key Management) — https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
