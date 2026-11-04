---
name: onboarding-documentation
description: Get a new engineer to a merged change in their first week—environment setup that works, a guided first task, and the context map that replaces tribal knowledge.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: low
---

# Onboarding Documentation

## 1. Purpose

Reduce time-to-first-meaningful-contribution from weeks to days and stop relying on a specific person being available to explain the system. Onboarding docs fail when they assume a working environment ("just run make"), when the first task is too large to finish, and when nobody checks whether the instructions still work. This skill covers the setup path, the first-week curriculum, the context map, and the feedback loop that keeps docs correct.

**Scope:** your own onboarding material. Access provisioning is security-sensitive: grant least privilege, never share personal credentials, and require MFA and completion of security training before production access.

## 2. Activation Conditions

- New hires, interns, contractors, or team transfers.
- Onboarding takes more than a week to reach a first merge.
- Setup instructions fail or require asking a person.
- After reorganizations or major architecture changes.
- Keywords: onboarding, onboarding docs, developer setup, first PR, dev environment, getting started, ramp-up, context map, buddy, access provisioning, 30/60/90.

## 3. When Not to Use

- Customer-facing getting-started guides (use technical-writing).
- Reference documentation (use technical-writing / api-documentation).
- Formal compliance training curriculums.

## 4. Required Context

1. Team and role the person is joining.
2. Existing tooling: repo, CI, environments, secrets, observability.
3. Access model: who grants repo, cloud, database, and production access, and how.
4. Typical time-to-first-merge and known blockers.
5. Local development support level (laptop specs, OS support).

## 5. Operating Procedure

1. **Start from a clean machine**: write instructions as if nothing is installed, and state supported OS versions explicitly.
2. **Make setup a single verified path**: one script or one ordered list, with expected output after each step and a `doctor` command that validates the environment.
3. **Separate access from code**: a checklist of accounts and permissions with owner and turnaround time, requested on day one (or before day one).
4. **Provide a guided first task** that is real but small: fix a documented typo, add a test, ship a trivial internal change. Aim for a merged PR within the first three days.
5. **Build a context map**: architecture overview (link to C4 container diagram), service catalogue, key repositories, where data lives, where to ask, and what breaks often.
6. **Explain the rituals**: standup, planning, review norms, on-call rotation, incident process, release cadence, and definition of done.
7. **Give a reading path with time estimates**: "30 minutes: architecture; 20 minutes: runbook index; 15 minutes: testing strategy."
8. **Assign a buddy** with explicit responsibilities and a daily 15-minute check-in for the first week.
9. **Collect friction continuously**: a shared doc where the new person logs every stumble, reviewed at the end of week one and fixed the same week.
10. **Track ramp metrics**: time to first PR, time to first merged PR, time to first on-call shadow, and questions repeated across cohorts.
11. **Re-run the path quarterly** or when setup changes; the docs are code and get the same review.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Setup automation | `make bootstrap`, devcontainers, Nix flakes, Docker Compose, `asdf`/`mise` |
| Environment check | custom `doctor` script, `mise doctor`, `devcontainer` checks |
| Docs hosting | repo `docs/onboarding`, wiki, Notion, MkDocs |
| Access requests | IdP groups, access portal, ticket template |
| First tasks | "good first issue" labels, curated backlog |
| Tracking | issue template per cohort, ramp metrics dashboard |

## 7. Practical Implementation

**Onboarding README (the front door):**

