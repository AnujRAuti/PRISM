---
name: rfc-and-design-docs
description: Write design documents and RFCs that drive decisions—problem framing, alternatives, trade-offs, rollout and rollback, and a review process with a clear outcome.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: low
---

# RFC and Design Docs

## 1. Purpose

Get a technical decision made, reviewed, and remembered. A design doc is not a specification of code you already wrote; it is a decision instrument: here is the problem, the constraints, the options, the trade-offs, the chosen path, and how it will be rolled out and rolled back. This skill covers structure, alternatives analysis, review mechanics, and the lifecycle that turns a doc into an accepted decision.

**Scope:** your own organization's documents. Design docs often describe unpatched weaknesses and internal topology—set access appropriately and never publish them externally.

## 2. Activation Conditions

- A change is cross-team, hard to reverse, or expensive.
- Multiple plausible approaches compete.
- New service, data model change, API version, or migration.
- A decision will be questioned in six months ("why did we do this?").
- Keywords: design doc, RFC, technical spec, proposal, alternatives, trade-offs, review, decision record, rollout plan, rollback, stakeholder sign-off.

## 3. When Not to Use

- Small, local, reversible changes (a PR description suffices).
- Purely exploratory spikes (use a research brief).
- Decisions already accepted and recorded (reference the ADR; do not re-litigate silently).

## 4. Required Context

1. Problem and its cost (incidents, revenue, velocity).
2. Constraints: deadlines, compliance, team size, existing systems.
3. Stakeholders who must consent (security, data, SRE, product).
4. Prior art inside and outside the organization.
5. Review timeframe and the decision owner.

## 5. Operating Procedure

1. **Write a one-paragraph summary and the decision requested** at the top. Reviewers should know within a minute what they are being asked to approve.
2. **State the problem in measurable terms**: "p99 checkout is 2.4 s; 8% of carts abandon after the payment step times out." Avoid solution-flavored problem statements.
3. **List constraints and non-goals** explicitly; non-goals prevent scope creep in review.
4. **Present at least two credible alternatives**, including "do nothing" and the simplest option. An alternatives section with one option is a rubber stamp.
5. **Analyze trade-offs on named axes** (cost, latency, operational burden, security, migration risk, team familiarity). Use a table, not prose.
6. **State the decision and its rationale**, and who decided it.
7. **Design the change at the level reviewers need**: data model, interfaces, failure behavior, and security boundaries. Include diagrams for anything with more than three components.
8. **Specify rollout**: stages, flags, metrics to watch, checkpoint criteria, and the audience percentage over time.
9. **Specify rollback**: exact steps, data implications, and whether the change is reversible. If not reversible, say so loudly.
10. **Define observability and SLOs** for the new component, plus alerts and dashboards to create.
11. **Estimate cost and effort** with ranges, and name the risks with mitigations.
12. **Circulate for review with a deadline**, comments in the doc, and a recorded resolution for each objection.
13. **Freeze and record the outcome**: accepted / rejected / deferred, the date, approvers, and any conditions. Link the implementation PRs and, later, an ADR if the decision is architectural.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Authoring | Google Docs (comment-first), Markdown in repo, Notion |
| Diagrams | Mermaid, Excalidraw, draw.io |
| Review | Comment threads, review meeting for contested items |
| Decision record | `architecture-decision-records`, docs/adr/ |
| Templates | Organization doc template with required sections |

## 7. Practical Implementation

**Design doc template:**

