---
name: github-actions
description: Author secure, fast GitHub Actions workflows—triggers, matrix builds, caching, reusable workflows, OIDC cloud auth, and permission hardening.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# GitHub Actions

## 1. Purpose

Write workflows that are fast, deterministic, and safe from the specific failure modes of GitHub Actions: over-broad `GITHUB_TOKEN` permissions, secret exposure to fork PRs, mutable action tags, and cache poisoning. This skill covers the trigger model, job/step semantics, matrix and caching, reusable workflows and composite actions, OIDC to cloud providers, and concurrency control.

**Scope:** repositories you administer. Workflows can deploy and hold credentials—changes require review like code.

## 2. Activation Conditions

- Creating CI for a repository on GitHub.
- Pipeline is slow, flaky, or duplicated across repos.
- Adding a deployment job that needs cloud credentials.
- Security review of `.github/workflows/*.yml`.
- Keywords: GitHub Actions, workflow YAML, `on:` triggers, matrix, `actions/cache`, reusable workflow, composite action, OIDC, environments, `GITHUB_TOKEN`, runner.

## 3. When Not to Use

- Repositories hosted on GitLab/Bitbucket (use gitlab-ci or the corresponding provider).
- Self-hosted runners with special network requirements (adapt, but review runner security first).
- The platform design questions (see cicd-pipeline-engineering).

## 4. Required Context

1. Repository visibility (public/private) and whether forks can open PRs.
2. Languages/toolchain and test commands.
3. Required secrets and whether OIDC federation is available for the cloud.
4. Runner type: `ubuntu-latest` (GitHub-hosted) vs. self-hosted (trust implications differ).
5. Environment names and protection rules.

## 5. Operating Procedure

1. **Choose triggers precisely**: `pull_request` for validation, `push` to protected branches for deploy, `workflow_dispatch` for manual, `schedule` for periodic. Avoid `pull_request_target` with checkout of PR code.
2. **Set top-level `permissions: contents: read`** and elevate per job only where needed.
3. **Pin actions to a commit SHA** for third-party actions; use major-version tags only for GitHub-owned actions in low-risk contexts.
4. **Define jobs with explicit `needs`**; parallelize independent jobs.
5. **Use a matrix** for multi-version/multi-platform testing, with `fail-fast: false` when you want full coverage.
6. **Cache dependencies** keyed by lockfile hash; never cache `~/.ssh`, credentials, or build outputs that embed secrets.
7. **Add `concurrency`** to cancel superseded runs on PR branches; never cancel production deploys mid-flight (use a separate group).
8. **Authenticate with OIDC** (`permissions: id-token: write`) instead of stored cloud keys.
9. **Encapsulate repeated logic** in composite actions or reusable workflows (`workflow_call`).
10. **Protect environments** with required reviewers and deployment branch rules.
11. **Add timeouts and `step-security/harden-runner`** where appropriate.
12. **Validate**: run `actionlint` locally; test on a branch; verify permissions with a dry run.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Lint | `actionlint`, `zizmor`, `shellcheck` for `run:` blocks |
| Caching | `actions/cache`, `actions/setup-*` built-in caching |
| Artifacts | `actions/upload-artifact`, `download-artifact` |
| Security | `step-security/harden-runner`, `github/codeql-action`, `aquasecurity/trivy-action` |
| Reuse | `workflow_call`, composite actions |
| Cloud auth | `aws-actions/configure-aws-credentials` (OIDC), `google-github-actions/auth`, `azure/login` |
| Local run | `act` (partial fidelity) |

## 7. Practical Implementation

**Secure CI workflow with matrix and caching:**

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with: {persist-credentials: false}
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -r requirements-dev.txt
      - run: ruff format --check . && ruff check . && mypy src

  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        python: ["3.11", "3.12"]
    services:
      postgres:
        image: postgres:16-alpine
        env: {POSTGRES_PASSWORD: test, POSTGRES_DB: test}
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s --health-timeout 3s --health-retries 10
    steps:
      - uses: actions/checkout@v4
        with: {persist-credentials: false}
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest -q --junitxml=reports/junit.xml
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/test
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: junit-${{ matrix.python }}
          path: reports/junit.xml
```

**Build and push an image with provenance:**

```yaml
  image:
    needs: [lint, test]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
        with: {persist-credentials: false}
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: build
        uses: docker/build-push-action@v6
        with:
          push: true
          provenance: true
          sbom: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**OIDC deploy to AWS without stored keys:**

```yaml
  deploy:
    needs: [image]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/gha-deploy-orders
          aws-region: ap-south-1
          role-session-name: gha-${{ github.run_id }}
      - run: |
          aws sts get-caller-identity
          aws ecs update-service --cluster prod --service orders --force-new-deployment
```

Trust policy (AWS side) restricted to repo + branch/environment:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
      "StringLike": {"token.actions.githubusercontent.com:sub": "repo:org/repo:environment:production"}
    }
  }]
}
```

**Reusable workflow (`.github/workflows/reusable-test.yml`):**

```yaml
on:
  workflow_call:
    inputs:
      python:
        type: string
        default: "3.12"
    secrets:
      CODECOV_TOKEN:
        required: false
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "${{ inputs.python }}", cache: pip}
      - run: pip install -r requirements-dev.txt
      - run: pytest -q
```

**Composite action (`.github/actions/setup/action.yml`):**

```yaml
name: setup
description: Install toolchain with cache
runs:
  using: composite
  steps:
    - uses: actions/setup-go@v5
      with: {go-version-file: go.mod, cache: true}
    - shell: bash
      run: go install github.com/golangci/golangci-lint/cmd/golangci-lint@v1.61.0
```

**Validation:**

```bash
go install github.com/rhysd/actionlint/cmd/actionlint@latest
actionlint -color
# optional deeper security lint
uvx zizmor .github/workflows/
```

## 8. Quality Standards

- Top-level `permissions` is minimal; elevated only per job.
- Third-party actions pinned to full commit SHAs.
- `pull_request_target` never checks out and executes PR code with secrets.
- Every job has `timeout-minutes`.
- Caches keyed by lockfile hash; no secrets cached.
- Concurrency groups prevent duplicate runs and protect deploys.
- Secrets referenced from environments, not hard-coded, and never echoed.
- `actionlint` passes in CI itself.

## 9. Verification and Testing

- Open a PR from a fork and confirm no secrets are exposed and the workflow runs with read-only permissions.
- Check the run log for the effective permissions (`GITHUB_TOKEN` permissions shown at job start).
- Confirm cache hit on a second run (log line "Cache restored successfully").
- Verify OIDC: `aws sts get-caller-identity` shows the assumed role, and no access keys exist.
- Test rollback by re-running the previous deployment workflow with the prior digest.

## 10. Security Considerations

- `pull_request_target` runs with secrets and base-branch context: treat PR content as hostile—do not run its code there.
- Self-hosted runners are persistent and shared: never use them for public-repo PRs without an ephemeral, isolated setup.
- `actions/checkout` with `persist-credentials: true` writes the token into `.git/config`, where later steps can read it—disable when not needed.
- Workflow files themselves are code: require review from a CODEOWNERS entry for `.github/workflows/`.
- Expressions are not shell-safe: never interpolate `${{ github.event.* }}` directly into `run:` shell lines; pass through `env:` and quote.
- Artifacts and caches are shared across runs within a branch scope; do not upload secrets.
- Restrict `GITHUB_TOKEN` via repository settings ("Read repository contents permission") and audit third-party app access.

## 11. Failure Handling

- **Workflow does not trigger:** check `on:` filters, branch protection, and whether the file is on the default branch for `schedule`/`workflow_dispatch`.
- **Secret is empty:** repository/organization/environment scoping—secrets are not inherited by reusable workflows unless declared.
- **Permission denied pushing to registry:** `packages: write` missing or the token lacks org SSO authorization.
- **Cache never hits:** key includes changing values (e.g. `github.run_id`); use lockfile hashes and stable OS identifiers.
- **Flaky service container:** add healthchecks and retries; avoid fixed `sleep` waits.
- **OIDC fails:** verify `id-token: write`, the account's OIDC provider exists, and the `sub` claim matches exactly.

## 12. Expected Deliverables

1. Workflow files with minimal permissions and pinned actions.
2. Reusable workflows/composite actions for shared logic.
3. OIDC configuration plus the cloud-side trust policy.
4. Environment protection settings.
5. `actionlint` output and a passing run link.
6. Rollback procedure.

## 13. References

- GitHub Actions documentation — https://docs.github.com/en/actions
- Workflow syntax — https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- Security hardening for Actions — https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- OIDC hardening — https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- `actionlint` — https://github.com/rhysd/actionlint
- `zizmor` — https://github.com/woodruffw/zizmor
- GitHub-hosted runners specs — https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners
