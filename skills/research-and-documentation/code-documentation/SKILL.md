---
name: code-documentation
description: Document code where it matters—docstrings that state contracts, comment discipline that explains why, generated reference docs, and examples that stay correct.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: low
---

# Code Documentation

## 1. Purpose

Make code understandable without reading every implementation, and make its contract enforceable. In-code documentation fails in two directions: comments that restate the code ("increment i") and absent contracts on public functions (units, ranges, error conditions, side effects). This skill covers docstring conventions, comment policy, public API documentation generation, examples that are tested, and deprecation notices.

**Scope:** your own codebase. Generated documentation may expose internal endpoints—control publication scope for private repositories.

## 2. Activation Conditions

- Public or cross-team API without documented contracts.
- Reviewers repeatedly ask what a parameter means or what a function can raise.
- Generated docs are empty or meaningless.
- Comments are stale and contradict the code.
- Keywords: docstring, JSDoc, TSDoc, doc comment, API reference, Sphinx, TypeDoc, comment policy, deprecation, examples, doctest, `@param`, `@returns`, `raises`.

## 3. When Not to Use

- User-facing guides and tutorials (use technical-writing).
- Architectural rationale and decisions (use rfc-and-design-docs / architecture-decision-records).
- Trivial private helpers with self-describing names.

## 4. Required Context

1. Language and documentation toolchain (Sphinx/pdoc, TypeDoc, rustdoc, godoc).
2. Which APIs are public (packages, exported symbols) versus internal.
3. Existing style for docstrings and type hints.
4. Documentation publication target and audience.
5. Test tooling for examples (doctest, tsdoc examples).

## 5. Operating Procedure

1. **Rely on types and names first.** With precise types and intention-revealing names, most comments are unnecessary; documentation should add what types cannot express.
2. **Document the contract, not the implementation**: purpose, parameters with units and ranges, return value, raised errors, side effects, thread-safety, and idempotency.
3. **Document every public symbol** (module, class, function, endpoint) and nothing private by default, except non-obvious invariants.
4. **Write comments to explain *why***, especially for workarounds, magic numbers, external constraints, and ordering requirements. Include a link to the issue or spec.
5. **Keep examples runnable and tested**: doctests or snippet tests, with real imports and realistic values.
6. **State failure modes explicitly** — what exceptions are raised and under which conditions; this is the most valuable docstring line for callers.
7. **Note deprecations with migration guidance**: use `@deprecated`/`.. deprecated::` with the version and the replacement.
8. **Generate reference docs in CI** and fail on undocumented public symbols where feasible.
9. **Delete stale comments** when changing code; a wrong comment is worse than none.
10. **Keep docstrings versioned with the code**, and publish docs per release tag.

## 6. Tools and Technologies

| Language | Tooling |
|---|---|
| Python | Google/NumPy docstrings, Sphinx + autodoc, pdoc, `interrogate` (coverage), `pytest --doctest-modules` |
| TypeScript | TSDoc, TypeDoc, ESLint `jsdoc` rules |
| Go | `go doc`, godoc conventions |
| Rust | rustdoc (`///`, `//!`), `cargo doc --no-deps` |
| Java | Javadoc |
| C/C++ | Doxygen |
| Cross-language | OpenAPI for HTTP APIs |

## 7. Practical Implementation

**Python docstring stating the full contract:**

