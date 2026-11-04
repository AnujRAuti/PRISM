---
name: agent-architecture
description: Design AI agent systems—loop structure, state model, tool interface, termination criteria, and failure boundaries—that are debuggable and bounded rather than emergent and fragile.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Agent Architecture

## 1. Purpose

Design the skeleton of an agent before writing prompts: what the loop is, what state it carries, how tools are exposed, when it stops, and how failures are contained. Most agent projects fail not from weak models but from unbounded loops, opaque state, and tools with too much authority. This skill produces an explicit architecture: control flow, state schema, tool contracts, budgets, and observability hooks.

**Scope:** agents you build and operate. An agent's blast radius equals the union of its tools' permissions—design authority deliberately and require human approval for irreversible effects.

## 2. Activation Conditions

- Building an agent that plans and acts over multiple steps.
- An existing agent loops, stalls, or takes unexpected actions.
- Deciding between a single-agent loop, a workflow with fixed steps, or multi-agent design.
- Defining tool boundaries and termination rules.
- Keywords: agent architecture, agent loop, ReAct, plan-execute, state machine, tool use, autonomy, termination, budget, agentic workflow.

## 3. When Not to Use

- A deterministic workflow solves the task (prefer explicit code over an agent).
- A single LLM call with structured output is sufficient.
- Multi-agent coordination specifics (use multi-agent-orchestration).
- Prompt engineering tactics only (use advanced-prompt-engineering).

## 4. Required Context

1. The task, its success criteria, and how success is verified objectively.
2. Available tools/systems and the harmful actions possible through them.
3. Latency and cost budget per task (steps × tokens).
4. Whether human review exists and at which checkpoints.
5. Failure tolerance: what happens when the agent is wrong, slow, or stuck.

## 5. Operating Procedure

1. **Decide whether an agent is warranted.** If the steps are known in advance, build a workflow. Use an agent only when the path must be discovered at runtime.
2. **Define the loop shape**: perceive → decide → act → observe → repeat, with an explicit max iteration count and a termination predicate.
3. **Design the state object** as a typed schema: goal, plan, completed steps, artifacts, accumulated evidence, errors, and budget counters. Persist it after each step (checkpointing).
4. **Define the tool surface** minimally: each tool has a name, description, input schema, output schema, idempotency semantics, and permission class (read-only vs. mutating).
5. **Set budgets**: max steps, max tokens, max wall-clock, max cost, and per-tool call caps. Exceeding any budget forces a graceful stop with a partial-result report.
6. **Choose a control policy**: hard-coded ordering where dependencies are known; model-driven planning only within a bounded scope.
7. **Add verification inside the loop**: after each action, check the observed result against expectations; on mismatch, replan rather than push forward.
8. **Design termination**: explicit `finish` with a structured result, abstention when evidence is insufficient, and escalation to a human when confidence is low.
9. **Define failure boundaries**: what the agent may retry, what it must never retry, and what requires approval.
10. **Instrument**: log every step with inputs, tool calls, outputs, token counts, and timing; attach a trace ID.
11. **Test the loop** with scripted tool fakes: happy path, tool errors, contradictory observations, and adversarial tool output.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Frameworks | Plain Python + provider SDK, LangGraph, PydanticAI, OpenAI Agents SDK, Strands |
| Structured model I/O | JSON schema / function calling, Pydantic |
| State persistence | SQLite/Postgres, Redis, object store |
| Tracing | OpenTelemetry GenAI conventions, Langfuse, LangSmith |
| Sandboxing | Firecracker/gVisor containers, restricted subprocess |
| Queueing | Celery/RQ/Temporal for long-running tasks |

## 7. Practical Implementation

**Explicit agent loop with budgets and typed state (Python, provider-agnostic):**

```python
from dataclasses import dataclass, field
from typing import Literal, Protocol
import json, time

@dataclass
class AgentState:
    goal: str
    scratch: list[str] = field(default_factory=list)      # observations
    artifacts: dict[str, str] = field(default_factory=dict)
    steps: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)

@dataclass
class Budget:
    max_steps: int = 20
    max_seconds: float = 180
    max_calls_per_tool: int = 5

class Tool(Protocol):
    name: str
    mutating: bool
    def schema(self) -> dict: ...
    def run(self, args: dict) -> dict: ...

def over_budget(state: AgentState, b: Budget) -> str | None:
    if state.steps >= b.max_steps:
        return "max_steps"
    if time.monotonic() - state.started_at >= b.max_seconds:
        return "deadline"
    if any(v >= b.max_calls_per_tool for v in state.tool_calls.values()):
        return "tool_cap"
    return None

def run_agent(goal: str, tools: dict[str, Tool], model, budget: Budget = Budget()) -> dict:
    state = AgentState(goal=goal)
    while True:
        reason = over_budget(state, budget)
        if reason:
            return {"status": "stopped", "reason": reason, "state": state.__dict__}

        decision = model.decide(goal=state.goal, scratch=state.scratch,
                                artifacts=state.artifacts,
                                tools=[t.schema() for t in tools.values()])

        if decision["type"] == "finish":
            return {"status": "done", "result": decision["result"], "state": state.__dict__}

        if decision["type"] == "tool":
            name = decision["tool"]
            if name not in tools:
                state.scratch.append(f"error: unknown tool {name}")
                state.steps += 1
                continue
            tool = tools[name]
            state.tool_calls[name] = state.tool_calls.get(name, 0) + 1
            try:
                observed = tool.run(decision["args"])
            except Exception as exc:                     # tool errors are data, not crashes
                observed = {"error": str(exc)}
            state.scratch.append(f"{name} -> {json.dumps(observed)[:2000]}")
            state.steps += 1
            continue

        state.scratch.append(f"error: unrecognized decision {decision['type']}")
        state.steps += 1
```

