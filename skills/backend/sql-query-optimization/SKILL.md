---
name: sql-query-optimization
description: Diagnose and fix slow SQL—read execution plans, interpret buffers and row estimates, choose indexes, and rewrite queries without changing results.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# SQL Query Optimization

## 1. Purpose

Turn slow queries into fast ones with evidence instead of guesses. Optimization is a loop: measure, read the plan, identify the dominant cost, change one thing, re-measure. This skill covers `EXPLAIN (ANALYZE, BUFFERS)`, statistics and estimates, index selection, join strategies, N+1 patterns, and the rewrites that preserve semantics.

**Scope:** your own databases. Never run `EXPLAIN ANALYZE` for a write statement on production without understanding its effects (it executes the statement). Locked or unindexed operations can impact other users—run heavy analysis on replicas or staging copies.

## 2. Activation Conditions

- Query p95/p99 exceeds the latency budget.
- Sequential scans on large tables; high buffer reads.
- Timeouts, connection pool exhaustion, or CPU spikes tied to a query.
- Need to validate an index before adding it.
- Keywords: EXPLAIN, execution plan, index scan, seq scan, nested loop, hash join, statistics, autovacuum, N+1, covering index, pg_stat_statements.

## 3. When Not to Use

- The bottleneck is application-side serialization or chatty round trips (fix the access pattern).
- Missing indexes because the schema has no constraints at all (use database-schema-design).
- Cacheable results served better from a cache layer (evaluate the trade-off first).

## 4. Required Context

1. The exact query and its parameters (plans differ by parameter values).
2. Table sizes and cardinality (`pg_class.reltuples`, `pg_stat_user_tables`).
3. Existing indexes and constraints.
4. Database engine/version and hardware limits.
5. A safe environment for `EXPLAIN ANALYZE` (replica/staging).

## 5. Operating Procedure

1. **Find the worst offenders** from `pg_stat_statements` ordered by total time and mean time, not by a single slow log line.
2. **Get the real plan**: `EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)` with representative parameters.
3. **Read from the innermost node outward**: look for rows with the largest actual time and the largest estimate-vs-actual mismatch.
4. **Check estimate accuracy**: if `rows` estimates are off by orders of magnitude, run `ANALYZE`, or add extended statistics for correlated columns.
5. **Identify the scan type**: sequential scan on a large table with a selective filter → index; index scan returning many rows → maybe a seq scan is cheaper; nested loop with high loops count → consider hash join via reordering or a better index.
6. **Design the index** matching filter + join + order: equality columns first, then range, then sort; consider covering (`INCLUDE`) and partial indexes.
7. **Rewrite only when semantics are preserved**: eliminate `SELECT *`, avoid functions on indexed columns, replace `NOT IN` with `NOT EXISTS`, ensure `UNION ALL` when dedup is unnecessary.
8. **Fix N+1 at the application layer** (batch or join), not by adding 40 indexes.
9. **Re-measure** with the same parameters, then test with different parameter values (plans are parameter-sensitive).
10. **Watch the write cost**: each index slows inserts/updates; drop unused indexes (`pg_stat_user_indexes.idx_scan = 0`).

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Plan visualization | `explain.dalibo.com`, `explain.depesz.com`, `pgAdmin` |
| Statement stats | `pg_stat_statements`, `pg_stat_activity` |
| Index advisors | `pg_stat_user_indexes`, `hypopg` (hypothetical indexes) |
| MySQL | `EXPLAIN ANALYZE`, `performance_schema`, `pt-query-digest` |
| Lint | `sqlfluff`, `pglast` |
| Load test | `pgbench`, `k6` |

## 7. Practical Implementation

**Find the top statements by total time:**

```sql
SELECT queryid, calls, round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       rows, round(100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0), 1) AS hit_pct,
       left(query, 120) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

**Read a plan with buffers:**

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT o.id, o.status, o.total_cents, c.email
FROM "order" o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = 'placed'
  AND o.created_at >= now() - interval '7 days'
ORDER BY o.created_at DESC
LIMIT 50;
```

