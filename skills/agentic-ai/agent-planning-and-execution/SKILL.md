---
name: agent-planning-and-execution
description: Make agents plan before acting—task decomposition, dependency-aware ordering, replanning on failure, and verification of each step against an explicit plan.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Agent Planning and Execution

## 1. Purpose

Give an agent a plan it can be held to. Without explicit planning, agents interleave reasoning and acting in ways that are hard to audit, hard to resume, and prone to skipping verification. This skill covers plan representations, decomposition strategies, execution with per-step verification, replanning triggers, and the plan/act separation that makes failures attributable.

**Scope:** agents you operate. A plan is a proposal, not an authorization—mutating steps still require the permission and approval controls described elsewhere.

## 2. Activation Conditions

- Multi-step tasks with ordering dependencies.
- Agents that skip steps, repeat work, or declare success prematurely.
- Long-running tasks that must survive interruptions.
- Need for a reviewable plan before execution (human approval of the plan).
- Keywords: planning, plan-and-execute, task decomposition, dependency graph, replanning, step verification, todo list, plan approval.

## 3. When Not to Use

- Single-step tasks or simple tool calls.
- Fully deterministic pipelines (encode the steps in code).
- Real-time systems where planning latency dominates the task.

## 4. Required Context

1. Task description and completion criteria.
2. Available actions and their preconditions/postconditions.
3. Dependency structure: what must happen before what.
4. Failure semantics per step: retryable, reversible, blocking.
5. Verification signals available (tests, checks, API reads).

## 5. Operating Procedure

1. **Define a plan schema**: ordered or DAG-structured steps, each with `id`, `goal`, `action`, `inputs`, `expected_outcome`, `verify`, and `on_failure`.
2. **Decompose top-down** until each step is a single verifiable action. If a step has no verification, it is too large or too vague.
3. **Model dependencies explicitly** (DAG, not just a list) when parallelism or ordering matters.
4. **Validate the plan before execution**: all required inputs available, actions permitted, no cycles, budgets respected.
5. **Optionally require plan approval** for high-risk tasks; the human reviews the plan, not just the output.
6. **Execute one step at a time**, verifying the expected outcome before proceeding. On mismatch: stop, classify (environment vs. plan defect), and replan.
7. **Maintain a live plan state** (pending/in-progress/done/failed) that is persisted, so a run can resume.
8. **Bound replanning**: max replans, and a rule that a repeated failure of the same step escalates instead of looping.
9. **Handle partial completion**: if blocked, report what is done, what remains, and why.
10. **Verify the plan's overall goal at the end** with an independent check, not the agent's own claim.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Plan representation | JSON schema, Pydantic models, DAG libraries (`networkx`) |
| Execution engine | Custom loop, LangGraph, Temporal workflows |
| State | Postgres/Redis checkpoint per step |
| Verification | Tests, assertions, read-back API calls, diff checks |
| Plan approval UI | Internal review app or ticket |

## 7. Practical Implementation

**Plan schema (Pydantic):**

```python
from pydantic import BaseModel, Field
from enum import Enum

class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"

class Step(BaseModel):
    id: str = Field(pattern=r"^s[0-9]{1,2}$")
    goal: str = Field(max_length=300)
    action: str                       # tool name or "reason"
    inputs: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    expected: str = Field(max_length=300)
    verify: str                       # verification method identifier
    on_failure: str = "replan"        # retry | replan | abort | ask_human

class Plan(BaseModel):
    goal: str
    steps: list[Step]

    def validate_dag(self) -> None:
        ids = {s.id for s in self.steps}
        assert len(ids) == len(self.steps), "duplicate step ids"
        for s in self.steps:
            missing = set(s.depends_on) - ids
            assert not missing, f"step {s.id} depends on unknown {missing}"
        # cycle detection
        graph = {s.id: list(s.depends_on) for s in self.steps}
        temp, perm = set(), set()
        def visit(n: str) -> None:
            assert n not in temp, f"cycle at {n}"
            if n in perm:
                return
            temp.add(n)
            for d in graph[n]:
                visit(d)
            temp.discard(n); perm.add(n)
        for n in graph:
            visit(n)
```

**Executor with per-step verification and bounded replanning:**

