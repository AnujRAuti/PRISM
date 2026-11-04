---
name: integration-testing
description: Test real boundaries—ephemeral databases with testcontainers, migration-aware fixtures, HTTP-level assertions, and controlled fakes for third parties.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Integration Testing

## 1. Purpose

Verify that your code and its real dependencies agree: SQL that actually runs, migrations that actually apply, serialization that actually matches the schema, and transactions that actually commit or roll back. Integration tests catch the class of bugs unit tests structurally cannot—type mismatches at the driver, constraint violations, and framework wiring. This skill covers ephemeral infrastructure, fixture design, isolation, and where to stop mocking.

**Scope:** your own environments. Never point integration tests at shared staging or production databases; every run must create and destroy its own state.

## 2. Activation Conditions

- Any repository, ORM, migration, or raw SQL change.
- HTTP handlers, serializers, auth middleware, or error mapping.
- Queues, caches, and object storage integration code.
- Tests that pass in isolation but fail in a real deployment.
- Keywords: integration test, testcontainers, docker compose, ephemeral database, fixtures, transactional rollback, httpx ASGI, WireMock, MSW, migration test, seed data.

## 3. When Not to Use

- Pure logic with no external boundary (use unit-testing).
- Full user journeys across a browser (use end-to-end-testing).
- Third-party services you cannot run locally and do not need to verify (use contract-testing).

## 4. Required Context

1. Dependencies to run for real: Postgres, Redis, broker, object store.
2. Application framework and test client (ASGI/WSGI, supertest).
3. Migration tooling and seed strategy.
4. External services: can they be faked at the HTTP layer?
5. CI runtime budget and parallelization options.

## 5. Operating Procedure

1. **Run real dependencies in containers, one per test session**, with a health check before tests start.
2. **Apply migrations, not `create_all()`**, so the test database matches production schema history. Run migrations once per session, then isolate per test.
3. **Isolate with a transaction rollback per test** where possible (fast), or truncate tables between tests (simple), and never share mutated state across tests.
4. **Drive the app through its real interface** (ASGI client for API tests) so routing, serialization, validation, and middleware are all exercised.
5. **Fake only beyond your trust boundary**: your own database is real; a payment provider is faked at the HTTP layer with recorded contracts.
6. **Seed via factories/builders**, not giant SQL dumps, so each test states only relevant data.
7. **Assert on the response and the persisted state** — a 201 that writes nothing is a bug.
8. **Test migrations explicitly**: apply from zero, then upgrade from the previous release's schema with representative data.
9. **Keep them parallel-safe**: unique identifiers per test, no global sequences assumptions, `--dist loadscope` or per-worker databases.
10. **Bound runtime**: integration suite under 5 minutes with `-n auto`; isolate slow cases into a separate marker.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Containers | testcontainers-python, Testcontainers for Node, docker compose |
| DB fixtures | pytest-postgresql, `pytest-django` `--reuse-db`, Alembic upgrade in fixture |
| API client | `httpx.AsyncClient(transport=ASGITransport(app))`, supertest |
| HTTP fakes | WireMock, `respx`, MSW, Prism |
| Broker | testcontainers RabbitMQ/Kafka, `LocalStack` for SQS |
| Object storage | MinIO container |
| Factories | `factory_boy`, `faker`, custom builders |
| Parallel | pytest-xdist, vitest `--threads` |

## 7. Practical Implementation

**Ephemeral Postgres with migrations applied once:**

```python
# tests/integration/conftest.py
import asyncio
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg

@pytest.fixture(scope="session")
def migrated_url(postgres):
    url = postgres.get_connection_url()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")          # real migration chain, not create_all()
    return url

@pytest_asyncio.fixture
async def engine(migrated_url):
    eng = create_async_engine(migrated_url, poolclass=None)
    yield eng
    await eng.dispose()

@pytest_asyncio.fixture
async def session(engine):
    """Each test runs in a transaction that is rolled back afterwards."""
    conn = await engine.connect()
    tx = await conn.begin()
    maker = async_sessionmaker(bind=conn, expire_on_commit=False)
    async with maker() as s:
        yield s
    await tx.rollback()
    await conn.close()
```

**API test through the real ASGI app:**

```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_create_order_persists_and_returns_location(client, session, auth_headers):
    r = await client.post("/v1/orders", headers=auth_headers,
                          json={"customer_id": 42, "lines": [{"product_id": 7, "quantity": 2}]})
    assert r.status_code == 201
    assert r.headers["location"].startswith("/v1/orders/")

    order_id = r.headers["location"].rsplit("/", 1)[1]
    row = await session.execute(select(OrderRow).where(OrderRow.id == order_id))
    assert row.scalar_one().status == "draft"          # assert persistence, not just the response
```

**Factoring data with builders:**

```python
# tests/factories.py
from decimal import Decimal
from app.domain.order import Order, OrderStatus

def make_order(**overrides) -> Order:
    base = dict(id="ord_1", customer_id=42, status=OrderStatus.DRAFT,
                total=Decimal("42.00"), currency="INR", tenant_id="t1")
    return Order(**{**base, **overrides})

async def persist_order(session, **overrides) -> Order:
    order = make_order(**overrides)
    session.add(OrderRow(**asdict(order)))
    await session.flush()
    return order
```

