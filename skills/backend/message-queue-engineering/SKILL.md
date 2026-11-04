---
name: message-queue-engineering
description: Design reliable asynchronous messaging—at-least-once delivery, idempotent consumers, retries with backoff, dead-letter queues, ordering, and the transactional outbox.
metadata:
  domain: backend
  version: 1.0.0
  risk: high
---

# Message Queue Engineering

## 1. Purpose

Move work off the request path and between services without losing or duplicating effects. Queues change the failure model: delivery is at-least-once, ordering is per-partition at best, and a consumer crash replays messages. This skill covers topology (queue vs. topic), message contracts with versioning, idempotent consumers, retry and dead-letter policy, ordering keys, and the transactional outbox that stops "database committed, event lost".

**Scope:** your own brokers and consumers. Publishing to a topic fans out to systems you may not own: a malformed or duplicated event can corrupt other services' data. Schema changes require producer/consumer coordination; never drop or repurpose a field in place.

## 2. Activation Conditions

- Long-running work (email, exports, video, payments) moved off the request path.
- Services need to react to domain events.
- Messages disappear, duplicate, or process out of order.
- Consumers fail and messages are lost or loop forever.
- Keywords: Kafka, RabbitMQ, SQS, NATS, Celery, BullMQ, at-least-once, idempotency, dead letter queue, retry, backoff, outbox, ordering key, consumer group, visibility timeout.

## 3. When Not to Use

- Synchronous request/response where the caller needs the result immediately.
- Tiny volumes where a database table plus a cron worker is simpler and sufficient.
- Cross-team event streaming without agreement on ownership and schema (design first).

## 4. Required Context

1. Broker in use and its delivery guarantees (SQS at-least-once, Kafka ordered per partition, RabbitMQ per-queue).
2. Producer and consumer ownership.
3. Ordering requirements per entity (e.g. per order ID).
4. Acceptable processing latency and throughput targets.
5. Retention and replay requirements.

## 5. Operating Procedure

1. **Choose the shape**: point-to-point queue for work distribution; topic/fan-out for events; partition key = the entity ID when ordering matters.
2. **Define the message contract explicitly**: event type, version, ID, timestamp, aggregate ID, correlation ID, and payload. Prefer schemas (JSON Schema/Avro/Protobuf) registered in a registry.
3. **Make producers transactional**: write to the database and publish via an outbox table, then a relay publishes; never publish before commit or after a failure without compensation.
4. **Make consumers idempotent**: store processed message IDs with a unique constraint in the same transaction as side effects.
5. **Acknowledge after processing**, not on receipt; configure visibility timeout longer than the p99 processing time.
6. **Retry with exponential backoff and jitter** for transient failures; cap attempts, then route to a dead-letter queue with the failure reason.
7. **Distinguish poison from transient**: validation errors go straight to DLQ (no retries); timeouts and 5xx retry.
8. **Set concurrency and prefetch** deliberately; a high prefetch with slow work causes rebalances and duplicate processing.
9. **Monitor queue depth, age of oldest message, consumer lag, retry rate, and DLQ size**; alert on age, not just depth.
10. **Document replay procedure**: how to re-drive DLQ messages safely after a fix.
11. **Test failure modes**: kill a consumer mid-message, publish a duplicate, and send an unparseable payload.

## 6. Tools and Technologies

| Broker | Strengths | Notes |
|---|---|---|
| Kafka | High throughput, replay, ordered partitions | Operational complexity; needs schema registry discipline |
| RabbitMQ | Flexible routing, per-message ack, DLX | Ordering per queue only |
| AWS SQS/SNS | Managed, at-least-once, FIFO option | Visibility timeout and DLQ configuration |
| NATS JetStream | Lightweight, at-least-once | Smaller ecosystem |
| App-level | Celery, BullMQ, Dramatiq, Sidekiq | Redis/RabbitMQ backed; watch for duplicate delivery |

## 7. Practical Implementation

**Transactional outbox table:**

```sql
CREATE TABLE outbox (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  aggregate_id  text        NOT NULL,
  event_type    text        NOT NULL,
  payload       jsonb       NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  published_at  timestamptz
);
CREATE INDEX outbox_unpublished ON outbox (id) WHERE published_at IS NULL;
```

