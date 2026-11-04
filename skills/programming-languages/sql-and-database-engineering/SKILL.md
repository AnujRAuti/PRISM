---
name: sql-and-database-engineering
description: Write SQL and database code that is correct under concurrency—index-aware query plans, explicit transactions, safe migrations, and parameterized access.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: high
---

# SQL and Database Engineering

## 1. Purpose

Write SQL and schema changes that stay correct when two transactions run at once and fast when the table has fifty million rows. The recurring failures are specific: a missing index turning a page load into a sequential scan, a read-modify-write race that oversells inventory, a migration that locks a hot table for twenty minutes, and string-concatenated queries that invite injection. This skill covers schema design, indexing, transaction isolation, migration safety, and query-plan-driven tuning.

**Scope:** databases you own. Every statement here can destroy production data: never run `UPDATE`/`DELETE` without a `WHERE` in a transaction you have verified, always take a backup before destructive DDL, and never paste credentials into query text or logs.

## 2. Activation Conditions

- Designing or changing a schema, index, or constraint.
- Slow queries, timeouts, or connection-pool exhaustion.
- Concurrency bugs: lost updates, overselling, deadlocks, phantom reads.
- Writing migrations for a live system.
- Keywords: PostgreSQL, MySQL, SQLite, indexes, EXPLAIN ANALYZE, transaction isolation, MVCC, deadlock, partitioning, migration, N+1, connection pool, advisory lock, `FOR UPDATE`, JSONB.

## 3. When Not to Use

- Pure NoSQL document modelling without relational constraints (still read the indexing and idempotency sections).
- Data warehouse/analytics tuning at petabyte scale (dedicated analytics engineering).
- ORM-specific mapping questions (combine with the language skill).

## 4. Required Context

1. Engine and version (PostgreSQL 16, MySQL 8, SQLite 3).
2. Data size, growth rate, and read/write ratio.
3. Latency SLOs and expected QPS per endpoint.
4. Isolation-level requirements for each business operation.
5. Migration tooling and deployment model (online, maintenance window).

## 5. Operating Procedure

1. **Design the schema from invariants**: not-null by default, `CHECK` constraints, unique constraints for real uniqueness, foreign keys with explicit `ON DELETE` behavior, and `timestamptz` (never local `timestamp`) for time.
2. **Choose keys deliberately**: `bigint generated always as identity` or UUIDv7 for primary keys; avoid natural keys that change; be aware UUIDv4 random inserts fragment B-trees.
3. **Index on access patterns, not guesses**: every foreign key, every column in frequent `WHERE`/`ORDER BY`, composite indexes ordered by equality-then-range, and partial indexes for skewed predicates (`WHERE status = 'pending'`).
4. **Read query plans before optimizing**: `EXPLAIN (ANALYZE, BUFFERS)`; look for sequential scans on large tables, underestimates, and nested loops with high row counts.
5. **Write concurrency-safe operations**: use `SELECT ... FOR UPDATE` (or `FOR NO KEY UPDATE`) or atomic `UPDATE ... WHERE` for read-modify-write; rely on a unique constraint plus `ON CONFLICT` for idempotent inserts.
6. **Keep transactions short**: open late, commit early, never hold a transaction across a network call (HTTP, email, queue publish). Use the transactional outbox for external side effects.
7. **Pick isolation deliberately**: `READ COMMITTED` is the default; use `REPEATABLE READ`/`SERIALIZABLE` only where the invariant demands it, and handle serialization failures with bounded retries.
8. **Make migrations safe**: additive first (add nullable column, backfill in batches, add constraint `NOT VALID` then `VALIDATE`), create indexes `CONCURRENTLY`, and never rewrite a hot table under load.
9. **Parameterize everything**: prepared statements or a query builder; identifiers must be allowlisted, never interpolated.
10. **Bound resources**: connection pool sized to the database's `max_connections`, statement timeouts, `lock_timeout`, and `idle_in_transaction_session_timeout`.
11. **Measure with `pg_stat_statements`** for the slowest total time, not just the slowest single query.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Engines | PostgreSQL, MySQL 8, SQLite, CockroachDB |
| Plans | `EXPLAIN (ANALYZE, BUFFERS)`, `pg_stat_statements`, `auto_explain` |
| Migrations | Flyway, Liquibase, `golang-migrate`, Alembic, Atlas, `sqitch` |
| Pooling | PgBouncer (transaction mode), HikariCP, `pgx` pool |
| Locking | Row locks, advisory locks, `SKIP LOCKED` queues |
| Extensions | `pg_stat_statements`, `pgcrypto`, `pg_trgm`, `pg_partman` |
| Load testing | `pgbench`, k6, custom workload replay |
| Safety | `pg_dump`/`pgBackRest`, `transaction_timeout`, `lock_timeout` |

