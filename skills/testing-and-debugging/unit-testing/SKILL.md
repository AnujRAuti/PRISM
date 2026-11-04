---
name: unit-testing
description: Write fast, isolated unit tests—behavior-focused assertions, fakes over mocks, parametrization, property-based testing, and deterministic time and randomness.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Unit Testing

## 1. Purpose

Prove small units of logic correct with tests that run in milliseconds and fail for exactly one reason. Unit tests go wrong in two directions: assertions on implementation details (so refactoring breaks 40 tests) and tests that are not actually isolated (sleeping, hitting the network, depending on time or iteration order). This skill covers structure, naming, fakes, parametrization, property-based testing, and determinism.

**Scope:** your own code. Unit tests must not touch production systems or real third-party APIs.

## 2. Activation Conditions

- Writing new business logic, parsers, validators, pricing, or state machines.
- A bug fix that needs a regression test.
- Refactoring where behavior must be preserved.
- Tests are slow, order-dependent, or break on unrelated changes.
- Keywords: unit test, pytest, vitest, assert, mock, stub, fake, fixture, parametrize, property-based, Hypothesis, deterministic, test double, arrange-act-assert.

## 3. When Not to Use

- The behavior crosses a database, HTTP, or filesystem boundary (use integration-testing).
- The bug can only be reproduced in a browser (use end-to-end-testing).
- Testing generated or framework code with no logic of your own.

## 4. Required Context

1. The unit's contract: inputs, outputs, errors, side effects.
2. Collaborators and whether they can be faked cheaply.
3. Test framework and existing conventions.
4. Time, randomness, and I/O dependencies in the code.
5. Language-specific tooling (pytest, vitest, JUnit).

## 5. Operating Procedure

1. **Test behavior through the public interface**, not private helpers. If a private method needs its own test, the boundary is probably wrong.
2. **Name by behavior**: `test_refund_rejected_when_amount_exceeds_remaining_balance`, not `test_refund_2`.
3. **Follow arrange–act–assert** with one logical assertion per test; multiple asserts are fine when they describe one outcome.
4. **Use fakes for collaborators** (in-memory implementations of the port) and mocks only to assert an interaction that is itself the requirement (e.g. "must publish an event").
5. **Never assert on call ordering or internal call counts** unless order is the contract.
6. **Make time injectable** (a `Clock` protocol) or freeze it; never `sleep()` to wait.
7. **Seed randomness explicitly** and assert on the seed; use property-based tests for arithmetic, parsers, and serializers.
8. **Parametrize** input matrices instead of copy-pasting tests.
9. **Keep each test independent**: no shared mutable module state, no reliance on execution order.
10. **Test the failure paths** (invalid input, boundary values, empty collections, unicode, very large inputs) as carefully as the happy path.
11. **Enforce a speed budget**: unit suite under 10 s for 1,000 tests; anything slower is not a unit test.

## 6. Tools and Technologies

| Concern | Python | TypeScript |
|---|---|---|
| Runner | pytest, unittest | vitest, jest, node:test |
| Parametrize | `@pytest.mark.parametrize` | `test.each` |
| Property-based | Hypothesis | fast-check |
| Time control | `freezegun`, `time-machine` | `vi.setSystemTime`, `sinon` fake timers |
| Fakes | hand-written classes, `faker` for data | hand-written, `msw` for HTTP |
| Coverage | coverage.py / pytest-cov | `c8`, `vitest --coverage` |
| Assertions | plain `assert`, `pytest.raises` | `expect` |

## 7. Practical Implementation

**Arrange–act–assert with a fake collaborator:**

```python
# app/services/refunds.py
from dataclasses import dataclass
from decimal import Decimal

class RefundError(Exception): ...

@dataclass(frozen=True)
class RefundPolicy:
    max_fraction: Decimal = Decimal("1.0")

    def refundable(self, *, paid: Decimal, already_refunded: Decimal, requested: Decimal) -> Decimal:
        remaining = paid - already_refunded
        if requested <= 0:
            raise RefundError("amount must be positive")
        if requested > remaining:
            raise RefundError("amount exceeds remaining balance")
        if requested > paid * self.max_fraction:
            raise RefundError("amount exceeds policy limit")
        return requested
```

```python
# tests/unit/test_refund_policy.py
from decimal import Decimal
import pytest
from app.services.refunds import RefundPolicy, RefundError

policy = RefundPolicy()

def test_refund_allowed_within_remaining_balance():
    amount = policy.refundable(paid=Decimal("100.00"), already_refunded=Decimal("0"),
                               requested=Decimal("40.00"))
    assert amount == Decimal("40.00")

@pytest.mark.parametrize(
    "paid, already, requested, message",
    [
        ("100.00", "0", "100.01", "exceeds remaining balance"),
        ("100.00", "60.00", "45.00", "exceeds remaining balance"),
        ("100.00", "0", "0", "must be positive"),
        ("100.00", "0", "-5", "must be positive"),
        ("0.00", "0", "0.01", "exceeds remaining balance"),
    ],
)
def test_refund_rejected_with_reason(paid, already, requested, message):
    with pytest.raises(RefundError, match=message):
        policy.refundable(paid=Decimal(paid), already_refunded=Decimal(already),
                          requested=Decimal(requested))
```

**Fake over mock for a repository port:**

```python
# tests/unit/test_order_service.py
import pytest
from app.domain.order import Order, OrderStatus
from app.services.orders import OrderService, OrderNotFound

class FakeOrderRepo:
    def __init__(self, orders: list[Order]) -> None:
        self._orders = {o.id: o for o in orders}
        self.saved: list[Order] = []

    async def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    async def save(self, order: Order) -> None:
        self._orders[order.id] = order
        self.saved.append(order)

@pytest.mark.asyncio
async def test_pay_transitions_placed_order_to_paid():
    repo = FakeOrderRepo([Order(id="o1", status=OrderStatus.PLACED, total_cents=4200, currency="INR")])
    svc = OrderService(repo=repo, payments=FakePayments(), uow=NoopUoW())

    order = await svc.pay("o1", idempotency_key="k-0001")

    assert order.status is OrderStatus.PAID
    assert repo.saved[0].status is OrderStatus.PAID
```

**Assert an interaction that is the requirement:**

```python
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_paid_order_emits_domain_event():
    events = AsyncMock()
    svc = OrderService(repo=FakeOrderRepo([paid_order]), payments=FakePayments(),
                       uow=NoopUoW(), events=events)

    await svc.pay("o1", idempotency_key="k-0002")

    events.publish.assert_awaited_once()
    topic, payload = events.publish.await_args.args
    assert topic == "orders"
    assert payload["type"] == "order.paid.v1"
    assert payload["data"]["order_id"] == "o1"
    # Do NOT assert on call ordering or unrelated internals
```

**Injectable clock (no sleeping):**

```python
from datetime import datetime, timedelta, timezone
from typing import Protocol

class Clock(Protocol):
    def now(self) -> datetime: ...

class FixedClock:
    def __init__(self, t: datetime) -> None: self._t = t
    def now(self) -> datetime: return self._t
    def advance(self, **kw) -> None: self._t += timedelta(**kw)

def test_session_expires_after_idle_timeout():
    clock = FixedClock(datetime(2026, 11, 4, 10, tzinfo=timezone.utc))
    session = Session(id="s1", last_seen=clock.now(), idle_timeout=timedelta(hours=12), clock=clock)

    clock.advance(hours=11)
    assert session.is_valid()

    clock.advance(hours=2)
    assert not session.is_valid()
```

**Property-based testing for a parser/round-trip:**

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers(min_value=0, max_value=10**9), max_size=50))
def test_cursor_round_trip(item_ids):
    cursor = encode_cursor(item_ids)
    assert decode_cursor(cursor) == item_ids

@given(st.text())
def test_cursor_never_crashes_on_garbage(raw):
    try:
        decode_cursor(raw)
    except ValueError:
        pass                      # rejecting garbage is the contract
```

**Table-driven tests (TypeScript/vitest):**

```ts
import {describe, expect, it} from "vitest";
import {formatMoney} from "../src/format";

describe("formatMoney", () => {
  it.each([
    [4200, "INR", "₹42.00"],
    [0, "INR", "₹0.00"],
    [1, "INR", "₹0.01"],
    [123456789, "USD", "$1,234,567.89"],
  ])("formats %i %s as %s", (cents, currency, expected) => {
    expect(formatMoney(cents, currency)).toBe(expected);
  });

  it("throws on a negative amount instead of displaying a negative price", () => {
    expect(() => formatMoney(-1, "INR")).toThrow(/negative/);
  });
});
```

**Boundary and edge-case checklist:**

```text
[ ] empty collection / zero quantity
[ ] single element
[ ] maximum allowed value and max+1
[ ] negative and zero where numbers are expected
[ ] unicode, emoji, RTL, very long strings (10k chars)
[ ] duplicate keys in input structures
[ ] null/undefined/None vs. missing key
[ ] timezone boundaries and DST transitions
[ ] concurrent invocation of a non-thread-safe function (documented as unsupported)
```

**Enforcing hermeticity:**

```python
# conftest.py — fail any accidental network access in unit tests
import socket
import pytest

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*args, **kwargs):
        raise RuntimeError("unit tests must not use the network; use a fake")
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
```

## 8. Quality Standards

- Tests assert observable behavior through public APIs; private helpers are covered indirectly.
- Each test is independent and passes in any order and in parallel.
- No network, filesystem, wall clock, or shared global state.
- No `sleep()`; time is injected or frozen.
- Every bug fix adds a regression test that fails before the fix.
- Error paths and boundaries are tested, not only the happy path.
- Test names describe the rule being enforced.
- The unit suite runs in seconds and gives a precise failure location.

## 9. Verification and Testing

- Run the suite in randomized order (`pytest-randomly`) and in parallel (`-n auto`) — all must pass.
- Mutation spot-check: change a comparison operator in the source; at least one test must fail.
- Delete the fix for a known bug; the regression test must fail.
- Measure per-test duration; anything above ~100 ms is a candidate for a lower layer or optimization.
- Run with `-W error` to catch hidden deprecation and resource warnings.

## 10. Security Considerations

- Do not embed real credentials, tokens, or customer data in fixtures; use obviously fake values.
- Security-relevant units (authz checks, token validation, path handling) must include negative tests—tests that the check rejects, not only that it accepts.
- Union types and error paths hide bugs: assert that invalid inputs raise, rather than merely returning falsy.
- Beware of tests that "prove" security by mocking the security function itself; fake the boundary, not the check.
- Test files can leak internal endpoints and keys in CI logs; keep artifacts clean.

## 11. Failure Handling

- **Test breaks on every refactor:** it is asserting implementation details—rewrite around behavior.
- **Intermittent failures locally only:** leftover shared state, unclosed resources, or parallel test interference; add fixtures that isolate.
- **Mocks drift from reality:** replace hand-rolled mocks of third parties with contract tests at the boundary, keeping units on fakes.
- **Huge fixture set-up:** extract builders with sensible defaults so a test states only what matters.
- **Coverage high but mutants survive:** assertions are too weak; assert on values, not just "no exception".

## 12. Expected Deliverables

1. Test file layout mirroring the module structure.
2. Fakes for each external port.
3. Parametrized matrices for boundary conditions.
4. Property-based tests for parsers and arithmetic.
5. Deterministic clock and random-seed fixtures.
6. Regression test for each fixed bug.
7. Documented speed budget and hermeticity guard.

## 13. References

- pytest documentation — https://docs.pytest.org/en/stable/
- pytest parametrize — https://docs.pytest.org/en/stable/how-to/parametrize.html
- Hypothesis (property-based testing) — https://hypothesis.readthedocs.io/
- fast-check — https://fast-check.dev/
- vitest — https://vitest.dev/guide/
- Martin Fowler, "Mocks Aren't Stubs" — https://martinfowler.com/articles/mocksArentStubs.html
- "Unit Testing Principles, Practices, and Patterns" (Vladimir Khorikov).
- pytest-randomly — https://github.com/pytest-dev/pytest-randomly