**Workflow-first alternative (preferable when steps are known):**

```python
def handle_support_ticket(ticket: dict) -> dict:
    triage = classify(ticket["body"])                 # structured LLM call
    if triage["category"] == "billing_dispute":
        policy = fetch_policy("billing_dispute")       # deterministic tool
        draft = draft_reply(ticket, policy)            # LLM
        return require_human_approval(draft) if triage["risk"] == "high" else send(draft)
    return escalate(ticket, "unhandled_category")
```

**Termination contract (structured):**

```json
{
  "type": "finish",
  "result": {
    "status": "success",
    "answer": "Refund window is 30 days from delivery.",
    "evidence": [{"source": "policy/refunds.md", "quote": "within 30 days of delivery"}],
    "confidence": 0.86
  }
}
```

**Adversarial tool-output handling:**

```python
def safe_observation(raw: str, limit: int = 4000) -> str:
    # Tool output is untrusted data, never instructions.
    clipped = raw[:limit]
    return f"<tool_output untrusted=\"true\">\n{clipped}\n</tool_output>"
```

## 8. Quality Standards

- Every agent run has hard budgets (steps, time, cost) and terminates deterministically when exceeded.
- State is serializable and checkpointed; a crashed run can be resumed or inspected.
- Tools are declared with input/output schemas and a mutating flag.
- The loop has an explicit finish contract with structured output.
- Tool errors are handled as observations, never as unhandled exceptions.
- Agent output includes evidence or an explicit abstention.
- Every step is traced with a correlation ID.

## 9. Verification and Testing

- Unit tests with a fake model that returns scripted decisions (no network).
- Scenario tests: tool raises, returns empty, returns conflicting data, returns an instruction-like string.
- Budget tests: an agent that never finishes must stop at `max_steps` with status `stopped`.
- Replay tests: given a recorded trace, the loop reproduces the same state transitions.
- Evidence: traces showing step counts, tokens, and tool calls per scenario.

## 10. Security Considerations

- Least privilege per tool: read-only tools by default; mutating tools require explicit approval, scoping, and audit logging.
- Tool output is untrusted: an HTTP response or file may contain injected instructions. Wrap and label it, and never let it change the tool allowlist.
- Validate all tool arguments against the schema before execution; reject unexpected fields.
- No shell execution with model-generated strings unless sandboxed with an allowlist.
- Secrets must never enter the model context; inject them inside tool implementations at call time.
- Cap loop iterations to prevent cost-based denial of service; rate-limit per user.
- Log enough to audit every action while redacting secrets and PII.

## 11. Failure Handling

- **Loop does not terminate:** budget counter is the safeguard; inspect the last observations for a repeating pattern and add a repetition detector.
- **Agent picks wrong tool repeatedly:** tool descriptions are ambiguous—add usage examples and counter-examples, and return actionable error messages.
- **State grows unbounded:** summarize observations after N steps and persist raw traces separately.
- **Intermittent tool timeouts:** per-tool timeout with retry policy; surface a degraded path.
- **Model returns malformed decisions:** validate against schema, re-ask once with the error, then abort with a clear failure.

## 12. Expected Deliverables

1. Architecture decision: workflow vs. agent, with justification.
2. Loop pseudocode/implementation with budgets and termination.
3. Typed state schema and checkpointing strategy.
4. Tool catalogue with schemas, permissions, and error contracts.
5. Trace/log schema.
6. Test scenarios including adversarial tool output.
7. Human-in-the-loop points and escalation rules.

## 13. References

- Yao et al., "ReAct: Synergizing Reasoning and Acting" — https://arxiv.org/abs/2210.03629
- Anthropic, "Building effective agents" — https://www.anthropic.com/research/building-effective-agents
- OpenAI Agents SDK — https://openai.github.io/openai-agents-python/
- LangGraph docs — https://langchain-ai.github.io/langgraph/
- OWASP LLM Top 10 (LLM06 excessive agency) — https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST AI RMF — https://www.nist.gov/itl/ai-risk-management-framework
