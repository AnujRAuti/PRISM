---
name: agent-permission-management
description: Scope what agents can do—per-tool authorization, per-user delegation, capability budgets, allowlists, and revocation—so a compromised or confused agent cannot exceed its mandate.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Agent Permission Management

## 1. Purpose

Define and enforce the boundary of an agent's authority. An agent's permissions are the union of its tools, credentials, and the data it can read—so the real security design is deciding that union deliberately and enforcing it in code. This skill covers permission models (capability-based, RBAC, delegated OAuth), per-action authorization, budgets and rate caps, sandboxing, and revocation.

**Scope:** agents you operate on systems you own. Test permission boundaries only in your own environments.

## 2. Activation Conditions

- Giving an agent write access to production systems.
- Multiple users share one agent deployment (multi-tenant authority).
- An agent can spend money, send messages, or modify data.
- Security review of an agent feature.
- Keywords: agent permissions, least privilege, capability, tool allowlist, delegated access, OAuth scopes, sandbox, budget, revocation, excessive agency.

## 3. When Not to Use

- The agent has no tool access (pure text generation).
- Human authorization design in general (use authentication-and-authorization-security) — though the delegation model must align.
- MCP server transport specifics (use mcp-server-integration).

## 4. Required Context

1. The agent's stated purpose and the minimum actions required.
2. Identity model: on whose behalf does the agent act, and with which credentials?
3. Data classification the agent may read.
4. Systems it can mutate and their blast radius.
5. Regulatory/contractual constraints on automated action.

## 5. Operating Procedure

