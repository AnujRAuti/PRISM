---
name: test-coverage-analysis
description: Use coverage as a diagnostic, not a trophy—branch and diff coverage, mutation-informed reading, dead-code detection, and honest gap analysis.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Test Coverage Analysis

## 1. Purpose

Find untested code and, more importantly, untested behavior. Line coverage says a line executed; it says nothing about whether an assertion would catch a bug. This skill covers branch/diff coverage, reading coverage reports to locate risk, mutation testing as the honest signal, dead-code elimination, and setting thresholds that drive behavior rather than gaming.

**Scope:** your own repository and CI. Coverage data can reveal internal structure; treat detailed reports as internal artifacts.

## 2. Activation Conditions

- Coverage debates ("we need 90%") with no shared interpretation.
- Large untested modules in a critical path.
- Refactor or legacy migration where preserved behavior must be verified.
- Coverage gate blocking merges or being trivially satisfied.
- Keywords: coverage, line coverage, branch coverage, diff coverage, mutation testing, mutmut, Stryker, PIT, dead code, vulture, knip, Codecov, coverage threshold.

## 3. When Not to Use

- Deciding what tests to write (use testing-strategy; coverage is a diagnostic afterwards).
- Language/framework generated code, migrations, or config files.
- Replacing code review and design judgment.

## 4. Required Context

1. Coverage tooling and its measurement mode (statement, branch, condition).
2. Risk tiers for modules (critical vs. ordinary).
3. Test suite runtime and CI budget.
4. Existing thresholds and how they are enforced.
5. Language-specific dead-code tools.

## 5. Operating Procedure

1. **Turn on branch coverage**, not just statement coverage; a statement can execute with an unexercised branch.
2. **Exclude generated and non-behavioral code explicitly** (migrations, protobuf output, config) so the number means something.
3. **Report per-module, not just overall**: one 40% module in payments matters more than an overall 85%.
4. **Adopt diff coverage as the merge gate** (e.g. ≥ 85% of changed lines), which prevents the number from rotting without punishing legacy code.
5. **Use per-project thresholds only where they encode a real policy** (critical packages 90%+), and review threshold changes like code.
6. **Read coverage to find gaps, then ask "what behavior is unverified?"** — write a test only if the behavior matters.
7. **Apply mutation testing to critical modules** on a nightly or pre-release job; surviving mutants reveal weak assertions.
8. **Pair coverage with dead-code detection**: delete unreachable code rather than testing it.
9. **Track coverage trends** (direction) over time; a drop after a big feature is the signal, not the absolute value.
10. **Never chase 100%**: defensive error branches, impossible states, and platform-specific code may not be worth testing—document exceptions.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Python | coverage.py (`--branch`), pytest-cov |
| JS/TS | `c8`, istanbul/nyc, `vitest --coverage` |
| Java | JaCoCo |
| Go | `go test -covermode=atomic -coverprofile` |
| Diff coverage | Codecov patch status, `diff-cover` |
| Mutation | mutmut, cosmic-ray, Stryker (JS/TS), PIT (Java) |
| Dead code | vulture, `ruff` F401/unused, knip (TS), `deadcode` (Go) |
| Reporting | Codecov, Coveralls, HTML reports in CI artifacts |

## 7. Practical Implementation

**Branch coverage with sensible exclusions:**

```toml
# pyproject.toml
[tool.coverage.run]
branch = true
source = ["app"]
omit = [
  "app/migrations/*",
  "app/generated/*",
  "app/__main__.py",
  "tests/*",
]

[tool.coverage.report]
show_missing = true
skip_covered = true
exclude_lines = [
  "pragma: no cover",
  "if TYPE_CHECKING:",
  "raise NotImplementedError",
  "@(abc\\.)?abstractmethod",
  "if __name__ == .__main__.:",
]
fail_under = 0        # global gate handled by diff coverage instead
```

```bash
pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=xml
```

**Reading `term-missing` output for real gaps:**

```text
Name                          Stmts   Miss Branch BrPart  Cover   Missing
-------------------------------------------------------------------------
app/services/refunds.py          48      6     14      3    85%   52-58, 71->75
app/services/orders.py           96      2     30      1    97%   118, 140->145
app/repositories/orders.py       71     29     22      8    55%   33-41, 58-74, 90-101
-------------------------------------------------------------------------
TOTAL                           812    104    196     38    86%
```

Interpretation: `orders.py` repository at 55% is the real risk (SQL mapping is untested), while a 97% service is fine. That is where an integration test earns the most.

**Diff coverage gate:**

```yaml
# .github/workflows/coverage.yml (job excerpt)
- run: pytest --cov=app --cov-branch --cov-report=xml
- uses: codecov/codecov-action@v4
  with:
    files: coverage.xml
    fail_ci_if_error: true
    token: ${{ secrets.CODECOV_TOKEN }}
```

```yaml
# codecov.yml
coverage:
  precision: 1
  status:
    project:
      default:
        target: auto
        threshold: 1%
    patch:
      default:
        target: 85%
ignore:
  - "app/migrations"
  - "app/generated"
comment:
  layout: "diff, files"
  require_changes: true
```

**Local diff coverage without a hosted service:**

