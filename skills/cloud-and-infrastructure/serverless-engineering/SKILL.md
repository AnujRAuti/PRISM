---
name: serverless-engineering
description: Build serverless systems that scale and stay cheap—cold-start control, idempotent event handling, concurrency limits, timeouts, and observability per invocation.
metadata:
  domain: cloud-and-infrastructure
  version: 1.0.0
  risk: medium
---

# Serverless Engineering

## 1. Purpose

Design functions and managed event pipelines that behave predictably under load, retry, and failure. Serverless shifts problems rather than removing them: cold starts replace warm-up tuning, at-least-once event delivery replaces client retries, concurrency limits replace thread pools, and per-invocation cost replaces fixed capacity. This skill covers function design, event source semantics, idempotency, timeout and memory sizing, cold-start mitigation, and cost-aware observability.

**Scope:** functions and event infrastructure you own. Serverless permissions are often broad because functions call many services: scope each function's role, and never let an event payload drive privilege or target selection.

## 2. Activation Conditions

- Moving spiky or event-driven work to functions (API handlers, queues, cron, webhooks).
- Functions timing out, throttling, or costing more than expected.
- Duplicate processing after retries.
- Cold starts hurting p99 latency.
- Keywords: Lambda, Cloud Functions, Azure Functions, cold start, provisioned concurrency, event source mapping, SQS trigger, idempotency, timeout, memory, concurrency, Step Functions, Durable Functions, serverless.

## 3. When Not to Use

- Steady high-throughput workloads where containers are cheaper and simpler.
- Long-running jobs beyond platform limits (use containers or a workflow engine).
- Stateful services with persistent connections (databases with connection limits).

## 4. Required Context

1. Platform and runtime (Lambda + API Gateway, Cloud Run, Functions).
2. Invocation model: synchronous HTTP, async queue, schedule, stream.
3. Traffic shape: peak concurrency, burstiness, payload sizes.
4. Downstream limits: database connections, third-party rate limits.
5. Latency SLOs, especially at p99.

## 5. Operating Procedure

1. **Choose the invocation model deliberately**: synchronous for user-facing APIs with tight latency, async queue for work that can retry, streams for ordered batches, schedules for cron.
2. **Make every handler idempotent**: async retries and at-least-once delivery will duplicate. Key on the event ID in a durable store within the same transaction as the side effect.
3. **Size memory by measurement**, not by default: memory also scales CPU on most platforms; pick the smallest size that meets the latency target and record the cost.
4. **Set timeouts from the dependency chain**: handler timeout below the caller's timeout, downstream client timeouts below the handler's, and a retry budget that fits inside the queue visibility timeout.
5. **Control concurrency**: reserved/provisioned concurrency for critical paths, queue max-concurrency to protect databases and third parties, and a dead-letter queue for exhausted retries.
6. **Mitigate cold starts**: keep the package small, initialize SDK clients outside the handler, prefer runtimes with fast init, use provisioned concurrency for latency-critical endpoints, and avoid VPC attachments unless required (or use VPC endpoints with adequate ENI capacity).
7. **Never open connections per invocation blindly**: use a pooler (RDS Proxy/PgBouncer) or HTTP-based data APIs; scale concurrency against database connection limits.
8. **Emit structured logs with request/event IDs and no PII**, plus metrics and traces (use AWS X-Ray/OpenTelemetry or platform equivalents).
9. **Version and alias functions**; deploy by alias with weighted traffic for canaries and instant rollback.
10. **Bound payloads and validate schemas** at the edge before invoking.
11. **Cost model per month** at expected invocations, GB-seconds, and egress; revisit when traffic triples.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Frameworks | AWS SAM, Serverless Framework, AWS CDK, Terraform, SST |
| Local dev | SAM CLI (`sam local`), LocalStack, Docker-based emulation |
| Orchestration | Step Functions, Durable Functions, Temporal |
| Data access | RDS Proxy, DynamoDB, Aurora Serverless v2, HTTP data APIs |
| Observability | CloudWatch metrics/logs, X-Ray, OpenTelemetry, Lumigo/Dashbird |
| Testing | pytest with moto, contract tests, load tests against deployed stages |
| Cost analysis | AWS Cost Explorer, Lambda Power Tuning |

## 7. Practical Implementation

**SAM template with concurrency, DLQ, and timeout discipline:**

