---
name: graphql-api-engineering
description: Design and operate GraphQL APIs—schema modeling, N+1 elimination with DataLoader, query cost limits, authorization per field, and persisted queries.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# GraphQL API Engineering

## 1. Purpose

Ship GraphQL APIs that stay fast and safe under arbitrary client queries. GraphQL moves query shape control to the client, which means N+1 explosions, unbounded nesting, and accidental data exposure are the default failure modes. This skill covers schema design, batching and caching with DataLoader, depth/cost limits, field-level authorization, error handling without leaking internals, and persisted queries.

**Scope:** your own API. GraphQL introspection and error messages can disclose internal structure—treat them as information disclosure surfaces in production.

## 2. Activation Conditions

- New GraphQL schema or a schema being extended.
- Resolvers cause N+1 queries or slow nested fields.
- Clients send pathological queries (deep nesting, huge lists) and degrade the service.
- Need field-level or object-level authorization.
- Keywords: GraphQL, schema, resolver, DataLoader, N+1, depth limit, query cost, persisted queries, Apollo, Strawberry, Strawberry, Relay, introspection, fragments.

## 3. When Not to Use

- Simple CRUD consumed by one first-party client — REST is cheaper to operate and cache.
- File uploads/downloads (use HTTP endpoints).
- Public APIs where CDN caching of GET responses is essential (REST wins).

## 4. Required Context

1. Clients and their query patterns (mobile, web, third parties).
2. Data sources: SQL, microservices, third-party APIs.
3. Authorization model (roles, ownership, tenants).
4. Expected query complexity and traffic.
5. Server stack (Python/Node/Java) and ORM.

## 5. Operating Procedure

1. **Model the domain, not the tables**: types with explicit nullability; use `ID!` for identifiers, connections for lists.
2. **Design the schema for the clients' core journeys**; avoid generic "everything" schemas and avoid exposing ORM models directly.
3. **Batch and cache with DataLoader** per request, keyed by parent ID; this eliminates N+1.
4. **Enforce complexity limits**: maximum depth (e.g. 10–12), maximum aliases, maximum nodes, and a per-query cost budget with a computed cost function.
5. **Disable introspection in production** and require persisted queries for known clients; allow ad-hoc queries only for trusted consumers.
6. **Authorize at the field and object level**, inside resolvers or a policy layer—never rely on the client not asking for a field.
7. **Return structured errors** with stable `extensions.code`; mask internal messages and stack traces in production.
8. **Use mutations with explicit input types** and return the affected entity plus user errors (`errors: [UserError!]!`), not just booleans.
9. **Add pagination with cursor connections** and enforce a max page size server-side.
10. **Instrument per-field latency** and track slow resolvers; log query hashes, not raw queries with PII.
11. **Version by evolution**: deprecate fields with `@deprecated(reason:)`, never remove without a usage check.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Python server | Strawberry, Ariadne, Graphene |
| Node server | Apollo Server, GraphQL Yoga, Pothos |
| Schema tools | GraphQL Code Generator, `graphql-inspector` |
| DataLoader | `aiodataloader` (Python), `dataloader` (JS) |
| Limits | `graphql-depth-limit`, `graphql-cost-analysis`, custom validation rules |
| Persisted queries | Apollo persisted queries, Relay compiler artifacts |
| Testing | `graphql-testing-library`, pytest + `graphql-core` |
| Tracing | OpenTelemetry GraphQL instrumentation |

## 7. Practical Implementation

**Schema (SDL-first intent, Strawberry shown):**

```python
import strawberry
from typing import Optional

@strawberry.type
class Product:
    id: strawberry.ID
    name: str
    price_cents: int
    description: Optional[str]

@strawberry.type
class OrderLine:
    product: Product
    quantity: int

@strawberry.type
class Order:
    id: strawberry.ID
    status: str
    lines: list[OrderLine]

@strawberry.type
class OrderEdge:
    cursor: str
    node: Order

@strawberry.type
class OrderConnection:
    edges: list[OrderEdge]
    page_info: "PageInfo"

@strawberry.type
class PageInfo:
    has_next_page: bool
    end_cursor: Optional[str]

@strawberry.input
class RefundInput:
    order_id: strawberry.ID
    amount_cents: int
    reason: str

@strawberry.type
class UserError:
    field: Optional[str]
    code: str
    message: str

@strawberry.type
class RefundPayload:
    refund: Optional["Refund"]
    errors: list[UserError]
```

