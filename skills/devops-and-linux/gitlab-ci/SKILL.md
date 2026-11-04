---
name: gitlab-ci
description: Build GitLab CI/CD pipelines—stages, needs/DAG, rules, caching, artifacts, environments, and protected-branch deployments—with secure defaults.
metadata:
  domain: devops-and-linux
  version: 1.0.0
  risk: medium
---

# GitLab CI

## 1. Purpose

Write `.gitlab-ci.yml` pipelines that are fast (DAG with `needs`), correct (rules and workflow), and safe (protected variables, masked secrets, no untrusted-code execution on protected runners). This skill covers the GitLab-specific model: stages vs. `needs`, `rules` vs. `only/except`, cache vs. artifacts, includes and components, environments and review apps, and security scanning templates.

**Scope:** projects you administer. CI variables can hold deploy credentials—protect environments and branches accordingly.

## 2. Activation Conditions

- Creating or refactoring a GitLab pipeline.
- Pipeline is slow due to stage serialization.
- Jobs run when they should not (or fail to run on merge requests).
- Migrating from `only/except` to `rules`.
- Keywords: GitLab CI, .gitlab-ci.yml, stages, needs, DAG, rules, cache, artifacts, environment, protected variables, includes, components, runners.

## 3. When Not to Use

- GitHub-hosted repositories (use github-actions).
- Jenkins/Buildkite-specific requirements.
- Conceptual pipeline design questions (see cicd-pipeline-engineering).

## 4. Required Context

1. GitLab edition/version (features like Components require 16.9+; `rules:changes:compare_to` availability varies).
2. Runner types and tags: shared vs. project vs. group; whether runners are protected.
3. Languages/toolchains and test commands.
4. Environments and who may deploy.
5. Variables: masked, protected, and file-type variables in use.

## 5. Operating Procedure

1. **Define `stages`** in order: `build`, `test`, `security`, `package`, `deploy`.
2. **Use `workflow:rules`** to prevent duplicate pipelines for branch + merge request events.
3. **Replace `only/except` with `rules`** — explicit conditions, `when`, and `allow_failure`.
4. **Use `needs` for DAG execution**: jobs start as soon as their dependencies finish, not when the whole stage ends.
5. **Cache dependencies by lockfile key** (`cache:key:files`); use artifacts only for files needed downstream.
6. **Pin images by digest**; set `image:entrypoint: [""]` when the image's entrypoint interferes.
7. **Protect the deploy**: `environment:` with `deployment_tier`, protected branches, and protected variables.
8. **Separate secrets**: masked + protected variables only visible on protected branches; never echo them.
9. **Add security templates**: SAST, Secret Detection, Dependency Scanning, Container Scanning.
10. **Use `include`** for shared config and `spec:inputs` for parameters; prefer Components for cross-project reuse.
11. **Validate** with the CI Lint API before pushing; run a pipeline on a branch and inspect job logs and durations.
12. **Measure** stage durations and optimize the longest path.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Lint | CI Lint API, `gitlab-ci-local` (community) |
| Reuse | `include:`, `spec:inputs`, CI/CD Components |
| Security | SAST/Secret Detection/Dependency Scanning/Container Scanning templates |
| Deployment | `environment:`, `kubernetes` executor, Helm, Argo CD |
| Runners | GitLab Runner executors (docker, kubernetes, shell) |
| Artifacts | `artifacts:`, `reports:junit`, `reports:coverage_report` |

## 7. Practical Implementation

**Full pipeline example:**

```yaml
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
    - if: $CI_COMMIT_TAG

stages: [build, test, security, package, deploy]

default:
  image: python:3.12-slim
  interruptible: true
  before_script:
    - pip install --no-cache-dir -r requirements-dev.txt

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"
  TZ: UTC

cache:
  key:
    files: [requirements.txt, requirements-dev.txt]
  paths: [.cache/pip]
  policy: pull-push

lint:
  stage: build
  script:
    - ruff format --check .
    - ruff check .
    - mypy src

unit:
  stage: test
  needs: [lint]
  script:
    - pytest -q --junitxml=reports/junit.xml --cov=src --cov-report=xml
  artifacts:
    when: always
    reports:
      junit: reports/junit.xml
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
    expire_in: 1 week

integration:
  stage: test
  needs: [lint]
  services:
    - name: postgres:16-alpine
      alias: db
  variables:
    POSTGRES_PASSWORD: test
    POSTGRES_DB: test
    DATABASE_URL: postgresql://postgres:test@db:5432/test
  script:
    - pytest -q tests/integration --timeout=120

sast:
  stage: security
  needs: []
  include:
    - template: Security/SAST.gitlab-ci.yml

secret_detection:
  stage: security
  needs: []
  include:
    - template: Security/Secret-Detection.gitlab-ci.yml

build-image:
  stage: package
  needs: [unit, integration]
  image: docker:27-cli
  services: [docker:27-dind]
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
  script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
    - docker build --pull -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA" .
    - docker push "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA"
    - |
      DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA" | cut -d@ -f2)
      echo "IMAGE_DIGEST=$DIGEST" > image.env
  artifacts:
    reports:
      dotenv: image.env

deploy-staging:
  stage: deploy
  needs: [build-image]
  image: bitnami/kubectl:latest
  environment:
    name: staging
    url: https://staging.example.com
    deployment_tier: staging
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
  script:
    - kubectl -n staging set image deploy/orders-api orders-api="$CI_REGISTRY_IMAGE@$IMAGE_DIGEST"
    - kubectl -n staging rollout status deploy/orders-api --timeout=180s

deploy-prod:
  stage: deploy
  needs: [deploy-staging]
  environment:
    name: production
    url: https://orders.example.com
    deployment_tier: production
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
      when: manual
      allow_failure: false
  script:
    - kubectl -n prod set image deploy/orders-api orders-api="$CI_REGISTRY_IMAGE@$IMAGE_DIGEST"
    - kubectl -n prod rollout status deploy/orders-api --timeout=300s
```

