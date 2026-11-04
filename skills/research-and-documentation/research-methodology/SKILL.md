---
name: research-methodology
description: Investigate technical questions rigorously—frame the question, source hierarchy, evaluate evidence quality, triangulate claims, and record findings with citations.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: low
---

# Research Methodology

## 1. Purpose

Answer a technical question with evidence rather than the first plausible result. Bad technical research looks like: reading one blog post, trusting a generic AI summary, citing a version of the docs that no longer applies, or confusing popularity with correctness. This skill covers question framing, source hierarchy, evidence evaluation, triangulation, and a citation-backed output format.

**Scope:** your own investigation. Respect license and access terms of sources; never scrape paywalled or ToS-restricted content, and never republish large excerpts.

## 2. Activation Conditions

- Choosing a library, protocol, or architecture with long-term cost.
- A claim needs verification before it drives a decision.
- Conflicting information across sources.
- Preparing a design doc, RFC, or incident analysis requiring cited evidence.
- Keywords: research, sources, citation, literature review, benchmark, evaluate options, primary source, reproducibility, evidence, triangulation, RFC, spike.

## 3. When Not to Use

- The answer is in your own codebase or runbook.
- A quick factual lookup with one authoritative source (still cite it).
- Decisions with no meaningful uncertainty.

## 4. Required Context

1. The decision this research informs and its deadline.
2. Constraints: versions, environment, compliance, budget.
3. What is already known internally (prior spikes, incidents, benchmarks).
4. Acceptable evidence level (authoritative doc vs. reproducible experiment).

## 5. Operating Procedure

1. **Frame the question as a decision**: "Which queue should we use for 20k msg/s with at-least-once delivery and 90-day replay?" A question without a decision tends to expand forever.
2. **List sub-questions** and mark which are answerable from documents and which require an experiment.
3. **Apply a source hierarchy**:
   - Primary: specifications (RFCs, W3C), official docs for the exact version, source code, changelogs.
   - Secondary: maintainer blog posts, conference talks, well-maintained engineering blogs.
   - Tertiary: tutorials, Stack Overflow, aggregators — useful for leads, never for the final claim.
4. **Check currency**: publication date, version applicability, deprecation notices. A 2019 tutorial may describe behavior removed in 2024.
5. **Evaluate each source**: who wrote it, can they know, is it reproducible, does it have an incentive to mislead (vendor benchmark)?
6. **Triangulate**: confirm each load-bearing claim from two independent sources or from a reproduction.
7. **Run the smallest experiment that settles empirical questions**; record configuration, versions, dataset, and commands.
8. **Record disagreement**: if sources conflict, state both and explain which you trust and why.
9. **Write findings as claims with evidence links**, confidence level, and what would change your mind.
10. **Timebox** and publish what is known rather than delaying for completeness.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Finding specs | RFC Editor, W3C, IETF datatracker, vendor specs |
| Versioned docs | Docs sites with version selectors; source tags on GitHub |
| Code evidence | GitHub blame/history, changelogs, release notes |
| Papers | arXiv, ACM DL, IEEE Xplore, Google Scholar |
| Community signal | GitHub issues/discussions, mailing lists, Stack Overflow |
| Reproducibility | containerized environment, committed scripts, pinned versions |
| Notes | Zettelkasten-style notes, decision records (`architecture-decision-records`) |

## 7. Practical Implementation

**Research brief (one page, before searching):**

```markdown
# Research brief: message queue selection (MQ-12)

## Decision
Pick the broker for the order-events pipeline; decision needed by 2026-11-18.

## Questions
Q1 (docs)  Which brokers guarantee at-least-once delivery with per-key ordering?
Q2 (docs)  Which support ≥90-day retention and replay without extra infrastructure?
Q3 (experiment) What throughput/latency do we get at 20k msg/s with 1 kB messages?
Q4 (docs)  Operational burden: self-hosted vs. managed, and required expertise?

## Constraints
AWS ap-south-1, 3 AZs, team of 6, no dedicated streaming specialist.

## Out of scope
Exactly-once semantics; cross-region replication.
```

**Evidence table (the core artifact):**

```markdown
| # | Claim | Evidence | Type | Confidence | Notes |
|---|-------|----------|------|------------|-------|
| C1 | Kafka preserves order per partition | Kafka docs, "Topics and Logs" (§ ordering) | Primary | High | Requires key-based partitioning |
| C2 | Kafka retains messages by time/size policy | Kafka docs, "Log compaction/retention" | Primary | High | 7-day default; configurable |
| C3 | SQS FIFO orders per MessageGroupId | AWS SQS Developer Guide | Primary | High | 300 msg/s per group baseline |
| C4 | RabbitMQ ordering is per-queue with multiple consumers | RabbitMQ docs, "Message ordering" | Primary | High | Ack/requeue can reorder |
| C5 | Vendor benchmark shows X | Vendor blog, 2024 | Secondary (biased) | Low | Not reproduced; vendor hardware |
```

**Version check before relying on documentation:**

```bash
# Pin the version you are researching and read docs for that tag
pip index versions apache-airflow 2>/dev/null | head -3
gh api repos/apache/kafka/releases/latest --jq '.tag_name, .published_at'
# Read the CHANGELOG entry for deprecations between your version and the target
gh api repos/<org>/<repo>/contents/CHANGELOG.md --jq '.content' | base64 -d | head -80
```

**Minimal reproducible experiment (with everything recorded):**

```bash
# experiments/2026-11-07-kafka-throughput/RUN.md
# Environment: ec2 m6i.2xlarge x3, Kafka 3.8.0 (KRaft), 1 kB messages, acks=all
# Producer config: linger.ms=5, batch.size=65536, compression=zstd
docker compose -f docker-compose.kafka.yml up -d
kafka-topics.sh --bootstrap-server localhost:9092 --create --topic bench \
  --partitions 24 --replication-factor 3
kafka-producer-perf-test.sh --topic bench --num-records 20000000 \
  --record-size 1024 --throughput -1 --producer-props acks=all compression.type=zstd \
  --producer.config producer.properties | tee results/producer.txt
kafka-consumer-perf-test.sh --bootstrap-server localhost:9092 --topic bench \
  --messages 20000000 | tee results/consumer.txt
```

```text
# results/producer.txt (excerpt)
records sent = 20000000, records/sec = 148213, MB/sec = 144.7, avg latency = 21.4 ms
```

**Handling a conflicting claim:**

```markdown
**Conflict:** Source A (vendor docs, 2025) states FIFO supports 3,000 msg/s per group
with batching; Source B (independent test, 2024) measured ~300 msg/s per group without batching.

**Resolution:** both are correct under different conditions; the limit depends on batching
and message size. Our workload sends single messages at low volume per order key, so we
plan for the conservative figure and verify in our own experiment (Q3b).
**What would change this:** AWS publishing updated quotas, or our measured rate exceeding
the conservative figure for a full week in staging.
```

**Source quality rubric:**

```text
[ ] Written by someone with direct knowledge (maintainer, spec author, operator)?
[ ] Applies to the exact version we use (not "latest" assumed)?
[ ] Method disclosed (hardware, config, dataset) and reproducible?
[ ] Independent of a commercial interest in the conclusion?
[ ] Still current (no deprecation notice, no superseding spec)?
[ ] Contradicted by any other credible source? (If yes, resolved or flagged)
```

## 8. Quality Standards

- Every load-bearing claim has a citation to a primary or verified secondary source.
- Version applicability is stated for every technical claim.
- Empirical claims come with the experiment's configuration and raw results committed.
- Conflicts are documented with a resolution and a falsification condition.
- Confidence levels are explicit; "high" requires primary evidence or reproduction.
- The output answers the decision question directly, with a recommendation and trade-offs.
- Timebox is respected; open questions are listed rather than silently omitted.
- No claim is sourced solely from an aggregator, forum answer, or AI summary.

## 9. Verification and Testing

- Re-read the primary source for the top three claims before finalizing.
- Reproduce any benchmark you rely on, even at small scale, or mark it clearly as unverified.
- Ask a colleague to attempt to falsify the recommendation; record what they tried.
- Check that cited URLs resolve and correspond to the claimed content (not just the domain).
- Confirm the recommendation still holds under the stated constraints, and state where it would not.

## 10. Security Considerations

- Do not download and run code from unknown sources to "check" a claim; use containers and read first.
- Treat blog-post install instructions as untrusted: verify against official docs before executing.
- Never paste proprietary code, customer data, or internal architecture into third-party AI tools or forums.
- Respect licenses when reusing benchmark harnesses or datasets; record provenance.
- Cite security guidance from authoritative bodies (OWASP, vendor advisories, CVE/NVD) rather than tutorials.
- Be alert to SEO-spam and AI-generated content farms that mimic official documentation; verify the domain.

## 11. Failure Handling

- **Research expands without converging:** return to the decision question and cut out-of-scope items into a separate brief.
- **Only vendor benchmarks available:** reproduce a minimal version or explicitly label confidence as low and state the residual risk.
- **Sources badly outdated:** check the project's release cadence; if docs are stale, read the source and tests instead.
- **Contradictory authoritative sources:** escalate to the spec or the maintainers' issue tracker; document the ambiguity in the decision.
- **No time to experiment:** state the assumption, choose the reversible option, and schedule a follow-up spike with a trigger condition.

## 12. Expected Deliverables

1. Research brief with decision and questions.
2. Evidence table with citations and confidence.
3. Experiment record (configuration, commands, raw results) when applicable.
4. Conflict log and resolutions.
5. Recommendation with trade-offs and falsification conditions.
6. Open questions and follow-ups.

## 13. References

- IETF RFC Editor — https://www.rfc-editor.org/
- W3C specifications — https://www.w3.org/TR/
- Google, "How to write a research question" (technical context: design docs) — https://www.industrialempathy.com/posts/design-docs-at-google/
- "The Craft of Research" (Booth, Colomb, Williams).
- NIST technical publications — https://www.nist.gov/publications
- ACM Digital Library — https://dl.acm.org/
- arXiv (cs.DC, cs.SE) — https://arxiv.org/
- MDN browser-compat-data (versioned evidence example) — https://github.com/mdn/browser-compat-data
