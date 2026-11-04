---
name: database-schema-design
description: Design relational schemas that stay correct and fast—normalization, key choice, constraints as documentation, indexing for real queries, and zero-downtime migrations.
metadata:
  domain: backend
  version: 1.0.0
  risk: high
---

# Database Schema Design

## 1. Purpose

Design schemas where correctness is enforced by the database and performance follows from the access patterns. Schema mistakes are the most expensive kind: wrong keys, missing constraints, and nullable everything produce application bugs that no amount of code fixes. This skill covers entity modeling, key selection, constraint strategy, index design, and safe migration practice.

**Scope:** schemas you own. DDL changes on production data are destructive by nature: destructive operations (drop column, rewrite table, change type) require explicit written authorization, a backup, and a tested rollback. Never run DDL against production that you have not rehearsed on a copy.

## 2. Activation Conditions

- New tables, or a redesign of core entities.
- Data integrity bugs (duplicates, orphans, impossible states) reaching production.
- Queries slow because indexes don't match query shapes.
- Need to add/rename/drop columns on a live table.
- Keywords: schema design, normalization, primary key, foreign key, unique constraint, check constraint, index, migration, zero downtime, partitioning, expand-contract.

## 3. When Not to Use

- Schema-less document stores where modeling differs fundamentally.
- Analytics/warehouse modeling (star schemas, columnar optimization) — separate concern.
- Pure query tuning on an existing correct schema (use sql-query-optimization).

## 4. Required Context

1. Database engine and version (Postgres, MySQL, SQLite).
2. Access patterns: the top 10 queries and their expected volumes.
3. Data volume and growth rate (rows per table per year).
4. Consistency requirements: which invariants must never be violated.
5. Deployment constraints: can you take downtime, and can you run multi-version deploys?

## 5. Operating Procedure

1. **Model entities and relationships first** on paper; identify the natural key and the surrogate key.
2. **Choose primary keys deliberately**: `bigint` identity or UUIDv7 for distributed writers; avoid random UUIDv4 as a clustered key (index bloat, poor locality).
3. **Normalize to 3NF by default**; denormalize only with a measured reason and a defined synchronization mechanism.
4. **Encode invariants as constraints**: `NOT NULL`, `UNIQUE`, `FOREIGN KEY` with explicit `ON DELETE`, `CHECK` for ranges and enums, and exclusion constraints for overlaps.
5. **Use the right types**: `timestamptz` (never `timestamp` for events), `numeric` for money (never `float`), `text` with `CHECK` instead of `varchar(n)` in Postgres, `uuid` for identifiers, enums as lookup tables or `CHECK`-constrained text.
6. **Index for the queries you will run**, in order of the query's filter/join/sort columns; composite index column order matters.
7. **Plan for soft delete deliberately**: a `deleted_at` column requires partial indexes and filtered uniqueness — or don't do it.
8. **Use expand/contract for schema changes**: add nullable column → backfill in batches → dual-write/read new → drop old. Never a single blocking `ALTER` on a hot table.
9. **Set constraints `NOT VALID` then `VALIDATE`** on large tables to avoid long locks (Postgres).
10. **Verify with a rehearsal** on a production-sized copy and measure lock duration.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Postgres migration | Alembic, Flyway, Sqitch, `pgroll`, `reshape` |
| MySQL migration | `gh-ost`, `pt-online-schema-change`, Flyway |
| Schema diff | `migra`, `atlas`, `sqldef` |
| Modeling | dbdiagram.io, `eralchemy`, Mermaid ER |
| Lint | `squawk`, `sqlfluff` |
| Inspection | `\d+`, `pg_indexes`, `EXPLAIN (ANALYZE, BUFFERS)` |

## 7. Practical Implementation

**Core tables with constraints that encode rules:**

