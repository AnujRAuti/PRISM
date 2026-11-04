---
name: test-data-management
description: Produce reliable test data—factories and builders, synthetic datasets, seeding strategies, anonymized snapshots, and teardown that never leaks into production.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: medium
---

# Test Data Management

## 1. Purpose

Give every test exactly the data it needs, cheaply and repeatably. Test data problems look like flakiness but are really design problems: shared fixture rows that two tests mutate, seed dumps nobody understands, and copied production data that carries PII into CI. This skill covers builders and factories, minimal-per-test data, synthetic dataset generation, anonymization when production shapes are needed, and isolation/teardown.

**Scope:** your own test environments. Production data copied into test systems is a privacy incident waiting to happen: prefer synthesis, and if you must sample production, anonymize irreversibly with documented approval.

## 2. Activation Conditions

- Tests fail intermittently due to shared rows or ordering.
- Fixtures are large SQL dumps or an opaque shared seed.
- Need realistic volume for performance or migration tests.
- Privacy review requires removing production data from lower environments.
- Keywords: test data, fixtures, factory, builder, faker, seeding, anonymization, synthetic data, snapshot, teardown, isolation, database reset, PII.

## 3. When Not to Use

- The test needs no persisted data (pure unit test).
- Mocking data for units where a literal is enough.
- Choosing *where* to test (use testing-strategy).

## 4. Required Context

1. Test layers and their data needs.
2. Schema constraints (unique keys, foreign keys, enums).
3. Data volumes needed (2 rows or 2 million).
4. Privacy classification: does the environment allow real PII at all?
5. Environment reset capabilities (transaction rollback, truncate, ephemeral DB).

## 5. Operating Procedure

1. **Default to per-test factories with overrides**: a `make_order(status="paid")` helper, so the test declares only what matters.
2. **Generate unique identifiers** per test (UUID or timestamp+counter) for any human-readable unique field, so parallel runs never collide.
3. **Keep baseline data empty**: no global seed rows for ordinary tests. Seeds belong to demos and performance environments only.
4. **Use the database's constraints to validate the data**: if a factory can produce an invalid row, the factory is wrong.
5. **Isolate**: transactional rollback per test where possible, otherwise truncate in dependency order or use a schema per worker.
6. **Generate synthetic volume with a deterministic seed** so a failing performance run can be reproduced.
7. **Anonymize production samples irreversibly**: replace identifiers, names, emails, phone numbers, addresses, and free-text with synthetic equivalents; preserve distributions, not values.
8. **Never copy secrets**: scrub credentials, tokens, and API keys from any sampled dataset.
9. **Version fixtures used in snapshot/schema tests** and review changes to them.
10. **Clean up external state** too: object storage keys, cache entries, and search indexes created by a test.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Factories | `factory_boy`, `polyfactory`, custom builders, `@faker-js/faker` |
| Synthetic data | Faker, `mimesis`, SDV (statistical synthesis) |
| Determinism | fixed seeds, `faker.seed_instance(...)` |
| Isolation | pytest fixtures, transaction rollback, per-worker schemas |
| Reset | `TRUNCATE ... RESTART IDENTITY CASCADE`, `pg_dump`/restore, template databases |
| Anonymization | column-level mapping scripts, `pg_anonymizer`, tokenization |
| Volume | `generate_series`, `pgbench`-style data loaders |

## 7. Practical Implementation

**Builder with sensible defaults:**

```python
# tests/builders.py
from decimal import Decimal
from app.domain.order import Order, OrderStatus, OrderLine

def make_line(**overrides) -> OrderLine:
    base = dict(line_no=1, product_id=7, quantity=1, unit_cents=1999)
    return OrderLine(**{**base, **overrides})

def make_order(**overrides) -> Order:
    base = dict(
        id="ord_test_1",
        customer_id=42,
        tenant_id="t1",
        status=OrderStatus.DRAFT,
        currency="INR",
        total=Decimal("19.99"),
        lines=[make_line()],
    )
    return Order(**{**base, **overrides})
```

