---
name: debugging-techniques
description: Find the cause of a defect systematically—reproduce, bisect, instrument, form and falsify hypotheses, and stop guessing with print statements.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: medium
---

# Debugging Techniques

## 1. Purpose

Convert a symptom into a root cause with a repeatable method rather than instinct. Debugging goes badly when people change code speculatively, trust the wrong layer ("the cache is fine"), or stop at the first plausible cause. This skill covers reproduction, binary search and `git bisect`, breakpoint-driven debugging, instrumentation, hypothesis discipline, and the heuristics that resolve the hard cases.

**Scope:** your own systems. Live debugging on production requires authorization and must be read-only first: never attach a debugger or run interactive introspection that pauses a production process without approval, and never log secrets while investigating.

## 2. Activation Conditions

- A reproducible defect with an unknown cause.
- Intermittent or environment-specific failures.
- Working code broke after a deploy or dependency change.
- A stack trace points into a library or generated code.
- Keywords: debugging, root cause, bisect, breakpoint, pdb, debugpy, gdb, strace, pdb, DevTools, stack trace, heap dump, core dump, race condition, heisenbug, differential debugging.

## 3. When Not to Use

- The cause is already known and only the fix remains.
- Test flakiness management (use flaky-test-diagnosis).
- Capacity/perf issues requiring measurement (use performance-and-load-testing).

## 4. Required Context

1. Exact reproduction steps and frequency.
2. Full error message and stack trace (not a screenshot of a summary).
3. Environment: version, commit SHA, config, data state.
4. Recent changes: commits, dependency bumps, infra/config changes.
5. Observability access: logs, traces, metrics for the failing window.

## 5. Operating Procedure

1. **Get a deterministic reproduction** before theorizing. If it is intermittent, quantify the rate and find the smallest configuration that makes it reliable (more iterations, same worker count, same data).
2. **Read the actual error**, top and bottom: Python tracebacks bottom-up from the frame in your code; JS errors plus the first user-code frame; network errors include status, headers, and body.
3. **State the expected vs. observed behavior and the first point where they diverge.** This localizes the fault to a layer.
4. **Use binary search on time**: `git bisect` with an automated pass/fail script when the regression is recent.
5. **Use binary search on space**: comment out, feature-flag, or route around half the system; then halve again. Never change two things at once.
6. **Observe, do not guess**: breakpoints with conditional expressions, watchpoints, `strace`/`ltrace` for syscalls, `py-spy dump` for stuck processes, `tcpdump`/DevTools for network.
7. **Form one hypothesis at a time, with a prediction**: "if X is the cause, then disabling it will stop the failure." Run the experiment and record the result — including when it disproves the hypothesis.
8. **Check the boring things early**: config file actually loaded, env var set in the right process, migrations applied, wrong virtualenv/node_modules, stale build artifact, DNS/cert, clock skew.
9. **Reproduce in isolation** with a minimal script; if it will not reproduce, the difference (env, data, concurrency) is part of the cause.
10. **Fix the root cause, not the symptom**, then add a regression test and clean up instrumentation.
11. **Write it down**: one paragraph in the ticket — cause, evidence, fix, and how it was found.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Python debugging | `breakpoint()`/pdb, debugpy + VS Code, `pdbpp`, `py-spy dump` |
| JS/TS | Chrome DevTools, `node --inspect`, VS Code launch config |
| Native | gdb/lldb, core dumps, `addr2line` |
| Syscall/IO | `strace`, `ltrace`, `lsof`, `ss` |
| Network | `tcpdump`, `mitmproxy`, DevTools Network, `curl -v` |
| Git | `git bisect`, `git log -S`, `git blame` |
| Time travel | `rr` (record/replay), `pg_stat_statements` |
| Observability | distributed traces, structured logs, `EXPLAIN` |

## 7. Practical Implementation

**Automated `git bisect` with a test script:**

```bash
git bisect start
git bisect bad HEAD
git bisect good v2.4.0

# tests/bisect_repro.sh
#!/usr/bin/env bash
set -euo pipefail
pytest tests/integration/test_refund_flow.py::test_partial_refund_totals -q >/dev/null 2>&1
```

```bash
git bisect run ./tests/bisect_repro.sh
# ...
# 3f9a1c2 is the first bad commit
git bisect reset
```

**Find where a string/behavior was introduced:**

```bash
git log -S "refundable_amount" --oneline -- app/services/refunds.py
git log -p --follow -- app/domain/pricing.py | head -200
git blame -L 40,80 app/services/refunds.py
```

**Conditional breakpoint for an intermittent state:**

```python
# Debugging a value that only occurs for one customer
for order in orders:
    breakpoint()  # then: `condition 1 order.id == "ord_8812"` in pdb
```

```bash
# Or launch with a debugger and set the condition in the IDE
python -m debugpy --listen 5678 --wait-for-client -m app.worker
```

**Non-interactive inspection of a stuck/frozen process:**

```bash
# Python: dump all thread stacks without stopping the process for long
py-spy dump --pid 4821

# Where is it blocked in the kernel?
cat /proc/4821/stack 2>/dev/null || sudo cat /proc/4821/stack
sudo strace -p 4821 -f -e trace=network,read,write -T -tt   # requires ptrace privileges
```

**Systematic printf → structured instrumentation:**

```python
import logging
log = logging.getLogger(__name__)

# Instead of scattered prints, one correlated trace that can be removed by level:
log.debug("refund.computed", extra={
    "order_id": order.id, "paid_cents": paid, "refunded_cents": refunded,
    "requested_cents": requested, "remaining_cents": remaining,
})
```

**Differential debugging (works vs. broken):**

```bash
# Compare two environments' resolved configuration
diff <(kubectl -n prod exec deploy/api -- env | sort) \
     <(kubectl -n staging exec deploy/api -- env | sort)

# Compare dependency trees
diff <(pip freeze) <(git show v2.4.0:requirements.lock | tail -n +1)
```

**Network-level truth (the client says 500, the server logs nothing):**

```bash
curl -sv https://api.example.com/v1/orders -H "Authorization: Bearer $TOKEN" 2>&1 | tail -40
sudo tcpdump -i any -n 'tcp port 5432' -w /tmp/db.pcap   # then open in Wireshark
```

**Reproduce timing bugs deterministically:**

```python
# Inject delays to widen the race window rather than hoping to hit it
import os, asyncio

async def fake_slow_write(*args, **kwargs):
    if os.getenv("DEBUG_RACE"):
        await asyncio.sleep(float(os.environ["DEBUG_RACE"]))
    return await real_write(*args, **kwargs)
```

**Minimal reproduction script:**

```python
"""Minimal repro: isolating whether the bug is in the serializer or the ORM.

Run: python -m scripts.repro_serializer_bug
"""
import asyncio
from decimal import Decimal
from app.api.schemas import OrderResponse
from app.domain.order import Order, OrderStatus

async def main() -> None:
    order = Order(id="o1", status=OrderStatus.PAID, total=Decimal("0.1"), currency="INR")
    payload = OrderResponse.model_validate(order).model_dump(mode="json")
    print(payload)                     # observed: total serialized as "0.1" instead of 10
    assert payload["total_cents"] == 10, payload

asyncio.run(main())
```

**Hypothesis log (kept in the ticket, not in your head):**

```markdown
| # | Hypothesis                          | Prediction                          | Result        |
|---|-------------------------------------|-------------------------------------|---------------|
| 1 | Cache returns stale order totals    | bypassing cache fixes totals        | disproved     |
| 2 | Float rounding in serializer        | values near .005 always wrong       | confirmed     |
| 3 | Wrong DB for the worker             | repro stops when pinning DATABASE_URL| confirmed (contributing) |
```

**Reading a stack trace correctly:**

```text
Traceback (most recent call last):
  File "app/api/routes/orders.py", line 41, in pay_order
    order = await svc.pay(order_id, idempotency_key=key)
  File "app/services/orders.py", line 67, in pay
    updated = order.pay()
  File "app/domain/order.py", line 38, in pay
    raise InvalidTransition(self.status, OrderStatus.PAID)
app.domain.errors.InvalidTransition: cannot move order from draft to paid
#                    ^^^^^^^^^^^^^^^^ the real message; read the LAST line first
```

## 8. Quality Standards

- A reproduction exists (or the intermittency is quantified) before any code change.
- Only one variable is changed per experiment, and the result is recorded.
- Root cause names the faulty assumption, not just the faulty line.
- The fix addresses the cause; the regression test fails without the fix.
- Temporary instrumentation is removed (or downgraded to a permanent debug log).
- The investigation is documented well enough for someone else to follow.
- Production debugging is read-only unless explicitly authorized; no interactive debuggers in production.

## 9. Verification and Testing

- Reproduce → fix → reproduce again: the failure is gone with the same steps.
- Run the new regression test against the pre-fix commit and confirm it fails.
- Verify no instrumentation remains (`grep -r "breakpoint()" app/`).
- Check the fix under the conditions that originally triggered it (same load, same data shape).
- Confirm the fix does not mask the problem elsewhere (grep for the same pattern in sibling code).

## 10. Security Considerations

- Debug logging frequently leaks tokens, cookies, and PII; enable at the narrowest scope and remove before merging.
- Never paste production data, keys, or full stack traces with secrets into tickets or chats—redact first.
- Interactive debuggers in production can pause the process and expose memory: require approval and use read-only telemetry instead.
- `strace`/`ptrace` and core dumps may contain secret memory contents; restrict access and delete afterwards.
- Reproducing with real customer data requires a lawful basis; prefer synthetic data that matches the shape.
- Debug endpoints (`/debug/vars`, profiler routes) must be authenticated, bound to localhost, or disabled in production.

## 11. Failure Handling

- **Cannot reproduce:** the difference is the clue — compare environments, data snapshots, and concurrency; capture more telemetry at the failing site.
- **Heisenbug disappears when logging is added:** a timing or memory-layout dependency; use record/replay (`rr`), deterministic delays, or thread sanitizers.
- **Fix works but nobody knows why:** investigate further; unexplained fixes usually return. At minimum, record the evidence chain.
- **Bisect run fails on unrelated tests:** tighten the repro script to the specific failing test and ensure dependencies install deterministically.
- **Stack trace points only to library code:** step up one frame into your call site; the bad input usually originates there.

## 12. Expected Deliverables

1. Reproduction steps or a repro script.
2. Evidence trail: logs, traces, experiment results.
3. Root cause statement.
4. Fix with regression test.
5. Documentation in the ticket/PR.
6. Removal of temporary instrumentation.

## 13. References

- `git bisect` documentation — https://git-scm.com/docs/git-bisect
- Python `pdb` — https://docs.python.org/3/library/pdb.html
- debugpy — https://github.com/microsoft/debugpy
- py-spy — https://github.com/benfred/py-spy
- `rr` record and replay debugger — https://rr-project.org/
- Chrome DevTools — https://developer.chrome.com/docs/devtools/
- "Debugging: The 9 Indispensable Rules" (David Agans).
- strace manual — https://man7.org/linux/man-pages/man1/strace.1.html
