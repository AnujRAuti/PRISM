---
name: technical-research-reports
description: Produce evaluation reports that drive procurement—weighted criteria, reproducible benchmarks, total-cost analysis, risk review, and a defensible recommendation.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: medium
---

# Technical Research Reports

## 1. Purpose

Turn an open-ended "which one should we use?" into a defensible, cited recommendation with reproducible evidence. Evaluation reports go wrong when criteria are chosen after the winner is known, when benchmarks come from vendor blog posts, when licensing and exit costs are ignored, and when the conclusion is "it depends" with no decision. This skill covers criteria design, weighted scoring, hands-on benchmarking, total cost of ownership, risk assessment, and the recommendation format.

**Scope:** your own evaluation. Vendor trial licenses, terms of service, and data-handling agreements apply: never put production data into an evaluation environment without approval, and never publish benchmarks of third-party products in a way that misrepresents their terms.

## 2. Activation Conditions

- Selecting a database, framework, queue, observability stack, or cloud service.
- Build vs. buy analysis.
- Annual vendor renewal with alternatives available.
- A team is split between two options and needs a decision record.
- Keywords: evaluation, comparison, benchmark, TCO, vendor selection, proof of concept, criteria matrix, weighted scoring, build vs buy, due diligence, recommendation.

## 3. When Not to Use

- A single authoritative constraint already decides it (compliance, existing contract).
- Exploratory learning with no decision attached (use research-methodology).
- Pure performance tuning of a system you already chose.

## 4. Required Context

1. The decision, its deadline, and the decision owner.
2. Non-negotiable constraints (compliance, data residency, existing stack, budget).
3. Workload characteristics: volume, latency, consistency, growth.
4. Team skills and operational capacity.
5. Options shortlisted and why.

## 5. Operating Procedure

1. **Define criteria and weights before evaluating anything**, with the decision owner's sign-off. Criteria come from requirements, not from feature lists of a favourite option.
2. **Separate must-haves from scored criteria**: a failed must-have eliminates an option regardless of score (licensing, residency, support model).
3. **Shortlist 3–5 options**, including the current solution and "do nothing" where relevant.
4. **Score with evidence, not impressions**: each cell cites a document, a test, or a quoted vendor commitment with a date.
5. **Benchmark hands-on for load-bearing questions** using your own workload shape; record hardware, versions, configuration, and scripts.
6. **Compute total cost of ownership over 3 years**: licensing, infrastructure, migration effort, training, on-call burden, and exit cost.
7. **Assess operational risk**: maturity, release cadence, community, single-vendor dependency, hiring market, security posture (CVEs, disclosure process), and data-processing terms.
8. **Run sensitivity analysis**: which weights or assumptions would change the winner? If a small change flips the result, say so.
9. **Recommend one option** with conditions ("choose X if the team hires one streaming specialist by Q2; otherwise Y").
10. **Record the decision and its triggers for revisit** ("re-evaluate if monthly cost exceeds ₹X or latency exceeds Y").

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Benchmarking | k6, `pgbench`, YCSB, custom harness with committed scripts |
| Profiling | `pprof`, `py-spy`, flamegraphs |
| Cost modeling | vendor pricing calculators, spreadsheets with assumptions listed |
| Scoring | weighted decision matrix (spreadsheet, or Markdown table for review) |
| Security review | NVD/CVE feeds, `osv-scanner`, vendor security page, SOC 2 reports |
| Licensing | SPDX identifiers, license scanners (`FOSSA`, `ScanCode`) |
| Reproducibility | containers + lockfiles + committed scripts |

## 7. Practical Implementation

**Weighted criteria matrix (the core artifact):**

```markdown
| Criterion | Weight | Option A: Postgres | Option B: ClickHouse | Option C: Managed SaaS |
|---|---|---|---|---|
| Query latency at 5k rps (measured) | 25% | 3 (240 ms p95) | 5 (38 ms p95) | 4 (70 ms p95) |
| Operational burden (team of 6) | 20% | 5 (already run PG) | 2 (new cluster to operate) | 5 (fully managed) |
| Cost over 3 years | 20% | 4 (₹0 new infra) | 3 (₹41L) | 2 (₹1.2Cr) |
| Data residency (ap-south-1 only) | 10% | 5 | 5 | 3 (region limited) |
| Ecosystem & skills | 10% | 5 | 3 | 4 |
| SQL compatibility with existing BI | 10% | 5 | 2 (dialect gaps) | 4 |
| Exit cost / lock-in | 5% | 5 | 4 | 1 (proprietary export) |
| **Weighted total** | 100% | **4.45** | **3.15** | **3.35** |

Scoring rubric: 1 = fails requirement, 3 = meets with meaningful trade-off, 5 = meets with margin.
Every cell must cite evidence in the appendix.
```