**Write business row + event atomically:**

```python
async def place_order(session: AsyncSession, order: Order) -> None:
    async with session.begin():
        session.add(order)
        session.add(Outbox(
            aggregate_id=order.id,
            event_type="order.placed.v1",
            payload={
                "order_id": order.id,
                "customer_id": order.customer_id,
                "total_cents": order.total_cents,
                "currency": order.currency,
                "occurred_at": order.created_at.isoformat(),
            },
        ))
```

**Outbox relay (publish then mark; at-least-once):**

```python
import asyncio, json
from sqlalchemy import select, update

async def relay_once(session: AsyncSession, producer) -> int:
    async with session.begin():
        rows = (await session.scalars(
            select(Outbox).where(Outbox.published_at.is_(None))
            .order_by(Outbox.id).limit(200).with_for_update(skip_locked=True)
        )).all()
        for row in rows:
            await producer.publish(
                topic="orders",
                key=row.aggregate_id,                      # ordering per aggregate
                value=json.dumps({"type": row.event_type, "data": row.payload}),
                headers={"event_id": str(row.id), "schema_version": "1"},
            )
            row.published_at = utcnow()
    return len(rows)
```

**Idempotent consumer with a processed-message table:**

```sql
CREATE TABLE processed_message (
  consumer    text        NOT NULL,
  event_id    text        NOT NULL,
  processed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer, event_id)
);
```

```python
async def handle(event: dict, session: AsyncSession, mailer) -> None:
    async with session.begin():
        inserted = await session.execute(
            """INSERT INTO processed_message (consumer, event_id) VALUES (:c, :e)
               ON CONFLICT DO NOTHING RETURNING event_id""",
            {"c": "order-confirmation-email", "e": event["event_id"]},
        )
        if inserted.first() is None:
            return                                     # duplicate: already handled
        await mailer.send_order_confirmation(event["data"]["order_id"])
        # side effect and dedupe row commit together
```

External side effects cannot be transactional: if the email service is not idempotent, pass an idempotency key (`event_id`) and let that service dedupe.

**Retry with exponential backoff and jitter (application-level):**

```python
import asyncio, random

async def with_retry(fn, *, attempts: int = 5, base: float = 0.5, cap: float = 30.0):
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except TransientError:
            if attempt == attempts:
                raise
            delay = min(cap, base * 2 ** (attempt - 1))
            await asyncio.sleep(delay * random.uniform(0.5, 1.5))
```

**RabbitMQ topology with DLX (Python + aio-pika):**

```python
import aio_pika

async def declare(channel: aio_pika.abc.AbstractChannel):
    dlx = await channel.declare_exchange("orders.dlx", aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue("orders.dlq", durable=True)
    await dlq.bind(dlx, routing_key="orders.failed")

    args = {
        "x-dead-letter-exchange": "orders.dlx",
        "x-dead-letter-routing-key": "orders.failed",
        "x-message-ttl": 86_400_000,          # 24 h in the DLQ
    }
    queue = await channel.declare_queue("orders.email", durable=True, arguments=args)
    await queue.bind("orders", routing_key="order.placed")
    return queue
```

**Manual ack after processing (never auto-ack for work you can fail):**

```python
async def consume(queue):
    async with queue.iterator() as it:
        async for message in it:
            async with message.process(requeue=False):     # ack on success, reject on exception
                payload = json.loads(message.body)
                await handle_event(payload)
```

**SQS with visibility extension for long jobs:**

```python
import boto3

sqs = boto3.client("sqs")

def receive():
    return sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
        VisibilityTimeout=120,
        MessageAttributeNames=["All"],
    )

def ack(receipt: str) -> None:
    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt)

# For work longer than the visibility timeout, call change_message_visibility periodically
```

**FIFO ordering key (SQS):**

```python
sqs.send_message(
    QueueUrl=FIFO_QUEUE_URL,
    MessageBody=json.dumps(event),
    MessageGroupId=f"order-{order_id}",       # strict order within the group only
    MessageDeduplicationId=event["event_id"],
)
```

