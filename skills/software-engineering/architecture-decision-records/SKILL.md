---
name: architecture-decision-records
description: Capture architecture decisions as immutable, numbered ADRs with context, options, consequences, and status—making trade-offs reviewable and reversible.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: low
---

# Architecture Decision Records

## 1. Purpose

Record *why* a significant technical decision was made, what alternatives were rejected, and what consequences follow—in a short, numbered, immutable document stored beside the code. ADRs solve decision amnesia: six months later nobody remembers why Kafka was chosen, so a new team either keeps an obsolete choice forever or reverses it by accident. This skill covers when an ADR is warranted, the exact structure, review flow, supersession, and tooling.

## 2. Activation Conditions

- Choosing a database, messaging system, framework, cloud service, or protocol.
- Changing a public contract, data model, or security model.
- Accepting a known technical debt or constraint with a deadline.
- Reversing a prior decision (must supersede an ADR, not delete it).
- Keywords: ADR, decision record, design decision, RFC, "why did we", trade-off documentation, supersede.

## 3. When Not to Use

- Reversible, low-impact changes (naming a variable, choosing a lint rule).
- Standard implementation details already covered by guidelines.
- As a substitute for a full design doc on a multi-week project (use both; ADR records the decision, not the design).
- Multiple ADRs for one decision; one decision = one ADR.

## 4. Required Context

1. The decision to be made and its deadline.
2. Forces at play: cost, latency, team skills, compliance, vendor lock-in, timeline.
3. Realistic options (at least two, including "do nothing" if viable).
4. Existing ADRs that constrain or relate to this choice.
5. Decision owner and stakeholders who must be consulted.
6. Reversibility: cost to undo, and the trigger that would cause reconsideration.

## 5. Operating Procedure

1. **Confirm an ADR is warranted** using the activation conditions; otherwise write a PR description instead.
2. **Assign the next number** (zero-padded, monotonic; never reuse).
3. **Write Context** as observable facts, not opinions: constraints, scale figures, deadlines, prior decisions.
4. **List Options** with honest pros/cons. Include the status quo.
5. **State the Decision** in one or two sentences, active voice ("We will use PostgreSQL 16 as the primary store for orders").
6. **Record Consequences**: positive, negative, risks, and follow-up actions. Include what becomes harder.
7. **Set Status**: proposed → accepted → (superseded by NNNN | deprecated). Mark acceptance date.
8. **Circulate for review**; resolve objections in the ADR's "Discussion" or link the PR thread.
9. **Commit with the code**, in `docs/adr/` or `docs/decisions/`.
10. **Link from code and docs** where relevant (`# See ADR-0042`).
11. **On reversal**, create a new ADR that supersedes the old one; update the old one's Status line only.
12. **Review the index** quarterly; close decisions whose context no longer holds.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| Markdown files in `docs/adr/` | Simplest, version-controlled |
| `adr-tools` (Nat Pryce) | CLI for numbering/index |
| MADR template | Structured template with options |
| Log4Brains | ADR site with publishing and search |
| `adr-viewer` | HTML render of ADR directory |
| Structurizr / C4 | Link decisions to architecture diagrams |
| GitHub PR reviews | Decision discussion trail |

## 7. Practical Implementation

**Directory layout:**

```
docs/adr/
├── README.md            # index + conventions
├── 0001-record-architecture-decisions.md
├── 0002-use-postgresql-for-orders.md
├── 0003-event-bus-kafka-vs-nats.md
└── 0004-supersede-kafka-with-nats.md
```

**ADR template (MADR-style, complete example):**

```markdown
# ADR-0003: Event bus selection for order events

- Status: accepted
- Date: 2026-03-10
- Deciders: @alice (platform), @bob (payments)
- Consulted: @carol (SRE), @dan (security)
- Supersedes: —
- Superseded by: —

## Context and Problem Statement
Order events (created, paid, shipped) must reach inventory, notification, and analytics
consumers. Expected volume 4k msg/s peak, 300 msg/s average, retention 7 days for replay,
at-least-once delivery required, operational team has no Kafka experience.

## Decision Drivers
- Retention and replay capability
- Operational burden for a 4-person platform team
- Exactly-once *effects* achievable via idempotent consumers
- Managed offering availability in our cloud region

## Considered Options
1. Apache Kafka (managed MSK)
2. NATS JetStream
3. PostgreSQL outbox + polling workers only
4. RabbitMQ with quorum queues

## Decision Outcome
Chosen: **NATS JetStream**, because it provides stream retention with replay, has a small
operational surface, and its managed offering costs ~40% less than MSK at our volume.

### Positive Consequences
- Replay of up to 7 days supported by stream retention.
- Single binary; team can operate it without new tooling.
- Lower infra cost at current volume.

### Negative Consequences
- Smaller ecosystem than Kafka; fewer connectors.
- Very high throughput (>100k msg/s) would require re-evaluating.
- Key-based ordering limited to subject partitioning rules; document consumer assumptions.

## Pros and Cons of the Options
### Kafka
- Good: ecosystem, connectors, proven at scale; Bad: ops complexity, cost at low volume.
### NATS JetStream
- Good: simple, cheap, retention; Bad: smaller ecosystem, fewer managed options.
### Postgres outbox only
- Good: no new infra; Bad: retention/replay awkward, polling overhead, poor fan-out.
### RabbitMQ
- Good: mature, flexible routing; Bad: retention for replay weak, ops overhead.

## Follow-ups
- [ ] Benchmark at 2× expected peak (issue #910)
- [ ] Document consumer idempotency requirement (link ADR-0005)

## Links
- Design doc: docs/design/order-events.md
```

**ADR index (`docs/adr/README.md`):**

```markdown
# Architecture Decision Records

| ID | Title | Status | Date |
|----|-------|--------|------|
| 0001 | Record architecture decisions | accepted | 2025-11-02 |
| 0002 | Use PostgreSQL for orders | accepted | 2026-01-14 |
| 0003 | Event bus selection | accepted | 2026-03-10 |
```

**Superseding an ADR:**

```markdown
# ADR-0004: Replace NATS JetStream with managed Kafka

- Status: accepted
- Date: 2026-09-01
- Supersedes: ADR-0003
```

and in ADR-0003 only the status line changes:

```markdown
- Status: superseded by ADR-0004
```

**adr-tools usage:**

```bash
brew install adr-tools          # or: apt install adr-tools
adr init docs/adr
adr new "Use PostgreSQL for orders"
adr new -s 3 "Replace NATS with Kafka"
adr list
```

## 8. Quality Standards

- One decision per ADR; the title is a decision, not a topic.
- Context states facts with numbers, not adjectives.
- At least two options are evaluated; the rejected reasons are specific.
- Consequences include the negative ones—an ADR with only benefits is marketing.
- Status is always present and current.
- ADRs are immutable after acceptance except for the Status line and links.
- Numbering has no gaps; superseded records remain in the repo.

## 9. Verification and Testing

- Index matches the directory (script check in CI).
- Every ADR has required front-matter fields.
- Links resolve (link checker).
- Code references to ADRs point at existing files.
- Review at each architecture review meeting: decisions older than a year are re-validated or marked deprecated.

```bash
python - <<'PY'
import pathlib, re, sys
adrs = sorted(pathlib.Path("docs/adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
missing = [p.name for p in adrs if "- Status:" not in p.read_text()]
print("missing status:", missing)
sys.exit(1 if missing else 0)
PY
```

## 10. Security Considerations

- ADRs may disclose architecture weaknesses: keep them in the same access-controlled repo as code, not a public wiki.
- Never include credentials, internal hostnames, or customer names; use roles and placeholders.
- Security decisions (crypto choices, auth flows) require a security reviewer listed under Consulted.
- Record the threat model or trust boundaries when the decision affects them.
- If an ADR includes an accepted risk, state the compensating control and review date explicitly.

## 11. Failure Handling

- **Decision made without an ADR:** write it retroactively, marked as `accepted (retroactive)`, noting the date of the actual decision.
- **Disagreement blocks progress:** record the majority decision plus a "Dissent" section; escalation owner named.
- **ADR becomes obsolete:** mark `deprecated` with a one-line reason; do not delete.
- **Too many trivial ADRs:** raise the bar—decisions that cost > 1 day to reverse or affect > 1 team.
- **ADR contradicts code:** code is wrong or the ADR is stale; open a ticket either way and link it in the ADR.

## 12. Expected Deliverables

- A numbered ADR in `docs/adr/` using the standard template.
- Updated index/README.
- Status set and reviewers recorded.
- Links from relevant code/docs.
- Follow-up tasks filed for consequences requiring action.
- Supersession chain when replacing a prior decision.

## 13. References

- Michael Nygard, "Documenting Architecture Decisions" — https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- MADR — Markdown Any Decision Records — https://adr.github.io/madr/
- ADR organization and templates — https://adr.github.io/
- adr-tools — https://github.com/npryce/adr-tools
- Log4Brains — https://github.com/thomvaill/log4brains
- AWS Prescriptive Guidance — ADR process — https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/
