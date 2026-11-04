---
name: authorization-and-permissions
description: Enforce authorization server-side—RBAC/ABAC models, deny-by-default policy layers, object-level checks, and tests that prove IDOR and privilege escalation are blocked.
metadata:
  domain: backend
  version: 1.0.0
  risk: high
---

# Authorization and Permissions

## 1. Purpose

Decide what an authenticated caller may do, and enforce it on the server for every object and every action. Broken access control is consistently the top application security risk: missing object-level checks (IDOR), trusting client-supplied roles, policy applied in the UI but not the API, and privilege escalation through bulk endpoints. This skill defines the authorization model, a single enforcement layer, object-level scoping, and adversarial tests.

**Scope:** authorization for systems you own. Testing authorization means attempting access that should fail—only against your own environments with written authorization. Never probe third-party systems.

## 2. Activation Conditions

- Adding roles, teams, tenants, or sharing to a product.
- Security review flags missing access checks.
- Permission logic scattered across handlers.
- Supporting external collaborators or admin impersonation.
- Keywords: RBAC, ABAC, ReBAC, authorization, permissions, roles, policy, OPA, Casbin, IDOR, object-level, tenant isolation, least privilege, privilege escalation.

## 3. When Not to Use

- Authentication (who you are) — separate concern; use authentication-and-session-management.
- Network-level segmentation, which complements but never replaces application authorization.
- Simple two-role admin/user apps where a check per route suffices—do not build a policy engine, but still scope objects.

## 4. Required Context

1. Actors: users, service accounts, agents, admins, support staff.
2. Resources and their hierarchy (org → project → item).
3. Sharing rules and ownership semantics.
4. Whether roles must be dynamic (attribute-based) or static (role-based).
5. Regulatory constraints on access logging (who saw what).

## 5. Operating Procedure

1. **Enumerate actions per resource** as explicit verbs: `order:read`, `order:refund`, `member:invite`.
2. **Choose the model**: RBAC for coarse roles, ABAC for attributes (region, clearance, ownership), ReBAC for sharing graphs; combine roles for actions with attributes for scope.
3. **Deny by default**: no rule matches → deny. Every route starts closed and opens explicitly.
4. **Enforce in one layer** (service/middleware), never only in the UI or only in individual handlers.
5. **Check object-level access, not just action-level**: `can(principal, "order:read", order)` verifies tenant and ownership, not merely that the role includes `order:read`.
6. **Pass the actor explicitly** through every layer (`principal` argument); never read the user from ambient globals.
7. **Prevent tenant leakage in queries**: add `WHERE tenant_id = :tenant` from the principal, and test with two tenants.
8. **Guard bulk and search endpoints**: filters must be scoped by policy, not by the client's parameters.
9. **Log authorization decisions** (allow and deny) with actor, action, resource, and reason for audit.
10. **Make admin bypass explicit and audited**: a separate permission (`admin:impersonate`) with mandatory justification and logging.
11. **Re-run the full permission matrix as tests** on each change; permissions drift silently otherwise.

## 6. Tools and Technologies

| Approach | Options |
|---|---|
| In-app | Policy functions/classes, Casbin, `oso`, `permit` |
| External | Open Policy Agent (OPA/Rego), Cerbos, SpiceDB/Zanzibar-style |
| Scope filters | ORM query scopes, Postgres Row-Level Security |
| Testing | `pytest` matrices, `httpx` with multiple principals |
| Audit | Append-only access log table, SIEM forwarding |

## 7. Practical Implementation

**Permission catalog and role mapping (deny by default):**

```python
from enum import StrEnum

class Action(StrEnum):
    ORDER_READ = "order:read"
    ORDER_REFUND = "order:refund"
    MEMBER_INVITE = "member:invite"
    REPORT_EXPORT = "report:export"

ROLE_PERMISSIONS: dict[str, frozenset[Action]] = {
    "viewer": frozenset({Action.ORDER_READ}),
    "support": frozenset({Action.ORDER_READ, Action.ORDER_REFUND}),
    "admin": frozenset(Action),          # explicit and reviewable
    "service": frozenset({Action.ORDER_READ}),
}
```

**Principal with frozen permissions:**

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)    # for service accounts

    def has(self, action: Action) -> bool:
        if action.value in self.scopes:
            return True
        return any(action in ROLE_PERMISSIONS.get(r, frozenset()) for r in self.roles)
