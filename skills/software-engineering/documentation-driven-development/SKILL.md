---
name: documentation-driven-development
description: Write the specification or design doc first, use it to drive implementation and tests, then keep code and docs in lockstep—with templates, review gates, and drift detection.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: low
---

# Documentation-Driven Development

## 1. Purpose

Use a written specification as the primary artifact driving implementation, instead of code first and documentation later (or never). The spec is short, testable, and version-controlled; it defines behavior, error cases, interfaces, and non-goals. This skill solves ambiguity-driven rework, mismatched expectations between stakeholders and engineers, and documentation that lies about what the software does.

## 2. Activation Conditions

- New feature with multiple stakeholders or ambiguous requirements.
- Public API, protocol, or data schema design before implementation.
- Regulated or audited work requiring traceable decisions.
- Distributed team or asynchronous handoff between agents/humans.
- Keyword triggers: spec-first, design doc, RFC, write the doc, requirements, acceptance criteria, contract-first, docstring-driven.

## 3. When Not to Use

- Trivial bug fixes or one-line changes; the commit message is enough.
- Exploratory spikes where the purpose is learning (write a short spike note instead).
- When a spec already exists—update it rather than writing a parallel document.
- As a bureaucratic gate for internal refactors with no external behavior change.

## 4. Required Context

1. The problem statement and who is affected.
2. Existing conventions: repo for docs (`docs/`), RFC process, template in `.github/`.
3. Consumers of the doc: engineers, reviewers, security, product.
4. Definition of done for the feature.
5. Tooling: Markdown, MkDocs, Docusaurus, Sphinx, doc tests.

## 5. Operating Procedure

1. **Create the spec skeleton** in the repository (not a private doc): Problem, Goals, Non-goals, Behavior, API/Data contract, Error cases, Security, Rollout, Test plan, Open questions.
2. **Write behavior as testable statements.** Each acceptance criterion must be verifiable by a test or a manual step with expected outcome.
3. **Define the interface before implementation**: function signatures, HTTP contracts, event schemas, database migrations.
4. **Enumerate error and edge cases** explicitly: empty input, huge input, unauthorized, concurrent modification, timeout.
5. **Get the spec reviewed** by at least one implementer and one consumer; resolve open questions in writing.
6. **Derive tests from the spec** before or alongside implementation (each criterion maps to a test ID).
7. **Implement**, updating the spec if reality demands a change—record the change and the reason in the doc's history.
8. **Annotate code with spec references** (`# See docs/specs/checkout-v2.md#idempotency`) where the logic is non-obvious.
9. **Extract docstrings from the contract** so public functions/docs stay aligned.
10. **Run drift checks**: doc tests for snippets, OpenAPI validation for contracts, and a review checklist item "spec updated?".
11. **Close out**: archive the spec with a status header (`implemented`, `superseded by`), link the PRs.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| Markdown + git | Spec storage and review via PR |
| MkDocs Material / Docusaurus | Rendered docs site |
| Sphinx + `autodoc` | Python API docs from docstrings |
| `doctest`, `pytest --doctest-modules` | Executable examples |
| OpenAPI / JSON Schema | Machine-checkable contracts |
| `markdownlint`, `vale` | Style/lint for docs |
| GitHub RFC template | Structured review workflow |
| `mermaid` | Diagrams inside the spec |

## 7. Practical Implementation

**Spec template (`docs/specs/checkout-v2.md`):**

```markdown
# Checkout v2

Status: draft | review | approved | implemented | superseded
Owner: @team-payments
Last updated: 2026-03-12
Related: ADR-0042, issue #881

## Problem
Checkout retries can produce duplicate charges when the client resubmits after a timeout.

## Goals
- G1: Duplicate submissions with the same idempotency key create exactly one charge.
- G2: p95 checkout API latency < 300 ms at 200 RPS.

## Non-goals
- Multi-currency support (separate spec).
- Saved payment methods.

## Behavior
B1. POST /v1/checkout requires `Idempotency-Key` (>= 8 chars).
B2. Replaying the same key with the same body returns the original response and status 200.
B3. Replaying the same key with a different body returns 409 `idempotency-key-conflict`.
B4. Keys expire after 24 h.

## Error cases
| Case | Status | Body type |
|---|---|---|
| Missing key | 400 | validation-error |
| Key conflict | 409 | idempotency-key-conflict |
| Provider timeout | 504 | provider-unavailable |

## Security
- Key must be bound to the authenticated principal; cross-tenant replay returns 409 without revealing the original.

## Test plan
- T1 (B2): two identical POSTs → one charge row, identical bodies.
- T2 (B3): identical key, changed amount → 409.
- T3 (B1): missing header → 400.
- T4 (security): key reuse across tenants → 409, no data leak.

## Rollout
Feature flag `checkout_idempotency`, 5% → 50% → 100% over 10 days.

## Open questions
- Q1: Should expired keys return 422 or create a new charge? (Owner: @payments, due 2026-03-15)
```