## 7. Practical Implementation

**Schema with invariants enforced by the database, not by hope:**

```sql
CREATE TABLE orders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  bigint NOT NULL REFERENCES customers (id) ON DELETE RESTRICT,
    status       text   NOT NULL DEFAULT 'placed'
                 CHECK (status IN ('draft','placed','paid','declined','refunded')),
    total_cents  bigint NOT NULL CHECK (total_cents >= 0),
    currency     char(3) NOT NULL DEFAULT 'USD',
    created_at   timestamptz NOT NULL DEFAULT now(),
    paid_at      timestamptz,
    CONSTRAINT paid_requires_status
        CHECK ((status = 'paid') = (paid_at IS NOT NULL))
);

CREATE TABLE order_lines (
    order_id        bigint NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    line_no         int    NOT NULL CHECK (line_no > 0),
    product_id      bigint NOT NULL REFERENCES products (id),
    quantity        int    NOT NULL CHECK (quantity > 0 AND quantity <= 999),
    unit_price_cents bigint NOT NULL CHECK (unit_price_cents >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE inventory (
    product_id  bigint PRIMARY KEY REFERENCES products (id),
    on_hand     int NOT NULL CHECK (on_hand >= 0)   -- overselling becomes impossible
);
```

**Indexes chosen for the actual queries:**

```sql
-- Equality on customer, then range/order on created_at: composite order matters
CREATE INDEX CONCURRENTLY idx_orders_customer_created
    ON orders (customer_id, created_at DESC);

-- Partial index: only the rows the reconciliation job scans
CREATE INDEX CONCURRENTLY idx_orders_pending_reconcile
    ON orders (created_at)
    WHERE status IN ('placed', 'paid') AND reconciled_at IS NULL;

-- Covering index: index-only scan for a frequent projection
CREATE INDEX CONCURRENTLY idx_orders_customer_covering
    ON orders (customer_id) INCLUDE (status, total_cents);

-- Trigram search without a full-text search engine
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY idx_products_name_trgm
    ON products USING gin (name gin_trgm_ops);
```

**Read-modify-write without lost updates (the oversell bug):**

```sql
-- BAD: two concurrent requests both read on_hand = 1 and both succeed
-- BEGIN;
--   SELECT on_hand FROM inventory WHERE product_id = 42;
--   UPDATE inventory SET on_hand = 0 WHERE product_id = 42;
-- COMMIT;

-- GOOD: atomic conditional update; the row lock is implicit and the check is enforced
BEGIN;
WITH claim AS (
    UPDATE inventory
       SET on_hand = on_hand - $2
     WHERE product_id = $1
       AND on_hand >= $2                 -- the business invariant, evaluated in the write
    RETURNING on_hand
)
INSERT INTO stock_movements (product_id, delta, reason)
SELECT $1, -$2, 'order'
WHERE EXISTS (SELECT 1 FROM claim);
-- 0 rows updated => insufficient stock; application raises a domain error
COMMIT;
```

**Explicit row locking when a read must inform a write:**

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';           -- fail fast instead of queueing behind a lock
SET LOCAL statement_timeout = '5s';

SELECT id, status, total_cents
  FROM orders
 WHERE id = $1
   FOR NO KEY UPDATE;                    -- blocks competing writers, not FK checks

UPDATE orders
   SET status = 'paid', paid_at = now()
 WHERE id = $1 AND status = 'placed';    -- status check repeated under lock
COMMIT;
```

**Idempotent writes with `ON CONFLICT`:**

```sql
-- Safe to retry the same webhook delivery any number of times
INSERT INTO payments (provider, provider_charge_id, order_id, amount_cents, status)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (provider, provider_charge_id)
DO UPDATE SET status = EXCLUDED.status
          WHERE payments.status <> 'captured';   -- never regress a captured payment
```

**A job queue that does not double-process:**

```sql
-- Claim a batch atomically; SKIP LOCKED lets workers run in parallel safely
WITH claimed AS (
    SELECT id
      FROM outbox
     WHERE published_at IS NULL
       AND next_attempt_at <= now()
     ORDER BY id
     FOR UPDATE SKIP LOCKED
     LIMIT 50
)
UPDATE outbox o
   SET claimed_at = now(), attempts = o.attempts + 1
  FROM claimed c
 WHERE o.id = c.id
