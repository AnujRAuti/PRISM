---
name: testing-strategy
description: Define a risk-based test strategy—layer allocation, coverage targets, CI gates, environment policy, and flaky-test governance that scales with the system.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Testing Strategy

## 1. Purpose

Decide what to test, at which level, and what blocks a merge. Teams rarely under-test in the abstract; they over-test the wrong things (slow end-to-end suites for logic) and under-test the things that break (boundaries, failure paths, migrations). This skill builds a strategy from risk: which behaviors are critical, which layer proves them fastest, what gates CI, and how tests are owned and retired.

**Scope:** your own codebase and CI. Strategy decisions affect release safety—changes to gates should be reviewed like code, not loosened under deadline pressure.

## 2. Activation Conditions

- New project, or a suite that is slow, flaky, or distrusted.
- Release incidents that tests did not catch.
- Test suite runtime blocking developer flow.
- Coverage debates with no shared standard.
- Keywords: test strategy, test pyramid, testing trophy, risk-based testing, coverage target, CI gates, test levels, shift left, acceptance criteria, quality gates.

## 3. When Not to Use

- Writing an individual test (use unit-testing, integration-testing, end-to-end-testing).
- Diagnosing a specific flaky test (use flaky-test-diagnosis).
- Pure exploratory testing sessions with no automation goal.

## 4. Required Context

1. Architecture: services, boundaries, data stores, external dependencies.
2. Release model: continuous deploy, weekly, mobile app store cycles.
3. Incident history: what actually breaks, and how it was found.
4. Current suite: layer counts, runtime, flake rate.
5. Compliance or contractual testing obligations.

## 5. Operating Procedure

1. **Inventory behaviors, not files.** List the user-visible and contract-visible behaviors (money moves, auth decisions, data integrity, external webhooks) and rank each by impact × likelihood.
2. **Choose the layer per behavior** using cost of feedback vs. confidence: pure logic → unit; persistence/HTTP/serialization → integration; critical user journeys → end-to-end. The "testing trophy" weighting (many integration, fewer unit and E2E) fits most web services better than a strict pyramid.
3. **Set a coverage policy by risk tier**, not one global number: critical modules require branch coverage ≥ 90% and mutation checks; ordinary modules use diff coverage on changed lines.
4. **Define the gates**: what runs on pre-commit (lint, fast unit), on PR (unit + integration + contract), and on main/pre-deploy (E2E, performance smoke).
5. **Budget the runtime**: PR feedback ≤ 10 minutes, pre-merge full suite ≤ 30 minutes. Enforce by sharding and selecting affected tests.
6. **Decide environments**: ephemeral databases per test run (containers), seeded staging for E2E, no shared mutable staging for integration.
7. **Assign ownership**: each test file maps to a code owner; orphaned tests are deleted, not left failing.
8. **Institutionalize flake handling**: quarantine with a time limit, owner assigned, and a rule that quarantined tests do not block merges but must be fixed or removed within two weeks.
9. **Review the strategy quarterly against incidents**: every escaped defect asks "which layer should have caught this?"
10. **Publish the strategy** in the repo with examples, so new tests land at the right level.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Unit | pytest, vitest, JUnit, Go testing |
| Integration | testcontainers, `pytest-postgresql`, `httpx` ASGI client |
| E2E | Playwright, Cypress |
| Contract | Pact, Schemathesis, `openapi-diff` |
| Coverage | coverage.py, `c8`, JaCoCo, Codecov diff coverage |
| Mutation | mutmut, Stryker, PIT |
| CI | GitHub Actions, GitLab CI, Nx/Turborepo affected-test selection |
| Test management | Markers/tags (`@pytest.mark.integration`), quarantine labels |

## 7. Practical Implementation

**Risk matrix driving layer choice:**

```markdown
| Behavior                          | Impact | Likelihood | Layer        | Gate        |
|-----------------------------------|--------|------------|--------------|-------------|
| Payment capture idempotency       | High   | Med        | Integration  | PR + main   |
| Order total calculation           | High   | High       | Unit + prop. | PR          |
| Refund authorization              | High   | Med        | Integration  | PR          |
| Checkout journey (happy + fail)   | High   | Med        | E2E          | Pre-deploy  |
| Report CSV formatting             | Low    | Med        | Unit         | PR          |
| Admin dashboard filters           | Low    | High       | Component    | PR          |
| Email template rendering          | Med    | Med        | Snapshot     | PR          |
| DB migration on live data         | High   | Low        | Rehearsal    | Pre-deploy  |
```

**Test markers and default selection (pytest):**

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
  "unit: fast, no I/O",
  "integration: uses database or HTTP boundary",
  "e2e: drives a browser",
  "slow: exceeds 2s",
]
addopts = "-q --strict-markers --durations=10"
```

```bash
pytest -m "unit" -n auto                    # pre-commit / fast feedback
pytest -m "unit or integration" -n auto     # PR gate
pytest -m "e2e" --shard=1/4                 # pre-deploy, sharded
```

**Layered CI workflow with runtime budget:**

```yaml
name: test
on: [pull_request]
jobs:
  fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -e ".[dev]"
      - run: ruff check . && mypy app
      - run: pytest -m unit -n auto --maxfail=1
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: {POSTGRES_PASSWORD: postgres}
        options: >-
          --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 10
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[dev]"
      - run: pytest -m integration -n 4
  e2e:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npx playwright install --with-deps chromium
      - run: npx playwright test --shard=${{ matrix.shard }}/4
        env: {BASE_URL: "https://staging.example.com"}
    strategy: {matrix: {shard: [1, 2, 3, 4]}}