```markdown
# RFC-0142: Move checkout session state to Redis

| Field | Value |
|---|---|
| Author | @priya |
| Reviewers | @sre, @security, @payments-lead |
| Status | In review → Accepted |
| Decision owner | @payments-lead |
| Review deadline | 2026-11-12 |
| Links | JIRA PAY-881, ADR-0061 |

## Summary
Store checkout session state in Redis with a 30-minute TTL instead of the
`checkout_session` table, cutting p99 checkout latency and removing DB write spikes.

## Problem
- p99 `POST /checkout/step` is 2.4 s (SLO 800 ms); 62% of that time is DB writes to
  `checkout_session` (pg_stat_statements, 30-day window).
- At 4× traffic during sales, the table drives connection-pool saturation (incident INC-4711).

## Goals
- p99 checkout step < 500 ms at 3× current peak.
- No session loss on single-node failure.
## Non-goals
- Reworking the payment provider integration.
- Multi-region checkout.

## Constraints
- India region only; session data may not leave `ap-south-1` (compliance).
- Must ship before the December sale freeze (2026-12-01).

## Alternatives

| Option | Latency | Ops burden | Failure mode | Cost/mo | Verdict |
|---|---|---|---|---|---|
| A. Keep Postgres, add index + partition | ~1.6 s | Low | Still pool-bound at peak | ~₹0 | Insufficient |
| B. Redis with TTL + DB audit trail | ~300 ms | Medium (new datastore) | Session loss if Redis flushed | ~₹18k | **Chosen** |
| C. Signed client-side cookies | ~50 ms | Low | Cookie size limits; tamper surface | ₹0 | Rejected (size, security) |
| D. Do nothing | 2.4 s → worse | None | SLO breach continues | ₹0 | Rejected |

## Design

```mermaid
flowchart LR
  web[checkout-web] --> api[checkout-api]
  api -->|HSET session:{id} EX 1800| redis[(Redis, AOF + replica)]
  api -->|append audit| pg[(checkout_audit)]
  redis -.replica.-> redisr[(Redis replica, other AZ)]
```

- Key: `sess:{tenant}:{id}`, value: hash of step/fields, TTL 30 min sliding on write.
- Redis: AOF `everysec`, one replica in a second AZ, eviction `noeviction` for this instance.
- Fallback: on Redis unavailability, read-through to Postgres and rebuild the key (degraded, ~1.6 s).
- Audit rows appended asynchronously; loss tolerated (analytics only).

## Failure behavior
| Failure | Behavior | Detection |
|---|---|---|
| Redis primary down | Failover to replica (≈15 s); requests may retry | `redis_up` alert |
| Redis fully unavailable | Fallback to Postgres path; latency SLO at risk | `checkout_fallback_rate > 1%` |
| Session key expired mid-flow | Client re-fetches from Postgres snapshot | `session_rebuild_total` |

## Rollout
1. Ship dual-write (Postgres + Redis) behind `checkout_redis_read` flag at 0%.
2. 1% → 5% → 25% → 100% over 5 days; checkpoints: p99 < 600 ms, error rate ≤ baseline, rebuild rate < 0.5%.
3. Stop writing `checkout_session` after 14 days at 100%; drop the table after 30.

## Rollback
- Set `checkout_redis_read` to 0 → all reads return to Postgres. Reversible within minutes.
- Dual-write remains during the entire rollout, so no data loss.
- After table drop (step 3, +30 days) rollback requires a restore: explicitly out of scope.

## Observability
- Metrics: `checkout_step_duration_seconds`, `checkout_fallback_total`, `redis_session_rebuild_total`.
- Alerts: fallback rate > 1% for 5 min; p99 > 800 ms for 10 min.

## Cost and effort
- Redis (cache.r7g.large + replica): ≈₹18,000/mo. Effort: 3 engineers × 2 weeks (range 1.5–3).

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Redis failover drops sessions | Medium | Medium | AOF everysec + client retry with idempotent step writes |
| Compliance review flags new datastore | Low | High | Store only session IDs/step data, no PII beyond cart refs |

## Open questions
- [ ] @security: is 30-min TTL acceptable for abandoned-cart data retention? (owner: @security, due 11-11)
```

**Review mechanics that produce decisions:**

```markdown
## Review log
| Reviewer | Comment | Resolution | Status |
|---|---|---|---|
| @sre | Who pages on Redis failover? | Same on-call as payments; runbook §4 added | Resolved |
| @security | Session data retention policy | Shortened TTL to 30 min; no PII stored | Resolved |
| @payments-lead | Prefer option A for cost | A insufficient at peak (evidence §Problem); accepted risk of new datastore | Accepted risk |
```

```text
Process rules
1. Comment in the doc, not in chat threads.
2. Every objection gets a resolution: changed, declined with reason, or deferred with owner/date.
3. The decision owner states the outcome in the doc; silence is not consent.
4. Review window is 3 business days; no response means no objection only if the doc says so.
```