RETURNING o.id, o.payload, o.attempts;
```

**Reading a query plan and reacting to it:**

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT o.id, o.total_cents, o.created_at
  FROM orders o
 WHERE o.customer_id = 8842
   AND o.created_at >= now() - interval '90 days'
 ORDER BY o.created_at DESC
 LIMIT 50;
```

```text
Limit  (cost=1820.44..1820.57 rows=50 width=28) (actual time=41.882..41.890 rows=50 loops=1)
  Buffers: shared hit=1204 read=3312
  ->  Sort  (cost=1820.44..1822.31 rows=749 width=28) (actual time=41.87..41.87 rows=50 loops=1)
        Sort Key: created_at DESC
        Sort Method: top-N heapsort  Memory: 30kB
        ->  Seq Scan on orders o  (cost=0.00..1601.10 rows=749 width=28) (actual time=0.31..38.20 rows=731 loops=1)
              Filter: ((customer_id = 8842) AND (created_at >= ...))
              Rows Removed by Filter: 998269
              Buffers: shared hit=1204 read=3312
Planning Time: 0.402 ms
Execution Time: 42.115 ms
```

```
Diagnosis: Seq Scan over ~1M rows, 998k discarded by the filter, 3312 blocks read from disk.
Fix: composite index on (customer_id, created_at DESC) -> Index Scan, buffers drop to ~12,
     and the Sort node disappears because the index provides the order.
```

**Safe migration sequence for a large live table:**

```sql
-- Step 1: add the column without a rewrite or an ACCESS EXCLUSIVE lock for long
ALTER TABLE orders ADD COLUMN channel text;
-- PostgreSQL 11+ makes a nullable column with no default metadata-only.

-- Step 2: backfill in bounded batches, outside the migration transaction
-- (application job or psql loop; keep each batch < ~5k rows)
UPDATE orders SET channel = 'web'
 WHERE channel IS NULL AND id BETWEEN 1 AND 5000;

-- Step 3: enforce without a long exclusive scan
ALTER TABLE orders
  ADD CONSTRAINT orders_channel_valid CHECK (channel IN ('web','app','partner')) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT orders_channel_valid;   -- SHARE UPDATE EXCLUSIVE
ALTER TABLE orders ALTER COLUMN channel SET NOT NULL;           -- uses the validated constraint

-- Step 4: build the index without blocking writes
CREATE INDEX CONCURRENTLY idx_orders_channel_created ON orders (channel, created_at DESC);
```

```bash
# Never ship a migration that can wait forever on a lock
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "SET lock_timeout = '3s';" -f migrations/0042_add_channel.sql
```

**Parameterized access from application code (no string building):**

```python
# GOOD: parameters, explicit timeout, bounded pool
async with pool.acquire() as conn:                 # acquire honors pool limits
    await conn.execute("SET LOCAL statement_timeout = '5s'")
    rows = await conn.fetch(
        """
        SELECT id, status, total_cents
          FROM orders
         WHERE customer_id = $1
           AND created_at >= $2
         ORDER BY created_at DESC
         LIMIT $3
        """,
        customer_id, since, limit,
    )

# BAD: injection + plan cache thrash
# await conn.fetch(f"SELECT * FROM orders WHERE customer_id = {customer_id}")
```

**Operational guardrails:**

```sql
-- Find the queries consuming the most total time
SELECT calls, round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms, left(query, 90) AS query
  FROM pg_stat_statements
 ORDER BY total_exec_time DESC
 LIMIT 20;

-- Find blocking locks and who holds them
SELECT blocked.pid AS blocked_pid, blocking.pid AS blocking_pid,
       left(blocked.query, 60) AS blocked_query, now() - blocked.query_start AS wait
  FROM pg_stat_activity blocked
  JOIN pg_stat_activity blocking
    ON blocking.pid = ANY (pg_blocking_pids(blocked.pid))
 WHERE cardinality(pg_blocking_pids(blocked.pid)) > 0;

-- Session hygiene for pooled connections
ALTER DATABASE orders SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE app SET statement_timeout = '10s';
```

## 8. Quality Standards