```
Limit  (cost=0.86..1204.55 rows=50 width=60) (actual time=0.08..18.42 rows=50 loops=1)
  ->  Nested Loop  (cost=0.86..985521.20 rows=41935 width=60) (actual time=0.07..18.40 rows=50 loops=1)
        ->  Index Scan using order_status_created on "order" o  (actual time=0.04..12.10 rows=1184 loops=1)
              Index Cond: ((status = 'placed') AND (created_at >= (now() - '7 days'::interval)))
              Buffers: shared hit=250 read=18
        ->  Index Scan using customer_pkey on customer c  (actual time=0.004..0.004 rows=1 loops=50)
              Index Cond: (id = o.customer_id)
              Buffers: shared hit=100
Planning Time: 0.412 ms
Execution Time: 18.46 ms
```

Read: the outer index scan stops after 50 rows (the `LIMIT` pushes down), so the cost is bounded. The `loops=50` on the inner scan is fine because each lookup is one page hit. If the inner node showed `loops=1184` with high time, that is the N+1 shape to fix.

**Estimate-vs-actual mismatch (the root cause of bad plans):**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM "order" WHERE status = 'placed' AND channel = 'web';
-- rows=5000 (estimated) vs rows=1200000 (actual)
```

```sql
-- Fix statistics for correlated columns
ANALYZE "order";
CREATE STATISTICS order_status_channel (dependencies, ndistinct)
  ON status, channel FROM "order";
ANALYZE "order";
```

**Composite index for filter + sort:**

```sql
-- Supports: WHERE customer_id = $1 AND created_at < $2 ORDER BY created_at DESC LIMIT 20
CREATE INDEX CONCURRENTLY order_customer_created_desc
  ON "order" (customer_id, created_at DESC, id DESC);

-- Covering index avoids heap fetches for a hot list query
CREATE INDEX CONCURRENTLY order_list_covering
  ON "order" (customer_id, created_at DESC)
  INCLUDE (status, total_cents);
```

**Partial index for a dominant predicate:**

```sql
CREATE INDEX CONCURRENTLY order_unpaid
  ON "order" (created_at)
  WHERE status IN ('placed','paid');
```

**Rewrites that keep semantics:**

```sql
-- Slow: NOT IN with nullable column and no use of index
SELECT id FROM customer c
WHERE c.id NOT IN (SELECT customer_id FROM "order");

-- Fast and null-safe
SELECT c.id FROM customer c
WHERE NOT EXISTS (SELECT 1 FROM "order" o WHERE o.customer_id = c.id);

-- Slow: function on an indexed column blocks the index
SELECT id FROM "order" WHERE date_trunc('day', created_at) = DATE '2026-11-04';

-- Fast: range predicate
SELECT id FROM "order"
WHERE created_at >= DATE '2026-11-04' AND created_at < DATE '2026-11-05';

-- Slow: SELECT * pulls wide columns
SELECT * FROM product WHERE sku = 'SKU-9';
-- Fast: only what's needed, index-only scan possible with INCLUDE
SELECT id, name, price_cents FROM product WHERE sku = 'SKU-9';
```

**Find unused and duplicate indexes:**

```sql
SELECT s.relname AS table, s.indexrelname AS index, s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0 AND NOT i.indisunique
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

**Fix N+1 with a single aggregated query:**

```sql
-- Instead of one query per order for its lines:
SELECT o.id, o.status,
       coalesce(json_agg(json_build_object('line_no', l.line_no, 'product_id', l.product_id,
                                           'quantity', l.quantity)
                ORDER BY l.line_no) FILTER (WHERE l.order_id IS NOT NULL), '[]') AS lines
FROM "order" o
LEFT JOIN order_line l ON l.order_id = o.id
WHERE o.customer_id = $1
GROUP BY o.id
ORDER BY o.created_at DESC
LIMIT 20;
```

**Parameter-sensitive plan test (same query, different values):**