```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31

Globals:
  Function:
    Runtime: python3.12
    Architectures: [arm64]
    MemorySize: 1024
    Timeout: 10                     # handler; caller timeout must be higher
    Tracing: Active
    Environment:
      Variables:
        LOG_LEVEL: INFO
        TABLE_NAME: !Ref ProcessedEvents
        POWERTOOLS_SERVICE_NAME: orders-worker

Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 60          # > handler timeout × retry attempts
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDLQ.Arn
        maxReceiveCount: 5

  OrdersDLQ:
    Type: AWS::SQS::Queue
    Properties: {MessageRetentionPeriod: 1209600}

  OrdersFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: handler.process
      Policies:
        - DynamoDBCrudPolicy: {TableName: !Ref ProcessedEvents}
        - SQSPollerPolicy: {QueueName: !GetAtt OrdersQueue.QueueName}
      Events:
        Queue:
          Type: SQS
          Properties:
            Queue: !GetAtt OrdersQueue.Arn
            BatchSize: 10
            MaximumBatchingWindowInSeconds: 5
            FunctionResponseTypes: [ReportBatchItemFailures]   # partial batch success

  ProcessedEvents:
    Type: AWS::DynamoDB::Table
    Properties:
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions: [{AttributeName: event_id, AttributeType: S}]
      KeySchema: [{AttributeName: event_id, KeyType: HASH}]
      TimeToLiveSpecification: {AttributeName: expires_at, Enabled: true}
```

**Idempotent handler with partial batch failure reporting:**

```python
import json, logging, os, time
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.getenv("LOG_LEVEL", "INFO"))

_table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])   # init outside handler
_ttl_seconds = 7 * 24 * 3600

def _claim(event_id: str) -> bool:
    """Atomically claim an event id. False means already processed."""
    try:
        _table.put_item(
            Item={"event_id": event_id, "expires_at": int(time.time()) + _ttl_seconds},
            ConditionExpression="attribute_not_exists(event_id)",
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise

def process(record: dict) -> None:
    body = json.loads(record["body"])
    # side effect here; for money/entitlements re-fetch authoritative state first
    log.info(json.dumps({"event": "order.processed", "event_id": body["id"],
                         "order_id": body.get("order_id")}))

def handler(event, context):
    failures = []
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            event_id = body.get("id") or record["messageId"]
            if not _claim(event_id):
                log.info(json.dumps({"event": "event.duplicate", "event_id": event_id}))
                continue
            process(record)
        except Exception as exc:
            log.exception(json.dumps({"event": "event.failed",
                                      "message_id": record.get("messageId")}))
            failures.append({"itemIdentifier": record["messageId"]})

    # Only failed messages are retried; the rest are acknowledged
    return {"batchItemFailures": failures}
```

**HTTP handler with strict validation and bounded downstream calls:**

```python
import json, os
import httpx
from pydantic import BaseModel, Field, ValidationError

class OrderIn(BaseModel):
    customer_id: int = Field(ge=1)
    lines: list[dict] = Field(min_length=1, max_length=100)

def lambda_handler(event, context):
    try:
        payload = OrderIn.model_validate(json.loads(event.get("body") or "{}"))
    except ValidationError as exc:
        return {"statusCode": 422,
                "headers": {"Content-Type": "application/problem+json"},
                "body": json.dumps({"type": "/problems/validation", "status": 422,
                                    "detail": f"{exc.error_count()} field(s) invalid"})}

    with httpx.Client(base_url=os.environ["ORDERS_API"], timeout=4.0) as client:
        resp = client.post("/v1/orders", json=payload.model_dump(),
                           headers={"Idempotency-Key": context.aws_request_id})
    return {"statusCode": resp.status_code,
            "headers": {"Content-Type": "application/json"},
            "body": resp.text}
```

**Concurrency and throttling controls:**

```yaml
# Protect the database: cap how many concurrent invocations can run
OrdersFunction:
  Type: AWS::Serverless::Function
  Properties:
    ReservedConcurrentExecutions: 20        # hard cap for this function
    ProvisionedConcurrentExecutions: 5      # via alias for latency-critical endpoint
```

```hcl
# Terraform: event source max concurrency on the SQS mapping
resource "aws_lambda_event_source_mapping" "orders" {
  event_source_arn                   = aws_sqs_queue.orders.arn
  function_name                      = aws_lambda_function.orders.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
  scaling_config {
    maximum_concurrency = 20               # backpressure instead of DB exhaustion
  }
}
```

**Least-privilege function role (no wildcards):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["dynamodb:PutItem"], "Resource": "arn:aws:dynamodb:ap-south-1:111122223333:table/ProcessedEvents"},
    {"Effect": "Allow", "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
     "Resource": "arn:aws:sqs:ap-south-1:111122223333:orders-queue"},
    {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
     "Resource": "arn:aws:logs:ap-south-1:111122223333:log-group:/aws/lambda/orders-worker:*"}
  ]
}
```

**Deployment with alias and canary, plus rollback:**

```bash
sam deploy --stack-name orders-worker \
  --parameter-overrides Stage=prod \
  --capabilities CAPABILITY_IAM --no-confirm-changeset