**DataLoader removing N+1:**

```python
from aiodataloader import DataLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db import ProductRow

class ProductLoader(DataLoader[str, dict]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def batch_load_fn(self, product_ids: list[str]) -> list[dict | None]:
        rows = (await self._session.execute(
            select(ProductRow).where(ProductRow.id.in_(product_ids))
        )).scalars().all()
        by_id = {r.id: {"id": r.id, "name": r.name, "price_cents": r.price_cents,
                        "description": r.description} for r in rows}
        return [by_id.get(pid) for pid in product_ids]      # order must match input
```

**Request-scoped context (loader per request, never global):**

```python
import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import Depends
from app.api.auth import require_user, Principal

@strawberry.type
class Query:
    @strawberry.field
    async def order(self, info: strawberry.Info, id: strawberry.ID) -> Order | None:
        ctx = info.context
        principal: Principal = ctx["principal"]
        repo = ctx["order_repo"]
        order = await repo.get(id)
        if order is None or order.tenant_id != principal.tenant_id:
            return None                                    # do not disclose existence
        return order

async def get_context(principal: Principal = Depends(require_user), session=Depends(get_session)):
    return {"principal": principal, "order_repo": SqlOrderRepository(session),
            "product_loader": ProductLoader(session)}

schema = strawberry.Schema(query=Query, mutation=Mutation, types=[UserError, RefundPayload])
graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql")
```

**Field-level authorization in a resolver:**

```python
@strawberry.type
class Order:
    id: strawberry.ID
    status: str

    @strawberry.field
    async def internal_notes(self, info: strawberry.Info) -> str | None:
        principal = info.context["principal"]
        if not principal.can("orders:read_internal"):
            return None            # or raise a masked GraphQLError
        return await info.context["order_repo"].internal_notes(self.id)
```

**Depth + cost validation rule:**

```python
from graphql import ValidationRule, GraphQLError, FragmentSpreadNode, FieldNode, Node

class DepthLimit(ValidationRule):
    def __init__(self, max_depth: int = 12) -> None:
        super().__init__()
        self.max_depth = max_depth

    def enter_field(self, node: FieldNode, *_args) -> None:
        depth = self._depth(node)
        if depth > self.max_depth:
            raise GraphQLError(f"query exceeds max depth of {self.max_depth}")

    def _depth(self, node: Node) -> int:
        depth, current = 0, node
        while current is not None:
            depth += 1
            current = getattr(current, "parent", None)
        return depth

class CostLimit(ValidationRule):
    """Charge 1 per field, extra for list fields; reject above budget."""
    def __init__(self, budget: int = 500) -> None:
        super().__init__()
        self.budget = budget
        self.cost = 0

    def enter_field(self, node: FieldNode, *_args) -> None:
        self.cost += 1
        if node.arguments and any(a.name.value in {"first", "last"} for a in node.arguments):
            self.cost += 10
        if self.cost > self.budget:
            raise GraphQLError("query exceeds cost budget")
```

**Mutation returning user errors:**

```python
@strawberry.type
class Mutation:
    @strawberry.mutation
    async def refund(self, info: strawberry.Info, input: RefundInput) -> RefundPayload:
        principal = info.context["principal"]
        if not principal.can("refunds:create"):
            raise GraphQLError("Not authorized", extensions={"code": "FORBIDDEN"})
        if input.amount_cents <= 0:
            return RefundPayload(refund=None, errors=[
                UserError(field="amountCents", code="INVALID_AMOUNT",
                          message="Refund amount must be positive.")])
        try:
            refund = await info.context["refund_service"].create(
                order_id=input.order_id, amount_cents=input.amount_cents, reason=input.reason)
        except InsufficientRefundable as exc:
            return RefundPayload(refund=None, errors=[
                UserError(field="amountCents", code="EXCEEDS_REFUNDABLE", message=str(exc))])
        return RefundPayload(refund=refund, errors=[])
```

**Error masking config (Strawberry examples of masking handler):**

```python
from strawberry.extensions import MaskErrors

schema = strawberry.Schema(query=Query, mutation=Mutation,
                           extensions=[MaskErrors()])
```

**Persisted queries (Apollo-style, server check):**

```python
from fastapi import Request, HTTPException

PERSISTED: dict[str, str] = load_persisted_queries()   # hash -> query text

async def enforce_persisted(request: Request) -> dict:
    body = await request.json()
    sha = body.get("extensions", {}).get("persistedQuery", {}).get("sha256Hash")
    if sha and sha in PERSISTED:
        return {"query": PERSISTED[sha], "variables": body.get("variables", {})}
    if settings.allow_adhoc_queries and authenticated_trusted(request):
        return body
    raise HTTPException(400, "PersistedQueryNotFound")
```

**Query plan visibility:**

```python
# Log slow fields with OpenTelemetry spans
from opentelemetry import trace
tracer = trace.get_tracer("graphql")

async def timed_resolve(field_name: str, fn, *args, **kwargs):
    with tracer.start_as_current_span(f"graphql.resolve.{field_name}") as span:
        result = await fn(*args, **kwargs)
        return result
```

## 8. Quality Standards

- No resolver issues queries in a loop; all parent-keyed fetches go through DataLoaders.
- Depth, cost, alias, and page-size limits are enforced before execution.
- Introspection disabled in production; persisted queries required for public clients.
- Every field is authorized server-side by ownership/role, verified by tests that call the field directly.
- Errors have stable `extensions.code`; internal messages never reach clients.
- Schema changes are additive; removals go through deprecation plus a usage audit.
- Per-field latency is observable.

## 9. Verification and Testing

- DataLoader test: query an order list with N lines and assert exactly 1 product SQL query (capture query count).
- Limit tests: a 15-level query and a 10k-field query are rejected with a clear error.
- Authorization test: query another tenant's order ID → `null`/`FORBIDDEN`, never data.
- Schema diff in CI (`graphql-inspector diff`) fails on breaking changes.
- Load test with realistic query mixes; check p99 and DB query counts per request.
- Error-masking test: force an exception and assert no stack trace leaks.

## 10. Security Considerations

- GraphQL authorization is per-field: a resolver that trusts its parent object enables privilege escalation through a different entry point.
- Disable introspection and GraphiQL/Playground in production unless the API is public by design.
- Enforce query limits and timeouts: one malicious query can exhaust DB connections (aliasing amplification).
- Do not expose `__schema` details publicly; schema disclosure aids attackers.
- Variables and directives can bypass naive string-based filters — validate at the resolver.
- Batch operations with `@include`/`@skip` and aliases can multiply writes; cap mutation count per request.
- Logs must not contain tokens or full query text with PII; log hashes and operation names.

## 11. Failure Handling

- **Sudden N+1:** a new resolver bypassed DataLoader; add query-count assertions in tests per field.
- **Timeouts under load:** reduce max depth, add per-field timeouts, and cache hot entities in a request-scoped loader plus a short-TTL cache.
- **Breaking schema change reaches clients:** run `graphql-inspector diff` on PRs and block incompatible changes.
- **Partial failures with nulls:** use nullable fields and error paths deliberately; make critical fields non-null only when a failure should fail the whole response.
- **Persisted query rollout:** support both modes during migration with telemetry on ad-hoc usage, then switch off.

## 12. Expected Deliverables

1. Schema with types, inputs, and deprecation policy.
2. Loader map per entity and request context design.
3. Limit configuration (depth, cost, aliases, page size).
4. Authorization matrix per field/object.
5. Error-code catalog and masking strategy.
6. Persisted-query strategy.
7. Query-count and limit test suite.

## 13. References

- GraphQL specification — https://spec.graphql.org/
- GraphQL security best practices — https://graphql.org/learn/security/
- Strawberry documentation — https://strawberry.rocks/docs
- Apollo Server — https://www.apollographql.com/docs/apollo-server/
- `aiodataloader` — https://github.com/syrusakbary/aiodataloader
- GraphQL Code Generator — https://the-guild.dev/graphql/codegen
- graphql-inspector — https://the-guild.dev/graphql/inspector
- OWASP GraphQL Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html