```

**Coverage policy encoded, not argued (Codecov-style):**

```yaml
coverage:
  status:
    project:
      default:
        target: auto
        threshold: 1%           # allow small dips, block large drops
    patch:
      default:
        target: 85%             # changed lines must be well covered
  ignore:
    - "app/migrations/*"
    - "app/generated/*"
```

**Quarantine mechanism with an expiry:**

```python
import datetime as dt
import pytest

QUARANTINED = {
    "tests/e2e/test_export.py::test_large_export": ("order-export", dt.date(2026, 11, 20)),
}

def pytest_collection_modifyitems(config, items):
    for item in items:
        entry = QUARANTINED.get(item.nodeid)
        if not entry:
            continue
        owner, expires = entry
        if dt.date.today() > expires:
            raise pytest.UsageError(f"quarantine expired for {item.nodeid} (owner {owner})")
        item.add_marker(pytest.mark.skip(reason=f"quarantined until {expires} (owner {owner})"))
```

**Escaped-defect review template:**

```markdown
## Escaped defect review — DEF-4821 (duplicate charge on retry)
Found by: customer report (12 h after deploy)
Which layer should have caught it: integration test for `POST /payments` retry
Why it did not: retries were only tested at the unit level with a fake gateway
Action: add integration test with a real idempotency table and a duplicate submit
Owner: @payments-team  Due: 2026-11-08
```

**Suite health dashboard fields:**

```text
tests_total{layer="unit"}            1,842
suite_duration_p50/pr                 4m 12s
flake_rate_7d                         0.8%   (target < 1%)
quarantined_tests                     3      (target 0, max age 14 days)
escaped_defects_30d                   2
diff_coverage_pr_median               91%
```

## 8. Quality Standards

- Every critical behavior has at least one test at a level that would actually catch its failure.
- Unit tests are hermetic (no network, no wall clock, no shared state) and run in under 100 ms each on average.
- Integration tests use ephemeral, real dependencies (containerized DB) rather than mocks of the database.
- E2E covers only critical journeys; the suite stays under 30 minutes sharded.
- PR feedback completes within 10 minutes for the affected test set.
- Flaky tests are quarantined with an owner and a hard expiry date, never silently retried forever.
- Coverage policy is tiered and enforced on changed lines, with generated code excluded.
- Each test has an owner via CODEOWNERS or a metadata header.

## 9. Verification and Testing

- Mutation spot-check: introduce a deliberate bug in a critical module; the suite must fail.
- Measure suite duration and flake rate weekly; compare against targets.
- Run the strategy audit: pick five recent incidents and trace which test would have caught each.
- Verify CI gates fail correctly by opening a PR with a broken test and a coverage drop.
- Confirm quarantined tests expire and break the build rather than lingering.

## 10. Security Considerations

- Test code runs with CI credentials: never print secrets, scope tokens to read-only where possible, and avoid `pull_request_target` with untrusted checkouts.
- Do not run untrusted fork PRs with repository secrets; use `pull_request` and explicit approvals.
- E2E environments need real auth but not production data; use dedicated test tenants.
- Tests that hit third-party sandboxes should use dedicated credentials with rate limits.
- Security tests belong in the strategy: dependency scanning, secret scanning, and authz tests are gates, not optional jobs.
- Keep test artifacts (traces, screenshots, HAR files) free of tokens and PII before uploading.

## 11. Failure Handling

- **Suite too slow:** move logic tests down a layer, shard CI, and select affected projects in a monorepo.
- **Tests pass but incidents happen:** the suite tests implementation, not behavior—rewrite around observable outcomes and add contract tests at boundaries.
- **Coverage high but bugs escape:** coverage measures execution, not correctness; add mutation testing on critical modules and property-based tests for parsers.
- **Flake rate rises after a platform change:** pin browser/DB versions and run E2E in containers matching production.
- **Team bypasses gates:** gates that fail spuriously get disabled. Fix determinism; a trusted gate is the only useful gate.

## 12. Expected Deliverables

1. Behavior risk register with assigned test layers.
2. Layer-by-layer tooling and conventions.
3. CI gate definitions with runtime budgets.
4. Coverage and mutation policy by risk tier.
5. Environment and test-data policy.
6. Flake/quarantine governance with expiry enforcement.
7. Escaped-defect review process.

## 13. References

- Martin Fowler, "The Practical Test Pyramid" — https://martinfowler.com/articles/practical-test-pyramid.html
- Kent C. Dodds, "The Testing Trophy" — https://kentcdodds.com/blog/the-testing-trophy-and-testing-classification
- Google Testing Blog — https://testing.googleblog.com/
- "Software Engineering at Google", Ch. 11 Testing Overview — https://abseil.io/resources/swe-book/html/ch11.html
- pytest documentation — https://docs.pytest.org/en/stable/
- Playwright test sharding — https://playwright.dev/docs/test-sharding
- Codecov status checks — https://docs.codecov.com/docs/commit-status