```

**Single enforcement point with object-level check:**

```python
class Forbidden(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

def authorize(principal: Principal, action: Action, resource: object | None = None, *,
              audit=None) -> None:
    if not principal.has(action):
        audit and audit.deny(principal, action, resource, "missing_permission")
        raise Forbidden("missing_permission")

    # Object-level scoping: tenants must match unless an explicit cross-tenant grant exists
    owner_tenant = getattr(resource, "tenant_id", None)
    if owner_tenant is not None and owner_tenant != principal.tenant_id:
        audit and audit.deny(principal, action, resource, "tenant_mismatch")
        raise Forbidden("tenant_mismatch")

    # Ownership rule for destructive actions on shared objects
    owner_user = getattr(resource, "owner_user_id", None)
    if action is Action.ORDER_REFUND and owner_user and owner_user != principal.user_id \
            and "support" not in principal.roles and "admin" not in principal.roles:
        audit and audit.deny(principal, action, resource, "not_owner")
        raise Forbidden("not_owner")

    audit and audit.allow(principal, action, resource)
```

**Usage in the service layer (transport-agnostic):**

```python
async def refund_order(session, principal: Principal, order_id: str, amount_cents: int) -> Refund:
    order = await OrderRepo(session).get(order_id)          # unscoped fetch
    if order is None:
        raise NotFound()
    authorize(principal, Action.ORDER_REFUND, order, audit=AUDIT)   # object-level check
    return await RefundService(session).create(order, amount_cents)
```

Wrap the same call in both the HTTP route and a CLI/worker command so no transport bypasses the check.

**Scoped query to prevent list-level leakage:**

```python
async def list_orders(session, principal: Principal, *, status: str | None, limit: int = 50):
    stmt = select(Order).where(Order.tenant_id == principal.tenant_id)   # mandatory scope
    if status:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(min(limit, 100))
    return (await session.scalars(stmt)).all()
```

**Postgres Row-Level Security as defense in depth:**

```sql
ALTER TABLE "order" ENABLE ROW LEVEL SECURITY;

CREATE POLICY order_tenant_isolation ON "order"
  USING (tenant_id = current_setting('app.tenant_id', true)::text)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::text);

-- Per-request, inside the transaction:
--   SET LOCAL app.tenant_id = 'tenant_42';
```

The application still filters by tenant; RLS catches a forgotten `WHERE`.

**OPA/Rego policy for externalized decisions:**

```rego
package app.authz

default allow := false

allow if {
  input.action == "order:read"
  some role in input.principal.roles
  role in {"viewer", "support", "admin"}
  input.resource.tenant_id == input.principal.tenant_id
}

allow if {
  input.action == "order:refund"
  some role in input.principal.roles
  role in {"support", "admin"}
  input.resource.tenant_id == input.principal.tenant_id
}
```

```python
import httpx

async def opa_decide(principal: Principal, action: Action, resource: dict) -> bool:
    async with httpx.AsyncClient(timeout=0.5) as client:
        r = await client.post(
            "http://opa:8181/v1/data/app/authz/allow",
            json={"input": {"principal": asdict(principal), "action": action.value,
                            "resource": resource}},
        )
        r.raise_for_status()
        return bool(r.json().get("result", False))
```

Policy-service failures must **deny** (fail closed), never default to allow.

**Admin impersonation with mandatory audit:**

```python
async def impersonate(admin: Principal, target_user_id: str, *, reason: str) -> Principal:
    if not admin.has(Action.ADMIN_IMPERSONATE):
        raise Forbidden("missing_permission")
    if len(reason.strip()) < 10:
        raise ValueError("a justification is required")
    await AUDIT.write(actor=admin.user_id, action="admin:impersonate",
                      target=target_user_id, reason=reason)
    target = await load_principal(target_user_id)
    return replace(target, roles=frozenset({"viewer"}))    # read-only during impersonation
```

**Permission matrix test (the core safety net):**

```python
import pytest

MATRIX = [
    # (role, action, resource_tenant, expected_status)
    ("viewer", "GET", "t1", 200),
    ("viewer", "POST_REFUND", "t1", 403),
    ("support", "POST_REFUND", "t1", 200),
    ("support", "POST_REFUND", "t2", 404),      # cross-tenant: not found, not forbidden
    ("admin", "POST_REFUND", "t2", 200),
    ("service", "GET", "t1", 200),
]