```bash
coverage xml -o coverage.xml
diff-cover coverage.xml --compare-branch=origin/main --fail-under=85
```

**Mutation testing on a critical module:**

```ini
# setup.cfg for mutmut
[mutmut]
paths_to_mutate = app/services/refunds.py,app/domain/pricing.py
runner = pytest -q -x -m unit
tests_dir = tests/unit
```

```bash
mutmut run --max-children 4
mutmut results            # list surviving mutants
mutmut show 7             # inspect a specific surviving mutant
```

A surviving mutant such as changing `>` to `>=` in a refund boundary proves the boundary is untested even at 100% line coverage.

**TypeScript equivalent:**

```bash
npx vitest run --coverage --coverage.provider=v8 \
  --coverage.include='src/**' --coverage.exclude='src/**/*.test.ts'
npx stryker run            # mutation testing with a stryker.conf.json
```

```json
{
  "mutate": ["src/pricing/**/*.ts", "!src/**/*.test.ts"],
  "testRunner": "vitest",
  "thresholds": {"high": 80, "low": 60, "break": 50}
}
```

**Dead-code detection before writing tests for it:**

```bash
vulture app --min-confidence 80
npx knip --include files,exports,dependencies
```

```text
# Example finding: app/legacy/price_v1.py:1: unused function 'compute_price_v1' (90% confidence)
# Action: delete the module (and its untested branches) instead of adding tests.
```

**Coverage policy by risk tier (documented, reviewed):**

```markdown
| Tier     | Modules                                  | Metric            | Target |
|----------|------------------------------------------|-------------------|--------|
| Critical | payments, auth, pricing, authorization   | branch + mutation | 90% / 70% mutants killed |
| Core     | orders, inventory, notifications         | branch            | 80%    |
| Support  | admin, reports                           | line              | 60%    |
| Legacy   | legacy/* (frozen)                        | diff only         | 85% on changed lines |
```

## 8. Quality Standards

- Branch coverage is measured; statement-only numbers are not used for gates.
- Generated code, migrations, and type-only branches are excluded explicitly and visibly.
- Per-module coverage is reviewed, not just the aggregate.
- The merge gate is diff coverage; the global number is a trend indicator.
- Critical modules additionally have mutation testing evidence.
- Unreachable code is deleted rather than tested.
- Threshold changes appear in the PR that changes them, with a rationale.
- Coverage failures name the uncovered lines and the behavior they represent.

## 9. Verification and Testing

- Confirm the coverage tool measures branch coverage (check the report contains branch columns).
- Introduce a knowingly untested branch and verify the diff-coverage gate fails.
- Run mutation testing on a critical module and act on at least one surviving mutant by adding a boundary assertion.
- Verify exclusions are intentional by listing them in review; no accidental broad globs.
- Check that a failing test does not still report high coverage (coverage is not correctness).

## 10. Security Considerations

- Coverage reports list internal file paths and branches, which can aid reconnaissance; keep reports private and out of public artifacts.
- Do not upload coverage data from untrusted forks with repository tokens; the `pull_request_target` pattern can leak secrets.
- Security-critical branches (authorization, token validation, path sanitization) need coverage of the *denial* path, not just the allow path.
- Treat "excluded from coverage" as a review flag for security-sensitive code; exclusion there is a red flag, not a convenience.
- Coverage tooling is a supply-chain dependency: pin versions and verify integrity in CI.

## 11. Failure Handling

- **Coverage drops after a refactor:** diff coverage protects the change; review whether deleted tests covered real behavior.
- **Team games the metric:** tests that execute lines without asserting. Mutation testing exposes this; switch the policy to mutation score for critical code.
- **Threshold blocks a legacy migration:** apply diff coverage to changed lines only, with a documented ratchet per module.
- **Mutation runs take hours:** scope to critical modules, run nightly, and parallelize with `--max-children` or per-module jobs.
- **Conflicting numbers between locally and CI:** different Python/Node version or omitted test paths; run the same command and include all test dirs.
- **Dead-code tool floods results:** raise confidence thresholds and fix obvious exports before enforcing in CI.

## 12. Expected Deliverables

1. Coverage configuration (branch mode, exclusions, reports).
2. Risk-tier policy with per-module thresholds.
3. Diff-coverage merge gate.
4. Gap analysis with prioritized modules.
5. Mutation-testing results for critical modules.
6. Dead-code findings and cleanup actions.
7. Trend dashboard or periodic report.

## 13. References

- coverage.py branch coverage — https://coverage.readthedocs.io/en/latest/branch.html
- pytest-cov — https://pytest-cov.readthedocs.io/
- Codecov status checks — https://docs.codecov.com/docs/commit-status
- diff-cover — https://github.com/Bachmann1234/diff_cover
- mutmut — https://github.com/boxed/mutmut
- Stryker Mutator — https://stryker-mutator.io/docs/
- PIT mutation testing — https://pitest.org/
- vulture (dead code) — https://github.com/jendrikseipp/vulture
- knip — https://knip.dev/
- Google Testing Blog, "Code Coverage Best Practices" — https://testing.googleblog.com/2020/08/code-coverage-best-practices.html