```markdown
# Welcome to Payments Platform

You should be able to merge your first change **within three working days**.
If anything here fails, log it in `onboarding-friction.md` and ping your buddy —
a broken step is a bug in these docs, not in you.

## Day 1 — access and environment
- [ ] Accept the GitHub org invite (owner: @platform-admin, ~1h)
- [ ] Request cloud sandbox role `payments-dev` (portal → Access → "Payments dev", ~1 day)
- [ ] Complete security training (required before production read access)
- [ ] Run `make bootstrap && make doctor` → expect `environment OK (12 checks)`
- [ ] Read [architecture overview](/explanation/architecture.md) (15 min)

## Day 2 — the system and your first change
- [ ] Pick a task from the [starter backlog](https://github.com/acme/orders/issues?q=label%3A%22good+first+issue%22)
- [ ] Follow [your first PR](/start-here/first-pr.md) (45 min)
- [ ] Shadow a code review: read the last 5 merged PRs and their comments

## Day 3–5 — go deeper
- [ ] Run one integration test suite locally (30 min)
- [ ] Read [testing strategy](/explanation/testing-strategy.md) (20 min)
- [ ] Pair with your buddy on a real bug
- [ ] Ship it: your first merged PR 🎉

## Where things live
| What | Where |
|---|---|
| Code | `github.com/acme/orders`, `github.com/acme/checkout-web` |
| Deploys | Argo CD `payments-prod`; staging auto-deploys from `main` |
| Dashboards | `grafana/payments` |
| Alerts & runbooks | `#payments-oncall`, [runbook index](/runbooks/index.md) |
| Ask questions | `#payments-help` (no question is too basic) |
| Secrets | 1Password vault `Payments Platform` — never in files or chat |
```

**Environment doctor (checks the things that actually break):**

```python
#!/usr/bin/env python3
"""Verify the developer environment; exit 1 on any failed check."""
import shutil
import subprocess
import sys

CHECKS: list[tuple[str, callable]] = []

def check(name: str):
    def register(fn):
        CHECKS.append((name, fn))
        return fn
    return register