**Must-have gate before scoring:**

```markdown
### Must-haves (pass/fail)
| Requirement | Why | A | B | C |
|---|---|---|---|---|
| Runs in `ap-south-1` | Data residency policy | ✅ | ✅ | ⚠️ (limited SKUs) |
| Apache-2.0 or commercial license compatible with redistribution | Legal review | ✅ | ✅ | ❌ |
| Point-in-time recovery < 5 min RPO | Incident policy | ✅ | ✅ | ✅ |
| On-prem option if required later | Strategy | ✅ | ✅ | ❌ |

Option C fails two must-haves and is excluded from scoring, despite competitive pricing.
```

**Benchmark record (reproducible, committed):**

```yaml
# benchmarks/2026-11-analytics-query/RESULTS.yaml
meta:
  date: 2026-11-02
  operator: "@priya"
  question: "Can the candidate store answer our top-5 dashboard queries at p95 < 100 ms under 5k rps?"
environment:
  instance: "m6i.4xlarge (16 vCPU, 64 GiB), gp3 500 GiB, 16000 IOPS"
  dataset: "synthetic events, 400M rows, 180 GiB, 1 kB average payload"
  versions: {postgres: "16.4", clickhouse: "24.8", saas: "2026-10-21 release"}
workload:
  queries: ["top-5 dashboard set (see queries.sql)", "70/20/10 read/write mix"]
  driver: "k6, ramping 500 → 5,000 rps, 10 min steady state"
results:
  postgres: {p50_ms: 61, p95_ms: 240, p99_ms: 610, error_rate: 0.002, cpu_pct: 93}
  clickhouse: {p50_ms: 9, p95_ms: 38, p99_ms: 95, error_rate: 0.000, cpu_pct: 41}
  saas: {p50_ms: 18, p95_ms: 70, p99_ms: 210, error_rate: 0.000, cpu_pct: null}
caveats:
  - "Postgres result is at saturation; adding a read replica would roughly halve p95 (untested)."
  - "SaaS latency measured from `ap-south-1` over public internet; private link not evaluated."
```

**Three-year TCO model with assumptions visible:**

```markdown
| Cost line | Year 1 | Year 2 | Year 3 | 3-yr total | Assumption |
|---|---|---|---|---|---|
| Infrastructure | ₹14.0L | ₹14.0L | ₹14.0L | ₹42.0L | 3 × m6i.4xlarge + 500 GiB gp3 |
| Licences | ₹0 | ₹0 | ₹0 | ₹0 | Apache-2.0 |
| Migration effort | ₹8.0L | — | — | ₹8.0L | 4 eng-weeks @ ₹2L/week fully loaded |
| Training | ₹1.5L | — | — | ₹1.5L | 3 engineers, 1 week each |
| On-call load | ₹4.0L/yr | ₹4.0L/yr | ₹4.0L/yr | ₹12.0L | +15% pager hours vs. current |
| **Total** | | | | **₹63.5L** | excludes opportunity cost |
```

```text
Assumptions to challenge:
- Cloud pricing as of 2026-10-15; no reserved-instance discount applied (would reduce ~30%).
- On-call uplift estimated from the team's last two quarters of pager data.
- Migration effort excludes the BI re-write (scoped separately as BI-2210).
```

**Sensitivity analysis (what flips the decision):**

```markdown
| Assumption | Base | Stress | Winner changes? |
|---|---|---|---|
| Sustained traffic | 5k rps | 15k rps | Yes — Postgres saturates; B wins |
| Team size | 6 engineers | 3 engineers | Yes — operational burden dominates; C wins |
| Data residency scope | India only | Global | No — B still needs regional clusters |
| Contract length | 1 year | 3-year commit | Yes — C's discount beats B on TCO |

**Conclusion:** the recommendation holds for the stated assumptions, and the two triggers
to revisit are traffic > 10k rps or the team dropping below 4 engineers.
```

**Risk register with vendor due diligence:**

