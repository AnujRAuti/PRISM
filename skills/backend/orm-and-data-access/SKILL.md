---
name: orm-and-data-access
description: Use ORMs and query builders safely and efficiently—session lifecycle, eager vs lazy loading, transaction discipline, bulk operations, and escaping to SQL when needed.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# ORM and Data Access

## 1. Purpose

Use an ORM for what it is good at (mapping, parameter binding, migrations, simple CRUD) without letting it hide expensive behavior. The recurring failures are predictable: unbounded lazy loading (N+1), sessions living too long, transactions spanning network calls, and bulk operations executed row-by-row. This skill covers session scope, loading strategies, transaction boundaries, bulk paths, and the discipline of dropping to SQL with parameters when the ORM cannot express a query well.

**Scope:** your own application and database. ORMs execute DDL/DML: any bulk delete, truncate, or schema change requires a backup and explicit authorization.

## 2. Activation Conditions

- Slow endpoints traced to many small queries.
- Session/connection pool exhaustion or "connection in transaction" warnings.
- Need to write bulk inserts/updates or complex reports.
- Deciding between ORM, query builder, or raw SQL for a feature.
- Keywords: SQLAlchemy, Prisma, TypeORM, Django ORM, Hibernate, session, transaction, eager loading, selectinload, N+1, bulk insert, connection pool, async session.

## 3. When Not to Use

- Analytics-heavy workloads better served by SQL or a warehouse.
- Simple scripts where a driver plus a few queries is clearer than a full ORM.
- Schema design decisions (use database-schema-design).

## 4. Required Context

1. ORM and version, sync or async driver.
2. Endpoint query patterns (lists, details, joins, aggregates).
3. Transaction requirements across services.
4. Connection pool settings and expected concurrency.
5. Reporting/export needs that may require raw SQL.

## 5. Operating Procedure

1. **Scope the session per request/unit of work.** One session per HTTP request or job; never a module-level session shared across threads or async tasks.
2. **Make transactions explicit and short**: begin at the service boundary, commit/rollback there, and never hold a transaction across an external HTTP call.
3. **Choose loading strategy per relationship**: lazy for rare access, `selectinload`/`joinedload` (SQLAlchemy) or `include` (Prisma) for known traversal.
4. **Detect N+1 automatically** in tests by asserting query counts per endpoint.
5. **Use bulk operations** for multi-row writes (`insert().values([...])`, `execute_values`, `createMany`) instead of loops.
6. **Page with keyset/cursor** for large tables; avoid `offset()/limit()` at depth.
7. **Drop to SQL with bound parameters** for aggregates, window functions, and CTEs; keep it in the data layer with tests.
8. **Disable implicit lazy loading in async contexts** and configure it to raise instead of silently emitting IO.
9. **Set pool sizes from database limits**: `pool_size + max_overflow` per process × replicas must be below `max_connections` (minus admin headroom).
10. **Enable statement logging in development** (`echo=True` / `log_statement=all`) and audit generated SQL for a feature before shipping.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Python | SQLAlchemy 2.0 (Core + ORM), Django ORM, `psycopg` 3, `databases` |
| Node/TS | Prisma, Drizzle, TypeORM, Kysely |
| Java | Hibernate/JPA, jOOQ |
| Pooling | SQLAlchemy pool, PgBouncer, `pgbouncer` transaction mode caveats |
| SQL helpers | `sqlalchemy-utils`, `pypika` |
| Query counting | `pytest-sqlalchemy`, custom event listeners, Prisma query events |
| Migrations | Alembic, Prisma Migrate, Django migrations |

## 7. Practical Implementation

**Session per request (FastAPI + SQLAlchemy 2.0 async):**

```python
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fastapi import Depends

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session                      # session closed at request end
```

**Explicit transaction at the service boundary:**

```python
async def place_order(session: AsyncSession, *, customer_id: int, lines: list[LineInput]) -> Order:
    async with session.begin():                       # one transaction, short
        order = Order(customer_id=customer_id, status="placed")
        session.add(order)
        await session.flush()                          # get the id without committing
        session.add_all([OrderLine(order_id=order.id, **line.model_dump()) for line in lines])
    # external calls (email, payment) happen AFTER commit, never inside the transaction
    return order
```

**Eager loading instead of lazy (N+1 fix):**

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# BAD: lazy loading in a loop issues one query per order
orders = (await session.scalars(select(Order).where(Order.customer_id == 42))).all()
for o in orders:
    print([line.product_id for line in o.lines])        # N queries

# GOOD: two queries total
stmt = (
    select(Order)
    .where(Order.customer_id == 42)
    .options(selectinload(Order.lines).selectinload(OrderLine.product))
    .order_by(Order.created_at.desc())
    .limit(20)
)
orders = (await session.scalars(stmt)).all()
```

**Fail loudly instead of lazy-loading in async code:**

```python
from sqlalchemy.orm import relationship

class Order(Base):
    __tablename__ = "order"
    id: Mapped[int] = mapped_column(primary_key=True)
    lines: Mapped[list["OrderLine"]] = relationship(
        lazy="raise",                       # raises instead of emitting IO at attribute access
        back_populates="order",
    )
```

**Query counting in tests:**

```python
import pytest
from sqlalchemy import event

@pytest.fixture
def query_counter(engine):
    statements: list[str] = []
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        statements.append(statement)
    yield statements
    event.remove(engine.sync_engine, "before_cursor_execute", _count)

async def test_order_list_query_count(client, query_counter):
    await client.get("/orders?limit=20")
    assert len(query_counter) <= 3        # auth + list + lines
```

**Bulk insert (one round trip):**

```python
from sqlalchemy import insert