@check("python 3.12+")
def _python():
    out = subprocess.run([sys.executable, "-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert tuple(map(int, out.split("."))) >= (3, 12), f"found {out}"

@check("docker running")
def _docker():
    assert shutil.which("docker"), "docker not installed"
    subprocess.run(["docker", "info"], capture_output=True, check=True)

@check("database reachable")
def _db():
    import os
    assert os.getenv("DATABASE_URL"), "DATABASE_URL not set (copy .env.example)"

@check("migrations applied")
def _migrations():
    subprocess.run(["alembic", "current"], capture_output=True, check=True)

@check("git hooks installed")
def _hooks():
    subprocess.run(["test", "-f", ".git/hooks/pre-commit"], check=True)

def main() -> int:
    failures = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
    print(f"\n{'environment OK' if not failures else f'{failures} check(s) failed'} "
          f"({len(CHECKS)} checks)")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
```

**Guided first PR with exact commands:**

```markdown
# Your first PR (45 minutes)

You will add a missing test for a documented behavior. No prior context needed.

```bash
git clone git@github.com:acme/orders.git && cd orders
git switch -c your-name/first-test
```

1. Open `tests/unit/test_refunds.py`. Note the pattern of the existing tests.
2. Add a test named `test_refund_rejected_when_order_is_cancelled` asserting a
   `RefundError` with message containing "cancelled".

   ```python
   def test_refund_rejected_when_order_is_cancelled():
       policy = RefundPolicy()
       with pytest.raises(RefundError, match="cancelled"):
           policy.refundable(paid=Decimal("100.00"), already_refunded=Decimal("0"),
                             requested=Decimal("10.00"), order_status="cancelled")
   ```

3. Run it: `pytest tests/unit/test_refunds.py -k cancelled -q` → expect it to **fail**
   (the guard does not exist yet — that is the point of the exercise).
4. Implement the guard in `app/services/refunds.py` (3 lines).
5. Run `pytest -m unit -q` and `ruff check .` → both green.
6. Commit with `feat(refunds): reject refunds on cancelled orders`, push, and open the PR.
   Fill the template; request review from your buddy.

**Done when:** CI is green and your buddy approves. Then merge with squash.
```

**Context map (the one-page system overview):**

```markdown
## The system in one page

**Purpose:** accepts orders, applies pricing and inventory checks, and emits lifecycle events.

| Container | Tech | Responsibility | Owns data |
|---|---|---|---|
| `checkout-web` | Next.js 15 | Customer UI | no |
| `orders-api` | FastAPI 0.115 | Order lifecycle, pricing | Postgres `orders` |
| `order-worker` | Celery | Emails, ERP sync, retries | no |
| `events` | RabbitMQ | Domain events | no |

**Where things break (top 3):**
1. DB connection pool saturation at peak → see [runbook](/runbooks/db-pool.md)
2. Provider timeouts during settlement → retries are idempotent, but check `provider_id`
3. Stale cache after admin edits → invalidate with `make cache-flush ORDER=<id>`

**Key decisions:** [ADR index](/explanation/adr/) — start with ADR-0061 (Redis sessions).
**Not obvious:** staging shares the payment provider sandbox; use the `sandbox` key only.
```

**Access checklist with owners and lead times:**

```markdown
| Access | Why | How | Owner | Typical time |
|---|---|---|---|---|
| GitHub org (write) | code | invite after manager approval | @platform-admin | 1 h |
| Cloud `payments-dev` | logs, sandbox deploys | access portal request | @cloud-ops | 1 day |
| Production read-only | incident shadowing | security training + manager | @sre-lead | 2 days |
| 1Password vault | secrets | vault manager invite | @team-lead | 1 h |
| PagerDuty observer | on-call shadowing | team assignment | @sre-oncall | 1 day |
```

**Friction log (the feedback loop):**

```markdown
# Onboarding friction — cohort 2026-11 (Priya)

| Day | Where | Problem | Fix | Fixed by |
|---|---|---|---|---|
| 1 | `make bootstrap` | failed on Ubuntu 24.04 (libpq missing) | added `libpq-dev` to bootstrap + doctor check | @dev-ex (same day) |
| 2 | First PR guide | test file path moved | updated link, added CI check for doc links | @dev-ex (same day) |
| 3 | Access | sandbox key not documented | added §Secrets to README | @team-lead (day 4) |
```

**Ramp metrics reviewed per cohort:**

```text
time_to_first_pr_days          target ≤ 1
time_to_first_merged_pr_days   target ≤ 3
time_to_first_oncall_shadow    target ≤ 30
repeated_questions_top5        drive doc updates each cohort
setup_failures_in_doctor       target 0 by end of each cohort
```

## 8. Quality Standards

- A new engineer can go from zero to a merged PR in three working days following the docs alone.
- Setup is one path with expected outputs; a `doctor` command validates it.
- Supported OS and hardware are stated; unsupported paths are explicitly out of scope.
- Access requests list owners and lead times, and are requested on day one.
- The first task is small, real, and completable without deep context.
- A buddy is assigned with explicit responsibilities and daily contact in week one.
- Context map covers architecture, data ownership, failure modes, and where to ask.
- Every friction item is fixed within the cohort's first week, or has an owner and date.

## 9. Verification and Testing

- Have someone (or a fresh VM/container) follow the setup from scratch and record every deviation.
- Run the `doctor` script on a clean machine; all checks must pass after the documented steps.
- Time the first-PR exercise; if it exceeds 60 minutes, simplify the task.
- Check every link in the onboarding docs with a link checker.
- Survey each cohort at day 5 and day 30; compare against the ramp targets.

## 10. Security Considerations

- Grant least privilege by default; production access follows security training and explicit approval.
- Never share personal accounts, tokens, or credentials; no secrets in docs, shell history examples, or screenshots.
- Sandbox credentials must be separate from production and clearly labelled in docs.
- Onboarding docs often name internal systems and admin URLs; keep them internal.
- Contractors and interns may have different access rules; encode them in the checklist rather than relying on memory.
- Require MFA enrollment and a secrets-manager invitation before any repository access that contains sensitive data.

## 11. Failure Handling

- **Setup breaks after a dependency change:** `doctor` fails in CI on a schedule (a container builds the environment), making drift visible before a new hire hits it.
- **New hire blocked on access:** escalate with the named owner and lead time; track as an onboarding incident.
- **Buddy unavailable:** assign a backup buddy in the plan; async check-ins with a written log as fallback.
- **First task too hard:** keep a curated starter backlog and add "expected time" to each issue.
- **Docs drift:** make the setup path part of CI; the environment build is the test.

## 12. Expected Deliverables

1. Onboarding README with day-by-day plan.
2. Verified setup instructions and `doctor` script.
3. Access checklist with owners and lead times.
4. Guided first-PR exercise.
5. Context map and reading path with time estimates.
6. Buddy responsibilities and check-in schedule.
7. Friction log and ramp metrics per cohort.

## 13. References

- Google, "Onboarding" (engineering practices) — https://abseil.io/resources/swe-book/html/ch03.html
- "The First 90 Days" (Michael Watkins) — ramp frameworks.
- Diátaxis (tutorial vs. how-to distinction) — https://diataxis.fr/
- Devcontainers specification — https://containers.dev/
- Nix flakes — https://nixos.wiki/wiki/Flakes
- mise (tool version manager) — https://mise.jdx.dev/
- Write the Docs, "Documentation Guide" — https://www.writethedocs.org/guide/
