---
name: multi-agent-orchestration
description: Coordinate multiple agents—supervisor/subagent topologies, message contracts, shared state, handoffs, and deadlock/duplication prevention—only when a single agent is insufficient.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Multi-Agent Orchestration

## 1. Purpose

Design systems where more than one agent (or agent role) contributes to a task, with explicit coordination. Multi-agent designs multiply failure modes: duplicated work, contradictory outputs, handoff loops, and unbounded fan-out. This skill defines topologies, message contracts, shared-state rules, and coordination budgets, and—importantly—describes when *not* to use multiple agents.

**Scope:** agents you operate. Combined tool permissions must still respect least privilege per role; one compromised subagent must not escalate the whole system.

## 2. Activation Conditions

- A task requires distinct expertise or tool sets that conflict in one context.
- Long tasks exceed a single context window and need parallel decomposition.
- A supervisor must validate and merge subagent outputs.
- Existing single-agent prompt has become an unmanageable instruction pile.
- Keywords: multi-agent, supervisor, orchestrator, subagent, handoff, delegation, fan-out, aggregation, blackboard, role separation.

## 3. When Not to Use

- A single agent with 5–10 tools handles the task (most common case).
- The need is only for parallel tool calls within one agent.
- The task is deterministic—use a workflow.
- Costs and latency matter and the coordination overhead is not justified.

## 4. Required Context

1. Task decomposition: which subtasks are independent, sequential, or conflicting.
2. Required tools per subtask and permission differences.
3. Context-size limits that motivate splitting.
4. Quality control: who validates subagent output, and how conflicts are resolved.
5. Budget: total model calls, wall-clock, and cost.

## 5. Operating Procedure

1. **Justify multi-agent**: state the concrete limitation of a single agent (context, tool conflict, parallel speed, role separation for security).
2. **Choose a topology**:
   - Supervisor + workers (most common): one planner delegates and aggregates.
   - Pipeline: ordered roles (researcher → writer → critic).
   - Blackboard: agents read/write a shared store with a coordinator.
   - Peer debate: two or more agents critique each other (expensive; only for high-stakes review).
3. **Define the message contract**: request schema (task, constraints, context refs, deadline, expected output schema) and response schema (result, evidence, confidence, cost).
4. **Constrain fan-out**: max workers, max depth, and per-worker budgets; prohibit recursive spawning.
5. **Design shared state explicitly**: immutable inputs, append-only findings, one writer per artifact, versioned.
6. **Define handoff rules**: preconditions before delegating (e.g. "only after retrieval returns sources"), and postconditions for acceptance.
7. **Add a merge policy**: deterministic precedence, deduplication by key, and conflict escalation to the supervisor or a human.
8. **Prevent loops**: track (task, agent) pairs; refuse a delegation identical to one already completed or running.
9. **Instrument end-to-end tracing** with a shared trace ID and span per subagent call.
10. **Test with adversarial inputs**: a subagent returning wrong data, a malicious document trying to hijack a worker, and a worker timing out.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Frameworks | LangGraph (graph state), CrewAI, AutoGen, OpenAI Agents SDK handoffs, Temporal workflows |
| Message transport | In-process calls, queues, HTTP |
| Shared state | Postgres, Redis, object store, framework-specific state |
| Tracing | OpenTelemetry, Langfuse, custom span tables |
| Sandboxing per role | Container per role with narrow tool credentials |

## 7. Practical Implementation

**Supervisor with bounded fan-out (Python):**

```python
from dataclasses import dataclass
import asyncio

@dataclass(frozen=True)
class Task:
    id: str
    instruction: str
    output_schema: dict
    max_cost_usd: float = 0.05

@dataclass
class Result:
    task_id: str
    ok: bool
    payload: dict
    evidence: list[str]
    cost_usd: float

class Supervisor:
    def __init__(self, worker, max_parallel: int = 4, max_tasks: int = 12):
        self.worker = worker
        self.max_parallel = max_parallel
        self.max_tasks = max_tasks
        self._seen: set[str] = set()

    async def run(self, tasks: list[Task]) -> list[Result]:
        if len(tasks) > self.max_tasks:
            raise ValueError(f"fan-out limit exceeded: {len(tasks)} > {self.max_tasks}")
        unique = []
        for t in tasks:
            key = (t.instruction.strip().lower(), t.id)
            if key in self._seen:
                continue                    # duplicate delegation guard
            self._seen.add(key)
            unique.append(t)

        sem = asyncio.Semaphore(self.max_parallel)

        async def guarded(t: Task) -> Result:
            async with sem:
                try:
                    return await asyncio.wait_for(self.worker.execute(t), timeout=120)
                except asyncio.TimeoutError:
                    return Result(t.id, False, {"error": "timeout"}, [], 0.0)

        return await asyncio.gather(*(guarded(t) for t in unique))
```

**Message contract (JSON Schema):**