```markdown
| Risk | Category | Likelihood | Impact | Evidence | Mitigation |
|---|---|---|---|---|---|
| Single-vendor dependency | Strategic | Medium | High | Only 1 managed provider in region | Keep schema open-standard; export tooling tested |
| Operational gap (no in-house ClickHouse) | Execution | High | Medium | Team survey: 1/6 used it | Hire or contract 1 specialist before Q2 |
| CVE response lag | Security | Low | High | 2 advisories in 12 mo, patched in 9 and 21 days | Subscribe to vendor advisory feed; pin versions |
| Support SLA mismatch | Commercial | Medium | Medium | Vendor SLA 99.9%, ours 99.95% | Negotiate credit terms or add redundant path |
```

**Recommendation block (what the reader needs):**

```markdown
## Recommendation
Adopt **Option B (ClickHouse, self-managed in `ap-south-1`)** for the analytics store.

**Why:** it is the only option that meets the p95 < 100 ms target at 5k rps on our
dashboard workload (measured: 38 ms p95) within the data-residency constraint, at 1.9×
the three-year cost of staying on Postgres but 47% below the managed alternative.

**Conditions:**
1. One engineer completes ClickHouse operations training before the first production cluster.
2. A quarterly re-evaluation of cost and latency; revisit if traffic exceeds 10k rps.

**Decision owner:** @data-platform-lead. **Due:** 2026-11-18. **Links:** RFC-0158, benchmarks, TCO sheet.
```

## 8. Quality Standards

- Criteria and weights are agreed before evaluation and documented.
- Must-haves gate options before scoring; failures are explicit.
- Every score cites evidence (documentation, test, quote with date).
- Benchmarks are reproducible: committed scripts, versions, hardware, dataset, and raw output.
- TCO covers three years and includes migration, training, operations, and exit.
- Sensitivity analysis names the assumptions that would flip the decision.
- Risks have likelihood, impact, evidence, and mitigation.
- The report makes one recommendation with conditions and a decision owner.

## 9. Verification and Testing

- Re-run a benchmark from the committed scripts on a fresh environment; results within ±15%.
- Have a reviewer attempt to break the scoring by re-weighting: is the conclusion robust?
- Verify each vendor claim cited with a link and date; re-check anything older than six months.
- Confirm TCO arithmetic by recomputing totals independently.
- Check license obligations against legal review, not just the project's claim.

## 10. Security Considerations

- Do not load production data into evaluation environments; use synthetic or properly de-identified data under agreement.
- Review the vendor's security posture: SOC 2/ISO 27001 reports, vulnerability disclosure policy, data-processing agreement, sub-processors, and breach notification terms.
- Check data residency and encryption (at rest, in transit, key management) against policy.
- Evaluate the software's supply chain: signed releases, dependency hygiene, CVE history, and maintainer concentration.
- Trial licenses and terms may forbid publishing benchmark results; confirm before sharing externally.
- Self-hosted open-source options shift patching responsibility to you; state who owns it.

## 11. Failure Handling

- **Criteria disputed after results:** return to the decision owner; do not retro-fit weights to a favourite.
- **Benchmarks inconclusive:** state the uncertainty, choose the reversible option, and define the trigger for a deeper test.
- **Vendor declines a needed commitment:** record it as a risk, not a footnote; absence of a commitment is evidence.
- **Evaluation exceeds its timebox:** narrow to the criteria that can change the decision and explicitly mark the rest as unknown.
- **Team disagrees with the recommendation:** publish the matrix and evidence; disagreement without counter-evidence is a decision, not a data problem.

## 12. Expected Deliverables

1. Criteria and weights with sign-off.
2. Must-have gate results.
3. Scored matrix with cited evidence.
4. Benchmark record (scripts, config, raw results).
5. Three-year TCO with assumptions.
6. Risk register and vendor due diligence.
7. Sensitivity analysis and revisit triggers.
8. Recommendation with conditions and owner.

## 13. References

- "Architecture Decision Records" (for recording the outcome) — https://adr.github.io/
- YCSB benchmark framework — https://github.com/brianfrankcooper/YCSB
- k6 load testing — https://grafana.com/docs/k6/latest/
- `pgbench` — https://www.postgresql.org/docs/current/pgbench.html
- SPDX license list — https://spdx.org/licenses/
- OSV vulnerability database — https://osv.dev/
- NIST SP 800-53 (security control considerations for vendor review) — https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- Gartner-style TCO methodology (general practice; apply your own assumptions).
