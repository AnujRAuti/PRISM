---
name: tool-calling-engineering
description: Design LLM tool/function interfaces that models call correctly—precise schemas, unambiguous descriptions, validation, error messages that teach, and idempotent side effects.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Tool Calling Engineering

## 1. Purpose

Make tool calling reliable. Models fail at tools for design reasons, not intelligence reasons: overlapping tool descriptions, loose schemas, ambiguous parameter names, and errors that do not explain how to recover. This skill covers tool schema design, description writing, argument validation, error contracts, idempotency, and measurement of tool-selection accuracy.

**Scope:** tools you expose to models. Each tool is a capability grant—treat schema design and permission scoping as security work.

## 2. Activation Conditions

- Exposing functions, APIs, or MCP tools to a model.
- The model calls the wrong tool, invents parameters, or loops on errors.
- Converting an internal API into a model-callable tool.
- Adding writes/deletes that a model can trigger.
- Keywords: tool calling, function calling, JSON schema, tool description, arguments validation, idempotency, idempotency keys, MCP tools, function definitions.

## 3. When Not to Use

- Building MCP servers specifically (use mcp-server-integration) — though the schema guidance applies.
- The task needs no external actions.
- The action is a simple deterministic call you can perform in code without the model deciding.

## 4. Required Context

1. The capability being exposed and its real-world side effects.
2. Underlying API semantics: pagination, rate limits, idempotency, error codes.
3. The model's constraints: context budget for tool definitions, provider limits on schema features.
4. Caller identity and authorization model (per-user tokens, tenant scoping).
5. Expected volume and latency.

## 5. Operating Procedure

1. **Scope tools narrowly.** Prefer `get_order(order_id)` over `query(sql)`. Small, single-purpose tools are selected more accurately and audited more easily.
2. **Write the schema in JSON Schema with constraints**: enums for fixed choices, `pattern` for IDs, `minimum`/`maximum`, `maxLength`, `required` for all essential fields, and `additionalProperties: false`.
3. **Write descriptions that disambiguate**: what the tool does, when to use it, when NOT to use it, and one input→output example. Descriptions are prompts.
4. **Name parameters in domain language** (`customer_id`, not `cid`), and use consistent naming across tools.
5. **Validate arguments server-side** before execution, even if the model produced schema-conforming output—never trust the client.
6. **Return structured results** with a stable shape: `{ok, data, error_code, message, retryable}`.
7. **Write errors that teach**: include what went wrong, which field, and what to try next ("order_id must be a UUID; received 'abc'"). Never return raw stack traces or SQL.
8. **Make writes idempotent**: accept an `idempotency_key`, deduplicate server-side, and document the effect window.
9. **Bound results**: paginate (`limit` with max), truncate long strings with a pointer, and cap token size of tool output.
10. **Measure tool accuracy** on an eval set of user intents: correct tool, correct args, unnecessary calls, and recovery-after-error rate.
11. **Iterate descriptions based on traces**, not intuition.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Schema | JSON Schema 2020-12, Pydantic v2, Zod |
| Providers | OpenAI function calling, Anthropic tool use, Gemini function calling |
| Protocol | MCP (for cross-client tools) |
| Validation | Pydantic, `jsonschema`, Zod |
| Tracing | OpenTelemetry spans per tool call |
| Testing | Scripted model simulators, recorded traces |

## 7. Practical Implementation

**Well-specified tool schemas (JSON Schema):**

```json
{
  "name": "lookup_order",
  "description": "Fetch a single order by its ID. Use when the user references a specific order and you need its status, items, or totals. Do NOT use for listing a customer's orders; use list_orders instead. Returns the order or a not_found error.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "required": ["order_id"],
    "properties": {
      "order_id": {
        "type": "string",
        "description": "Order identifier, format ord_ followed by 16 hex characters.",
        "pattern": "^ord_[0-9a-f]{16}$"
      },
      "include": {
        "type": "array",
        "description": "Optional related objects to embed. Omit for a compact response.",
        "items": {"enum": ["items", "shipping_address"]},
        "maxItems": 2,
        "uniqueItems": true
      }
    }
  }
}
```

**Pydantic implementation with validation and error contract:**

```python
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class Include(str, Enum):
    items = "items"
    shipping_address = "shipping_address"

class LookupOrderArgs(BaseModel):
    model_config = {"extra": "forbid"}
    order_id: str = Field(pattern=r"^ord_[0-9a-f]{16}$")
    include: list[Include] = Field(default_factory=list, max_length=2)

class ToolError(BaseModel):
    ok: bool = False
    error_code: str
    message: str
    retryable: bool = False
    hint: str | None = None

def lookup_order(args: dict, principal) -> dict | ToolError:
    try:
        parsed = LookupOrderArgs.model_validate(args)
    except Exception as exc:
        return ToolError(error_code="invalid_arguments",
                         message=str(exc),
                         hint="order_id must look like ord_0123456789abcdef")
    order = db.fetch_order(parsed.order_id, tenant_id=principal.tenant_id)
    if order is None:
        return ToolError(error_code="not_found", retryable=False,
                         message=f"no order {parsed.order_id} for this account",
                         hint="Ask the user to confirm the order ID; do not retry with a guess.")
    return {"ok": True, "data": serialize(order, include=parsed.include)}
```