**Factory that satisfies constraints and generates unique keys:**

```python
# tests/factories.py
import itertools
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db import CustomerRow, ProductRow

fake = Faker()
_sku_counter = itertools.count(1)

async def create_product(session: AsyncSession, **overrides) -> ProductRow:
    sku = overrides.pop("sku", f"SKU-{next(_sku_counter):06d}")
    row = ProductRow(
        sku=sku,
        name=overrides.pop("name", fake.sentence(nb_words=3)),
        price_cents=overrides.pop("price_cents", 1999),
        currency=overrides.pop("currency", "INR"),
        **overrides,
    )
    session.add(row)
    await session.flush()
    return row

async def create_customer(session: AsyncSession, **overrides) -> CustomerRow:
    email = overrides.pop("email", f"user{next(_sku_counter)}@example.test")
    row = CustomerRow(email=email, **overrides)
    session.add(row)
    await session.flush()
    return row
```

Note `@example.test` and clearly fake values: no real domains, no plausible phone numbers that could belong to someone.

**Deterministic faker per test:**

```python
import pytest
from faker import Faker

@pytest.fixture
def fake_data(request):
    f = Faker("en_IN")
    Faker.seed(abs(hash(request.node.nodeid)) % (2**32))    # deterministic per test
    return f
```

**Isolation by transaction (fastest) or truncation (simplest):**

```python
# Option A: transaction rollback per test (see integration-testing)
# Option B: truncate between tests in dependency order
TABLES_IN_ORDER = ["order_line", "payment", "order", "product", "customer"]

@pytest.fixture(autouse=True)
async def clean_tables(session):
    yield
    for table in TABLES_IN_ORDER:
        await session.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
    await session.commit()
```

Never truncate a database you did not create in this test session—guard with an environment variable check:

```python
def assert_test_database(url: str) -> None:
    if "test" not in url and os.getenv("ALLOW_NON_TEST_DB") != "1":
        raise RuntimeError(f"refusing to run destructive fixture against {url}")
```

**Synthetic volume dataset for performance and migration tests:**

```python
# scripts/generate_perf_data.py
import random
from datetime import datetime, timedelta, timezone
from faker import Faker

def seed_orders(conn, *, customers=10_000, orders_per_customer=50, seed=1337):
    rng = random.Random(seed)                      # reproducible
    fake = Faker()
    Faker.seed_instance(seed)

    with conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")   # skip FK checks for bulk load only
        cur.executemany(
            "INSERT INTO customer (id, email) VALUES (%s, %s)",
            [(i, f"cust{i}@example.test") for i in range(customers)],
        )
        now = datetime.now(timezone.utc)
        rows = [
            (f"ord_{c}_{n}", c, rng.choice(["draft", "placed", "paid"]),
             rng.randint(100, 500_000), now - timedelta(days=rng.randint(0, 730)))
            for c in range(customers)
            for n in range(rng.randint(1, orders_per_customer))
        ]
        cur.executemany(
            'INSERT INTO "order" (id, customer_id, status, total_cents, created_at) '
            "VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
        cur.execute("SET session_replication_role = DEFAULT")
    conn.commit()
```

**Irreversible anonymization when production shapes are required:**

```python
# scripts/anonymize_dump.py — run on a copy, never on the source
import hashlib, hmac, secrets
from faker import Faker

SALT = secrets.token_bytes(32)       # throw away after the run so mappings cannot be reversed
fake = Faker("en_IN")

def token(value: str) -> str:
    return hmac.new(SALT, value.encode(), hashlib.sha256).hexdigest()[:20]

def anonymize_row(row: dict) -> dict:
    return {
        **row,
        "email": f"{token(row['email'])}@example.test",       # stable within the dataset
        "full_name": fake.name(),
        "phone": f"+91 9{fake.numerify('#########')}",         # not a real allocatable pattern guaranteed
        "address": fake.address(),
        "notes": "[redacted]",
        "date_of_birth": fake.date_of_birth(minimum_age=18, maximum_age=90).isoformat(),
        "last_login_ip": "0.0.0.0",
        "api_token": None,                                     # never copy credentials
    }
```

