---
name: agent-observability
description: Trace and monitor agents end-to-end—span-per-step tracing, cost and token accounting, tool latency, failure attribution, and replayable session logs.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: medium
---

# Agent Observability

## 1. Purpose

Make agent behavior diagnosable after the fact and monitorable in production. An agent that fails silently is worse than one that fails loudly: without traces, "the agent did something weird" is unfalsifiable. This skill defines the span model for agent runs, what to record at each step, how to attribute cost and latency, which metrics to alert on, and how to keep traces privacy-safe.

**Scope:** your own agent deployments. Traces contain user prompts and tool outputs—treat them as sensitive data with retention limits and redaction.

## 2. Activation Conditions

- Launching or operating an agent in production.
- Debugging a specific bad run or a class of failures.
- Cost or latency regressions in agent workloads.
- Need to audit what an agent did on behalf of a user.
- Keywords: agent tracing, observability, spans, token accounting, cost monitoring, LLM telemetry, OpenTelemetry GenAI, replay, session logs, failure attribution.

## 3. When Not to Use

- Classic service monitoring without LLM calls (use observability-and-monitoring).
- Evaluation harness design (use agent-evaluation) — though the same spans feed both.

## 4. Required Context

1. Framework and runtime (custom loop, LangGraph, SDK-based).
2. Existing telemetry stack (OpenTelemetry collector, backend, sampling policy).
3. Data classification of prompts/outputs and retention requirements.
4. Cost model per model and tool.
5. SLOs: latency, success rate, and cost per task.

## 5. Operating Procedure

1. **Define the trace hierarchy**: `agent.run` (root) → `agent.step` → `llm.call` / `tool.call` / `retrieval` / `approval.wait`. Each span carries `run_id`, `user_id_hash`, `agent_version`, `prompt_version`.
2. **Record structured attributes** per span using GenAI semantic conventions where available: model, provider, input/output token counts, temperature, tool name, argument hash, result status, error class.
3. **Capture the decision**: what the model chose and why (short rationale if available), so failures are attributable to reasoning vs. tools vs. environment.
4. **Redact at the source**: hash identifiers, mask secrets/PII, and store full content in a separate access-controlled store referenced by `trace_id`.
5. **Sample sensibly**: 100% of errors and high-cost runs, plus a low percentage of successes; never sample away the interesting cases.
6. **Compute derived metrics**: cost per run, tokens per step, steps per run, tool error rate, p50/p95 run duration, success rate by task family.
7. **Alert on leading indicators**: step count spikes, tool error rate, cost per run increase, retry storms, approval queue age.
8. **Build a replay capability**: enough state to re-execute a run with the same inputs against a new version (in a sandbox).
9. **Review traces weekly** for a sample of runs; observability without review becomes archaeology.
10. **Set retention**: short for content, longer for aggregates; comply with deletion requests by trace ID.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Tracing | OpenTelemetry SDK + Collector, Jaeger, Tempo |
| LLM-specific | Langfuse, LangSmith, Phoenix (Arize), Helicone |
| Logs | Structured JSON to Loki/CloudWatch |
| Metrics | Prometheus (counters/histograms) |
| Cost | Provider usage APIs, per-call accounting |
| Replay | Deterministic fixtures + sandbox |

## 7. Practical Implementation

**Instrumented step wrapper (OpenTelemetry, Python):**

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
import hashlib, json, time

tracer = trace.get_tracer("agent.runtime")

def hash_args(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]

