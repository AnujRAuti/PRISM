---
name: backend-architecture
description: Structure backend services with enforced layers, clear transaction and dependency boundaries, and composition roots that keep business logic framework-independent.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# Backend Architecture

## 1. Purpose

Give a backend a shape that survives growth: business rules isolated from frameworks, one direction of dependencies, transactions owned by a single layer, and explicit module boundaries. Most backend decay comes from business logic leaking into HTTP handlers and ORM models, cyclic imports between modules, and transactions opened in three different places. This skill defines layers, boundaries, and the enforcement that keeps them real.

**Scope:** your own services and codebase. Architectural changes touch deployment and data access—plan migrations and rollout, and never restructure a production database without an approved migration plan.

## 2. Activation Conditions

- New service or module, or a service being split.
- Handlers contain business logic and are hard to test.
- Cyclic imports, god-services, or "change one table, break five modules".
- Transaction scope is unclear or duplicated.
- Keywords: layered architecture, hexagonal, ports and adapters, clean architecture, service layer, repository, dependency injection, module boundaries, composition root.

## 3. When Not to Use

- Throwaway scripts and one-off internal tools.
- A single-endpoint function where a framework route is the whole program.
- Choosing between monolith and microservices as an organizational decision (address separately with system-architecture).

## 4. Required Context

1. Language/framework and ORM in use.
2. Domain areas and their data ownership.
3. Transactional requirements (which operations must be atomic).
4. Existing test strategy and CI constraints.
5. Deployment topology (single service, modular monolith, multiple services).

## 5. Operating Procedure

1. **Define layers** with one allowed direction: `api` (transport) → `services` (use cases, transactions) → `repositories` (persistence) → `domain` (entities, value objects, rules). `domain` imports nothing from the others.
2. **Make the domain framework-free**: no FastAPI/Express/Django imports in domain code; no ORM classes used as domain entities where avoidable.
3. **Put transaction boundaries in the service layer**: one use case = one transaction; repositories never commit.
4. **Define ports as Protocols/interfaces** in the service layer and implement adapters in infrastructure.
5. **Use a composition root** (app startup / DI container) to wire concrete implementations; never construct adapters inside business code.
6. **Enforce boundaries in CI** with `import-linter`, ESLint rules, or ArchUnit—not by convention.
7. **Keep module APIs explicit**: each module exposes a small public interface; cross-module calls go through it, not through tables.
8. **Map errors at the edge**: domain errors → transport errors (HTTP/gRPC) in one place.
9. **Write tests per layer**: domain unit tests (fast), service tests with fake repositories, API tests with a real database.
10. **Document the shape** with a layer diagram and a dependency rule list in the repo.

## 6. Tools and Technologies

| Concern | Options (Python) | Options (Node) |
|---|---|---|
| Web | FastAPI, Django, Litestar | Fastify, NestJS, Express |
| Persistence | SQLAlchemy 2.0, asyncpg | Prisma, Drizzle, Kysely |
| DI | `dependency-injector`, FastAPI `Depends` | NestJS providers, `tsyringe` |
| Boundary enforcement | `import-linter`, `pytest-archon` | `eslint-plugin-boundaries`, `dependency-cruiser` |
| Validation | Pydantic v2, msgspec | Zod, TypeBox |
| Testing | pytest, testcontainers | vitest, testcontainers |

## 7. Practical Implementation

**Directory layout (hexagonal, pragmatic):**

```
app/
├── api/                 # transport: routers, schemas, error mapping
│   ├── routes/orders.py
│   ├── schemas.py
│   └── errors.py
├── services/            # use cases; owns transactions
│   ├── orders.py
│   └── ports.py         # Protocol definitions
├── repositories/        # persistence adapters (SQLAlchemy)
│   └── orders_sql.py
├── domain/              # entities, value objects, rules (no framework imports)
│   ├── order.py
│   └── errors.py
├── infrastructure/      # db session, cache, queue clients, config
│   ├── db.py
│   └── config.py
└── main.py              # composition root
```