- Constraints in the database: `NOT NULL`, `CHECK`, `UNIQUE`, and foreign keys with deliberate `ON DELETE` behavior.
- `timestamptz` everywhere; money as integer minor units or `numeric`, never `float`.
- Every foreign key and frequent filter/sort column is indexed; index order matches `equality, equality, range`.
- Query plans reviewed with `EXPLAIN (ANALYZE, BUFFERS)` for any new hot query; no sequential scans on large tables for OLTP paths.
- Read-modify-write operations are atomic in SQL, not in application code between two queries.
- Transactions are short, never span remote calls, and always set a `lock_timeout` and `statement_timeout`.
- All access is parameterized; dynamic identifiers come from allowlists only.
- Migrations are reversible or explicitly documented as irreversible, run with `CONCURRENTLY`/`NOT VALID` on live tables, and are tested against a production-sized copy.
- Connection pool size is derived from the DB's capacity, and pooling is used (PgBouncer in transaction mode for many app instances).

## 9. Verification and Testing

- Run `EXPLAIN (ANALYZE, BUFFERS)` on every new/changed query with representative data volume; compare buffers before/after.
- Concurrency test: two sessions exercising the read-modify-write path with a parallel client; assert the invariant holds (e.g., `on_hand` never negative, no oversell).
- Deadlock test: run competing transactions in opposite order; verify the app retries with backoff and surfaces a clean error.
- Migration test: apply to a snapshot of production size, measure lock time and duration, then roll back in a staging clone.
- Restore test: verify a backup restores to a known point and that constraints/indexes survive.
- Load test with `pgbench` or k6 against realistic read/write ratios; watch pool saturation and p99 latency.

## 10. Security Considerations

- SQL injection is the top risk: parameterize all values, allowlist dynamic table/column names, and never log full SQL with literals.
- Least-privilege roles: the app role should have no DDL, no `SUPERUSER`, and no access to other schemas; migrations run under a separate role.
- Row-level security for multi-tenant tables (`ENABLE ROW LEVEL SECURITY` plus per-tenant policies) where the app cannot guarantee tenant scoping.
- Encrypt in transit (`sslmode=verify-full`) and at rest; rotate credentials and prefer IAM/managed auth over static passwords.
- Backups are high-value targets: restrict access, encrypt, and test that a restore does not require exposing credentials.
- Audit sensitive tables (who read/wrote what) with triggers or `pgaudit`; be aware that triggers can be disabled by an attacker with rights.
- Avoid `SECURITY DEFINER` functions that run with elevated rights unless inputs are validated and `search_path` is pinned.
- Never expose database errors verbatim to clients (they leak schema and data); map to problem responses.

## 11. Failure Handling

- **Deadlocks:** replicate the ordering (locks acquired in a consistent order), shorten transactions, and retry on `40P01` with jittered backoff.
- **Serialization failures (`40001`):** retry the whole transaction up to N times; do not retry partial work.
- **Long lock waits during DDL:** check `pg_blocking_pids()`, set `lock_timeout`, and retry the DDL outside peak hours; `CONCURRENTLY` indexes can still wait on older transactions — monitor for `wait_event = 'virtualxid'`.
- **Connection pool exhaustion:** reduce per-request concurrency, add PgBouncer, and find leaked connections (missing `finally` release); never raise `max_connections` as the first fix.
- **Bloated tables/plan regressions after mass delete:** `VACUUM (ANALYZE)` or `pg_repack`; run `ANALYZE` after large data changes.
- **Slow query after data growth:** statistics stale or index not selective; refresh statistics, add the right index, and confirm the plan flipped.

## 12. Expected Deliverables

1. Schema DDL with constraints, keys, and referential actions.
2. Index plan tied to named queries and access patterns.
3. Concurrency-safe write patterns for each invariant (stock, balance, state machine).
4. Migration scripts with lock-safe sequencing and rollback notes.
5. Query-plan evidence for hot paths (before/after buffers and timings).
6. Role/permission model and RLS policies where applicable.
7. Timeout/pooling configuration and monitoring queries.

## 13. References

- PostgreSQL documentation — https://www.postgresql.org/docs/current/
- `EXPLAIN` / plan analysis — https://www.postgresql.org/docs/current/using-explain.html
- Transaction isolation — https://www.postgresql.org/docs/current/transaction-iso.html
- `pg_stat_statements` — https://www.postgresql.org/docs/current/pgstatstatements.html
- Lock monitoring — https://www.postgresql.org/docs/current/monitoring-locks.html
- MySQL reference manual — https://dev.mysql.com/doc/refman/8.0/en/
- SQLite documentation — https://www.sqlite.org/docs.html
- Use The Index, Luke (indexing for developers) — https://use-the-index-luke.com/
- OWASP SQL injection — https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- PgBouncer docs — https://www.pgbouncer.org/usage.html