```python
def execute_plan(plan: Plan, tools: dict, state: dict, max_replans: int = 2) -> dict:
    plan.validate_dag()
    replans = 0
    status = {s.id: StepStatus.pending for s in plan.steps}

    while any(v == StepStatus.pending for v in status.values()):
        ready = [s for s in plan.steps
                 if status[s.id] == StepStatus.pending
                 and all(status[d] == StepStatus.done for d in s.depends_on)]
        if not ready:
            return {"status": "blocked", "state": state, "statuses": status}

        step = ready[0]
        status[step.id] = StepStatus.running
        try:
            result = tools[step.action].run(step.inputs) if step.action != "reason" \
                     else {"ok": True, "data": step.inputs}
            verified = VERIFIERS[step.verify](step, result, state)
        except Exception as exc:
            result, verified = {"error": str(exc)}, False

        if verified:
            status[step.id] = StepStatus.done
            state["artifacts"].update(result.get("data", {}) if isinstance(result, dict) else {})
            continue

        status[step.id] = StepStatus.failed
        if step.on_failure == "abort":
            return {"status": "failed", "step": step.id, "state": state, "statuses": status}
        if step.on_failure == "ask_human":
            return {"status": "needs_human", "step": step.id, "state": state, "statuses": status}
        if replans >= max_replans:
            return {"status": "replan_exhausted", "step": step.id, "state": state, "statuses": status}

        plan = replan(plan, failed_step=step, observed=result)   # model-proposed, validated by schema
        plan.validate_dag()
        replans += 1
        status = {s.id: (StepStatus.done if s.id in {x.id for x in plan.steps
                     if status.get(x.id) == StepStatus.done} else StepStatus.pending)
                  for s in plan.steps}

    return {"status": "done", "state": state, "statuses": status}
```

**Verifiers (independent of the agent's claim):**

```python
VERIFIERS = {
    "file_exists": lambda step, result, state: os.path.exists(step.inputs["path"]),
    "test_passed": lambda step, result, state: result.get("exit_code") == 0,
    "row_count": lambda step, result, state: result.get("data", {}).get("count", 0) == step.inputs["expected"],
    "http_200": lambda step, result, state: result.get("status") == 200,
    "diff_contains": lambda step, result, state: step.inputs["needle"] in result.get("data", {}).get("diff", ""),
}
```

**Replan prompt contract:**

```text
The step {step_id} failed with observation: {observation}
Current plan: {plan_json}
Produce a revised plan as JSON matching the Plan schema.

Rules:
- Keep completed steps unchanged.
- Do not repeat the exact failed action with identical inputs.
- If the failure is environmental (tool down), insert a diagnostic step first.
- Maximum {remaining} steps. If the goal is unachievable, return {"goal": ..., "steps": []}
  and set "unachievable": true with a one-line reason.
```

**Plan approval gate for high-risk tasks:**

```python
if plan_touches(plan, MUTATING_ACTIONS) and risk_level >= 3:
    approval = request_plan_approval(plan, requester=user_id)
    if approval.decision != "approve":
        return {"status": "rejected", "plan": plan.model_dump()}
    plan = approval.edited_plan or plan
```

## 8. Quality Standards

- Every step is a single action with an explicit expected outcome and a verification method.
- The plan is validated for completeness, permissions, and acyclicity before execution.
- Verification is independent (tests, read-backs), not the agent's self-assessment.
- Replanning is bounded and never repeats an identical failed action.
- Plan state is persisted; resume after interruption works.
- Partial results are reported honestly with what remains undone.
- Final success is verified against the original goal.

## 9. Verification and Testing

- Plan validation tests: cycles, unknown dependencies, duplicate IDs, disallowed actions.
- Executor tests: a step whose verification fails triggers the configured `on_failure` path.
- Replan-limit test: a permanently failing step stops after `max_replans`.
- Resume test: interrupt mid-plan and resume from the persisted state.
- End-to-end: the goal check fails when a step is skipped (no false success).

## 10. Security Considerations

- A plan can include harmful steps; validate every step's action against the agent's capability set before execution.
- Plan approval must bind to the exact plan hash; edits after approval require re-approval.
- Untrusted content can influence planning (injected instructions in retrieved docs); keep plan generation grounded in the user's stated goal and reject plans that introduce new objectives.
- Verification methods must not be influenced by the model (e.g. the agent must not be able to write its own test to pass).
- Persisted plans may contain sensitive values; restrict access.
- Bound plan size and step count to prevent resource exhaustion.

## 11. Failure Handling

- **Plan is too fine-grained:** steps lose meaning and cost explodes—coarsen to 3–8 steps.
- **Plan is too coarse:** verification is impossible—split until each step has an observable outcome.
- **Replan loop:** detect repeated failures on the same step and escalate to human with the trace.
- **Environment changed mid-run:** re-validate preconditions of remaining steps before continuing.
- **Agent declares success without verification:** make the goal check mandatory and independent; fail the run if it cannot be evaluated.

## 12. Expected Deliverables

1. Plan schema and validation code.
2. Decomposition examples for representative tasks.
3. Executor with verification and replan limits.
4. Persisted plan state and resume procedure.
5. Approval gate for high-risk plans.
6. Test results for failure, replan, and resume paths.

## 13. References

- "Plan-and-Solve Prompting" — https://arxiv.org/abs/2305.04091
- "ReAct" (interleaved reasoning and acting) — https://arxiv.org/abs/2210.03629
- "Tree of Thoughts" — https://arxiv.org/abs/2305.10601
- LangGraph planning patterns — https://langchain-ai.github.io/langgraph/concepts/
- Temporal durable execution — https://docs.temporal.io/
- Anthropic, "Building effective agents" — https://www.anthropic.com/research/building-effective-agents
