---
name: cicd-pipeline-engineering
description: Design CI/CD pipelines that are fast, deterministic, and safe—build once and promote, caching, parallelism, gates, environments, and rollback—independent of the specific CI vendor.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# CI/CD Pipeline Engineering

## 1. Purpose

Design the delivery pipeline as a product: fast feedback on pull requests, a build artifact that is produced once and promoted through environments, automated gates that are meaningful, and a rollback path that is tested. This skill is vendor-neutral; GitHub Actions and GitLab CI specifics live in their own skills.

**Scope:** pipelines for repositories you own. Pipelines hold deployment credentials—design them with least privilege and environment protection.

## 2. Activation Conditions

- Creating or reworking a CI/CD pipeline.
- Build times exceed 10 minutes, or tests are flaky/unreliable.
- Deployments are manual, undocumented, or irreproducible.
- Need for environment promotion, approval gates, or a rollback strategy.
- Keywords: CI/CD, pipeline, build once, artifact promotion, caching, matrix builds, deployment gates, blue-green, canary, rollback, DORA.

## 3. When Not to Use

- Single-person throwaway scripts with no deployment target.
- Writing a specific vendor's YAML without the design (use github-actions or gitlab-ci, but read this first for the model).
- Kubernetes deployment internals (use kubernetes-engineering).

## 4. Required Context

1. Repository layout, languages, and build commands.
2. Target environments and how deployment currently happens.
3. Test inventory and typical durations; known flaky tests.
4. Secrets and credentials needed, and who may deploy to production.
5. Compliance requirements (approvals, separation of duties, audit logs).
6. Current metrics: lead time, build duration, deployment frequency, change failure rate.

## 5. Operating Procedure

1. **Model the stages**: `lint` → `build` → `unit test` → `integration test` → `security scan` → `package artifact` → `deploy staging` → `e2e` → `approve` → `deploy prod` → `verify`.
2. **Fail fast and in parallel**: run independent jobs concurrently; put cheap checks first.
3. **Build once**: produce an immutable artifact (image digest, tarball + SHA-256) in the build stage; every later stage consumes that exact artifact, never rebuilt from source.
4. **Pin everything**: action/runner versions by SHA or immutable tag, base images by digest, tool versions explicitly.
5. **Cache correctly**: dependency caches keyed by lockfile hash; build caches in a content-addressed store; never cache secrets.
6. **Isolate environments**: separate credentials and protection rules per environment; production requires approval + audit trail.
7. **Use OIDC over static cloud keys**: short-lived credentials exchanged at run time.
8. **Make tests deterministic**: locks, fixed time zone (UTC), seeded randomness, ephemeral services via containers.
9. **Define gates that matter**: coverage threshold on the diff, security scan on new findings, migration check, contract tests.
10. **Deploy with a strategy**: rolling/blue-green/canary, with automated rollback on health-check failure.
11. **Verify after deploy**: smoke tests against the live environment, then update the deployment record.
12. **Measure**: pipeline duration p50/p95, queue time, flake rate, MTTR; publish to the team.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| CI providers | GitHub Actions, GitLab CI, Jenkins, Buildkite, CircleCI |
| Artifacts | Container registry, S3/GCS, `actions/upload-artifact`, GitLab artifacts |
| Caching | `actions/cache`, GitLab `cache:`, sccache, npm/pip/go caches |
| Security | Trivy, Semgrep, gitleaks, cosign |
| Deploy | Argo CD, Flux, Helm, Terraform, `kubectl`, Ansible |
| Feature flags | Unleash, LaunchDarkly |
| Metrics | DORA metrics, pipeline dashboards |

## 7. Practical Implementation

**Vendor-neutral pipeline definition (documented as YAML for clarity):**

```yaml
stages:
  - name: lint
    runs: [ruff, mypy, eslint]
  - name: build
    outputs: [oci-image@sha256, sbom, provenance]
  - name: test
    needs: [build]
    parallel: [unit, integration]
  - name: security
    needs: [build]
    runs: [sast, dependency, secret, image-scan, sign]
  - name: deploy-staging
    needs: [test, security]
    artifact: pinned-digest
  - name: e2e
    needs: [deploy-staging]
  - name: deploy-prod
    needs: [e2e]
    requires: [manual-approval, change-ticket]
```

**Build-once / promote pattern (shell-level, provider-agnostic):**

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IMAGE="registry.example.com/orders-api"
SHA="$(git rev-parse --short HEAD)"
DIGEST_FILE=".artifacts/digest.txt"

case "${1:-}" in
  build)
    docker buildx build --push --provenance=true --sbom=true \
      -t "${IMAGE}:${SHA}" -t "${IMAGE}:latest" .
    docker buildx imagetools inspect "${IMAGE}:${SHA}" \
      | awk '/Digest:/{print $2; exit}' > "$DIGEST_FILE"
    ;;
  promote)
    # promote by digest: same bytes, new tag, no rebuild
    REF="${IMAGE}@$(cat "$DIGEST_FILE")"
    docker buildx imagetools create -t "${IMAGE}:${2:?env required}" "$REF"
    ;;
  verify)
    cosign verify --key cosign.pub "${IMAGE}@$(cat "$DIGEST_FILE")"
    ;;
  *) echo "usage: $0 build|promote <env>|verify" >&2; exit 2 ;;
