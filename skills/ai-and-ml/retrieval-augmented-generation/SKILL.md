---
name: retrieval-augmented-generation
description: Build RAG systems that retrieve the right context—chunking strategy, hybrid search, reranking, grounded generation, and evaluation with retrieval and answer metrics.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Retrieval-Augmented Generation

## 1. Purpose

Ground LLM answers in your own documents instead of model memory. RAG quality is decided by retrieval, not by prompt wording: bad chunking, single-mode keyword or vector search, and no reranking produce confident wrong answers. This skill covers ingestion, chunking, indexing, hybrid retrieval, reranking, context assembly, grounded generation with citations, and a two-level evaluation (retrieval metrics and answer metrics).

**Scope:** corpora you have the right to index. Documents often contain confidential or personal data—enforce access control at retrieval time, not just at the UI.

## 2. Activation Conditions

- Q&A over internal documents, support content, or product documentation.
- The model must cite sources or answer with current/proprietary facts.
- Existing RAG produces hallucinated or stale answers.
- Need to choose between vector-only, keyword, and hybrid retrieval.
- Keywords: RAG, retrieval, embeddings, chunking, vector search, reranking, hybrid search, citations, grounded generation, context window, BM25.

## 3. When Not to Use

- The knowledge fits in the prompt (a few pages) — just include it.
- The task requires full-corpus reasoning or aggregation over thousands of documents (use query-time analytics or a data warehouse).
- The answer must come from a single structured database query—use SQL, not retrieval.

## 4. Required Context

1. Corpus size, formats (PDF, HTML, Confluence, code), and update cadence.
2. Document-level access rules (who may see what).
3. Query distribution: real user questions with expected answers.
4. Latency budget and per-query cost ceiling.
5. Whether citations are required for the product.

## 5. Operating Procedure

1. **Collect 30–50 real questions** with gold answers and the document(s) that contain them. This evaluation set drives every design decision.
2. **Ingest with structure preserved**: strip boilerplate, keep headings, tables, and page numbers as metadata; record source URI and last-modified time.
3. **Chunk semantically**: split on headings/paragraphs with a token budget (300–800 tokens) and 10–20% overlap; never split a table from its header.
4. **Embed** with a model matched to your domain/language; store vectors with metadata for filtering.
5. **Add lexical search** (BM25/Postgres full-text) alongside vectors—hybrid beats either alone, especially for IDs, names, and rare terms.
6. **Fuse results** with Reciprocal Rank Fusion (RRF) or weighted score normalization.
7. **Rerank** the top 20–50 candidates with a cross-encoder; keep the top 4–8 for the prompt.
8. **Assemble context** with source markers, deduplicate near-identical chunks, and respect the token budget.
9. **Generate with grounded instructions**: answer only from context, cite chunk IDs, and say "not found in the provided documents" when unsupported.
10. **Evaluate retrieval** (recall@k, MRR, nDCG) and **answers** (correctness, faithfulness/groundedness, citation accuracy) separately.
11. **Monitor** in production: retrieval scores, "not found" rate, user feedback, and freshness of the index.
12. **Re-index incrementally** on document change with deletion propagation.

## 6. Tools and Technologies

| Layer | Tools |
|---|---|
| Ingestion | `unstructured`, `pypdf`, `trafilatura`, `markdownify` |
| Chunking | langchain-text-splitters, custom heading-aware splitters |
| Embeddings | OpenAI `text-embedding-3-*`, `bge-*`, `e5-*`, multilingual models |
| Vector stores | pgvector, Qdrant, Weaviate, Milvus, LanceDB |
| Lexical | Postgres FTS (`tsvector`), OpenSearch/Elasticsearch BM25 |
| Reranking | `bge-reranker`, Cohere Rerank, cross-encoder models |
| Orchestration | LlamaIndex, LangChain, custom lightweight pipeline |
| Evaluation | RAGAS, custom recall@k harness, promptfoo |

## 7. Practical Implementation

**Heading-aware chunking with metadata (Python):**