```python
def refundable_amount(
    *,
    paid_cents: int,
    already_refunded_cents: int,
    policy_fraction: Decimal = Decimal("1.0"),
) -> int:
    """Compute how much of a payment can still be refunded.

    Args:
        paid_cents: Total captured amount in minor currency units. Must be >= 0.
        already_refunded_cents: Sum of prior successful refunds, in minor units.
            Must be >= 0 and <= ``paid_cents``.
        policy_fraction: Maximum share of the original payment that may be refunded,
            in (0, 1]. Defaults to 1.0 (no cap).

    Returns:
        The remaining refundable amount in minor units, in the range
        ``[0, int(paid_cents * policy_fraction)]``.

    Raises:
        ValueError: If any amount is negative, if ``already_refunded_cents``
            exceeds ``paid_cents``, or if ``policy_fraction`` is outside (0, 1].

    Notes:
        Amounts are integers to avoid floating-point drift; the policy cap is
        floored, never rounded up. Safe to call concurrently; performs no I/O.

    Example:
        >>> refundable_amount(paid_cents=10000, already_refunded_cents=6000)
        4000
        >>> refundable_amount(paid_cents=9999, already_refunded_cents=0,
        ...                   policy_fraction=Decimal("0.1"))
        999
    """
    if paid_cents < 0 or already_refunded_cents < 0:
        raise ValueError("amounts must be non-negative")
    if already_refunded_cents > paid_cents:
        raise ValueError("refunded amount exceeds paid amount")
    if not (Decimal(0) < policy_fraction <= Decimal(1)):
        raise ValueError("policy_fraction must be in (0, 1]")
    remaining = paid_cents - already_refunded_cents
    return min(remaining, int(paid_cents * policy_fraction))
```

**TSDoc for a public function:**

```ts
/**
 * Formats a minor-unit amount for display in the user's locale.
 *
 * @param cents - Amount in minor units (e.g. paise). Must be a safe integer.
 * @param currency - ISO 4217 code; must be uppercase and 3 characters.
 * @param locale - BCP 47 tag used for grouping and symbol placement.
 * @returns A localized string such as `₹1,234.50`.
 * @throws {@link RangeError} If `cents` is negative or not a safe integer.
 *
 * @remarks
 * Uses `Intl.NumberFormat`, so output differs by platform ICU version.
 * Do not use this for arithmetic; keep integers until rendering.
 *
 * @example
 * ```ts
 * formatMoney(123450, "INR", "en-IN"); // "₹1,234.50"
 * ```
 */
export function formatMoney(cents: number, currency: string, locale = "en-IN"): string {
  if (!Number.isSafeInteger(cents) || cents < 0) {
    throw new RangeError(`cents must be a non-negative safe integer, got ${cents}`);
  }
  return new Intl.NumberFormat(locale, {style: "currency", currency})
    .format(cents / 100);
}
```

**Comment discipline: explain why, link evidence**

```python
# Cap retries at 4 because the payment provider's idempotency window is 24 h and
# exponential backoff beyond that produces duplicate-charge risk. See PAY-8812.
MAX_PAYMENT_RETRIES = 4

# We must sort by (created_at, id): created_at alone is not unique and causes
# duplicate rows at page boundaries. See incident INC-4711.
ORDER_BY = ("created_at DESC", "id DESC")

# Workaround for WebKit < 17.4 ignoring `popover` in a fixed container.
# Remove after 2026-06 when iOS 17.4+ is > 99% of traffic (see compat dashboard).
if is_legacy_webkit():
    anchor_to_body(popover)
```

**Anti-patterns to reject in review:**

```python
# BAD: restates the code
i += 1  # increment i

# BAD: stale and wrong (the function returns None now)
def save(order):
    """Returns the saved order."""     # <- not true
    ...

# BAD: commented-out code (delete it; git remembers)
# order.total = compute_old(order)

# BAD: a TODO with no owner or issue
# TODO: fix this later
```

```python
# GOOD: actionable TODO
# TODO(@priya, PAY-9123): remove the legacy path once v1 clients are zero. Blocked on app-store rollout.
```

**Module-level docstring with ownership and invariants:**

```python
"""Checkout session handling.

Invariants:
    - A session in state ``paid`` can never return to ``open``.
    - Session IDs are tenant-scoped; cross-tenant reads are impossible by key layout.

Owner: @payments-platform
Related: RFC-0142, ADR-0061
"""
```

**Doc coverage and generation in CI:**

```bash
# Python: fail if public modules/functions lack docstrings
interrogate -vv --fail-under 90 --ignore-init-method --ignore-private app/

# Generate HTML reference
sphinx-build -b html docs docs/_build -W      # -W turns warnings into errors
pdoc app -o docs/_build/api

# TypeScript
npx typedoc --entryPoints src/index.ts --out docs/api --validation.notDocumented

# Rust
cargo doc --no-deps --document-private-items=false
```

```yaml
# CI job: docs build must not warn on public API
- run: sphinx-build -b html docs docs/_build -W --keep-going
- run: interrogate --fail-under 90 app/
```

**Deprecation notice with migration path:**

```python
import warnings
from typing import Any

def create_order_v1(payload: dict[str, Any]) -> dict[str, Any]:
    """Deprecated. Use :func:`create_order` instead.

    .. deprecated:: 2.14
       Removed in 3.0 (planned 2027-01-31). Returns the legacy response shape
       without ``links``. Migration: pass the same payload to ``create_order``
       and read ``id`` from the response.
    """
    warnings.warn(
        "create_order_v1 is deprecated; use create_order (removal: 3.0, 2027-01-31)",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_order(payload, legacy_shape=True)
```

**Tested examples stay correct:**

```bash
pytest --doctest-modules app/ --doctest-continue-on-failure
```

```python
# tests/test_docs_examples.py — run README code blocks
import json, re, subprocess, sys, pathlib

def test_readme_python_examples_compile():
    text = pathlib.Path("README.md").read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    assert blocks, "README should contain runnable Python examples"
    for i, block in enumerate(blocks):
        compile(block, f"README-block-{i}", "exec")     # syntax check; run with fixtures if safe
```

## 8. Quality Standards

- Every public symbol documents purpose, params (units/ranges), return, errors, and side effects.
- Comments explain why, with a link to an issue, spec, or incident for non-obvious decisions.
- No commented-out code; no TODOs without an owner and a ticket.
- Examples are executed by a test, not just written.
- Deprecations state the version, removal date, and migration path.
- Generated docs build with zero warnings for the public API.
- Docstrings are updated in the same commit as the behavior change.
- No docstring restates the signature in prose.

## 9. Verification and Testing

- `sphinx-build -W` / `typedoc --validation.notDocumented` passes in CI.
- Docstring coverage tooling reports the agreed threshold for public modules.
- Doctests run in the test suite and fail on behavior change.
- Reviewers can explain a function's failure modes using only its docstring.
- Grep for banned patterns (`TODO:` without an ID, `XXX`, commented-out code) in the lint step.

## 10. Security Considerations

- Docstrings for internal endpoints reveal topology and parameters; publishing generated docs from a private repo must be deliberate.
- Do not include real credentials, tokens, or customer data in examples or docstrings.
- Document security-relevant preconditions (e.g. "caller must already be authorized; this function performs no permission check") so callers do not assume safety.
- Deprecation of a security-related API should state whether the replacement changes threat properties.
- Generated documentation sites can expose source code; verify what `typedoc`/`pdoc` include before publishing.

## 11. Failure Handling

- **Docs drift from code:** generate what is mechanical, test examples, and make doc updates part of the definition of done.
- **Docstrings become essays:** move narrative to module docs or a design doc; keep the function contract short.
- **Coverage tooling blocks legacy code:** scope the threshold to new/changed modules and ratchet over time.
- **Examples fail in CI after a refactor:** that is the feature working; fix the example in the same PR.
- **Comments contradict code:** delete or correct them immediately; a misleading comment causes real bugs.

## 12. Expected Deliverables

1. Docstring style guide and examples in the repo.
2. Documented public API surface.
3. Comment policy with what to explain and what to avoid.
4. CI checks for docstring coverage and docs build.
5. Tested examples (doctests/snippet tests).
6. Deprecation notices with migration paths.

## 13. References

- PEP 257 Docstring Conventions — https://peps.python.org/pep-0257/
- Google Python Style Guide (docstrings) — https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings
- Sphinx autodoc — https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
- TSDoc specification — https://tsdoc.org/
- TypeDoc documentation — https://typedoc.org/
- Python `doctest` — https://docs.python.org/3/library/doctest.html
- interrogate — https://interrogate.readthedocs.io/
- Rustdoc book — https://doc.rust-lang.org/rustdoc/what-is-rustdoc.html