@pytest.mark.parametrize("role,op,resource_tenant,expected", MATRIX)
async def test_permission_matrix(client, make_token, seed, role, op, resource_tenant, expected):
    token = make_token(role=role, tenant="t1")
    order = seed.order(tenant_id=resource_tenant, owner_user_id=make_token.owner_id)
    r = await client.request("POST" if op == "POST_REFUND" else "GET",
                             f"/orders/{order.id}/refunds" if op == "POST_REFUND" else f"/orders/{order.id}",
                             headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == expected
```

**Enumeration resistance:** return `404` for resources in another tenant rather than `403`, so IDs cannot be probed for existence.

## 8. Quality Standards

- Deny by default; every permission is granted by an explicit rule.
- One enforcement layer used by every transport (HTTP, gRPC, CLI, jobs, agents).
- Object-level checks on every read, write, and delete—not just route-level.
- Tenant scope is applied in the query itself, verified by cross-tenant tests.
- Authorization failures return `403` for known resources the caller cannot access and `404` where existence is sensitive.
- Permission catalog is versioned in code and reviewed like a schema.
- All decisions (allow and deny) are audit-logged with actor, action, resource, and reason.
- Admin/imitation actions require a separate permission and a written justification.

## 9. Verification and Testing

- Full permission matrix test across roles × actions × resource ownership × tenant.
- IDOR sweep: for each `/{id}` endpoint, request another tenant's and another user's object with a valid token; expect `403`/`404`, never data.
- Privilege escalation test: a viewer attempts to modify their own role or add permissions; must fail.
- Bulk endpoint test: passing foreign IDs in a batch request fails per item.
- Policy-service outage test: OPA/Cerbos unreachable → requests are denied, not allowed.
- Audit completeness: every denied request produces a log entry.

## 10. Security Considerations

- Never trust client-supplied identity, role, tenant, or `is_admin` fields; derive them server-side from the session/token.
- Avoid "hidden field" authorization (admin UI only); the API is the security boundary.
- Mass assignment can silently change `tenant_id` or `owner_id` — use explicit input schemas with an allowlist.
- Beware of confused-deputy patterns: a service acting on behalf of a user must carry the user's scoped principal, not a super-token.
- Caching authorization decisions across users is a leakage risk; key by principal and invalidate on role change.
- Soft-deleted or transferred objects must not retain stale access; re-check on every request.
- Impersonation and support access are high-risk: time-box them, log them, and notify account owners per policy.
- Watch GraphQL/REST field-level exposure: authorize the field, not just the object.

## 11. Failure Handling

- **Legitimate user gets 403:** role mapping missing a permission or the object's tenant/owner field is unset — log the deny reason and fix the data, not the check.
- **User can access another tenant's data:** a query omitted the scope filter. Add RLS as a backstop and a cross-tenant test for every list endpoint.
- **Permission checks slow the request:** cache the role→permission map in-process (it changes rarely) but fetch object attributes per request; never cache per-object decisions across principals.
- **Policy service latency or outage:** fail closed with a short timeout and a clear 503; never fall back to allow.
- **Permission drift after refactor:** keep the matrix test as a required CI check; add a case whenever a new action is introduced.
- **Admin lockout:** keep one break-glass procedure with dual approval, documented and audited.

## 12. Expected Deliverables

1. Actor/action/resource catalog.
2. Authorization model choice and rationale.
3. Enforcement layer implementation with object-level checks.
4. Scoped query helpers per resource.
5. Permission matrix test suite.
6. Audit log schema and retention.
7. Admin/impersonation procedure.

## 13. References

- OWASP Top 10 — A01 Broken Access Control — https://owasp.org/Top10/A01_2021-Broken_Access_Control/
- OWASP Authorization Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- NIST RBAC model (INCITS 359) — https://csrc.nist.gov/projects/role-based-access-control
- Open Policy Agent — https://www.openpolicyagent.org/docs/latest/
- Cerbos — https://docs.cerbos.dev/
- SpiceDB / Zanzibar-style authorization — https://authzed.com/docs
- PostgreSQL Row Security Policies — https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- Casbin — https://casbin.org/docs/overview
