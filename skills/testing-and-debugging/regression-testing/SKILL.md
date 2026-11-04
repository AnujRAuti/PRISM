---
name: regression-testing
description: Build regression suites that actually prevent recurrences—bug-reproducing tests, snapshot baselines, upgrade matrices, and the policy that keeps old bugs fixed.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Regression Testing

## 1. Purpose

Guarantee that fixed bugs stay fixed and that untouched behavior survives change. Regression testing is not "re-run everything"; it is a curated set of tests tied to real past failures plus a policy that every bug fix ships a failing-first test. This skill covers converting incidents into tests, snapshot/golden-master baselines, upgrade and migration regression matrices, and governance for suite growth.

**Scope:** your own code and environments. Golden-master baselines may contain production-derived data—use synthetic data or sanitize before committing.

## 2. Activation Conditions

- A production bug was fixed and needs a permanent guard.
- A refactor or dependency upgrade risks silent behavior change.
- Legacy system needs characterization before modernization.
- Regression suite is huge, slow, or full of duplicates.
- Keywords: regression test, regression suite, bug reproduction, golden master, characterization test, snapshot, approval test, upgrade matrix, backward compatibility, replay, differential testing.

## 3. When Not to Use

- Verifying new functionality (that is feature testing).
- Catching unauthorized UI changes only (use visual-regression-testing).
- Load/capacity questions (use performance-and-load-testing).

## 4. Required Context

1. Incident and bug history with severity.
2. Code areas with high change frequency (churn) and high risk.
3. Existing suites and their overlap.
4. Release cadence and upgrade dependencies (languages, frameworks, DB).
5. Data availability for golden masters and replay.

## 5. Operating Procedure

1. **Write the failing test first** for every bug fix: reproduce the bug on the current code, watch it fail, then fix and watch it pass. Commit both together.
2. **Name the test after the bug**, including the ticket ID, so future readers know why it exists (`test_refund_3456_rejects_amount_over_remaining`).
3. **Keep reproductions minimal**: the smallest input that triggers the bug, at the lowest layer that can catch it.
4. **Use characterization tests for legacy code**: capture current behavior (including quirks) before refactoring, then assert it is preserved.
5. **Adopt golden-master/approval tests** for large outputs (report rendering, serializers, generated files), with reviewable diffs and committed baselines.
6. **Maintain an upgrade matrix** for language/runtime/framework/DB versions and run the suite against supported combinations.
7. **Add differential tests** where old and new implementations coexist: run both, compare outputs on real input samples.
8. **Curate the suite**: remove tests that duplicate a lower-level test, and delete tests for removed features within the same PR.
9. **Tag regression tests** so you can run a fast targeted subset during hotfixes.
10. **Review suite growth quarterly** against incident recurrence: if the same class of bug recurs, the tests are at the wrong layer.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Failing-first workflow | pytest, vitest, any runner |
| Golden master | ApprovalTests, `syrupy`, Jest snapshots, custom file comparisons |
| Characterization | Recorded input/output corpora, `vcrpy` cassettes |
| Differential | Dual-run harnesses, shadow traffic replay |
| Upgrade matrix | tox/nox (Python), GitHub Actions matrix, `nvm`/`asdf` |
| Replay | `goreplay`, HAR replay, recorded request fixtures |
| Tagging | pytest markers, test IDs in names |

## 7. Practical Implementation

**Bug-reproducing test committed with the fix:**

```python
# Ticket: ORD-3456 — refund allowed more than the remaining balance after partial refunds
def test_refund_3456_rejects_amount_over_remaining_balance():
    # Given an order paid 100.00 with 60.00 already refunded
    policy = RefundPolicy()
    paid, refunded = Decimal("100.00"), Decimal("60.00")

    # When requesting 45.00 back (40.00 remain)
    with pytest.raises(RefundError, match="exceeds remaining balance"):
        policy.refundable(paid=paid, already_refunded=refunded, requested=Decimal("45.00"))

    # And 40.00 is still allowed
    assert policy.refundable(paid=paid, already_refunded=refunded,
                             requested=Decimal("40.00")) == Decimal("40.00")
```

**Characterization test before refactoring legacy code:**

```python
"""Characterization of the legacy price calculator.

Captured from production behavior on 2026-10-30; documents deliberate quirks.
Do not "fix" these expectations without a product decision (see PRICE-118).
"""
import pytest
from app.legacy.price_v1 import compute_price_v1

CASES = [
    # (subtotal_cents, discount_pct, expected_total_cents, note)
    (10000, 0, 10000, "baseline"),
    (10000, 10, 9000, "simple discount"),
    (9999, 10, 8999, "truncates rather than rounds (documented quirk)"),
    (10000, 100, 0, "full discount"),
    (0, 10, 0, "zero subtotal"),
]

@pytest.mark.parametrize("subtotal, discount, expected, note", CASES, ids=[c[3] for c in CASES])
def test_legacy_pricing_characterization(subtotal, discount, expected, note):
    assert compute_price_v1(subtotal, discount) == expected, note
```

**Golden master / approval test with reviewable baseline:**

```python
from syrupy.extensions.single_file import SingleFileSnapshotExtension

def test_monthly_invoice_pdf_layout(snapshot):
    invoice = build_invoice(customer="Acme", lines=[("Widget", 2, 1500)], currency="INR")
    rendered = render_invoice_html(invoice)
    assert rendered == snapshot(extension_class=SingleFileSnapshotExtension)
```

```bash
pytest tests/regression/test_invoice_render.py --snapshot-update   # after reviewing the diff
git diff tests/regression/__snapshots__/                             # the diff IS the review
```

```text
Rule: a snapshot update is only acceptable when the diff is explainable by the change in the PR.
Never run --snapshot-update as part of a fix without reading every changed file.
```

**Upgrade matrix (Python versions × dependency majors):**

```ini
# noxfile.py
import nox

@nox.session(python=["3.11", "3.12", "3.13"])
@nox.parametrize("sqlalchemy", ["2.0.36", "2.0.40"])
def regression(session, sqlalchemy):
    session.install(f"sqlalchemy=={sqlalchemy}", "-e", ".[dev]")
    session.run("pytest", "-m", "unit or integration", "-q")
```

```yaml
# CI: run the matrix only on main and release branches to bound cost
strategy:
  matrix:
    python: ["3.11", "3.12", "3.13"]
```

**Differential testing during a rewrite:**

```python
import pytest

@pytest.mark.parametrize("document", load_corpus("tests/corpus/documents/*.json"))
def test_new_parser_matches_legacy_output(document):
    old = parse_legacy(document)
    new = parse_v2(document)
    if new != old:
        pytest.fail(f"divergence on {document['id']}: legacy={old} new={new}")
```

**Record/replay regression for third-party interactions:**

```python
import vcr

@pytest.fixture(scope="module")
def vcr_cassette_dir():
    return "tests/cassettes"

@vcr.use_cassette("tests/cassettes/inventory_sync.yaml", record_mode="none")
def test_inventory_sync_against_recorded_provider():
    result = sync_inventory(provider=WarehouseClient())
    assert result.updated == 12
    assert result.errors == []
```

Cassettes must be sanitized (no tokens, no PII) before they are committed:

```python
def scrub(request):
    request.headers.pop("Authorization", None)
    request.uri = request.uri.replace("api_key=live_", "api_key=test_")
    return request
```

**Regression tag for fast hotfix verification:**

```python
@pytest.mark.regression
def test_refund_3456_rejects_amount_over_remaining_balance(): ...
```

```bash
pytest -m regression -q            # 40 tests, 20 seconds, run before every hotfix deploy
```

**Suite curation query (find duplicates by name pattern):**

```bash
pytest --collect-only -q | sed 's/\[.*//' | sort | uniq -c | sort -rn | head -20
```

## 8. Quality Standards

- Every production bug fix includes a test that fails without the fix.
- Regression tests reference the incident/ticket in name or docstring.
- Characterization tests document quirks explicitly rather than encoding them silently.
- Golden masters are reviewed in the PR diff; no blind `--update` runs.
- Upgrade matrices cover supported runtime/driver versions.
- A tagged regression subset runs in under a minute for hotfix verification.
- Tests for removed features are deleted in the same change.
- Recurring bug classes trigger a test-layer review, not just another test.

## 9. Verification and Testing

- Revert the fix and confirm the regression test fails (do this before merging).
- Run the regression subset against the previous release tag; it should pass (guards against test coupling to new code).
- For golden masters, deliberately change one output byte and confirm the failure message points at the diff.
- Verify no cassette or baseline contains secrets or PII (grep for `Authorization`, `token`, email patterns).
- Confirm the upgrade matrix fails when a known-incompatible dependency version is forced.

## 10. Security Considerations

- A fixed security bug must have a regression test that asserts the *denial*, verifiable without describing an exploit recipe in a public repo.
- Do not commit tests that contain real payloads from an incident (customer data, tokens, exploit strings that are actual live credentials).
- Golden masters from production output often embed personal data—regenerate with synthetic fixtures.
- Cassettes and HAR files capture headers; scrub tokens before committing.
- Coordination with disclosure: regression tests for an unfixed vulnerability in a public repo reveal it—keep them private until patched.

## 11. Failure Handling

- **Regression test passes without the fix:** it asserts the wrong thing (e.g. only that no exception was raised). Strengthen to the exact observable outcome.
- **Golden-master churn:** outputs contain timestamps, IDs, or float formatting; normalize nondeterministic fields before comparison.
- **Suite grows without value:** quarterly dedupe; prefer one integration test over five unit duplicates.
- **Upgrade matrix floods failures:** pin the failing minor version and fix compatibility in a dedicated PR with the matrix narrowing to it.
- **Characterization test blocks a needed behavior change:** mark it as expected-to-change, update with a product decision recorded in the PR.

## 12. Expected Deliverables

1. Regression test list mapped to incidents.
2. Failing-first evidence for each fix (test fails before, passes after).
3. Characterization suites for legacy areas.
4. Golden-master baselines with review process.
5. Upgrade matrix configuration.
6. Regression tag and fast-subset command.
7. Suite curation report.

## 13. References

- "Working Effectively with Legacy Code" (Michael Feathers) — characterization tests.
- ApprovalTests — https://approvaltests.com/
- syrupy — https://syrupy.js.org/
- Jest snapshot testing — https://jestjs.io/docs/snapshot-testing
- nox — https://nox.thea.codes/
- tox — https://tox.wiki/
- VCR.py — https://vcrpy.readthedocs.io/
- Hypothesis stateful testing (for model-based regression) — https://hypothesis.readthedocs.io/en/latest/stateful.html