**Domain entity with invariant:**

```python
# app/domain/order.py
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

class OrderStatus(StrEnum):
    DRAFT = "draft"
    PLACED = "placed"
    PAID = "paid"
    CANCELLED = "cancelled"

class DomainError(Exception): ...

class InvalidTransition(DomainError):
    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        super().__init__(f"cannot move order from {current} to {target}")

@dataclass(frozen=True)
class Order:
    id: str
    status: OrderStatus
    total: Decimal
    currency: str

    def pay(self) -> "Order":
        if self.status is not OrderStatus.PLACED:
            raise InvalidTransition(self.status, OrderStatus.PAID)
        return Order(id=self.id, status=OrderStatus.PAID, total=self.total, currency=self.currency)
```

**Ports (Protocols) in the service layer:**

```python
# app/services/ports.py
from typing import Protocol
from app.domain.order import Order

class OrderRepository(Protocol):
    async def get(self, order_id: str) -> Order | None: ...
    async def save(self, order: Order) -> None: ...

class PaymentGateway(Protocol):
    async def charge(self, *, order_id: str, amount: int, currency: str) -> str: ...
```

**Use case with its own transaction:**

```python
# app/services/orders.py
import logging
from app.domain.errors import InvalidTransition
from app.services.ports import OrderRepository, PaymentGateway

log = logging.getLogger(__name__)

class OrderNotFound(Exception): ...
class PaymentFailed(Exception): ...

class OrderService:
    def __init__(self, repo: OrderRepository, payments: PaymentGateway, uow: "UnitOfWork") -> None:
        self._repo, self._payments, self._uow = repo, payments, uow

    async def pay(self, order_id: str, *, idempotency_key: str) -> Order:
        async with self._uow.begin():                       # one transaction per use case
            order = await self._repo.get(order_id)
            if order is None:
                raise OrderNotFound(order_id)
            if order.status.value == "paid":
                return order                                  # idempotent replay
            updated = order.pay()                             # domain enforces the rule
            charge_id = await self._payments.charge(
                order_id=order.id,
                amount=int(order.total * 100),
                currency=order.currency,
            )
            await self._repo.save(updated)
            await self._uow.record_audit("order.paid", order_id, charge_id)
            return updated
```

**Repository adapter (SQLAlchemy 2.0 async):**

```python
# app/repositories/orders_sql.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.order import Order, OrderStatus
from app.infrastructure.db import OrderRow

class SqlOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, order_id: str) -> Order | None:
        row = await self._session.get(OrderRow, order_id)
        return None if row is None else Order(
            id=row.id, status=OrderStatus(row.status),
            total=row.total, currency=row.currency,
        )

    async def save(self, order: Order) -> None:
        await self._session.execute(
            select(OrderRow).where(OrderRow.id == order.id)
        )  # lock/touch as needed
        row = await self._session.get(OrderRow, order.id)
        if row is not None:
            row.status = order.status.value
```

**Transport layer maps domain errors, nothing else:**

```python
# app/api/routes/orders.py
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from app.api.schemas import OrderResponse
from app.services.orders import OrderService, OrderNotFound, PaymentFailed
from app.services.deps import get_order_service

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/{order_id}/pay", response_model=OrderResponse)
async def pay_order(
    order_id: str,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8),
    svc: OrderService = Depends(get_order_service),
) -> OrderResponse:
    try:
        order = await svc.pay(order_id, idempotency_key=idempotency_key)
    except OrderNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found") from exc
    except PaymentFailed as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "payment provider unavailable") from exc
    return OrderResponse.model_validate(order)
```

**Boundary enforcement (`.importlinter`):**

```ini
[importlinter]
root_package = app

[importlinter:contract:layers]
name = Layered architecture
type = layers
layers =
    app.api
    app.services
    app.repositories
    app.domain

[importlinter:contract:domain-is-pure]
name = Domain must not import framework, ORM, or infrastructure
type = forbidden
source_modules = app.domain
forbidden_modules =
    fastapi
    sqlalchemy
    app.infrastructure
    app.api
```