await session.execute(
    insert(OrderLine),
    [{"order_id": oid, "line_no": i, "product_id": p, "quantity": q, "unit_cents": c}
     for i, (p, q, c) in enumerate(lines, start=1)],
)
await session.commit()
```

**Bulk update with a join (single statement):**

```sql
UPDATE order_line l
SET unit_cents = p.price_cents
FROM product p
WHERE p.id = l.product_id
  AND l.order_id = :order_id;
```

**Keyset pagination in the ORM:**

```python
from sqlalchemy import tuple_

stmt = select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(50)
if cursor:
    created_at, last_id = decode_cursor(cursor)
    stmt = stmt.where(
        tuple_(Order.created_at, Order.id) < tuple_(created_at, last_id)
    )
```

**Escaping to Core/SQL with parameters for an aggregate:**

```python
from sqlalchemy import text

sql = text("""
    WITH monthly AS (
      SELECT date_trunc('month', created_at) AS month,
             sum(total_cents) AS revenue_cents,
             count(*) AS orders
      FROM "order"
      WHERE customer_id = :customer_id
        AND status = 'paid'
        AND created_at >= :since
      GROUP BY 1
    )
    SELECT month, revenue_cents, orders,
           revenue_cents - lag(revenue_cents) OVER (ORDER BY month) AS delta_cents
    FROM monthly
    ORDER BY month DESC
""")
rows = (await session.execute(sql, {"customer_id": cid, "since": since})).mappings().all()
```

**Prisma equivalents (Node/TS):**

```ts
// Eager load to avoid N+1
const orders = await prisma.order.findMany({
  where: {customerId: 42},
  include: {lines: {include: {product: true}}},
  orderBy: [{createdAt: "desc"}, {id: "desc"}],
  take: 20,
  ...(cursor ? {cursor: {id: cursor}, skip: 1} : {}),
});

// Bulk insert
await prisma.orderLine.createMany({
  data: lines.map((l, i) => ({orderId, lineNo: i + 1, ...l})),
});

// Transaction with short scope
await prisma.$transaction(async (tx) => {
  const order = await tx.order.create({data: {customerId, status: "placed"}});
  await tx.orderLine.createMany({data: lines.map((l) => ({orderId: order.id, ...l}))});
  return order;
});
```

**Verify generated SQL before shipping:**

```python
print(stmt.compile(compile_kwargs={"literal_binds": False}))   # inspect structure
# or enable echo in dev:
# create_async_engine(url, echo=True)
```

**Pool sizing math:**

```text
max_connections = 100            (database limit)
reserved_for_admin = 10
usable = 90
app_processes = 6   (replicas × workers)
pool_size + max_overflow <= 90 / 6 = 15   -> pool_size=10, max_overflow=5
```

## 8. Quality Standards

- One session per request/job; sessions never shared across tasks or threads.
- Transactions are short, explicit, and never wrap external network calls.
- All relationship access in request paths is eager-loaded or raises.
- Query-count assertions exist for list and detail endpoints.
- Bulk writes use multi-row statements, not loops.
- Pool sizing is documented and within database limits.
- Raw SQL is parameterized and lives in the data layer with tests.

## 9. Verification and Testing

- Query-count tests per endpoint (catch N+1 regressions).
- Load test at expected concurrency; watch pool wait time and DB connection count.
- Verify `lazy="raise"` paths by testing every endpoint that touches relationships.
- Compare ORM output with expected SQL for critical queries (structure review, not string equality).
- Test transaction rollback: force an error mid-transaction and assert no partial writes.
- Check for connection leaks: run 1,000 requests and confirm connections return to baseline.

## 10. Security Considerations

- ORMs parameterize by default; never use f-string interpolation into `text()` or `raw()` — that reintroduces SQL injection.
- Mass assignment is a real risk: bind only explicit input schemas to models; never `**request.json()`.
- Row-level authorization must be in the query (`WHERE tenant_id = :tenant`), not filtered in Python after fetching.
- Disable SQL echo in production: logs will contain PII and parameter values.
- Database credentials come from a secret manager; the app role has only required privileges (no DDL in production runtime).
- Destructive bulk operations require a `WHERE` clause gate in code and a review step; consider `LIMIT`-batched deletes.

## 11. Failure Handling

- **"This session is provisioning a new connection" hangs:** pool exhausted by unclosed sessions—ensure context managers everywhere and add pool timeout alerts.
- **`MissingGreenlet` / lazy-load errors:** a relationship was accessed outside a load strategy; add `selectinload` or restructure the query.
- **Transaction left open:** an exception skipped commit/rollback; use `async with session.begin()` so it closes automatically.
- **Bulk insert OOM:** batch in chunks of 1,000–10,000 rows and commit per chunk if idempotent.
- **ORM cannot express the query:** move to Core/SQL with parameters; keep the boundary (repository method) so callers are unaffected.
- **Prisma transaction timeouts:** default interactive transaction timeout is short; keep work minimal or increase deliberately with monitoring.

## 12. Expected Deliverables

1. Session and transaction lifecycle policy.
2. Loading strategy per relationship.
3. Query-count tests per endpoint.
4. Bulk operation patterns with chunk sizes.
5. Pool configuration and sizing calculation.
6. Raw SQL inventory with parameterization review.
7. Repository API boundary for data access.

## 13. References

- SQLAlchemy 2.0 ORM — https://docs.sqlalchemy.org/en/20/orm/
- SQLAlchemy relationship loading — https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html
- SQLAlchemy asyncio — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Prisma Client — https://www.prisma.io/docs/orm/prisma-client
- Django database access optimization — https://docs.djangoproject.com/en/stable/topics/db/optimization/
- PgBouncer — https://www.pgbouncer.org/usage.html
- Hibernate performance — https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html