**Poison-payload handling (route straight to DLQ):**

```python
try:
    data = OrderPlacedV1.model_validate(payload["data"])
except ValidationError as exc:
    await dlq.send({"raw": payload, "error": exc.errors()[:3], "consumer": CONSUMER_NAME})
    return            # ack original; do not retry an invalid payload
```

**Monitoring metrics:**

```text
queue_depth{queue="orders.email"}           -> alert if > 5,000 for 10 min
oldest_message_age_seconds{queue=...}       -> alert if > 300
consumer_lag{topic="orders", group="email"} -> alert if growing monotonically
dlq_messages_total{queue="orders.dlq"}      -> alert on any increase
```

## 8. Quality Standards

- Publish and state change are atomic (outbox or equivalent); no event is lost on crash.
- Every consumer is idempotent, proven by duplicate-delivery tests.
- Delivery is acknowledged only after successful processing.
- Transient failures retry with capped exponential backoff and jitter; permanent failures go to a DLQ with reason.
- Each event has a version, ID, timestamp, and correlation ID.
- Ordering guarantees are documented per topic, including partition-key choice.
- Queue depth, message age, lag, and DLQ are monitored with alerts.
- Replay procedure is written and rehearsed.

## 9. Verification and Testing

- Duplicate test: publish the same `event_id` twice; the side effect occurs once.
- Crash test: kill the consumer mid-handler; the message is redelivered and processed exactly once (effectively).
- Poison test: publish invalid JSON and an unknown schema version; both land in the DLQ without blocking the queue.
- Backlog test: publish 10k messages and confirm throughput and message age recover.
- Ordering test: publish A then B for one aggregate ID and assert processing order.
- Outbox test: commit a transaction and kill the relay; on restart, the event is still published.

## 10. Security Considerations

- Brokers must require authentication (SASL/TLS, IAM) and be on a private network; an open broker is remote code execution through consumers.
- Treat message payloads as untrusted input: validate against a schema before use, and never `eval`/unpickle payloads.
- Do not put secrets or full PII in messages; reference records by ID and fetch with authorization.
- Per-consumer least privilege: separate credentials and topics per service; no wildcard consume permissions.
- DLQs hold raw payloads that failed validation — restrict access and set retention.
- Guard against message-injection attacks: sign or authenticate producers where the broker cannot, and validate the producer identity.
- Consumer deserialization of polymorphic types is a known exploit class (Java `ObjectInputStream`) — use explicit schema types.

## 11. Failure Handling

- **Messages lost:** producer published before commit, or auto-ack was enabled. Adopt the outbox and manual ack.
- **Infinite retry loop:** a permanently failing message is being requeued. Add attempt counting in the message header and route to DLQ after N.
- **Duplicates after rebalance:** processing exceeded the visibility timeout. Extend visibility or reduce work per message.
- **Consumer lag grows:** scale consumers, increase prefetch only if handlers are fast, or fix a slow downstream dependency.
- **Ordering violated:** multiple consumers per partition key, or a producer without a key. Key by aggregate ID and process per-key serially.
- **Outbox table bloat:** the relay is stopped or erroring; archive published rows after a retention window.
- **Schema change breaks consumers:** publish a new version and support both; never mutate an existing field's type.

## 12. Expected Deliverables

1. Topology diagram (exchanges/queues/topics, keys, consumers).
2. Event catalog with schemas and versions.
3. Outbox/relay implementation.
4. Idempotency strategy per consumer.
5. Retry, backoff, and DLQ policy.
6. Ordering guarantees and partition-key rules.
7. Monitoring, alerts, and replay runbook.

## 13. References

- RabbitMQ reliability guide — https://www.rabbitmq.com/docs/reliability
- RabbitMQ dead lettering — https://www.rabbitmq.com/docs/dlx
- Apache Kafka documentation — https://kafka.apache.org/documentation/
- AWS SQS visibility timeout & DLQs — https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html
- Transactional outbox pattern (microservices.io) — https://microservices.io/patterns/data/transactional-outbox.html
- Idempotent consumer pattern — https://microservices.io/patterns/communication-style/idempotent-consumer.html
- Celery task retries — https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying
