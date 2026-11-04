---
name: technical-debt-management
description: Identify, quantify, prioritize, and retire technical debt—using interest/principal framing, hotspot analysis, and a tracked repayment plan tied to business risk.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: low
---

# Technical Debt Management

## 1. Purpose

Convert vague "the codebase is a mess" complaints into an ordered, cost-justified backlog of debt items with owners and measurable payoff. Debt that is never measured either gets ignored or becomes an unbounded rewrite. This skill provides classification, quantification (interest paid per sprint vs. principal to fix), prioritization scoring, and repayment tactics that keep delivery flowing.

## 2. Activation Conditions

- Velocity is falling; features take longer each quarter in the same areas.
- Repeated incidents or rollbacks trace to the same modules.
- Migration planning (framework upgrade, language version bump, cloud move).
- Budget or leadership asks: "what is our technical debt and what should we fix first?".
- Keywords: technical debt, tech debt backlog, refactoring backlog, legacy cleanup, hotspot, maintainability, code health.

## 3. When Not to Use

- Fresh codebases with no change history (debt is not yet measurable).
- When the request is a full rewrite proposal—evaluate that separately with risk analysis.
- As a license for unplanned refactors during a release freeze.
- When the real problem is process (no tests, no review) rather than code.

## 4. Required Context

1. VCS history (≥ 6 months) for hotspot analysis.
2. Incident/defect data by module and frequency of change.
3. Current test coverage and build times.
4. Team capacity and next quarter's roadmap.
5. Business-critical modules (revenue, compliance, safety).
6. Existing debt list, if any, to avoid duplication.

## 5. Operating Procedure

1. **Collect signals**, not opinions: change frequency (`git log --numstat`), defect density, coverage gaps, complexity, dependency age, build time, flaky tests, incident tickets per module.
2. **Compute hotspots** (files that are both frequently changed and complex). Those are where debt interest is actually paid.
3. **Classify each item** into: code debt, design debt, test debt, dependency debt, infrastructure debt, documentation debt, data debt.
4. **Quantify interest.** Estimate recurring cost: e.g. "2 h/sprint of incident triage", "40 min extra CI per run", "3 days per feature in this module vs. 1 day elsewhere".
5. **Estimate principal.** Effort to fix, in engineer-days, with a range and the assumption behind it.
6. **Score** with a transparent formula: `priority = (business_impact × change_frequency × risk) / effort`.
7. **Choose a tactic per item:** opportunistic (boy-scout in touched files), scheduled sprint allocation (e.g. 15–20%), dedicated debt sprint, or strangler migration for systemic items.
8. **Set a stopping condition** for each item so it can be closed: "p95 build < 6 min", "zero unhandled promise rejections", "module coverage ≥ 70%".
9. **Attach an owner and a review date**; put the top items into the normal backlog with tickets.
10. **Publish a one-page dashboard** tracking top 10 items, trend of debt metrics, and repayment burn-down.
11. **Prevent new debt:** add fitness functions (coverage gates, dependency rules, complexity ceilings) in CI.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| `git log --format --numstat` / `git-of-theseus` | Churn analysis |
| CodeScene | Hotspot and knowledge-map analysis |
| SonarQube | Maintainability rating, debt ratio |
| `radon`, `lizard` | Cyclomatic complexity |
| `pip-audit`, `npm audit`, `osv-scanner` | Dependency debt |
| `grype`, `trivy` | Image/dependency vulnerabilities |
| Renovate / Dependabot | Automated dependency upgrades |
| `diff-cover`, coverage gates | Test debt prevention |
| Jira/Linear labels | Debt inventory and tracking |

## 7. Practical Implementation

**Churn + complexity hotspot table (Bash + Python):**

```bash
git log --since="12 months ago" --numstat --pretty=format:'' -- '*.py' \
  | awk '{files[$3]+=1; adds[$3]+=$1} END {for (f in files) print files[f], adds[f], f}' \
  | sort -rn | head -25
```

```python
# hotspots.py — join churn with complexity
import subprocess, json, collections, radon.complexity as rc

def churn(root="."):
    out = subprocess.run(
        ["git", "log", "--since=12 months ago", "--numstat", "--pretty=format:"],
        capture_output=True, text=True, cwd=root).stdout
    counts = collections.Counter()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].endswith(".py"):
            counts[parts[2]] += 1
    return counts

def complexity(path):
    with open(path) as fh:
        blocks = rc.cc_visit(fh.read())
    return sum(b.complexity for b in blocks) / max(len(blocks), 1)

scores = []
for path, changes in churn().items():
    try:
        scores.append((changes * complexity(path), changes, round(complexity(path), 1), path))
    except OSError:
        continue
for score, ch, cx, path in sorted(scores, reverse=True)[:15]:
    print(f"{score:9.1f}  churn={ch:3d}  avg_cx={cx:5.1f}  {path}")
```

**Debt register (Markdown table committed in repo):**

```markdown
| ID | Area | Type | Interest / sprint | Principal (days) | Score | Tactic | Owner | Stopping condition |
|----|------|------|-------------------|------------------|-------|--------|-------|--------------------|
| D-01 | checkout/pricing | design | 1.5 d | 6 | 12.5 | Strangler | A. | Pricing rules isolated, 2 variants |
| D-02 | CI pipeline | infra | 40 min/run | 3 | 9.0 | Scheduled | B. | CI wall time < 6 min |
| D-03 | auth middleware | security | 0 d (risk) | 2 | 20.0 | Opportunistic | C. | All routes use single guard |
```

**CI fitness gate (GitHub Actions snippet):**

```yaml
- name: Coverage gate on changed files
  run: diff-cover coverage.xml --compare-branch=origin/main --fail-under=70
- name: Complexity ceiling
  run: |
    radon cc src -n D --total-average -j > cc.json
    python -c "import json,sys; d=json.load(open('cc.json')); sys.exit(1 if d['total_average']>8 else 0)"
```

## 8. Quality Standards

- Every debt item has measurable interest and principal, not adjectives.
- Scores derive from a stated formula any stakeholder can recompute.
- At most 10 active debt items to avoid diffuse effort.
- Each item has an owner, ticket, and stopping condition.
- Repayment is visible in sprint reports (percentage of capacity spent).
- Prevention gates exist in CI so debt inflow slows measurably.

## 9. Verification and Testing

- Recompute the hotspot table after a quarter; hotspot set should shrink.
- Track mean time to change in high-debt modules (lead time from PR open to deploy).
- Track incident count attributable to listed modules.
- Test the fitness gates with a deliberately bad PR to confirm they fail.
- Evidence: before/after dashboards, closed debt tickets, CI gate failure screenshots.

## 10. Security Considerations

- Security debt is never deprioritized behind feature work; separate it into a security track with a fixed deadline.
- Do not defer dependency CVE updates as "debt"—they are incidents with a timeline (see vulnerability-assessment).
- Refactoring must not weaken auth, logging, or validation; review diffs for removed checks.
- Debt dashboards may reveal architecture and weaknesses; keep access internal.
- Avoid running unvetted third-party "code health" tools against private code; check data egress.

## 11. Failure Handling

- **Debt list grows faster than repayment:** cap inflow with fitness gates and mandatory boy-scout rule.
- **Estimates wildly wrong:** start with spikes (≤ 1 day) before committing to multi-week items.
- **Business pushes back:** express as interest in engineer-days per quarter and risks to the roadmap dates.
- **Big rewrite temptation:** prefer strangler; only rewrite with an explicit time-box and a rollback plan.
- **Metric gaming:** balance quantitative metrics with a quarterly manual review.

## 12. Expected Deliverables

1. Debt inventory classified by type with owners.
2. Hotspot report (churn × complexity) with the top 10 files.
3. Quantified interest/principal and a priority score per item.
4. Repayment plan with capacity allocation and calendar dates.
5. Prevention gates added to CI.
6. One-page dashboard for stakeholders.

## 13. References

- Martin Fowler, "TechnicalDebt" — https://martinfowler.com/bliki/TechnicalDebt.html
- Adam Tornhill, *Your Code as a Crime Scene* (hotspot analysis).
- SonarQube metric definitions — https://docs.sonarsource.com/sonarqube/latest/user-guide/metric-definitions/
- CodeScene — https://codescene.com/
- radon — https://radon.readthedocs.io/
- diff-cover — https://github.com/Bachmann1234/diff_cover
- Renovate — https://docs.renovatebot.com/