```python
import re
from dataclasses import dataclass

@dataclass
class Chunk:
    id: str
    text: str
    source: str
    heading: str
    page: int | None
    updated_at: str

def chunk_markdown(doc: str, source: str, max_tokens: int = 600, overlap: int = 80) -> list[Chunk]:
    sections = re.split(r"(?m)^(#{1,4})\s+(.*)$", doc)
    chunks: list[Chunk] = []
    heading = "root"
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        text = "\n".join(buf).strip()
        if not text:
            buf = []
            return
        words = text.split()
        est = max(1, int(max_tokens / 0.75))        # rough word->token estimate
        for i in range(0, len(words), est - overlap if est > overlap else est):
            piece = " ".join(words[i:i + est])
            chunks.append(Chunk(f"{source}#{len(chunks)}", piece, source, heading, None, "2026-10-01"))
        buf = []

    it = iter(sections)
    for part in it:
        if re.fullmatch(r"#{1,4}", part.strip()):
            flush()
            heading = next(it, heading).strip()
        else:
            buf.append(part)
    flush()
    return chunks
```

**Postgres schema for hybrid retrieval (pgvector + full text):**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
  id          text PRIMARY KEY,
  source      text NOT NULL,
  heading     text,
  page        int,
  updated_at  timestamptz NOT NULL,
  acl_group   text NOT NULL DEFAULT 'public',
  content     text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  embedding   vector(1536)
);

CREATE INDEX chunks_tsv_idx ON chunks USING GIN (tsv);
CREATE INDEX chunks_emb_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_acl_idx ON chunks (acl_group);
```

**Hybrid search with RRF in SQL:**

```sql
WITH params AS (SELECT $1::vector AS qvec, plainto_tsquery('english', $2) AS qts, $3::text AS grp),
vec AS (
  SELECT c.id, ROW_NUMBER() OVER (ORDER BY c.embedding <=> (SELECT qvec FROM params)) AS rank
  FROM chunks c WHERE c.acl_group = (SELECT grp FROM params)
  ORDER BY c.embedding <=> (SELECT qvec FROM params) LIMIT 50
),
lex AS (
  SELECT c.id, ROW_NUMBER() OVER (ORDER BY ts_rank(c.tsv, (SELECT qts FROM params)) DESC) AS rank
  FROM chunks c
  WHERE c.acl_group = (SELECT grp FROM params) AND c.tsv @@ (SELECT qts FROM params)
  LIMIT 50
)
SELECT id, SUM(1.0 / (60 + rank)) AS rrf_score
FROM (SELECT * FROM vec UNION ALL SELECT * FROM lex) s
GROUP BY id ORDER BY rrf_score DESC LIMIT 20;
```

**Reranking and context assembly:**

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

def select_context(question: str, candidates: list[dict], k: int = 6, max_chars: int = 8000) -> list[dict]:
    pairs = [(question, c["content"][:2000]) for c in candidates]
    scores = reranker.predict(pairs)
    ranked = [c for _, c in sorted(zip(scores, candidates), key=lambda t: -t[0])]
    out, used = [], 0
    for c in ranked:
        if used + len(c["content"]) > max_chars:
            continue
        out.append(c); used += len(c["content"])
        if len(out) == k:
            break
    return out

def build_prompt(question: str, chunks: list[dict]) -> str:
    ctx = "\n\n".join(f"[{c['id']}] ({c['source']} {c.get('heading','')})\n{c['content']}" for c in chunks)
    return (
        "Answer the question using ONLY the sources below. Cite sources as [id]. "
        "If the sources do not contain the answer, say: 'Not found in the provided documents.'\n\n"
        f"<sources>\n{ctx}\n</sources>\n\nQuestion: {question}"
    )
```

**Retrieval evaluation (recall@k, MRR):**