**Executable examples in docs (Python doctest):**

```python
def apply_discount(total_cents: int, percent: int) -> int:
    """Apply a percentage discount, rounding down.

    >>> apply_discount(1000, 15)
    850
    >>> apply_discount(999, 0)
    999
    """
    if not 0 <= percent <= 100:
        raise ValueError("percent must be within 0..100")
    return total_cents * (100 - percent) // 100
```

```bash
pytest --doctest-modules src/ -q
```

**Spec-to-test traceability in test names:**

```python
def test_b2_replay_same_key_returns_original_response():
    ...
def test_b3_replay_same_key_different_body_conflicts():
    ...
```

**Drift check in CI:**

```yaml
- name: Docs lint and doc tests
  run: |
    npx markdownlint-cli2 "docs/**/*.md"
    pytest --doctest-modules src/ -q
    python scripts/check_spec_status.py   # fails if spec says implemented but PRs missing
```

## 8. Quality Standards

- Every behavior statement is testable and has an ID.
- Non-goals are explicit—scope creep becomes visible.
- Specs live in the repo with the code they describe.
- Open questions have owners and dates; none are silently dropped.
- Docs render without broken links (CI link check).
- Code comments referencing the spec stay short and point to anchors.
- Superseded specs are archived, not deleted.

## 9. Verification and Testing

- Acceptance criteria coverage report: each B* maps to at least one test.
- `pytest --doctest-modules` passes.
- Link checker (`lychee`, `markdown-link-check`) clean.
- Reviewer checklist confirms spec, implementation, and tests agree.
- Post-implementation read-through: does the doc describe the system as shipped? Any diff → fix doc or file a bug.

## 10. Security Considerations

- Specs often contain architecture and adversary-relevant detail: apply the same access control as the code repo.
- Never paste real credentials, customer data, or internal hostnames into examples; use placeholders.
- Threat-model sections belong in the spec for anything touching auth, payments, or PII.
- Review specs for instructions that could be interpreted as agent directives when the doc is machine-read; keep normative language clearly separated from examples.
- Public docs must not disclose internal endpoints, rate limits that aid abuse, or vulnerability details before a fix ships.

## 11. Failure Handling

- **Spec becomes stale:** assign doc ownership per module and add the "spec updated?" checkbox to PR templates.
- **Endless spec debate:** timebox to one review cycle; move unresolved items to open questions with a decision owner and a default.
- **Spec too long to read:** split into a one-page summary plus appendices; link the long form.
- **Implementation diverges for good reasons:** amend the spec in the same PR as the code, with a "Deviation" section.
- **Doc tests break on formatting:** keep examples minimal and deterministic (no timestamps, no random IDs).

## 12. Expected Deliverables

- A spec document in the repo with the standard sections and testable criteria.
- Reviewed and approved status with recorded decisions.
- Tests mapped to criteria IDs.
- Executable doc examples that pass in CI.
- Drift-check automation.
- Final status header and links to implementation PRs.

## 13. References

- Diátaxis documentation framework — https://diataxis.fr/
- Python doctest — https://docs.python.org/3/library/doctest.html
- Write the Docs — https://www.writethedocs.org/guide/
- Google Technical Writing course — https://developers.google.com/tech-writing
- RFC process example (Rust) — https://github.com/rust-lang/rfcs
- MkDocs Material — https://squidfunk.github.io/mkdocs-material/
- Vale style linter — https://vale.sh/
