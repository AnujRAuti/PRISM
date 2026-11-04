---
name: agent-memory-engineering
description: Design agent memory—working context, episodic and semantic stores, consolidation, retrieval, and forgetting—with privacy, poisoning, and staleness controls.
metadata:
  domain: agentic-ai
  version: 1.0.0
  risk: high
---

# Agent Memory Engineering

## 1. Purpose

Give agents useful memory without letting it become a liability. Memory spans a spectrum: the working context (short-term), episodic logs of past interactions, semantic stores of facts and preferences, and procedural memory (learned routines). Bad memory design produces context bloat, stale facts presented as truth, cross-user leakage, and memory poisoning. This skill defines memory types, write policies, retrieval, consolidation, and deletion.

**Scope:** memory about your users and systems. Stored memory is personal data in most jurisdictions—retention, access, and deletion must be designed, not bolted on.

## 2. Activation Conditions

- Agent must remember facts across sessions (preferences, project state).
- Conversations exceed the context window and need summarization.
- Retrieval over past interactions or documents is required.
- Users report the agent "forgetting" or "remembering wrong things".
- Keywords: agent memory, long-term memory, episodic, semantic memory, summarization, consolidation, memory store, context compaction, personalization, forgetting.

## 3. When Not to Use

- The task is stateless and single-turn.
- Simple conversation history within the context window is sufficient.
- Document retrieval for grounding (use retrieval-augmented-generation) — different concern from user memory.

## 4. Required Context

1. What must be remembered, for whom, and for how long.
2. Privacy classification and user consent model for stored memory.
3. Retrieval triggers: when memory is read and by which key.
4. Storage options available (Postgres, vector store, KV, file).
5. Budget: memory retrieval tokens per turn.

## 5. Operating Procedure

1. **Classify memory types** you need:
   - Working: current task state and recent turns (in context).
   - Episodic: past session summaries with timestamps.
   - Semantic: durable facts (`user.timezone = Asia/Kolkata`) with provenance.
   - Procedural: reusable instructions/playbooks.
2. **Define a schema per type** with keys: `user_id`, `tenant_id`, `type`, `content`, `source`, `confidence`, `created_at`, `updated_at`, `expires_at`, `sensitivity`.
3. **Write policy**: only persist what is useful and permissible. Never store secrets, credentials, or full raw transcripts by default. Require confidence for inferred facts.
4. **Deduplicate and supersede**: semantic facts keyed by (entity, attribute) so updates overwrite rather than accumulate contradictions.
5. **Retrieval**: fetch by explicit key first (cheap, precise), then similarity search; rank by recency × importance × confidence; cap tokens.
6. **Consolidation**: summarize old episodes into semantic facts on a schedule; keep the raw episode for an audit window.
7. **Forgetting**: TTL for ephemeral memory, decay for low-confidence items, hard delete on user request, and purge on tenant offboarding.
8. **Provenance**: every memory records where it came from (user statement, inference, document) so the agent can qualify it.
9. **Isolation**: namespace by tenant/user; assert in the query, never post-filter.
10. **Evaluate**: memory precision (is retrieved memory relevant and correct) and impact on task success; track wrong-memory incidents.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Structured memory | Postgres (JSONB + indexes) |
| Semantic search over memory | pgvector, Qdrant |
| Session state | Redis with TTL |
| Summarization | LLM with strict length/format constraints |
| Orchestration | Framework memory modules (LangGraph checkpointer, Mem0-style stores) |
| Governance | Row-level security, audit tables, retention jobs |

## 7. Practical Implementation

**Schema with supersession and provenance:**

```sql
CREATE TABLE agent_memory (
  id            bigserial PRIMARY KEY,
  tenant_id     text NOT NULL,
  user_id       text NOT NULL,
  kind          text NOT NULL CHECK (kind IN ('fact','preference','episode','procedure')),
  entity        text,                 -- e.g. 'user', 'project:alpha'
  attribute     text,                 -- e.g. 'timezone'
  content       text NOT NULL,
  confidence    real NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  source        text NOT NULL,        -- 'user_stated' | 'inferred' | 'document:<id>'
  sensitivity   text NOT NULL DEFAULT 'normal',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz,
  superseded_by bigint REFERENCES agent_memory(id),
  UNIQUE (tenant_id, user_id, entity, attribute, superseded_by) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX memory_lookup ON agent_memory (tenant_id, user_id, entity, attribute)
  WHERE superseded_by IS NULL;
```

**Upsert with supersession (no contradictory facts):**

```python
def remember_fact(conn, tenant_id, user_id, entity, attribute, content,
                  source, confidence=1.0, expires_at=None) -> int:
    with conn.transaction():
        old = conn.execute(
            """UPDATE agent_memory SET superseded_by = nextval('agent_memory_id_seq')
               WHERE tenant_id=%s AND user_id=%s AND entity=%s AND attribute=%s
                 AND superseded_by IS NULL
               RETURNING id""",
            (tenant_id, user_id, entity, attribute)).fetchone()
        new_id = conn.execute(
            """INSERT INTO agent_memory (tenant_id, user_id, kind, entity, attribute,
                                         content, confidence, source, expires_at)
               VALUES (%s,%s,'fact',%s,%s,%s,%s,%s,%s) RETURNING id""",
            (tenant_id, user_id, entity, attribute, content, confidence, source, expires_at)
        ).fetchone()[0]
        return new_id
```

**Retrieval with explicit keys first, then bounded similarity:**