1. **Enumerate capabilities** the agent needs, expressed as verbs and resources (`read:invoices(tenant)`, `send:email(customer)`, `write:repo(branch)`).
2. **Choose the delegation model**:
   - On-behalf-of-user (OAuth token with user's scopes) — strongest for per-user isolation.
   - Service identity with narrow scopes — simpler, but must enforce per-user authorization inside the tool.
   - Capability token minted per run, single-purpose and short-lived.
3. **Enforce authorization at the tool layer**, never in the prompt: every tool call checks `principal.has(capability, resource)`.
4. **Apply per-user scoping** inside queries (`tenant_id`, `user_id`) — the agent should not be able to request another user's data even if it tries.
5. **Set quantitative budgets**: max spend per run/day, max records written, max emails sent, max API calls. Enforce and alert.
6. **Allowlist outbound destinations** (domains, repos, branches) rather than blocklisting.
7. **Sandbox execution**: containers with no network by default, read-only mounts, no host credentials.
8. **Separate credential per agent deployment**; never share a human's personal token.
9. **Design revocation**: a kill switch that disables the agent's credentials and cancels queued runs within minutes.
10. **Audit every privileged action**: who (which user), what (tool, args hash), when, result.
11. **Test the boundary**: attempt cross-tenant access, tool calls outside the allowlist, budget overruns, and prompt-injected escalation.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Authorization engine | Open Policy Agent (Rego), Cedar, Casbin, custom policy module |
| Delegation | OAuth 2.1 with narrow scopes, token exchange (RFC 8693), workload identity |
| Secrets | Vault dynamic secrets, cloud STS, short-lived tokens |
| Sandbox | containers + seccomp/AppArmor, gVisor, Firecracker |
| Budgets | Redis counters, quota service, gateway rate limits |
| Audit | append-only log + SIEM |
| Kill switch | feature flag + credential revocation runbook |

## 7. Practical Implementation

**Capability model:**

```python
from dataclasses import dataclass
from enum import Enum

class Action(str, Enum):
    read = "read"
    write = "write"
    send = "send"
    delete = "delete"

@dataclass(frozen=True)
class Capability:
    action: Action
    resource: str          # e.g. "invoices", "email", "repo:org/app"

@dataclass
class Principal:
    user_id: str
    tenant_id: str
    capabilities: frozenset[Capability]
    run_id: str

    def can(self, action: Action, resource: str) -> bool:
        return Capability(action, resource) in self.capabilities
```

**Tool-level enforcement with resource scoping:**

```python
from fastapi import HTTPException

def require(principal: Principal, action: Action, resource: str) -> None:
    if not principal.can(action, resource):
        audit.denied(principal, action, resource)
        raise HTTPException(403, f"agent not permitted to {action.value} {resource}")

def send_email(principal: Principal, to_customer_id: str, subject: str, body: str) -> dict:
    require(principal, Action.send, "email")
    customer = crm.get(to_customer_id, tenant_id=principal.tenant_id)  # tenant-scoped
    if customer is None:
        raise HTTPException(404, "customer not found")
    if not budget.try_consume(principal.run_id, "emails", 1, limit=25):
        raise HTTPException(429, "email budget exhausted for this run")
    return email_service.send(to=customer.email, subject=subject, body=body,
                              idempotency_key=f"{principal.run_id}:{to_customer_id}")
```

**Per-run capability token (minted narrow, short-lived):**

```python
import time, jwt

def mint_run_token(user_id: str, tenant_id: str, caps: list[str], ttl_s: int = 900) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": f"agent:{user_id}", "tenant": tenant_id, "caps": caps,
         "iat": now, "exp": now + ttl_s, "aud": "agent-tools"},
        signing_key, algorithm="ES256",
    )

# Downstream tool services verify signature, audience, expiry, and the specific capability claim.
```

**OPA policy (Rego) for tool authorization:**

```rego
package agent.authz

default allow := false

allow if {
  input.capability.action == "read"
  input.capability.resource == "invoices"
  input.principal.tenant_id == input.resource_tenant
}

allow if {
  input.capability.action == "send"
  input.capability.resource == "email"
  input.context.budget_emails_remaining > 0
  not input.context.customer_opted_out
}
```

**Budgets with hard stops:**

```python
class RunBudget:
    LIMITS = {"tool_calls": 60, "emails": 25, "refund_cents": 500_000, "spend_usd": 2.0}

    def __init__(self, redis, run_id: str):
        self.redis, self.run_id = redis, run_id

    def try_consume(self, counter: str, amount: float) -> bool:
        key = f"budget:{self.run_id}:{counter}"
        pipe = self.redis.pipeline()
        pipe.incrbyfloat(key, amount)
        pipe.expire(key, 86_400)
        used, _ = pipe.execute()
        return float(used) <= self.LIMITS[counter]
```

**Kill switch:**

```python
def kill_agent(agent_id: str, reason: str, operator: str) -> None:
    flags.disable(f"agent:{agent_id}")                    # stops new runs immediately
    secrets.revoke_all(agent_id)                          # invalidate credentials
    db.execute("UPDATE runs SET status='cancelled' WHERE agent_id=%s AND status IN "
               "('queued','running','awaiting_approval')", (agent_id,))
    audit.write(actor=operator, action="agent.kill", target=agent_id, detail=reason)
```

**Boundary test suite:**

```python
def test_cross_tenant_read_denied(client, principal_a):
    r = client.get("/tools/invoices/INV-FROM-TENANT-B", headers=auth(principal_a))
    assert r.status_code in (403, 404)

def test_unlisted_tool_denied(client, principal_a):
    r = client.post("/tools/shell", json={"cmd": "id"}, headers=auth(principal_a))
    assert r.status_code in (403, 404)

def test_budget_enforced(client, principal_a):
    for _ in range(26):
        client.post("/tools/send_email", json=valid_email(), headers=auth(principal_a))
    r = client.post("/tools/send_email", json=valid_email(), headers=auth(principal_a))
    assert r.status_code == 429
```

## 8. Quality Standards

- Capabilities are explicit, enumerated, and checked in code at every tool entry point.
- No tool trusts the model's claim about who the user is; identity comes from the authenticated context.
- Per-user/tenant scoping is applied in the data query.
- Budgets are enforced with hard stops and alerts.
- Credentials are per-agent, short-lived, and revocable.
- Outbound destinations are allowlisted.
- Every privileged action is audited with actor, resource, and outcome.
- Revocation takes effect within the documented window and is tested.

## 9. Verification and Testing

- Cross-tenant access tests for every read and write tool.
- Tool allowlist tests: unlisted tool → 403 with no side effect.
- Budget tests for each counter (calls, emails, spend, records).
- Token tests: expired, wrong audience, missing capability, tampered signature → rejected.
- Kill-switch test: after revocation, queued runs cancel and new runs fail closed.
- Audit test: each denied and allowed action appears in the log with a correlation ID.

## 10. Security Considerations

- **Prompt injection is the primary escalation vector:** injected content can convince the model to call any available tool. The only reliable defense is that the tool itself refuses unauthorized actions.
- Never place credentials in the model context; inject at call time inside the tool.
- Avoid "confused deputy" designs: a service credential with broad access must still enforce the end user's authority.
- Deny by default; new tools require an explicit capability grant and review.
- Rate-limit agent actions per user to prevent runaway cost or spam.
- Separate duties: the agent that drafts an email should not also hold the send capability without approval.
- Log denials; repeated denials indicate either misconfiguration or an attack.

## 11. Failure Handling

- **Agent blocked on legitimate work:** grant the narrowest additional capability for the specific task with an expiry, not a broad scope.
- **Budget exhausted mid-task:** return a structured partial result and require human continuation; do not silently retry.
- **Credential leak suspected:** revoke, rotate, audit usage, and check for actions outside the normal pattern.
- **Policy engine unavailable:** fail closed for privileged actions (deny), with a clear error; never fall back to allow.
- **Cross-tenant data observed in output:** treat as an incident; rotate, audit, and fix the query-level scoping.

## 12. Expected Deliverables

1. Capability inventory per agent role.
2. Delegation model and token design.
3. Enforcement code at every tool boundary.
4. Budget policy and implementation.
5. Allowlists for outbound destinations and tools.
6. Audit schema and sample entries.
7. Revocation runbook with a tested kill switch.
8. Boundary test suite results.

## 13. References

- OWASP LLM06 Excessive Agency — https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST SP 800-162 (ABAC) — https://csrc.nist.gov/pubs/sp/800/162/upd2/final
- RFC 8693 OAuth 2.0 Token Exchange — https://www.rfc-editor.org/rfc/rfc8693
- Open Policy Agent — https://www.openpolicyagent.org/docs/
- Cedar policy language — https://docs.cedarpolicy.com/
- Google BeyondCorp / zero trust principles — https://cloud.google.com/beyondcorp
- ISO/IEC 42001 (AI management systems) — https://www.iso.org/standard/42001