```sql
CREATE TABLE customer (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email       citext NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT customer_email_unique UNIQUE (email)
);

CREATE TABLE product (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sku         text NOT NULL,
  name        text NOT NULL,
  price_cents integer NOT NULL CHECK (price_cents >= 0),
  currency    char(3) NOT NULL DEFAULT 'INR',
  CONSTRAINT product_sku_unique UNIQUE (sku)
);

CREATE TABLE "order" (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id  bigint NOT NULL REFERENCES customer(id) ON DELETE RESTRICT,
  status       text NOT NULL DEFAULT 'draft'
               CHECK (status IN ('draft','placed','paid','shipped','cancelled')),
  total_cents  integer NOT NULL CHECK (total_cents >= 0),
  currency     char(3) NOT NULL,
  placed_at    timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT placed_requires_time CHECK (
    (status = 'draft' AND placed_at IS NULL) OR (status <> 'draft' AND placed_at IS NOT NULL)
  )
);

CREATE TABLE order_line (
  order_id     uuid NOT NULL REFERENCES "order"(id) ON DELETE CASCADE,
  line_no      integer NOT NULL CHECK (line_no > 0),
  product_id   bigint NOT NULL REFERENCES product(id) ON DELETE RESTRICT,
  quantity     integer NOT NULL CHECK (quantity > 0),
  unit_cents   integer NOT NULL CHECK (unit_cents >= 0),
  PRIMARY KEY (order_id, line_no),
  UNIQUE (order_id, product_id)
);

CREATE TABLE payment (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id      uuid NOT NULL REFERENCES "order"(id) ON DELETE RESTRICT,
  amount_cents  integer NOT NULL CHECK (amount_cents > 0),
  provider_ref  text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payment_provider_ref_unique UNIQUE (provider_ref)
);

-- One payment per order (business rule expressed as a constraint)
CREATE UNIQUE INDEX payment_one_per_order ON payment (order_id);
```

**Indexes derived from query shapes:**

```sql
-- Query: list a customer's orders, newest first, filter by status
CREATE INDEX order_customer_status_created
  ON "order" (customer_id, status, created_at DESC, id DESC);

-- Query: open orders dashboard, partial index keeps it small
CREATE INDEX order_open ON "order" (created_at DESC)
  WHERE status IN ('placed','paid');

-- Query: look up by external reference
CREATE INDEX payment_provider_ref ON payment (provider_ref);

-- Case-insensitive email search
CREATE INDEX customer_email_lower ON customer (lower(email));
```

**Expand/contract migration (adding NOT NULL with default on a hot table):**

```sql
-- Step 1 (deploy N): add nullable column, no default rewrite
ALTER TABLE "order" ADD COLUMN channel text;

-- Step 2 (deploy N): backfill in batches, no long lock
--   run in app/job:
--   UPDATE "order" SET channel = 'web' WHERE channel IS NULL AND id IN (SELECT id FROM "order" WHERE channel IS NULL LIMIT 5000);
--   repeat until zero rows

-- Step 3 (deploy N+1): enforce, cheap because no rows violate it
ALTER TABLE "order" ALTER COLUMN channel SET DEFAULT 'web';
ALTER TABLE "order" ALTER COLUMN channel SET NOT NULL;

-- Step 4: add constraint without a long lock
ALTER TABLE "order" ADD CONSTRAINT channel_valid
  CHECK (channel IN ('web','mobile','partner')) NOT VALID;
ALTER TABLE "order" VALIDATE CONSTRAINT channel_valid;   -- takes a weaker lock
```

**Index that must be built without blocking writes:**

```sql
CREATE INDEX CONCURRENTLY order_created_brin ON "order" USING brin (created_at);
-- Note: cannot run inside a transaction block; run as its own migration step.
```

**Renaming a column safely (three deploys):**

```sql
-- 1) add new column, dual-write from app, backfill
ALTER TABLE customer ADD COLUMN full_name text;
-- 2) switch reads to full_name; keep writing both
-- 3) drop old column after telemetry shows no reads
ALTER TABLE customer DROP COLUMN name;
```

**Partitioning a large event table (Postgres declarative):**

