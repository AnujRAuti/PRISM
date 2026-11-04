---
name: distributed-systems
description: Design and debug multi-node systems—consistency, consensus, partitioning, replication, idempotency, retries, and failure semantics under partial failure.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: high
---

# Distributed Systems

## 1. Purpose

Reason correctly about systems where networks partition, clocks disagree, and messages duplicate. This skill gives the agent a working model (CAP/PACELC in practice, delivery semantics, failure detectors) plus concrete techniques: idempotency, exactly-once effects via outbox+dedupe, leader election, quorum reads/writes, sagas, and backpressure. It solves bugs caused by assuming reliable networks and synchronous state.

## 2. Activation Conditions

- Multiple services, databases, or regions must agree on state.
- Designing queues/streams, retries, or cross-service workflows.
- Debugging duplicates, lost messages, split-brain, stale reads, or clock-dependent bugs.
- Choosing a database consistency level or replication topology.
- Keywords: distributed, consensus, Raft, quorum, replication, partition, CAP, eventual consistency, saga, exactly-once, leader election, split-brain, clock skew.

## 3. When Not to Use

- Single-process, single-database applications; transactions in one Postgres instance are sufficient.
- When a monolith with one DB meets the requirements (prefer the simpler system).
- Pure client-side work.
- When the user needs conceptual theory only—answer directly instead of activating a build workflow.

## 4. Required Context

1. Topology: nodes, regions, network paths, latencies between them.
2. Data model and which invariants must hold (e.g. "balance never negative").
3. Failure budget: which failures are acceptable (stale reads for 5 s? duplicate charge? none?).
4. Existing infrastructure: managed DB with replicas, Kafka, etcd, Redis cluster.
5. Observed symptoms: p99 spikes, duplicate records, lost events, timeouts.
6. Time-sync setup (NTP/chrony, clock skew between nodes).

## 5. Operating Procedure

1. **Write invariants and failure tolerances first.** "No double charge" is stronger than "eventually consistent orders".
2. **Classify each operation**: read-only, idempotent write, non-idempotent write, cross-entity transaction.
3. **Choose the consistency plan per operation**, not per system. Some reads can be stale; balances cannot.
4. **Design for at-least-once delivery by default** and make every consumer idempotent with a dedupe key (`event_id` unique index) and a TTL.
5. **Use the transactional outbox** to couple DB writes and event publication atomically; relay with a poller/CDC and mark published.
6. **Use sagas for multi-service transactions**: explicit compensating actions per step, persisted state machine, idempotent compensations.
7. **Set timeouts, deadlines, and retry budgets** on every network call; propagate deadlines downstream.
8. **Choose retry policy**: exponential backoff with jitter, capped attempts, only on retryable errors (timeouts, 429, 5xx except 501), never on 4xx validation.
9. **Add circuit breakers and bulkheads** to stop cascading failure; define fallback behavior.
10. **Pick consistency mechanism where needed**: quorum (R/W > N/2), single-writer per partition, or consensus (Raft/etcd) for leader election and config.
11. **Handle clock skew:** use monotonic clocks for durations, logical clocks/versions for ordering, NTP-synced UTC for timestamps but never as the sole ordering key.
12. **Instrument** with trace IDs propagated across hops, per-hop latency, retry counts, and queue depth.
13. **Test failures deliberately**: network partitions, node kills, clock skew, duplicate delivery.

## 6. Tools and Technologies

| Concern | Tools |
|---|---|
| Consensus / coordination | etcd (Raft), Consul, ZooKeeper |
| Streaming | Kafka (partitions, consumer groups, idempotent producer), NATS JetStream, Pulsar |
| Outbox / CDC | Debezium, `pg_logical`, poller workers |
| Workflow/saga | Temporal, Camunda, custom state machine |
| Resilience | `resilience4j`, `tenacity`, Envoy retries/outlier detection |
| Chaos testing | Toxiproxy, Chaos Mesh, `tc netem`, `iptables` |
| Tracing | OpenTelemetry, Jaeger, Tempo |
| Distributed DBs | CockroachDB, YugabyteDB, Cassandra/ScyllaDB |

## 7. Practical Implementation

**Idempotent consumer (Python + Postgres):**

```python
def handle(event: dict, conn) -> None:
    with conn.transaction():
        inserted = conn.execute(
            "INSERT INTO processed_events (event_id, processed_at) "
            "VALUES (%s, now()) ON CONFLICT (event_id) DO NOTHING RETURNING 1",
            (event["id"],),
        ).fetchone()
        if not inserted:
            return  # duplicate: ack and move on
        conn.execute(
            "UPDATE accounts SET balance = balance + %s WHERE id = %s",
            (event["amount_minor"], event["account_id"]),
        )
```

