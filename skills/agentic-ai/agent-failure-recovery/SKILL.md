---
name: agent-failure-recovery
description: Recover agents from failure—classify faults, checkpoint and resume, retry safely, compensate partial side effects, and degrade gracefully instead of crashing the run.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Agent Failure Recovery

## 1. Purpose

Keep agent runs recoverable when models, tools, networks, and environments fail. Agents fail in ways ordinary services do not: partial tool side effects, poisoned context, and self-reinforcing loops. This skill defines fault taxonomy, checkpoint/resume, safe retries with idempotency, compensating actions for partial work, and the degradation ladder that returns a useful partial result instead of a stack trace.

**Scope:** agents you operate. Compensation actions (refunds, deletes, rollbacks) are themselves mutating operations—they require the same authorization and audit as the original action.

## 2. Activation Conditions

- Building a long-running or expensive agent.
- A run failed midway and left inconsistent state.
- Tool or model errors cause frequent aborts.
- Need for retries without duplicating side effects.
- Keywords: agent recovery, checkpoint, resume, retry, idempotency, compensation, saga, degradation, graceful failure, poison context.

## 3. When Not to Use

- Short, stateless single-call features where a simple retry suffices.
- Infrastructure-level resilience (use distributed-systems for retries/breakers).
- Incident response for a live security event (use incident-response).

## 4. Required Context

1. Failure history: which errors occur and their frequency.
2. Side-effect inventory: which tools mutate state and how to undo them.
3. Checkpoint granularity options (per step, per tool call, per turn).
4. Model/tool alternatives available for degradation.
5. User-facing expectations on partial results.

## 5. Operating Procedure

1. **Build a fault taxonomy**:
   - Transient (timeouts, 429/503) → retry with backoff.
   - Permanent (400, invalid args, permission denied) → fix or fail fast.
   - Semantic (tool returns unusable data, contradictory evidence) → replan.
   - Resource (budget exhausted, context overflow) → compact/degrade.
   - Loop (repeated identical action) → break with escalation.
   - Safety (policy violation signaled by a guardrail) → stop and report.
2. **Checkpoint after every step**: persist state, tool outputs, and plan status with a monotonically increasing version.
3. **Resume by replaying the checkpoint**, not by re-running from scratch; verify external state matches expectations before continuing (idempotent re-reads).
4. **Retry only transient faults**, with exponential backoff + jitter, bounded attempts, and a deadline.
5. **Make mutations idempotent** with keys derived from run ID + step ID, so a retry cannot double-apply.
6. **Implement compensation** for multi-step mutations (saga pattern): each step registers its undo; on abort, run undos in reverse order, idempotently.
7. **Degrade in a defined ladder**: full → reduced tools → cached/simplified answer → partial result with gaps → human handoff.
8. **Handle poison context**: on repeated semantic failures, compact/prune the observations that are likely causing the loop, then retry once.
9. **Surface a structured failure object** to the caller: status, what completed, what remains, error class, and the resume handle.
10. **Alert and aggregate** failure classes to drive fixes in tools and prompts.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Durable execution | Temporal, Restate, Step Functions, custom checkpoint table |
| Idempotency | Dedup table keyed by (run_id, step_id), provider idempotency keys |
| Compensation | Saga orchestration, explicit undo tool registry |
| Backoff | `tenacity`, custom policy, gateway retries |
| State | Postgres JSONB per step, object store snapshots |
| Observability | OpenTelemetry spans per attempt with attempt number |

## 7. Practical Implementation

**Fault classification:**

```python
from enum import Enum

class FaultClass(str, Enum):
    transient = "transient"
    permanent = "permanent"
    semantic = "semantic"
    resource = "resource"
    loop = "loop"
    safety = "safety"

def classify(exc: Exception | None, tool_result: dict | None = None) -> FaultClass:
    if exc is not None:
        name = type(exc).__name__
        if name in {"TimeoutError", "ConnectionError", "RateLimitError"}:
            return FaultClass.transient
        if name in {"ValidationError", "PermissionError", "ValueError"}:
            return FaultClass.permanent
        return FaultClass.permanent
    if tool_result and tool_result.get("retryable"):
        return FaultClass.transient
    if tool_result and tool_result.get("unusable"):
        return FaultClass.semantic
    return FaultClass.permanent
```

**Checkpoint and resume:**

```python
import json, datetime as dt

def checkpoint(conn, run_id: str, step_index: int, state: dict) -> None:
    conn.execute(
        """INSERT INTO agent_checkpoints (run_id, step_index, state, created_at, version)
           VALUES (%s,%s,%s,now(),
                   COALESCE((SELECT MAX(version)+1 FROM agent_checkpoints WHERE run_id=%s), 1))""",
        (run_id, step_index, json.dumps(state), run_id))

def load_latest(conn, run_id: str) -> tuple[int, dict]:
    row = conn.execute(
        """SELECT step_index, state FROM agent_checkpoints
           WHERE run_id=%s ORDER BY version DESC LIMIT 1""", (run_id,)).fetchone()
    if row is None:
        return 0, {}
    return row["step_index"], json.loads(row["state"])

def resume(conn, run_id: str, agent) -> dict:
    step_index, state = load_latest(conn, run_id)
    reconcile_external_state(state)          # verify side effects present/absent as recorded
    return agent.run_from(state, start_index=step_index)
```

**Idempotent mutating tool:**

```python
def apply_change(conn, run_id: str, step_id: str, change: dict) -> dict:
    key = f"{run_id}:{step_id}"
    with conn.transaction():
        done = conn.execute(
            "SELECT result FROM idempotency WHERE key=%s", (key,)).fetchone()
        if done:
            return {"ok": True, "data": json.loads(done["result"]), "deduplicated": True}
        result = perform_change(change)          # the real side effect
        conn.execute("INSERT INTO idempotency (key, result, created_at) VALUES (%s,%s,now())",
                     (key, json.dumps(result)))
        return {"ok": True, "data": result}
```

**Saga with compensation:**

```python
class Saga:
    def __init__(self, conn, run_id: str):
        self.conn, self.run_id = conn, run_id
        self.completed: list[tuple[str, callable]] = []

    def step(self, name: str, do, undo) -> dict:
        res = do()
        self.completed.append((name, undo))
        checkpoint(self.conn, self.run_id, len(self.completed), {"last_step": name})
        return res

    def compensate(self) -> list[str]:
        undone = []
        for name, undo in reversed(self.completed):
            try:
                undo()                            # undo must itself be idempotent
                undone.append(name)
            except Exception as exc:
                audit.write(run_id=self.run_id, action="compensation_failed",
                            detail=f"{name}: {exc}")
        return undone

# usage
saga = Saga(conn, run_id)
try:
    saga.step("reserve_stock", lambda: inventory.reserve(sku, qty),
              lambda: inventory.release(sku, qty))
    saga.step("charge", lambda: payments.charge(order_id, amount, idem_key=f"{run_id}:charge"),
              lambda: payments.refund(order_id, idem_key=f"{run_id}:refund"))
except Exception:
    saga.compensate()
    raise
```

**Loop breaker:**

```python
def detect_loop(recent_calls: list[dict], threshold: int = 3) -> bool:
    if len(recent_calls) < threshold:
        return False
    window = recent_calls[-threshold:]
    sigs = {(c["tool"], json.dumps(c["args"], sort_keys=True)) for c in window}
    return len(sigs) == 1

def handle_loop(state) -> dict:
    # 1) prune the observation that likely drives the loop, 2) retry once, 3) escalate
    state.scratch = state.scratch[-2:]
    state.scratch.append("NOTE: previous identical action was already executed; choose a "
                         "different approach or finish with a partial result.")
    return state
```

**Degradation ladder:**

```python
LADDER = ["full", "reduced_tools", "cached_answers", "partial_report", "human_handoff"]

def degrade(current: str, reason: str) -> str:
    idx = min(LADDER.index(current) + 1, len(LADDER) - 1)
    audit.write(action="degrade", detail=f"{current}->{LADDER[idx]}: {reason}")
    return LADDER[idx]
```

**Structured failure object:**

```json
{
  "status": "failed",
  "error_class": "transient_exhausted",
  "completed_steps": ["s1", "s2"],
  "remaining_steps": ["s3", "s4"],
  "partial_result": {"found": 12, "expected": 30},
  "resume_handle": "run_7f3c...",
  "user_message": "I gathered 12 of 30 records before the search service timed out. You can retry from here."
}
```

## 8. Quality Standards

- Every step is checkpointed; resume works from the latest checkpoint.
- Retries are limited to transient faults with bounded attempts and a deadline.
- Mutations are idempotent by construction (keys derived from run and step).
- Compensation is implemented for multi-step mutations and tested.
- Loop detection breaks repetition within ≤ 3 identical calls.
- Failures return structured objects, never raw stack traces, to users.
- Degradation is explicit and logged.

## 9. Verification and Testing

- Kill the process mid-run; resume and confirm no duplicate side effects.
- Force a tool to return 429 five times; confirm bounded retries and clean failure.
- Force a permanent error; confirm no retry storm and no compensation for steps not taken.
- Trigger a loop with a stub model; confirm detection and escalation.
- Verify compensation runs in reverse order and is itself idempotent.

## 10. Security Considerations

- Compensation actions are privileged; require the same authorization as the original action and audit them.
- Do not retry non-idempotent actions without keys—duplicate refunds/emails are real financial harm.
- Checkpoint data may contain sensitive content; encrypt at rest and restrict access.
- A failure message must not leak internal details (stack traces, hostnames, secrets) to end users.
- Guard against retry amplification attacks (user-triggered loops burning budget) with per-user caps.
- Poisoned context can cause infinite replanning; bound replans and log the triggering content for review (redacted).

## 11. Failure Handling

- **Resume replays a completed step:** checkpoint index drift—store the step ID, not just an integer index.
- **Compensation fails:** mark the run `needs_reconciliation`, alert, and provide a manual repair checklist.
- **Repeated transient failures:** circuit-break the tool and degrade; do not retry indefinitely.
- **Budget exhausted mid-run:** return partial results with a clear explanation and a resume handle.
- **Context overflow on resume:** reload a compacted state, not the raw transcript.

## 12. Expected Deliverables

1. Fault taxonomy and classification code.
2. Checkpoint schema and resume procedure.
3. Idempotency implementation for mutating tools.
4. Saga/compensation design with tested undos.
5. Loop detection and poison-context handling.
6. Degradation ladder configuration.
7. Structured failure contract and test results.

## 13. References

- microservices.io — Saga pattern — https://microservices.io/patterns/data/saga.html
- Temporal durable execution — https://docs.temporal.io/evaluate/understanding-temporal
- AWS Builders' Library — Timeouts, retries, backoff — https://aws.amazon.com/builders-library/
- "Release It!" (Nygard) — circuit breakers and stability patterns.
- Google SRE Workbook — Managing load and failure — https://sre.google/workbook/
- OWASP LLM Top 10 (LLM06 Excessive Agency) — https://owasp.org/www-project-top-10-for-large-language-model-applications/