def traced_llm_call(model: str, prompt_version: str, messages: list[dict], call_fn):
    with tracer.start_as_current_span("llm.call") as span:
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("agent.prompt_version", prompt_version)
        span.set_attribute("agent.input_messages", len(messages))
        try:
            t0 = time.perf_counter()
            resp = call_fn(messages)
            span.set_attribute("gen_ai.usage.input_tokens", resp.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", resp.usage.completion_tokens)
            span.set_attribute("agent.latency_ms", round((time.perf_counter() - t0) * 1000, 1))
            span.set_attribute("agent.cost_usd", estimate_cost(model, resp.usage))
            return resp
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            span.record_exception(exc)
            raise

def traced_tool_call(name: str, args: dict, run_fn):
    with tracer.start_as_current_span("tool.call") as span:
        span.set_attribute("agent.tool.name", name)
        span.set_attribute("agent.tool.args_hash", hash_args(args))
        span.set_attribute("agent.tool.mutating", name in MUTATING_TOOLS)
        try:
            out = run_fn(args)
            span.set_attribute("agent.tool.status", "ok")
            return out
        except Exception as exc:
            span.set_attribute("agent.tool.status", "error")
            span.set_attribute("agent.tool.error_class", type(exc).__name__)
            raise
```

**Root span with run metadata:**

```python
def run_agent_traced(agent, goal: str, user_id: str, agent_version: str) -> dict:
    with tracer.start_as_current_span("agent.run") as root:
        run_id = root.get_span_context().trace_id
        root.set_attribute("agent.run_id", f"{run_id:032x}")
        root.set_attribute("agent.user_id_hash", hashlib.sha256(user_id.encode()).hexdigest()[:16])
        root.set_attribute("agent.version", agent_version)
        result = agent.run(goal)
        root.set_attribute("agent.outcome", result["status"])
        root.set_attribute("agent.steps", result["state"]["steps"])
        return result
```

**Prometheus metrics:**

```python
from prometheus_client import Counter, Histogram

RUNS = Counter("agent_runs_total", "Agent runs", ["agent", "outcome"])
STEPS = Histogram("agent_steps_per_run", "Steps per run", ["agent"],
                  buckets=(1, 2, 4, 8, 12, 16, 24, 32, 48))
TOOL_ERRORS = Counter("agent_tool_errors_total", "Tool errors", ["agent", "tool", "error_class"])
COST = Counter("agent_cost_usd_total", "Estimated cost", ["agent", "model"])
LATENCY = Histogram("agent_run_duration_seconds", "Run duration", ["agent"],
                    buckets=(1, 5, 10, 30, 60, 120, 300))

def record_run(agent: str, result: dict, cost_usd: float, duration_s: float) -> None:
    RUNS.labels(agent, result["status"]).inc()
    STEPS.labels(agent).observe(result["state"]["steps"])
    COST.labels(agent, result.get("model", "unknown")).inc(cost_usd)
    LATENCY.labels(agent).observe(duration_s)
```

**Alert rules:**

```yaml
groups:
  - name: agents
    rules:
      - alert: AgentStepSpike
        expr: histogram_quantile(0.95, sum by (le) (rate(agent_steps_per_run_bucket[30m]))) > 20
        for: 20m
        labels: {severity: page}
        annotations: {summary: "Agent step p95 > 20 (possible loop)"}
      - alert: AgentToolErrorRate
        expr: |
          sum(rate(agent_tool_errors_total[10m])) by (agent)
          / sum(rate(agent_tool_calls_total[10m])) by (agent) > 0.2
        for: 10m
        labels: {severity: page}
      - alert: AgentCostSpike
        expr: increase(agent_cost_usd_total[1h]) > 3 * avg_over_time(agent_cost_usd_total[24h] offset 1h)
        for: 30m
        labels: {severity: ticket}
```

**Privacy-safe content store:**

```python
def store_trace_content(trace_id: str, messages: list[dict], tool_outputs: list[dict]) -> None:
    redacted = redact(messages + tool_outputs)          # removes emails, tokens, card numbers
    blob_store.put(f"trace-content/{trace_id}.json", json.dumps(redacted),
                   metadata={"retention_days": "14", "classification": "internal"})
    # Span attributes carry only trace_id + hashes; content lives here, access-controlled.
```

**Replay harness (sandboxed):**

```python
def replay(trace_id: str, new_agent_version: str) -> dict:
    inputs = blob_store.get(f"trace-inputs/{trace_id}.json")      # original goal + tool fakes
    sandbox = Sandbox(tool_fakes=inputs["tool_fixtures"])         # no real side effects
    return run_agent_traced(new_agent_version, sandbox, inputs["goal"], "replay-user", new_agent_version)
```

## 8. Quality Standards

- Every run has a root span with run/user/version attributes; every model and tool call is a child span.
- Token counts and cost are recorded per call and aggregated per run.
- Tool calls record argument hashes and result status, never raw secrets.
- Errors carry error class and are recorded on spans, not swallowed.
- Sampling keeps 100% of errors and high-cost runs.
- Content is stored separately with redaction and retention limits.
- Alerts exist for step spikes, tool error rate, cost anomalies, and approval queue age.
- A run can be replayed from recorded inputs in a sandbox.

## 9. Verification and Testing

- Generate a synthetic run and verify all spans appear with correct parent/child relations.
- Assert redaction: a run containing an email/credit card has no such values in span attributes.
- Verify cost computation against provider usage for 10 sample calls.
- Fire each alert with a simulated metric and confirm routing.
- Replay a historical run and confirm the same outcome (or a documented, explained difference).

## 10. Security Considerations

- Traces are a rich data store of user content: encrypt, restrict, and set retention. Do not ship them to third-party tools without a data processing review.
- Redact at capture time; retroactive scrubbing is unreliable.
- Do not record secrets or full API keys in tool arguments—record hashes and lengths instead.
- Access to traces should be role-based and audited; support staff may not need full content.
- Beware of prompt-injection content stored in traces that a future agent (or analyst tool) might read.
- Trace IDs should not be guessable in public-facing endpoints.

## 11. Failure Handling

- **Missing spans:** auto-instrumentation not initialized before imports, or context not propagated across async tasks—verify with a known multi-step run.
- **Trace volume/cost too high:** sample successes, aggregate attributes, and move content to cheap storage.
- **Cost numbers wrong:** pricing table stale or cached tokens not accounted; reconcile with the provider invoice monthly.
- **Alert fatigue:** tighten thresholds to leading indicators and add `for:` durations; remove alerts that never lead to action.
- **Cannot reproduce a bad run:** inputs were not recorded—store the exact assembled prompt hash and tool fixtures going forward.

## 12. Expected Deliverables

1. Span schema and naming conventions.
2. Instrumentation code for model, tool, retrieval, and approval spans.
3. Redaction and content-store design.
4. Metrics and dashboards.
5. Alert rules with routing.
6. Sampling policy.
7. Replay procedure and a worked example.
8. Data retention and access policy.

## 13. References

- OpenTelemetry GenAI semantic conventions — https://opentelemetry.io/docs/specs/semconv/gen-ai/
- OpenTelemetry Python — https://opentelemetry.io/docs/languages/python/
- Langfuse — https://langfuse.com/docs
- Arize Phoenix — https://docs.arize.com/phoenix
- Google SRE Book (monitoring) — https://sre.google/sre-book/monitoring-distributed-systems/
- NIST AI RMF (measurement and monitoring) — https://www.nist.gov/itl/ai-risk-management-framework