**Fake a third-party at the HTTP layer (recorded shape, not a mock of your code):**

```python
import respx
from httpx import Response

@respx.mock
@pytest.mark.asyncio
async def test_payment_declined_maps_to_422(client, auth_headers, persisted_order):
    respx.post("https://api.payments.test/v1/charges").mock(
        return_value=Response(402, json={"error": {"code": "card_declined",
                                                   "message": "Insufficient funds"}})
    )
    r = await client.post(f"/v1/orders/{persisted_order.id}/pay", headers=auth_headers,
                          json={"idempotency_key": "k-0001"})
    assert r.status_code == 422
    assert r.json()["type"].endswith("/problems/card-declined")
```

**Migration test from the previous release:**

```python
def test_migration_from_previous_release_preserves_orders(tmp_path, postgres):
    url, cfg = _url_and_config(postgres, tmp_path)
    command.upgrade(cfg, "0042")                      # previous release
    with psycopg.connect(url) as conn:
        conn.execute("INSERT INTO \"order\" (id, status, total_cents) VALUES ('o1','paid',4200)")
    command.upgrade(cfg, "head")                      # this release
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT status FROM \"order\" WHERE id='o1'").fetchone()[0] == "paid"
```

**Redis container with isolated logical DB per worker:**

```python
from testcontainers.redis import RedisContainer
import redis

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as rc:
        yield rc

@pytest.fixture
def redis_client(redis_container, worker_id):
    db = int(worker_id.replace("gw", "")) if worker_id != "master" else 0
    client = redis.Redis(host=redis_container.get_container_host_ip(),
                         port=redis_container.get_exposed_port(6379), db=db, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
```

**Marking and running by layer:**

```bash
pytest -m integration -n auto --timeout=60
```

```python
# conftest.py
def pytest_collection_modifyitems(config, items):
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
```

## 8. Quality Standards

- Real dependencies run in containers pinned to versions matching production.
- Schema comes from the migration chain, never `create_all()`.
- Every test isolates its data; no cross-test contamination and no dependence on ordering.
- Both response and persisted state are asserted.
- Third-party services are faked at the HTTP boundary with realistic payloads, not by mocking your own service functions.
- Migrations are tested from the previous release with representative data.
- The suite is parallel-safe (distinct IDs, per-worker databases).
- Runtime stays within the CI budget; slow outliers are marked and justified.

## 9. Verification and Testing

- Run twice in a row: the second run must pass (no leftover state).
- Run with `-p no:randomly` and with random order: identical results.
- Parallel run with 4 workers: no deadlocks or duplicate-key failures.
- Introduce a schema change without a migration: integration tests must fail loudly.
- Break a transaction boundary (commit before a failing step) and confirm a test catches it.
- Confirm container startup is bounded (health checks) and failures produce a clear message.

## 10. Security Considerations

- Never run integration tests against production or shared staging databases; connection strings in tests must point at containers.
- Test fixtures must not contain real PII or production credentials; use generated data.
- Fake third-party calls must go to a local mock, not to the real API with test keys, unless the provider has an isolated sandbox.
- Test containers expose ports on localhost only; avoid binding `0.0.0.0` in CI runners with open networks.
- Migrations executed by tests must never include destructive statements targeting a persistent volume.
- If a test needs elevated privileges, isolate it in a separate job with restricted credentials.

## 11. Failure Handling

- **Tests pass locally, fail in CI:** different database version or locale/collation; pin the image tag.
- **Deadlocks under parallel runs:** tests share rows or sequences; use unique IDs and per-worker schemas.
- **Slow startup dominates runtime:** one session-scoped container plus per-test transactions; avoid per-test container creation.
- **Foreign key violations from leftover data:** truncation order or `TRUNCATE ... CASCADE` in the reset fixture.
- **Mocked response drifts from the real API:** capture real payload shapes into fixtures periodically and add a contract test against the provider's sandbox.
- **Migration test fails on old data:** the migration assumes a default that old rows violate; fix the backfill step.

## 12. Expected Deliverables

1. Container and dependency fixtures with version pins.
2. Migration-based schema setup.
3. Per-test isolation strategy.
4. API test client wired to the real app.
5. HTTP-level fakes for third parties.
6. Migration upgrade tests.
7. CI configuration with parallelization and timeouts.

## 13. References

- Testcontainers for Python — https://testcontainers-python.readthedocs.io/
- Testcontainers — https://testcontainers.com/
- httpx ASGI transport — https://www.python-httpx.org/async/#calling-into-python-web-apps
- pytest-asyncio — https://pytest-asyncio.readthedocs.io/
- Alembic — https://alembic.sqlalchemy.org/en/latest/
- respx (httpx mocking) — https://lundberg.github.io/respx/
- MSW (Mock Service Worker) — https://mswjs.io/
- WireMock — https://wiremock.org/docs/
- pytest-xdist — https://pytest-xdist.readthedocs.io/