```sql
PREPARE q(text, timestamptz) AS
  SELECT id FROM "order" WHERE status = $1 AND created_at >= $2;

EXPLAIN (ANALYZE) EXECUTE q('placed', now() - interval '1 day');    -- selective
EXPLAIN (ANALYZE) EXECUTE q('placed', now() - interval '5 years');  -- not selective
```

**Lock and block diagnosis while a query is running:**

```sql
SELECT pid, wait_event_type, wait_event, state,
       now() - query_start AS duration, left(query, 80)
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC;
```

## 8. Quality Standards

- Every optimization is justified by a before/after plan and timing, not intuition.
- No `SELECT *` in application queries; only required columns.
- No functions or casts on indexed columns in `WHERE` clauses; predicates are sargable.
- Indexes map to named queries; unused indexes are removed.
- Query latency budget defined per endpoint (e.g. p95 < 50 ms for list endpoints).
- Parameter sensitivity tested: no plan regressions for common and rare values.
- Connection pooling configured; no per-request connection churn.

## 9. Verification and Testing

- Before/after `EXPLAIN (ANALYZE, BUFFERS)` captured in the PR.
- `pgbench` or `k6` load test at expected concurrency, measuring p95/p99 and buffer hit ratio.
- Test with production-shaped data volumes (small dev DBs hide seq-scan problems).
- Verify results are identical to the original query (row counts, checksums).
- Confirm new indexes are used (`pg_stat_user_indexes.idx_scan` after traffic).

## 10. Security Considerations

- Parameterized queries only: `EXPLAIN` will happily show literal values, and string-built SQL is a SQL injection vector.
- Plans can reveal table names and data distributions; never expose `EXPLAIN` output to end users.
- `EXPLAIN ANALYZE` executes `INSERT/UPDATE/DELETE` — use `BEGIN; EXPLAIN ANALYZE ...; ROLLBACK;` for writes.
- Read-only roles for analytics jobs; a runaway query on the primary can take down the service.
- Set `statement_timeout` per role/connection to bound resource use, and `idle_in_transaction_session_timeout`.
- Query logs may contain PII; redact or disable `log_min_duration_statement` payloads where required.

## 11. Failure Handling

- **Index added but not used:** the predicate is not sargable, the table is too small for the planner to care, or statistics are stale — re-`ANALYZE`, check the plan again.
- **Plan flips under load:** parameter sniffing or stale statistics; consider `CREATE STATISTICS`, or split the query for hot parameter values.
- **Index build blocks writes:** `CREATE INDEX CONCURRENTLY`, run outside a transaction block, monitor for INVALID indexes.
- **Query fine alone, slow under concurrency:** check lock waits, pool saturation, and IOPS limits — not the query plan.
- **EXPLAIN shows huge estimated rows:** missing `ANALYZE` after bulk load; run `VACUUM ANALYZE`.
- **Deletes leave bloat:** autovacuum tuning or `pg_repack` for hot tables; monitor `pg_stat_user_tables.n_dead_tup`.

## 12. Expected Deliverables

1. Slow-query inventory with call counts and latency.
2. Before/after plans and timings.
3. Index changes with rationale and write-cost note.
4. Query rewrites with equivalence proof (same results).
5. Statistics/autovacuum adjustments.
6. Load test results at production scale.
7. Monitoring queries/alerts for regressions.

## 13. References

- PostgreSQL `EXPLAIN` — https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL `pg_stat_statements` — https://www.postgresql.org/docs/current/pgstatstatements.html
- PostgreSQL planner statistics — https://www.postgresql.org/docs/current/planner-statistics.html
- "Use The Index, Luke" — https://use-the-index-luke.com/
- explain.dalibo.com (plan visualizer) — https://explain.dalibo.com/
- MySQL `EXPLAIN ANALYZE` — https://dev.mysql.com/doc/refman/8.4/en/explain.html
- `hypopg` (hypothetical indexes) — https://github.com/HypoPG/hypopg