```sql
CREATE TABLE event_log (
  id          bigint GENERATED ALWAYS AS IDENTITY,
  occurred_at timestamptz NOT NULL,
  kind        text NOT NULL,
  payload     jsonb NOT NULL,
  PRIMARY KEY (occurred_at, id)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE event_log_2026_11 PARTITION OF event_log
  FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

**Schema lint in CI:**

```bash
squawk migrations/*.sql --exclude=prefer-text-field
migra postgresql://localhost/dev postgresql://localhost/new --unsafe   # inspect, then review
```

## 8. Quality Standards

- Every table has a primary key; every relationship has a foreign key with explicit delete behavior.
- Money in integer minor units or `numeric`; timestamps with time zone; no floats for currency.
- Nullable columns are justified; states impossible by rule are prevented by `CHECK` constraints.
- Indexes exist for every top query; unused indexes are identified and dropped.
- Migrations are reversible or have a written forward-fix plan, and are rehearsed at production scale.
- No long locks on hot tables; `NOT VALID`/`VALIDATE` and `CONCURRENTLY` where appropriate.
- Schema changes are reviewed as code with a rollback note.

## 9. Verification and Testing

- Run migrations against a production-sized copy; measure lock time and total duration.
- `EXPLAIN (ANALYZE, BUFFERS)` for each top query; verify index use and no sequential scans on large tables.
- Constraint tests: attempt duplicate SKU, negative quantity, invalid status, orphan child — all must fail.
- Backfill scripts validated for idempotency and batch size; re-run twice safely.
- Rollback test: apply migration, then roll back, confirm data intact.

## 10. Security Considerations

- Row-level security (Postgres RLS) for multi-tenant tables is defense-in-depth; still enforce tenancy in queries.
- Never grant `SUPERUSER` to application roles; use least-privilege roles per service.
- Column-level encryption or tokenization for PII (card data must never be stored; use a payment provider token).
- Backups are sensitive: encrypt at rest, restrict restore access, and test restore.
- Migrations that copy data must not log row contents.
- `pg_dump` of production contains all data — treat as a secrets artifact and delete after use.
- Audit logs (who changed what) are themselves PII-bearing; set retention.

## 11. Failure Handling

- **Migration locked the table:** cancel and rerelease; use `lock_timeout` and `statement_timeout` in migrations:
  ```sql
  SET lock_timeout = '3s';
  SET statement_timeout = '30s';
  ```
- **Duplicate rows after a failed unique index build:** `CREATE UNIQUE INDEX CONCURRENTLY` can leave an INVALID index; drop and retry after deduplication.
- **Backfill overloads the database:** batch by primary key ranges with sleeps, run off-peak, and monitor replication lag.
- **Wrong type discovered late:** add a new column, backfill with cast, dual-write, then drop—do not `ALTER TYPE` on a hot table.
- **Orphan rows after deleting a parent:** the FK was missing or `ON DELETE` was wrong; add the constraint `NOT VALID`, clean up, then validate.

## 12. Expected Deliverables

1. ER diagram and table definitions with constraints.
2. Key strategy and identifier rationale.
3. Index plan mapped to named queries.
4. Migration scripts with rollback notes and lock analysis.
5. Data-integrity test suite.
6. Retention and archival policy.

## 13. References

- PostgreSQL documentation — DDL — https://www.postgresql.org/docs/current/ddl.html
- PostgreSQL concurrency / explicit locking — https://www.postgresql.org/docs/current/explicit-locking.html
- Alembic — https://alembic.sqlalchemy.org/
- squawk (Postgres migration linter) — https://squawkhq.com/
- migra — https://databaseci.com/docs/migra
- gh-ost (online schema change for MySQL) — https://github.com/github/gh-ost
- "Use The Index, Luke" — https://use-the-index-luke.com/
- Zero-downtime Postgres migrations (expand/contract) — https://www.postgresql.org/docs/current/sql-altertable.html
