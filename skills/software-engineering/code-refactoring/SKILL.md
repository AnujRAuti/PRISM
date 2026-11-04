---
name: code-refactoring
description: Restructure existing code safely—small, reversible, behavior-preserving steps backed by tests, mechanical verification, and clean commits.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: medium
---

# Code Refactoring

## 1. Purpose

Change the shape of code without changing what it does, in steps small enough that any failure is instantly attributable. This skill supplies the safety protocol (characterization tests, seams, IDE mechanics), the catalogue of concrete moves (extract, inline, move, rename, replace conditional with polymorphism), and the verification loop. It solves the problem of "big-bang rewrites" that stall for months and break production.

## 2. Activation Conditions

- A function/class must change but is untestable, duplicated, or too large.
- Before adding a feature to code you do not understand.
- Merge-conflict-prone hot spots; repeated bug fixes in the same file.
- Framework migrations where behavior must be preserved (e.g. Flask → FastAPI incrementally).
- Keywords: refactor, extract method, legacy, untangle, decouple, split module, strangler, in-place rewrite.

## 3. When Not to Use

- When behavior must change too (that is a feature change; separate the refactor commit).
- When the code will be deleted soon—do not polish dead code.
- When you cannot run the system or tests and have no way to observe behavior; establish observability first.
- As cover for a rewrite the user did not approve. A rewrite is a separate, explicitly authorized decision.

## 4. Required Context

1. Build/test commands and current pass/fail state.
2. How to run the app locally and exercise the target path (seed data, fixtures).
3. Version control state: clean working tree, branch name, ability to revert.
4. Ownership: who reviews changes in this module.
5. Runtime behavior capture options: logs, traces, recorded request/response pairs, production samples (sanitized).

## 5. Operating Procedure

1. **Freeze scope.** Write the exact list of files/units to change and the behavior that must not change.
2. **Baseline.** Run the full test suite and record results. Commit or stash unrelated changes.
3. **Characterization tests.** For uncovered paths, write tests that capture *current* behavior, including quirks. Use recorded inputs (sanitized production samples) plus golden outputs.
4. **Create a seam.** Introduce a thin wrapper or interface so the untested part can be isolated.
5. **Refactor in micro-steps.** One move per commit (extract function → run tests → commit). Use IDE refactorings for mechanical safety.
6. **Verify mechanically.** After each step, diff should be explainable line-by-line; run `git diff --stat` and the test suite.
7. **Use branch-by-abstraction / strangler** for large migrations: new code behind a flag, route a percentage of traffic, then delete the old path.
8. **Compare outputs.** When replacing an algorithm, run old and new implementations side-by-side on the same inputs and diff results (shadow mode).
9. **Delete the scaffolding** when the new path is proven: remove flags, dead branches, and compatibility shims in a dedicated final commit.
10. **Document** the structural change and remaining known issues.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| `git rebase -i`, `git stash` | Small commit series |
| IDE refactorings (JetBrains, VS Code) | Mechanical rename/extract/move |
| `pytest --cov`, `coverage.py` | Spot untested paths |
| Approval tests (`approvaltests`) / golden files | Pin output behavior |
| `hypothesis`, `fast-check` | Differential testing old vs new |
| Feature flags (`unleash`, `LaunchDarkly`, env flags) | Branch by abstraction |
| `git bisect` | Locate the behavior change |
| `radon`, CodeScene | Complexity trends |

## 7. Practical Implementation

**Characterization test with approval/golden output (Python):**

```python
# tests/test_price_characterization.py
from pathlib import Path
import json
from app.pricing import compute_quote  # existing, untested

GOLDEN = Path(__file__).parent / "golden" / "quotes.json"

def test_quotes_unchanged():
    inputs = json.loads((GOLDEN.parent / "inputs.json").read_text())
    actual = [compute_quote(**case) for case in inputs]
    expected = json.loads(GOLDEN.read_text())
    assert actual == expected  # regenerate only with explicit review
```

**Extract + guard clauses (before/after):**

```python
# before
def handle(req):
    if req.get("user"):
        u = req["user"]
        if u.get("role") == "admin":
            if req.get("action") == "delete":
                return do_delete(req["id"])

# after
def handle(req):
    user = req.get("user")
    if not user or user.get("role") != "admin":
        return None
    if req.get("action") != "delete":
        return None
    return do_delete(req["id"])
```

**Branch by abstraction (TypeScript):**

```ts
export interface TaxCalculator { compute(net: number, region: string): number; }

export function createTaxCalculator(flag: boolean): TaxCalculator {
  return flag ? new FlatTaxCalculator() : new LegacyTaxCalculator();
}
```

**Strangler routing at the edge (nginx):**

```nginx
upstream legacy_app { server 10.0.0.11:8080; }
upstream new_app    { server 10.0.0.12:8080; }

location /api/v2/ {
    proxy_pass http://new_app;
}
location /api/ {
    proxy_pass http://legacy_app;
}
```

**Differential test (Python):**

```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=0), st.integers(min_value=1, max_value=10_000))
def test_new_matches_old(basket_value, distance):
    assert quote_new(basket_value, distance) == quote_old(basket_value, distance)
```

## 8. Quality Standards

- Public behavior is identical (or differences are enumerated and approved).
- Each commit is independently reversible and passes tests.
- No mixed commits (refactor + feature + formatting in one commit).
- Coverage on the touched module does not decrease.
- No new TODO markers without an issue link.
- Scalar metrics improve or hold: cyclomatic complexity down, duplicate lines down, import cycles zero.

## 9. Verification and Testing

```bash
pytest -q --cov=app --cov-report=term-missing
git log --oneline -n 20
git diff --stat HEAD~1
```

Additional evidence:
- Side-by-side shadow comparison logs (N requests, 0 diffs).
- Load test before/after when performance is a stated constraint.
- `git bisect run pytest -q` if a regression appears.

## 10. Security Considerations

- Never refactor away input validation, authorization checks, or audit logging—grep for them before and after.
- Preserve exact error semantics: generalized exceptions can leak stack traces where a 404 was previously returned.
- Do not weaken TLS verification, CORS, CSP, or cookie flags "temporarily".
- Recorded production data used for characterization tests must be sanitized (no tokens, PII).
- Feature flags must not grant access to unfinished paths for unauthorized users; gate by role and environment.
- Verify that renamed environment variables do not silently fall back to insecure defaults.

## 11. Failure Handling

- **Tests fail after a "pure" refactor:** revert the commit, inspect the diff for a subtle semantic change (evaluations order, mutability, exception type).
- **No safe seam:** add logging and compare behavior before restructuring.
- **Refactor scope explodes:** stop, split into a plan with phases, and get approval.
- **Performance regression:** measure before/after with the same workload; revert if the regression is unacceptable.
- **Merge conflicts:** rebase frequently, keep commits small; refactor hot files early.

## 12. Expected Deliverables

- Characterization tests (committed) and a baseline test report.
- A series of small, reviewed commits implementing named refactorings.
- Shadow-comparison evidence for replacement of algorithms.
- Summary of structural changes, metrics before/after, and any residual risk.

## 13. References

- Martin Fowler, *Refactoring*, 2nd ed. — https://refactoring.com/catalog/
- Michael Feathers, *Working Effectively with Legacy Code*.
- Martin Fowler, "BranchByAbstraction" — https://martinfowler.com/bliki/BranchByAbstraction.html
- Martin Fowler, "StranglerFigApplication" — https://martinfowler.com/bliki/StranglerFigApplication.html
- Hypothesis documentation — https://hypothesis.readthedocs.io/
- approvaltests — https://github.com/approvals/ApprovalTests.Python