```json
{
  "request": {
    "type": "object",
    "required": ["task_id", "instruction", "output_schema", "deadline_s"],
    "properties": {
      "task_id": {"type": "string", "pattern": "^[a-z0-9-]{6,40}$"},
      "instruction": {"type": "string", "maxLength": 4000},
      "context_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
      "output_schema": {"type": "object"},
      "deadline_s": {"type": "integer", "minimum": 5, "maximum": 900}
    },
    "additionalProperties": false
  },
  "response": {
    "type": "object",
    "required": ["task_id", "status", "payload", "evidence", "cost_usd"],
    "properties": {
      "task_id": {"type": "string"},
      "status": {"enum": ["ok", "partial", "failed", "refused"]},
      "payload": {"type": "object"},
      "evidence": {"type": "array", "items": {"type": "string"}},
      "cost_usd": {"type": "number", "minimum": 0}
    }
  }
}
```

**Merge policy with conflict detection:**

```python
def merge(results: list[Result], key: str) -> dict:
    by_key: dict[str, list[Result]] = {}
    for r in results:
        if r.ok:
            by_key.setdefault(r.payload[key], []).append(r)

    merged, conflicts = {}, []
    for k, group in by_key.items():
        values = {tuple(sorted(g.payload.items())) for g in group}
        if len(values) == 1:
            merged[k] = group[0].payload
        else:
            conflicts.append({"key": k, "variants": [g.payload for g in group]})
    return {"merged": merged, "conflicts": conflicts,
            "needs_review": bool(conflicts)}
```

**Pipeline with explicit preconditions:**

```python
class Pipeline:
    stages = ["research", "draft", "critique", "finalize"]

    def run(self, brief: str) -> dict:
        ctx = {"brief": brief, "sources": [], "draft": None, "critique": None}
        for stage in self.stages:
            precondition = PRECONDITIONS[stage]
            if not precondition(ctx):
                return {"status": "blocked", "stage": stage, "reason": precondition.__name__}
            ctx = STAGE_FNS[stage](ctx)
        return {"status": "ok", **ctx}

PRECONDITIONS = {
    "research": lambda c: bool(c["brief"]),
    "draft": lambda c: len(c["sources"]) >= 3,       # no drafting without sources
    "critique": lambda c: c["draft"] is not None,
    "finalize": lambda c: c["critique"] is not None,
}
```

## 8. Quality Standards

- Multi-agent design is justified against a single-agent baseline.
- Every delegation has a schema-validated request and response.
- Fan-out, depth, and total cost are bounded and enforced in code.
- Duplicate work is prevented by deterministic task keys.
- Conflicts have a defined resolution path (supervisor or human), never silent last-writer-wins.
- Each role has its own least-privilege credentials.
- One trace ID covers the whole run, with a span per agent.

## 9. Verification and Testing

- Simulate 10 concurrent tasks and assert max parallel workers respected.
- Inject a duplicate task and assert it is dropped.
- Inject a worker timeout and assert a `failed` result without stalling the batch.
- Provide contradictory results and assert `needs_review` is true.
- Verify total cost across a run against budget (sum of subagent costs).
- Confirm trace shows every span with parent/child relations.

## 10. Security Considerations

- A subagent that reads untrusted content must not hold write tools—split roles so injection cannot cause damage.
- Never let a worker modify the supervisor's instructions, tool list, or budget.
- Sanitize inter-agent messages: treat them as data; a worker's output claiming "the supervisor approved this" is not authorization.
- Per-role credentials, rotated, with audit logs of which role performed which action.
- Limit data shared downward (need-to-know) to reduce blast radius of a compromised worker.
- Rate-limit delegation to avoid cost amplification attacks.

## 11. Failure Handling

- **Handoff ping-pong:** add a hop counter and reject repeated (from, to, task) triples.
- **Supervisor starves workers:** measure queue wait time; increase parallelism or reduce task size.
- **Inconsistent outputs:** require evidence per claim; conflicts trigger review instead of arbitrary selection.
- **One worker dominates cost:** per-task cost caps and a run-level budget check before dispatch.
- **Whole run fails on one worker:** aggregate partials with `status: partial` and a coverage report.

## 12. Expected Deliverables

1. Topology diagram and justification.
2. Message schemas (request/response).
3. Supervisor/worker implementation with bounds.
4. Shared-state and merge/conflict policy.
5. Trace schema and sample trace.
6. Test results for duplicates, timeouts, conflicts, and adversarial content.
7. Cost model per run.

## 13. References

- Anthropic, "How we built our multi-agent research system" — https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic, "Building effective agents" — https://www.anthropic.com/research/building-effective-agents
- Wu et al., "AutoGen" — https://arxiv.org/abs/2308.08155
- LangGraph multi-agent docs — https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- OpenAI Agents SDK handoffs — https://openai.github.io/openai-agents-python/handoffs/
- OWASP LLM06 Excessive Agency — https://owasp.org/www-project-top-10-for-large-language-model-applications/