**Retry with jitter and deadline (Python):**

```python
import random, time
from dataclasses import dataclass

@dataclass
class RetryPolicy:
    attempts: int = 5
    base_s: float = 0.2
    cap_s: float = 5.0

    def sleep_for(self, attempt: int) -> float:
        exp = min(self.cap_s, self.base_s * (2 ** attempt))
        return random.uniform(0, exp)  # full jitter

def call_with_retry(fn, policy: RetryPolicy, deadline: float, retryable=(TimeoutError, ConnectionError)):
    for attempt in range(policy.attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("deadline exceeded before attempt")
        try:
            return fn(timeout=remaining)
        except retryable:
            if attempt == policy.attempts - 1:
                raise
            time.sleep(min(policy.sleep_for(attempt), remaining))
```

**Kafka idempotent producer + transactional consumer offset commit (Java):**

```java
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, "true");
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

**Saga step definition (language-neutral, JSON state):**

```json
{
  "saga": "create-order",
  "steps": [
    {"name": "reserve_stock", "compensate": "release_stock", "idempotency_key": "saga:{saga_id}:reserve"},
    {"name": "charge_payment", "compensate": "refund_payment", "idempotency_key": "saga:{saga_id}:charge"},
    {"name": "confirm_order", "compensate": "cancel_order", "idempotency_key": "saga:{saga_id}:confirm"}
  ]
}
```

**Partition simulation for testing:**

```bash
sudo tc qdisc add dev eth0 root netem delay 300ms 100ms loss 5%
# ... run test ...
sudo tc qdisc del dev eth0 root
```

## 8. Quality Standards

- Every state-changing operation has a defined idempotency strategy.
- No unbounded retries; every call has a deadline that propagates.
- Single-writer rule per key/partition; no two nodes write the same row without coordination.
- Consumer lag, retry rate, and duplicate rate are observable metrics.
- Ordering guarantees are documented per topic (per-partition only) and never assumed globally.
- Failure tests exist for duplicate delivery, partition, and node loss.
- All times stored in UTC; duration math uses monotonic clocks.

## 9. Verification and Testing

```bash
# duplicate delivery test: publish same event twice, assert single effect
pytest -q tests/test_idempotency.py
# partition test
toxiproxy-cli create pg --listen 127.0.0.1:26379 --upstream 127.0.0.1:5432
toxiproxy-cli toxic add pg -t latency -a latency=2000
# kafka consumer lag
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orders
```

Evidence: duplicated event → exactly one DB effect; killed node during write → no lost acknowledged write; retry storm does not amplify load (metrics flat); recovery time documented.

## 10. Security Considerations

- Encrypt inter-node traffic (mTLS); assume the network is hostile inside the cluster too.
- Authenticate and authorize at every service boundary; do not trust `X-User-Id` headers set by clients—validate JWT signatures and claims.
- Sign and verify internal webhooks; verify HMAC before processing.
- Protect the message broker: ACLs per topic, TLS, no anonymous access; scrub PII from payloads and rely on references where possible.
- Clock manipulation can bypass token expiry—validate `nbf`/`exp` server-side with small leeway.
- Split-brain risk in clustered systems can lead to conflicting writes: use fencing tokens (e.g. ZK/etcd lease with monotonically increasing epoch) for any resource requiring single-writer safety.

## 11. Failure Handling

- **Duplicates observed:** add dedupe store keyed by event ID; verify unique constraint exists.
- **Lost messages:** check producer acks, consumer commit timing (commit after processing), and retention settings.
- **Cascading timeouts:** tighten upstream deadlines, add circuit breakers, reduce retry budgets; find the slow dependency with traces.
- **Stale reads after write:** route read-your-write to primary or use a version token; document the consistency window.
- **Split brain:** stop writes on the minority side (quorum-gated), require fencing token, reconcile divergent data with a documented merge policy.

## 12. Expected Deliverables

- Invariant and failure-tolerance table per operation.
- Delivery and idempotency design (keys, dedupe store, TTL).
- Outbox/saga implementation or specification.
- Retry/timeout/breaker configuration with rationale.
- Observability plan (traces, lag, retry metrics).
- Failure-injection test results.

## 13. References

- Martin Kleppmann, *Designing Data-Intensive Applications*.
- "Nobody Ever Got Fired for Choosing Kafka" — delivery semantics discussion (confluent docs): https://docs.confluent.io/kafka/
- etcd Raft documentation — https://etcd.io/docs/
- microservices.io — Saga, Outbox patterns: https://microservices.io/patterns/
- AWS Builders' Library — Timeouts, retries, backoff: https://aws.amazon.com/builders-library/
- OpenTelemetry — https://opentelemetry.io/docs/
- Jepsen analyses — https://jepsen.io/analyses