```python
def retrieve_context(conn, tenant_id: str, user_id: str, query: str, budget_chars: int = 3000) -> str:
    facts = conn.execute(
        """SELECT entity, attribute, content, source, confidence, updated_at
           FROM agent_memory
           WHERE tenant_id=%s AND user_id=%s AND superseded_by IS NULL
             AND (expires_at IS NULL OR expires_at > now())
           ORDER BY confidence DESC, updated_at DESC
           LIMIT 20""", (tenant_id, user_id)).fetchall()

    lines, used = [], 0
    for f in facts:
        line = f"- {f['entity']}.{f['attribute']}: {f['content']} (source={f['source']}, conf={f['confidence']:.2f})"
        if used + len(line) > budget_chars:
            break
        lines.append(line); used += len(line)
    return "\n".join(lines)
```

**Episode summarization with strict output contract:**

```python
SUMMARY_PROMPT = """Summarize the conversation for future reference.
Output JSON: {"summary": "<=120 words", "facts": [{"entity": str, "attribute": str,
"content": str, "confidence": 0-1}], "open_loops": [str]}
Only include facts the user stated or clearly implied. Do not include secrets, credentials,
or sensitive personal data beyond preferences relevant to the product."""

def consolidate(episode_transcript: str) -> dict:
    out = llm_json(SUMMARY_PROMPT, episode_transcript, schema=SUMMARY_SCHEMA)
    for fact in out["facts"]:
        if fact["confidence"] >= 0.7:
            remember_fact(conn, tenant, user, fact["entity"], fact["attribute"],
                          fact["content"], source="inferred", confidence=fact["confidence"])
    return out
```

**Deletion (user request / GDPR):**

```sql
BEGIN;
DELETE FROM agent_memory WHERE tenant_id = $1 AND user_id = $2;
DELETE FROM memory_vectors WHERE tenant_id = $1 AND user_id = $2;
INSERT INTO memory_audit (tenant_id, user_id, action, at)
VALUES ($1, $2, 'erasure', now());
COMMIT;
```

**Memory-quality eval:**

```python
def memory_eval(cases):
    """Each case: setup facts -> question -> expected answer; checks relevance and correctness."""
    correct = leaks = 0
    for c in cases:
        seed_memory(c["user_id"], c["facts"])
        answer = agent_answer(c["user_id"], c["question"])
        correct += int(all(x in answer for x in c["expect_substrings"]))
        leaks += int(any(x in answer for x in c.get("must_not_contain", [])))
    n = len(cases)
    return {"accuracy": correct / n, "leak_rate": leaks / n}
```

## 8. Quality Standards

- Memory entries have type, provenance, confidence, and timestamps.
- Semantic facts are unique per (entity, attribute) with supersession, not duplicates.
- Retrieval is keyed and tenant-scoped in SQL; tokens per turn are capped.
- No secrets or raw credentials are stored.
- Every entry has a retention/expiry policy.
- Deletion is complete across stores (relational, vector, cache) and audited.
- Memory provenance is surfaced to the agent so it can say "you told me" vs. "I inferred".

## 9. Verification and Testing

- Cross-tenant test: a query by user A never returns user B's memory.
- Supersession test: writing a new timezone yields one active fact.
- Expiry test: expired facts are excluded automatically.
- Deletion test: after erasure, similarity search returns nothing for that user.
- Poisoning test: an injected "fact" from untrusted content is not stored as user-stated.

## 10. Security Considerations

- **Memory poisoning:** untrusted content (emails, web pages, tool output) must never be written as durable memory without confidence gating and provenance tagging.
- **Prompt injection via memory:** a stored instruction can hijack future sessions—store facts, not instructions; never auto-execute stored procedures from untrusted sources.
- **Cross-user leakage:** enforce isolation in the query and test it; vector search on a shared collection is a common leak path.
- **Sensitive data:** classify memory entries; exclude health/financial/credential data unless explicitly required and consented.
- **Retention:** memory without expiry becomes a compliance liability; default TTLs by type.
- **Auditability:** log who read/wrote memory for regulated deployments.

## 11. Failure Handling

- **Context bloat:** cap retrieved memory tokens and prioritize keyed facts over similarity results.
- **Contradictory memories:** supersession failed (multiple writers or bad keys) — enforce unique constraints and reconcile with a confidence-weighted merge.
- **Agent ignores memory:** retrieval returned nothing (wrong key) or the memory block was placed after long instructions — put critical memory near the end of the system context.
- **Wrong inferences stored as facts:** require confidence ≥ threshold and mark source as `inferred`; prompt the agent to hedge.
- **Deletion requests keep reappearing:** vectors or caches not purged—include all stores in the deletion routine.

## 12. Expected Deliverables

1. Memory taxonomy with schemas.
2. Write policy and confidence thresholds.
3. Retrieval algorithm with token budget.
4. Consolidation and forgetting jobs.
5. Isolation and deletion procedures with audit.
6. Memory quality evaluation results.
7. Privacy note covering retention and consent.

## 13. References

- Packer et al., "MemGPT: Towards LLMs as Operating Systems" — https://arxiv.org/abs/2310.08560
- LangGraph memory concepts — https://langchain-ai.github.io/langgraph/concepts/memory/
- Anthropic, "Contextual retrieval" (for document memory) — https://www.anthropic.com/news/contextual-retrieval
- GDPR Article 17 (right to erasure) — https://gdpr-info.eu/art-17-gdpr/
- OWASP LLM Top 10 (LLM08 vector/embedding weaknesses) — https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST AI RMF — https://www.nist.gov/itl/ai-risk-management-framework
