---
name: vector-database-engineering
description: Operate vector indexes in production—schema and index selection (HNSW, IVF, DiskANN), filtering, sharding, upserts and deletes, recall/latency tuning, and cost control.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Vector Database Engineering

## 1. Purpose

Make similarity search fast, cheap, and correct at scale. Vector search is approximate by nature: every index trades recall for latency and memory. This skill covers index selection, distance metric correctness, metadata filtering pitfalls, ingestion/update patterns, deletion and compaction, capacity planning, and how to measure recall against ground truth instead of trusting defaults.

**Scope:** indexes over data you own. Embeddings are derived from potentially sensitive content and can be partially inverted—treat the vector store with the same care as the source documents.

## 2. Activation Conditions

- Choosing between pgvector, Qdrant, Milvus, Weaviate, or a managed service.
- Search quality drops after data growth or index changes.
- Need to tune recall/latency or reduce memory cost.
- Designing filtered search (tenant/ACL filters + similarity).
- Keywords: vector database, HNSW, IVF, ANN, cosine similarity, recall@k, embedding index, pgvector, Qdrant, filtering, sharding, quantization.

## 3. When Not to Use

- Fewer than a few thousand vectors where exact search (brute force) is fast enough.
- The retrieval problem is really keyword search (use BM25).
- RAG pipeline design (use retrieval-augmented-generation); this skill is about the storage layer.

## 4. Required Context

1. Vector count, dimensionality, growth rate, and deletion rate.
2. Query volume (QPS), latency target (p95), and recall target.
3. Filter dimensions (tenant, ACL, language, date) and their cardinality.
4. Embedding model and distance metric it was trained for.
5. Memory/disk budget and whether the store is managed.
6. Consistency needs: how soon must new vectors be searchable?

## 5. Operating Procedure

1. **Confirm the metric**: normalization + cosine vs. inner product vs. L2 — use the metric the embedding model was trained with; normalize vectors if using cosine.
2. **Start exact**: brute-force search on a sample (e.g. 100k vectors) to establish ground truth recall before adding an ANN index.
3. **Choose an index**:
   - HNSW: best recall/latency, high memory, expensive rebuilds.
   - IVF-PQ: lower memory, needs training data and tuning (`nprobe`, `nlist`), some recall loss.
   - DiskANN/IVF on disk: large corpora with memory limits.
4. **Tune parameters empirically** on ground truth: HNSW `M`, `ef_construction`, `ef_search`; IVF `nlist`, `nprobe`.
5. **Handle filters correctly**: pre-filter for high-selectivity filters (tenant/ACL); post-filter destroys recall on small result sets. Some engines require filter-aware index types or partition keys.
6. **Partition by tenant** when queries are always tenant-scoped — it caps fan-out and simplifies deletion (GDPR).
7. **Design the write path**: stable IDs, upsert semantics, batched inserts, and transaction boundaries with the source of truth (outbox or CDC).
8. **Plan deletions**: soft delete + compaction/vacuum; HNSW deletion behavior varies (tombstones, re-index cost).
9. **Apply quantization** (int8, binary, product) only after measuring recall impact; rescore the top candidates with full precision.
10. **Benchmark** with realistic queries: measure recall@10 vs. exact ground truth, p50/p95/p99 latency, and memory/disk usage; then load test.
11. **Monitor**: index build lag, query latency, recall sampling in production, and index size growth.

## 6. Tools and Technologies

| Option | Notes |
|---|---|
| pgvector (Postgres) | Best when you already run Postgres; HNSW/IVFFlat; joins and transactions for free |
| Qdrant | Strong filtering, payload indexes, quantization, snapshots |
| Milvus | Large scale, multiple index types, distributed |
| Weaviate | Hybrid search built-in, modules for vectorizers |
| LanceDB | Embedded/columnar, good for local and serverless |
| OpenSearch k-NN | If you already run OpenSearch |
| FAISS | Library, not a database—good for offline evaluation |
| Benchmarks | `ann-benchmarks`, custom ground-truth harness |

## 7. Practical Implementation

**pgvector HNSW index and query:**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE docs (
  id uuid PRIMARY KEY,
  tenant_id text NOT NULL,
  lang text NOT NULL,
  content text NOT NULL,
  embedding vector(1024) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- HNSW with cosine distance; m and ef_construction tuned by benchmark
CREATE INDEX docs_emb_hnsw ON docs
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

-- Session-level recall knob (higher = better recall, more latency)
SET hnsw.ef_search = 80;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, content, 1 - (embedding <=> $1::vector) AS score
FROM docs
WHERE tenant_id = $2            -- pre-filter on a btree-indexed column
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

**Qdrant collection with payload indexes and filter:**

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(url="http://qdrant:6333")

client.create_collection(
    collection_name="docs",
    vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE,
                                       hnsw_config=models.HnswConfigDiff(m=16, ef_construct=200)),
    hnsw_config=models.HnswConfigDiff(m=16, ef_construct=200),
    quantization_config=models.ScalarQuantization(
        scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, quantile=0.99, always_ram=True)
    ),
)
client.create_payload_index("docs", field_name="tenant_id", field_schema=models.PayloadSchemaType.KEYWORD)
client.create_payload_index("docs", field_name="lang", field_schema=models.PayloadSchemaType.KEYWORD)

hits = client.search(
    collection_name="docs",
    query_vector=vector,
    query_filter=models.Filter(must=[
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value="acme")),
        models.FieldCondition(key="lang", match=models.MatchValue(value="en")),
    ]),
    limit=10,
    with_payload=["id", "content"],
    search_params=models.SearchParams(hnsw_ef=96, exact=False),
)
```

**Measuring recall against exact search (the only trustworthy metric):**

```python
import numpy as np

def exact_topk(vectors: np.ndarray, q: np.ndarray, k: int = 10) -> set[int]:
    sims = vectors @ q / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(q))
    return set(np.argsort(-sims)[:k].tolist())

def recall_at_k(ann_ids: list[int], truth: set[int], k: int = 10) -> float:
    return len(set(ann_ids[:k]) & truth) / k

# 200 sample queries, compare ANN vs exact
recalls = []
for i in range(200):
    q = queries[i]
    ann = [h.id for h in search_ann(q, k=10)]
    recalls.append(recall_at_k(ann, exact_topk(vectors, q, 10)))
print(f"recall@10 mean={np.mean(recalls):.3f} p05={np.percentile(recalls, 5):.3f}")
```

**Batched upsert with stable IDs (idempotent ingestion):**

```python
import hashlib

def stable_id(source: str, chunk_index: int) -> str:
    return hashlib.sha256(f"{source}:{chunk_index}".encode()).hexdigest()[:32]

def upsert_batch(client, collection: str, rows: list[dict]) -> None:
    points = [
        models.PointStruct(
            id=stable_id(r["source"], r["chunk_index"]),
            vector=r["embedding"],
            payload={"source": r["source"], "tenant_id": r["tenant_id"],
                     "content": r["content"], "updated_at": r["updated_at"]},
        )
        for r in rows
    ]
    client.upsert(collection_name=collection, points=points, wait=True)
```

**Postgres: delete propagation with soft delete + vacuum:**

```sql
-- Soft-delete immediately (queryable state changes at once)
UPDATE docs SET deleted_at = now() WHERE source = $1;
-- Query always filters
SELECT id FROM docs WHERE deleted_at IS NULL AND tenant_id = $2
ORDER BY embedding <=> $3 LIMIT 10;
-- Hard delete in a maintenance job, then reclaim space
DELETE FROM docs WHERE deleted_at < now() - INTERVAL '30 days';
-- pgvector: REINDEX if HNSW becomes fragmented after heavy churn
REINDEX INDEX CONCURRENTLY docs_emb_hnsw;
```

**Capacity estimate:**

```text
memory ≈ N × D × 4 bytes (float32) × (1 + overhead)
example: 10M × 1024 × 4 ≈ 41 GB raw; int8 quantization → ~10 GB; add ~30–50% for HNSW graph.
```

## 8. Quality Standards

- Distance metric matches the embedding model's training objective; vectors normalized where required.
- Recall is measured against exact search and reported with the latency at that setting.
- Filters are applied pre-search where the engine supports it; tenant isolation is enforced in the query.
- IDs are stable and idempotent; re-ingestion does not duplicate points.
- Deletion path is defined and tested (soft delete + compaction policy).
- Index parameters are documented with the benchmark that justified them.
- Index build/refresh lag is monitored.

## 9. Verification and Testing

```bash
pytest -q tests/test_vector_store.py -k "recall or filter or delete"
psql "$DB" -c "EXPLAIN (ANALYZE, BUFFERS) SELECT id FROM docs WHERE tenant_id='acme' ORDER BY embedding <=> '[...]' LIMIT 10;"
```

Tests: recall@10 ≥ target on the gold query set; a cross-tenant query never returns another tenant's rows; deleting a document removes it from results immediately; re-running ingestion produces the same point count; latency p95 within budget under 2× expected QPS.

## 10. Security Considerations

- Enforce tenant/ACL filters server-side in the query; never rely on the client to scope results.
- Vector stores are often exposed internally without auth; require authentication, TLS, and network policy.
- Embeddings can leak source text (inversion attacks); restrict access and avoid publishing raw vectors.
- Ingestion pipelines should strip secrets/PII when the use case does not require them.
- Snapshot/backup files contain the full corpus—encrypt and restrict.
- Guard against query-cost abuse: cap `limit`, `ef_search`, and filter complexity; rate-limit per principal.
- Deletion requests must remove vectors and snapshots, not just the source row.

## 11. Failure Handling

- **Recall drops after growth:** index outgrew memory or parameters are stale—re-benchmark `ef_search`/`nprobe`, check for memory pressure and disk-based fallback.
- **Filtered queries return too few results:** post-filtering starvation; switch to pre-filter/partitioned index or raise candidate count.
- **Slow index builds:** reduce `ef_construction`/`M`, build offline, or shard; monitor build progress.
- **Duplicates after re-ingestion:** non-stable IDs; switch to deterministic IDs derived from source + chunk.
- **Deletes not reflected:** HNSW tombstones need vacuum/compaction; schedule it and verify with a query test.
- **Latency spikes under load:** too many concurrent queries per shard; add replicas, reduce `ef_search`, or batch.

## 12. Expected Deliverables

1. Index/schema design with metric and dimensionality.
2. Parameter choices with benchmark evidence (recall vs. latency).
3. Ingestion code with stable IDs and batching.
4. Filter/isolation design and tests.
5. Deletion and compaction procedure.
6. Capacity and cost estimate with growth projection.
7. Monitoring plan.

## 13. References

- pgvector README — https://github.com/pgvector/pgvector
- Qdrant documentation — https://qdrant.tech/documentation/
- Milvus documentation — https://milvus.io/docs
- Weaviate documentation — https://weaviate.io/developers/weaviate
- HNSW paper (Malkov & Yashunin) — https://arxiv.org/abs/1603.09320
- FAISS wiki — https://github.com/facebookresearch/faiss/wiki
- ANN-Benchmarks — https://ann-benchmarks.com/