**Status header discipline:**

```markdown
Status: Draft → In review → Accepted (2026-11-12) → Implemented (PR #8812, #8840) → Superseded by RFC-0167
```

**Filled ADR generated from an accepted RFC:**

```markdown
# ADR-0061: Redis for checkout session state

- Status: Accepted
- Date: 2026-11-12
- Deciders: @payments-lead, @sre-lead, @security-lead
- RFC: RFC-0142

## Context
Checkout session writes dominated p99 latency and caused pool saturation (INC-4711).

## Decision
Session state lives in Redis with a 30-minute TTL; Postgres retains an audit trail only.

## Consequences
- Positive: p99 checkout step ~300 ms; DB write load removed at peak.
- Negative: new stateful dependency in the critical path; failover can drop in-flight sessions.
- Follow-ups: runbook §4, dashboard `checkout-sessions`, quarterly datastore review.
```

## 8. Quality Standards

- Summary and requested decision appear before any detail.
- Problem is measurable and free of embedded solutions.
- At least two credible alternatives, including the simplest and "do nothing", with a trade-off table.
- Rollout has stages, checkpoints, and metric thresholds; rollback has exact steps.
- Non-goals and out-of-scope items are explicit.
- Security, privacy, and data-residency implications are addressed, not implied.
- Every reviewer objection has a recorded resolution.
- The outcome, approvers, and date are recorded; implementation links are added later.

## 9. Verification and Testing

- **Pre-mortem test**: ask "if this fails in six months, why?" and confirm the doc names that risk with a mitigation.
- Reviewer comprehension test: a non-author should be able to summarize the decision and top risk after 5 minutes.
- Verify rollback instructions by rehearsing them in staging (where feasible) and recording the result.
- Check that quoted metrics have a source and a date; re-run the query if stale.
- Confirm the doc's status matches reality (accepted docs should link to their implementation).

## 10. Security Considerations

- Design docs describe internal topology and unpatched weaknesses; restrict access to the organization or the specific reviewers.
- Include a threat-model section for changes touching auth, payments, PII, or external input: trust boundaries, new attack surface, and mitigations.
- Never include live secrets, tokens, or production connection strings in examples.
- Call out data-classification changes (new datastore, new fields) so privacy review is triggered early.
- Document security trade-offs explicitly; "we skipped rate limiting to ship" belongs in the Risks table, not in a chat.
- Vendor choices involve supply-chain and data-processing implications; note the review status.

## 11. Failure Handling

- **Review stalls:** set a deadline, name a decision owner, and state the default if no response (usually "defer").
- **Doc becomes a spec of code already written:** reframe as a decision record; state what is reversible and what is not.
- **Endless alternatives:** cap at four; more options means the problem is not framed.
- **Disagreement without progress:** escalate to a single decision owner, record the dissent, and move on; dissent is valuable, deadlock is not.
- **Implementation diverges from the doc:** update the doc or write a superseding RFC; never let the doc silently mislead.

## 12. Expected Deliverables

1. RFC/design doc with summary, problem, goals, non-goals, alternatives, design, rollout, rollback.
2. Trade-off table with named axes.
3. Failure-behavior matrix.
4. Observability and alert plan.
5. Cost/effort estimate with ranges.
6. Risk register with mitigations.
7. Review log with resolutions and recorded outcome.
8. Follow-up ADR when the decision is architectural.

## 13. References

- Google, "Design Docs at Google" (Malte Ubl) — https://www.industrialempathy.com/posts/design-docs-at-google/
- Rust RFC process — https://github.com/rust-lang/rfcs
- Kubernetes Enhancement Proposals (KEP) template — https://github.com/kubernetes/enhancements/tree/master/keps
- "Design Docs, ADRs, and RFCs" (Michael Nygard on ADRs) — https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- ADR GitHub organization — https://adr.github.io/
- "Writing Technical Design Docs" (AWS Prescriptive Guidance) — https://docs.aws.amazon.com/prescriptive-guidance/latest/arch-decision-records/welcome.html