# Weighted alias shift (10% for 10 minutes), roll back on any error alarm
aws lambda update-alias --function-name orders-worker --name live \
  --function-version 42 --routing-config AdditionalVersionWeights={"41"=0.1}
aws lambda update-alias --function-name orders-worker --name live \
  --function-version 42 --routing-config '{}'          # full cutover after verification
```

**Cold-start and cost measurement (don't guess):**

```bash
# Power tuning: measure duration and cost across memory sizes
npx serverless-plugin-aws-alerts 2>/dev/null || true
# Or read CloudWatch for p99 Init Duration and Duration by memory size:
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda --metric-name InitDuration \
  --dimensions Name=FunctionName,Value=orders-worker \
  --start-time "$(date -u -d '-1 hour' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
  --period 300 --statistics p99
```

```text
Example conclusion: at 1024 MB, p99 init = 210 ms and mean duration = 95 ms
(₹0.0000213/invocation); at 512 MB, init = 480 ms, duration 160 ms — cheaper but
breaches the 300 ms p99 target for the API path. Use 1024 MB for API, 512 MB for the queue worker.
```

## 8. Quality Standards

- Every async handler is idempotent with a durable dedupe key.
- Timeouts form a descending chain: CDN/gateway > function > downstream client; queue visibility > function timeout × attempts.
- Concurrency is capped where a downstream dependency has limits.
- Dead-letter queues exist for every async source, with an alarm on depth.
- Function roles are scoped to specific resources; no `*` actions or resources.
- Structured logs include request/event IDs and exclude secrets and PII.
- Images/packages are minimal; SDK clients initialized outside the handler.
- Memory is chosen from measurement with cost recorded.
- Deploys use versions + aliases with canary and rollback.
- Cost per 1,000 invocations is known and tracked.

## 9. Verification and Testing

- Duplicate-delivery test: invoke the same message twice; one side effect.
- Partial batch test: one bad record in a batch of 10 leaves the other 9 acknowledged.
- Timeout test: force a slow downstream; confirm the handler returns an error before the platform timeout and the message is retried/DLQ'd.
- Throttle test: burst above reserved concurrency; confirm backpressure rather than database exhaustion.
- Cold-start measurement: p99 `InitDuration` per memory size before shipping a latency SLO.
- Role test: `aws iam simulate-principal-policy` for expected allow and deny paths.
- Load test the deployed stage (not local emulation) with realistic payloads.

## 10. Security Considerations

- Event payloads are untrusted input: validate against a schema, never use fields to select credentials, buckets, or database names.
- Function roles are the blast radius; separate functions by privilege (a read-only webhook parser should not be able to write to billing).
- Never log the whole event: payloads often contain tokens, PII, or full request bodies.
- Secrets belong in a secret manager with rotation; environment variables are visible to anyone with `lambda:GetFunctionConfiguration`.
- Public function URLs need auth (IAM, JWT authorizer) plus rate limiting; an open URL is an open wallet.
- Supply chain: pin dependency versions, scan the package, and sign artifacts where supported.
- VPC-attached functions must restrict egress (security groups + NAT) so a compromised function cannot reach the internet freely.

## 11. Failure Handling

- **Timeouts under load:** downstream is slow or concurrency is unbounded — check p99 by dependency, add timeouts and concurrency caps.
- **Duplicate work after retries:** the dedupe write is not transactional with the side effect, or the key is per-attempt rather than per-event.
- **Throttles (`429`/`TooManyRequestsException`):** account-level concurrency exhausted by another function; set reserved concurrency and alarm on `Throttles`.
- **Database connection exhaustion:** functions × concurrency exceeds connection limit; introduce a pooler and cap concurrency.
- **Cold starts on the critical path:** add provisioned concurrency, shrink the deployment package, or move the endpoint to a container service.
- **DLQ filling:** inspect a sample, fix the cause, then redrive deliberately (never bulk redrive into a still-broken handler).

## 12. Expected Deliverables

1. Function inventory with invocation model, timeout, memory, and concurrency.
2. Idempotency implementation and dedupe store.
3. Queue/topic topology with DLQs and alarms.
4. Timeout and retry chain documented end to end.
5. Least-privilege roles per function.
6. Observability (structured logs, metrics, traces, dashboards).
7. Cost model and cold-start measurements.
8. Deployment strategy with aliases, canary, and rollback.

## 13. References

- AWS Lambda developer guide — https://docs.aws.amazon.com/lambda/latest/dg/welcome.html
- Lambda quotas and concurrency — https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html
- SQS event source with partial batch responses — https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-batch.html
- AWS SAM specification — https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-specification.html
- AWS Lambda Power Tuning — https://github.com/alexcasalboni/aws-lambda-power-tuning
- Google Cloud Run documentation — https://cloud.google.com/run/docs
- Azure Functions documentation — https://learn.microsoft.com/azure/azure-functions/
- AWS X-Ray — https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html