Rules for sampled data: transform before it leaves the production network, drop source columns you do not need, and record the mapping procedure (not the values) in the data-handling doc.

**External state cleanup:**

```python
@pytest.fixture
async def s3_prefix(minio, run_id):
    prefix = f"test/{run_id}/"
    yield prefix
    for key in await minio.list_keys(prefix=prefix):
        await minio.delete(key)
```

**Fixture review checklist:**

```text
[ ] Only the fields the test asserts on are set explicitly
[ ] Unique fields are generated, not hard-coded to colliding values
[ ] No dependency on rows created by another test
[ ] No real names, emails, phone numbers, or IDs from production
[ ] Dates are explicit where time matters, random where it does not
[ ] Teardown removes external artifacts (objects, cache keys, index docs)
```

## 8. Quality Standards

- Tests declare only the data they need; defaults live in builders.
- No shared global seed for ordinary test suites.
- Unique constraints are satisfied by per-test generated values.
- Every fixture that touches a database verifies it is a test database before destructive operations.
- Synthetic data is clearly fake (`.test` domains, `example` identifiers).
- Volume datasets are deterministic and regenerate reproducibly from a seed.
- Anonymization is irreversible, documented, and applied before data leaves production.
- Cleanup covers database rows, cache, object storage, and search indexes.

## 9. Verification and Testing

- Run the suite in random order and in parallel (`pytest-randomly`, `-n 4`); no collisions.
- Run twice against the same database without cleanup between; suite still passes (or cleanup is proven).
- Check the anonymization output for any preserved PII patterns (regex sweep for emails, card patterns, phone numbers).
- Verify the destructive-fixture guard rejects a non-test URL.
- Regenerate the volume dataset from the same seed and confirm identical row counts and checksums.

## 10. Security Considerations

- Copying production data into development or CI is a data-protection event: require approval, minimize columns, anonymize irreversibly, and set retention.
- Never put live credentials, API keys, or session tokens in fixtures; use fake values with test-only endpoints.
- Test accounts in hosted third-party sandboxes must have the lowest privilege and be rotated.
- Fixtures in repositories are permanent records—never commit real customer records, even one row.
- Data used in screenshots, video artifacts, and seed demos must also be synthetic.
- Deletion requests from real users do not automatically propagate to test copies; treat test data as its own dataset with its own retention.

## 11. Failure Handling

- **Flaky tests from data collisions:** hard-coded unique values; switch to generated IDs.
- **Factory drifts from schema:** add a test that builds every factory and persists it, so constraint changes fail fast.
- **Seed dumps become unmaintainable:** replace with builders plus targeted seeds for demo environments only.
- **Truncation leaves orphans:** order tables by dependency or use `CASCADE`, and verify with a row-count assertion.
- **Anonymization broke relationships:** anonymize in place with stable tokens per entity, not per row, so joins still work.
- **Volume dataset too slow to build:** load via `COPY` rather than individual inserts, and keep a template database snapshot for reuse.

## 12. Expected Deliverables

1. Builder/factory layer with defaults and overrides.
2. Determinism conventions (seeds, fake locales).
3. Isolation and teardown strategy.
4. Test-database guard for destructive fixtures.
5. Synthetic volume generator with a fixed seed.
6. Anonymization procedure and approval record (if production sampling is used).
7. Fixture review checklist in the repo.

## 13. References

- factory_boy — https://factoryboy.readthedocs.io/
- polyfactory — https://polyfactory.litestar.dev/
- Faker (Python) — https://faker.readthedocs.io/
- Faker.js — https://fakerjs.dev/
- Mimesis — https://mimesis.name/
- PostgreSQL `TRUNCATE` — https://www.postgresql.org/docs/current/sql-truncate.html
- PostgreSQL `pg_anonymizer`-style approaches (extension ecosystem) — https://www.postgresql.org/docs/current/contrib.html
- NIST SP 800-188 (De-Identifying Government Datasets) — https://csrc.nist.gov/pubs/sp/800/188/final