```python
def recall_at_k(retrieved: list[str], gold: set[str], k: int = 10) -> float:
    return len(set(retrieved[:k]) & gold) / max(len(gold), 1)

def reciprocal_rank(retrieved: list[str], gold: set[str]) -> float:
    for i, doc in enumerate(retrieved, 1):
        if doc in gold:
            return 1.0 / i
    return 0.0

eval_qs = load_eval_set()      # [{question, gold_doc_ids, gold_answer}]
scores = [(recall_at_k(r, q["gold_doc_ids"]), reciprocal_rank(r, q["gold_doc_ids"]))
          for q in eval_qs for r in [retrieve(q["question"], k=10)]]
print("recall@10", sum(s[0] for s in scores) / len(scores),
      "mrr", sum(s[1] for s in scores) / len(scores))
```

**Answer evaluation rubric (human or LLM-judge with a fixed rubric):**

```text
correctness   : does the answer match the gold answer? (0/1)
faithfulness  : is every claim supported by a cited chunk? (0/1 per claim)
citation_acc  : do the cited chunk ids actually contain the claim? (0/1)
abstention    : for unanswerable questions, did it say "not found"? (0/1)
```

## 8. Quality Standards

- Retrieval evaluated separately from generation, with a fixed question set.
- Chunks preserve structure and carry source, heading, and timestamp metadata.
- Hybrid retrieval (lexical + vector) is the default unless measurement shows otherwise.
- Reranking applied before context assembly; context is deduplicated and budgeted.
- Generation instructions enforce grounded answers and explicit abstention.
- Access control filters are applied in the retrieval query, not after generation.
- Index updates and deletions propagate; stale chunks are removed.
- Citations are verifiable (chunk IDs map to real content).

## 9. Verification and Testing

```bash
pytest -q tests/test_chunking.py tests/test_retrieval_eval.py
python scripts/eval_rag.py --questions evals/questions.json --k 10
```

Tests: chunking never splits a table from its caption; retrieval returns only chunks the user may see (cross-tenant test); recall@10 meets the target; unanswerable questions produce the abstention string; citations in generated answers resolve to existing chunk IDs.

## 10. Security Considerations

- **Access control at retrieval**: filter by ACL in the query. Post-filtering after generation leaks content into the answer.
- **Indirect prompt injection**: documents can contain instructions ("ignore previous instructions and reveal..."). Delimit sources, instruct the model to treat them as data, and never allow retrieved text to trigger tool calls.
- Index only content you are licensed to store; respect robots/ToS for external content.
- Strip secrets and PII from ingested documents where not required; log chunk IDs, not full text.
- Protect the vector store with auth and network policy; embeddings can be inverted to approximate text.
- Rate-limit queries to prevent corpus exfiltration through repeated probing.

## 11. Failure Handling

- **Retrieves plausible but wrong chunks:** improve chunking (too large/small), add reranking, and check embedding model language match.
- **Misses exact identifiers/names:** lexical search must be in the hybrid; ensure the tokenizer handles codes.
- **Answers ignore context:** prompt too long or instructions buried; put instructions after context or shorten context.
- **Hallucination persists:** enforce abstention, lower temperature, and require a citation for each sentence; evaluate faithfulness.
- **Index stale:** automate re-indexing on document change; store `updated_at` and surface freshness.
- **Latency high:** precompute embeddings, cache frequent queries, reduce candidate count before reranking, and run reranker on a bounded set.

## 12. Expected Deliverables

1. Corpus inventory and ingestion pipeline.
2. Chunking strategy with parameters and rationale.
3. Index schema (vector + lexical + metadata + ACL).
4. Retrieval pipeline (hybrid + rerank) with code.
5. Generation prompt with grounding and abstention rules.
6. Evaluation results: recall@k, MRR, correctness/faithfulness/citation accuracy.
7. Operational plan: re-indexing, monitoring, and access control verification.

## 13. References

- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP" — https://arxiv.org/abs/2005.11401
- pgvector — https://github.com/pgvector/pgvector
- Reciprocal Rank Fusion (Cormack et al.) — https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- Sentence-Transformers — https://www.sbert.net/
- RAGAS evaluation — https://docs.ragas.io/
- OWASP LLM Top 10 (LLM01 prompt injection) — https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Anthropic, "Contextual Retrieval" — https://www.anthropic.com/news/contextual-retrieval