```bash
pip install import-linter
lint-imports
```

**Composition root:**

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import orders
from app.infrastructure.db import make_engine, make_session_factory
from app.repositories.orders_sql import SqlOrderRepository
from app.services.deps import build_container

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine(settings.database_url)
    app.state.container = build_container(engine)   # wires repo + gateway + uow
    yield
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
app.include_router(orders.router)
```

**Service test with a fake repository (no database):**

```python
import pytest
from app.domain.order import Order, OrderStatus
from app.services.orders import OrderService, OrderNotFound

class FakeRepo:
    def __init__(self, orders): self.orders, self.saved = orders, []
    async def get(self, oid): return self.orders.get(oid)
    async def save(self, order): self.saved.append(order)

class FakeUoW:
    def begin(self): return self
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    async def record_audit(self, *a): pass

@pytest.mark.asyncio
async def test_pay_missing_order_raises():
    svc = OrderService(FakeRepo({}), payments=None, uow=FakeUoW())
    with pytest.raises(OrderNotFound):
        await svc.pay("nope", idempotency_key="k-12345678")
```

## 8. Quality Standards

- Dependency direction is enforced by CI; zero imports from `api` into `services` or `domain`.
- Domain modules import no web framework and no ORM.
- Exactly one transaction per use case, opened in the service layer.
- Handlers only translate: parse → call service → map errors/status.
- Every module has an explicit public surface.
- Domain rules are unit-tested without a database; use cases are testable with fakes.

## 9. Verification and Testing

```bash
lint-imports                     # boundary contracts pass
pytest tests/unit -q             # domain + service tests, no I/O
pytest tests/integration -q --testcontainers
```

- Confirm the API test can run against a real Postgres/Redis via testcontainers.
- Add a deliberate cross-layer import and verify CI fails.
- Measure coverage by layer; domain should be near 100%.

## 10. Security Considerations

- The layer that owns authorization must be explicit—usually the service layer, never only the route. A second transport (gRPC, CLI, job worker) must not bypass checks.
- Never let ORM entities be returned directly from the API; response schemas prevent accidental field exposure (password hashes, internal flags).
- Parameterized queries only; repositories must not concatenate SQL with input.
- Configuration and secrets come from the environment/secret manager at the composition root, never hard-coded in modules.
- Audit-log at the use-case boundary so every transport is covered.
- Treat dynamic dependency resolution (plugin loading) as a trust boundary; allowlist modules.

## 11. Failure Handling

- **Layer enforcement blocks an urgent fix:** document an exception with an expiry ticket; do not silently disable the contract.
- **Transactions spanning HTTP calls:** move the external call outside the transaction or use a saga/outbox; holding a DB transaction across a network call exhausts connections.
- **God service:** split by use case; if methods share no state, they belong in separate services.
- **Circular imports:** inject a port rather than importing the concrete adapter; if two modules need each other, one owns the data.
- **Over-engineered abstraction:** collapse layers that only forward calls; a two-layer app (routes + queries) is fine for small services.

## 12. Expected Deliverables

1. Layer diagram and dependency rules.
2. Directory layout with module public interfaces.
3. Ports and adapters for external systems.
4. Transaction boundary policy.
5. Boundary enforcement configuration in CI.
6. Error-mapping table (domain → transport).
7. Test plan by layer.

## 13. References

- "Architecture Patterns with Python" (Percival & Gregory) — https://www.cosmicpython.com/book/preface.html
- import-linter — https://import-linter.readthedocs.io/
- FastAPI bigger applications — https://fastapi.tiangolo.com/tutorial/bigger-applications/
- SQLAlchemy 2.0 asyncio — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Alistair Cockburn, Hexagonal Architecture — https://alistair.cockburn.us/hexagonal-architecture/
- Martin Fowler, Presentation Domain Data Layering — https://martinfowler.com/bliki/PresentationDomainDataLayering.html