**Idempotent write tool:**

```python
import hashlib, json

def refund_order(args: dict, principal) -> dict:
    parsed = RefundArgs.model_validate(args)          # amount_cents, reason enum
    key = f"refund:{principal.tenant_id}:{parsed.order_id}:{parsed.amount_cents}"
    existing = idempotency.get(key)
    if existing:
        return {"ok": True, "data": existing, "deduplicated": True}
    with db.transaction():
        result = payments.refund(parsed.order_id, parsed.amount_cents,
                                 idempotency_key=key, reason=parsed.reason)
        idempotency.put(key, result, ttl_days=7)
    audit.log(actor=principal.id, action="refund", order=parsed.order_id,
              amount=parsed.amount_cents, key=key)
    return {"ok": True, "data": result}
```

**Result truncation with a continuation handle:**

```python
MAX_CHARS = 4000

def bounded_result(rows: list[dict], cursor: str | None) -> dict:
    out, used = [], 0
    for row in rows:
        s = json.dumps(row)
        if used + len(s) > MAX_CHARS:
            break
        out.append(row); used += len(s)
    return {"ok": True, "data": out, "truncated": len(out) < len(rows),
            "next_cursor": cursor if out else None}
```

**Tool-selection eval:**

```python
CASES = [
    {"intent": "what's the status of order ord_0123456789abcdef",
     "expected_tool": "lookup_order",
     "expected_args": {"order_id": "ord_0123456789abcdef"}},
    {"intent": "show me all my orders from last month",
     "expected_tool": "list_orders", "expected_args": {"since": "last_month"}},
]

def score_tool_choice(run_model, cases) -> dict:
    correct_tool = correct_args = 0
    for c in cases:
        call = run_model(c["intent"])      # returns {"tool": ..., "args": ...}
        if call["tool"] == c["expected_tool"]:
            correct_tool += 1
            if all(call["args"].get(k) == v for k, v in c["expected_args"].items()):
                correct_args += 1
    n = len(cases)
    return {"tool_accuracy": correct_tool / n, "arg_accuracy": correct_args / n}
```

**Retry-after-error guidance:**

```text
Retryable:   rate_limited (backoff), timeout, 503
Not retryable: not_found (ask user), invalid_arguments (fix args), permission_denied (escalate)
```

## 8. Quality Standards

- Every tool has a schema with constraints, a description covering when not to use it, and a documented error contract.
- All arguments validated server-side with `additionalProperties: false`.
- Writes accept an idempotency key and are safe to retry.
- Tool outputs are bounded and token-efficient.
- Errors are actionable and never leak internals.
- Authorization is applied per call using the caller's identity, not a shared service account.
- Tool-selection accuracy is measured and tracked.

## 9. Verification and Testing

- Unit tests call each tool with valid, boundary, and malformed arguments; assert error codes.
- Property tests for pattern constraints (random invalid IDs must be rejected).
- Idempotency test: call a write twice with the same key → one side effect.
- Context test: tool result larger than the cap is truncated with a cursor.
- Eval: run 50 realistic intents through the model and report tool/arg accuracy.

## 10. Security Considerations

- Treat model-generated arguments as untrusted input: validate types, ranges, patterns, and authorization.
- Never expose a generic `execute_sql`, `run_shell`, or `fetch_url` tool without a hard allowlist and sandbox.
- Enforce tenant scoping inside the tool, not in the prompt.
- Do not return secrets in tool output; redact fields not needed for the task.
- Rate-limit per tool per user; writes should also have volume caps (e.g. max refunds/day) with alerting.
- Log every tool invocation with actor, arguments hash, and outcome for audit; never log credentials.
- Guard against injection in tool results (a web page fetched by a tool may contain instructions).

## 11. Failure Handling

- **Model invents tools/params:** tighten descriptions, reduce tool count per turn, and return a schema validation error listing valid fields.
- **Model calls the same tool repeatedly:** detect identical consecutive calls and return "you already called this with the same arguments; here is the result" instead of re-executing.
- **Downstream API rate limits:** surface `retryable: true` with a suggested backoff, and back off internally before returning.
- **Ambiguous user requests:** expose a `clarify` tool rather than guessing parameters.
- **Tool too slow:** per-tool timeout plus an async job tool (`start_job`/`check_job`) for long operations.

## 12. Expected Deliverables

1. Tool catalogue with schemas and descriptions.
2. Validation and authorization implementation.
3. Error contract and examples.
4. Idempotency design for mutating tools.
5. Truncation/pagination strategy.
6. Tool-selection eval results.
7. Audit logging spec.

## 13. References

- OpenAI function calling — https://platform.openai.com/docs/guides/function-calling
- Anthropic tool use — https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview
- JSON Schema reference — https://json-schema.org/docs
- Model Context Protocol specification — https://modelcontextprotocol.io/specification
- OWASP LLM06 Excessive Agency — https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Pydantic documentation — https://docs.pydantic.dev/