**`rules` patterns (replacing `only/except`):**

```yaml
# Run only for merge requests touching backend files
rules:
  - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    changes:
      paths: ["backend/**/*", "pyproject.toml"]
  - when: never
```

**Protected variables checklist:**

```yaml
# Set in Settings > CI/CD > Variables:
#   AWS_ROLE_ARN      : protected, masked (not secret but scoped)
#   DEPLOY_TOKEN      : protected, masked, environment scope = production
# Never use: unprotected variables for production credentials.
```

**Include with inputs (parameterized CI config):**

```yaml
include:
  - local: /ci/build.yml
    inputs:
      image_name: orders-api
      dockerfile: Dockerfile
```

```yaml
# ci/build.yml
spec:
  inputs:
    image_name: {type: string}
    dockerfile: {type: string, default: Dockerfile}
---
build:
  script:
    - docker build -f "$[[ inputs.dockerfile ]]" -t "$CI_REGISTRY_IMAGE/$[[ inputs.image_name ]]:$CI_COMMIT_SHORT_SHA" .
```

**Validate pipeline before push:**

```bash
curl --silent --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
  --header "Content-Type: application/json" \
  --data-binary @<(jq -Rs '{content: .}' .gitlab-ci.yml) \
  "https://gitlab.example.com/api/v4/projects/${PROJECT_ID}/ci/lint"
```

## 8. Quality Standards

- `workflow:rules` prevents duplicate pipelines.
- `rules` used everywhere; no `only/except`.
- `needs` used to break stage serialization where dependencies allow.
- Cache key includes lockfile hashes; artifacts have `expire_in`.
- Production credentials only in protected, masked variables scoped to the environment.
- Images pinned by digest or immutable tag; `interruptible: true` on non-deploy jobs.
- Deploy jobs have `environment:` and rollouts wait for status.
- Security scanning templates included in the default branch pipeline.

## 9. Verification and Testing

- Use the CI Lint endpoint; confirm no YAML errors and review the merged configuration.
- Open an MR and verify pipelines trigger once (not twice) and only intended jobs run.
- Check job durations and the critical path; confirm DAG parallelism.
- Confirm a protected variable is unavailable on a feature branch (`echo ${DEPLOY_TOKEN}` should be empty—do not print secrets; check the variable list instead).
- Verify deploy job creates an environment deployment record and that rollback re-runs a previous pipeline.

## 10. Security Considerations

- Forked MRs run in the target project's context only if configured; never enable "merge request pipelines in the parent project" for public projects without understanding variable exposure.
- Protected variables are only exposed on protected branches/tags—keep production credentials protected.
- Masked variables still leak if transformed; never echo or write them to artifacts.
- `docker:dind` requires privileged runners: prefer Kaniko/Buildah or a dedicated runner pool.
- Cache and artifacts are downloadable by project members; never store secrets there.
- Runner shells persist state: use ephemeral runners (docker/kubernetes executor) for untrusted jobs.
- Enable "Prevent outdated deployment jobs" and required approvals for production environments.

## 11. Failure Handling

- **Pipeline runs twice on MR:** `workflow:rules` missing the `merge_request_event` guard or branch rules overlap.
- **Job cannot find artifacts:** `needs` across stages requires the producing job in `needs`; artifacts download only from `needs` dependencies.
- **Cache never restored:** cache keys must match; `policy: pull` jobs must have a preceding `pull-push` job.
- **Service container unreachable:** use the `alias` hostname, not `localhost`, and wait for readiness.
- **Deploy job blocked:** protected branch or environment approval rules; check Settings > CI/CD > Protected environments.
- **`rules:changes` never matches:** on scheduled/API pipelines `changes` cannot evaluate; add an explicit `if` fallback.

## 12. Expected Deliverables

1. `.gitlab-ci.yml` with stages, rules, needs, and caching.
2. Include/component structure for shared config.
3. Protected variable and environment configuration notes.
4. Security template inclusion.
5. Lint output and a link to a passing pipeline.
6. Deployment and rollback procedure.

## 13. References

- GitLab CI/CD documentation — https://docs.gitlab.com/ee/ci/
- `.gitlab-ci.yml` reference — https://docs.gitlab.com/ee/ci/yaml/
- `needs` (DAG) — https://docs.gitlab.com/ee/ci/yaml/#needs
- CI/CD components — https://docs.gitlab.com/ee/ci/components/
- Protected environments — https://docs.gitlab.com/ee/ci/environments/protected_environments.html
- CI Lint API — https://docs.gitlab.com/ee/api/lint.html
- GitLab security scanning — https://docs.gitlab.com/ee/user/application_security/