esac
```

**Secrets via OIDC (AWS example, provider-neutral concept):**

```yaml
permissions:
  id-token: write     # required for OIDC
  contents: read
# exchange the OIDC token for short-lived role credentials; no AWS_SECRET_ACCESS_KEY stored
```

**Deterministic test environment:**

```yaml
services:
  postgres:
    image: postgres:16-alpine@sha256:<digest>
    env: {POSTGRES_PASSWORD: test, POSTGRES_DB: test}
    options: >-
      --health-cmd "pg_isready -U postgres" --health-interval 5s
      --health-retries 10
env:
  TZ: UTC
  PYTHONHASHSEED: "0"
```

**Deployment with automated rollback:**

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
NEW_DIGEST="$(cat .artifacts/digest.txt)"
PREV_DIGEST="$(kubectl -n orders get deploy orders-api -o jsonpath='{.spec.template.spec.containers[0].image}' | cut -d@ -f2)"

kubectl -n orders set image deploy/orders-api "orders-api=registry.example.com/orders-api@${NEW_DIGEST}"
if ! kubectl -n orders rollout status deploy/orders-api --timeout=180s; then
  echo "rollout failed, reverting to ${PREV_DIGEST}" >&2
  kubectl -n orders set image deploy/orders-api "orders-api=registry.example.com/orders-api@${PREV_DIGEST}"
  exit 1
fi
./scripts/smoke.sh https://orders.example.com || {
  kubectl -n orders set image deploy/orders-api "orders-api=registry.example.com/orders-api@${PREV_DIGEST}"
  exit 1
}
```

**Coverage gate on changed lines only:**

```bash
diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
```

**Pipeline metrics:**

```text
DORA:
  deployment frequency      = deploys to prod per day
  lead time for changes     = commit -> running in prod (p50, p90)
  change failure rate       = failed deploys / total deploys
  time to restore           = incident start -> service restored
Local:
  pipeline duration p50/p95, queue time, flaky test rate
```

## 8. Quality Standards

- The same artifact is deployed to every environment; the digest is recorded.
- Pull request feedback arrives in under 10 minutes for the common case.
- Pipelines are reproducible: same commit + same inputs → same artifact digest.
- All credentials are short-lived and scoped per environment.
- Production deployment requires an explicit approval with an audit trail.
- Every deploy has a defined rollback procedure, rehearsed at least quarterly.
- Flaky tests are quarantined and fixed, not retried silently forever.

## 9. Verification and Testing

```bash
# Reproduce a pipeline build locally where possible
make ci
# Confirm artifact identity
docker buildx imagetools inspect registry.example.com/orders-api:1.4.2
cosign verify --key cosign.pub registry.example.com/orders-api@sha256:...
# Confirm rollback works
./scripts/deploy.sh promote staging && ./scripts/rollback.sh
# Confirm pipeline timing
gh run list --limit 20 --json displayTitle,conclusion,createdAt,updatedAt
```

Expected evidence: identical digests across environments, successful signed-artifact verification, green pipeline with stable timings, rollback executed with a recorded previous digest.

## 10. Security Considerations

- Untrusted PR code must never receive production secrets: separate workflows, `pull_request` (not `pull_request_target`) for forks, and no secret exposure in logs.
- Use OIDC federation instead of long-lived cloud keys; scope the trust policy to repo + branch/environment.
- Pin third-party actions by commit SHA; an action is arbitrary code with your token.
- Mask and avoid echoing secrets; scan logs for accidental leaks.
- Sign artifacts and verify at deploy (cosign/Sigstore, SLSA provenance).
- Protect branches and environments: required reviews, signed commits where feasible, and deployment protection rules.
- Keep an SBOM per artifact for vulnerability response.
- Log every production deployment with actor, artifact digest, approvals, and timestamps.

## 11. Failure Handling

- **Tests pass locally, fail in CI:** environment drift—pin tool versions, use the same container image, check locale/timezone and parallelism.
- **Flaky tests block merges:** quarantine with a tracked issue, run them in a nightly suite, and fix within a sprint.
- **Pipeline queue times dominate:** add runners, split long jobs, reduce matrix size, cache aggressively.
- **Deploy succeeds but service is broken:** missing post-deploy verification—add smoke tests and make them a gate.
- **Rollback impossible because the DB migrated:** use expand/contract migrations so old and new code can run against the same schema during rollout.
- **Secret leaked in logs:** rotate immediately, then add masking and a log scanner.

## 12. Expected Deliverables

1. Pipeline stage diagram with jobs, parallelism, and caching.
2. Configuration files for the chosen provider (see vendor skills for syntax).
3. Build-once/promote implementation and artifact digest recording.
4. Environment protection and approval configuration.
5. Rollback runbook with a rehearsal record.
6. Metrics dashboard specification.

## 13. References

- DORA / State of DevOps research — https://dora.dev/
- SLSA framework — https://slsa.dev/
- Sigstore/cosign — https://docs.sigstore.dev/
- "Continuous Delivery" (Humble & Farley).
- GitHub Actions security hardening — https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- GitLab CI/CD — https://docs.gitlab.com/ee/ci/
- OpenSSF Scorecards — https://github.com/ossf/scorecard
