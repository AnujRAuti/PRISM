---
name: contract-testing
description: Verify service boundaries with consumer-driven contracts and schema checks—Pact flows, provider verification, breaking-change detection, and API compatibility gates.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Contract Testing

## 1. Purpose

Catch integration breakage without running every service together. Contract tests pin the exact shape a consumer needs from a provider, and verify the provider still satisfies it. This skill covers choosing between consumer-driven contracts (Pact) and schema-based checks (OpenAPI/GraphQL/Protobuf diffing), writing meaningful interactions, running the broker pact verification flow, and gating incompatible changes in CI.

**Scope:** your own services and their published specifications. Provider verification must run against a controlled test instance of the provider, never production.

## 2. Activation Conditions

- Multiple services or teams with a shared API.
- Integrating with a third-party API whose payloads change.
- A provider change broke a consumer in production.
- Mobile clients that cannot deploy in lockstep with the backend.
- Keywords: contract testing, Pact, consumer-driven contract, pact broker, provider verification, schema diff, breaking change, OpenAPI, GraphQL schema, Protobuf, compatibility.

## 3. When Not to Use

- A single deployable with internal function calls (use integration-testing).
- Full user journeys across a real UI (use end-to-end-testing).
- Providers with no stable contract at all (fix the API first).

## 4. Required Context

1. Consumer/provider pairs and who owns each.
2. Contract artifact type: OpenAPI, GraphQL SDL, Protobuf, or a message schema.
3. Broker availability (Pact Broker, PactFlow, or a registry).
4. Deployment coupling: can the consumer be updated first?
5. Compatibility policy: what counts as breaking for each consumer.

## 5. Operating Procedure

1. **Choose the approach**:
   - Consumer-driven (Pact) when multiple consumers need different subsets and the provider must not break any of them.
   - Provider schema diff (OpenAPI/GraphQL) when a single published spec governs the contract and consumers generate clients from it.
   - Message contracts for queues (Pact messages or schema registry compatibility checks).
2. **Write interactions from the consumer's perspective**: exactly the fields the client reads, with realistic matchers (types and formats), not brittle literals everywhere.
3. **Include failure interactions** the consumer depends on (404 shape, 422 error body) — errors are part of the contract.
4. **Publish pacts to a broker** with version tags (`main`, `prod`, feature branches) and record the consumer version.
5. **Verify the provider in CI** by fetching pacts for the deployed consumer versions and replaying them against a test instance.
6. **Gate on `can-i-deploy`**: a consumer may only deploy if the provider version it targets satisfies all its pacts.
7. **For schema-based APIs, diff in CI** and fail on incompatible changes; classify each change explicitly.
8. **Keep contracts small and consumer-specific**; a contract is not an exhaustive API test.
9. **Retire pacts** when a consumer version is decommissioned, so providers are not pinned to dead clients.
10. **Monitor contract drift**: alert when a provider has no verification for a newly deployed consumer.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Consumer-driven | Pact (pact-python, Pact JS, Pact JVM), PactFlow |
| Broker | Pact Broker, PactFlow, self-hosted |
| OpenAPI diff | `openapi-diff`, `oasdiff`, `graphql-inspector` |
| Protobuf | `buf breaking` |
| JSON Schema | `ajv` compatibility checks, schema registry (`Confluent`) |
| Mock server from pact | `pact-mock-service`, provider states |
| CI gates | `pact-broker can-i-deploy`, `buf breaking --against` |

## 7. Practical Implementation

**Consumer test producing a pact (Python):**

```python
# tests/contract/test_order_client.py
import pytest
from pact import Consumer, Provider

pact = Consumer("checkout-web").has_pact_with(Provider("orders-api"), pact_dir="./pacts")

@pytest.fixture(scope="module")
def orders_pact():
    pact.start_service()
    yield pact
    pact.stop_service()

def test_get_order_returns_status_and_total(orders_pact):
    (orders_pact
     .given("order ord_1 exists and is paid")
     .upon_receiving("a request for order ord_1")
     .with_request("get", "/v1/orders/ord_1")
     .will_respond_with(200, body={
         "id": "ord_1",
         "status": "paid",
         "total_cents": 4200,               # only the fields the consumer reads
         "currency": "INR",
     }))
    orders_pact.setup()

    from app.clients.orders import OrdersClient
    order = OrdersClient(base_url=pact.uri).get("ord_1")

    assert order.status == "paid"
    assert order.total_cents == 4200
```

**Consumer test using matchers (stable against value changes):**

```python
from pact import Like, Term, Format

.will_respond_with(200, body={
    "id": Like("ord_1"),
    "status": Term(r"draft|placed|paid|shipped|cancelled", "paid"),
    "created_at": Format().iso_8601_datetime,
    "links": {"self": Term(r"^/v1/orders/[\w-]+$", "/v1/orders/ord_1")},
})
```

**Contract for an error the consumer handles:**

```python
def test_get_missing_order_returns_problem_details(orders_pact):
    (orders_pact
     .given("order ord_missing does not exist")
     .upon_receiving("a request for a missing order")
     .with_request("get", "/v1/orders/ord_missing")
     .will_respond_with(404, headers={"Content-Type": "application/problem+json"}, body={
         "type": Like("https://api.example.com/problems/not-found"),
         "title": Like("Not found"),
         "status": 404,
     }))
    orders_pact.setup()
    with pytest.raises(OrderNotFound):
        OrdersClient(base_url=pact.uri).get("ord_missing")
```

**Provider verification against a running app with provider states:**

```python
# tests/contract/test_provider.py
import pytest
from pact import Verifier

@pytest.mark.contract
def test_orders_api_honors_pacts(postgres, migrated_url, live_server):
    verifier = (Verifier("orders-api", url=live_server.url)
                .add_transport(url=live_server.url)
                .state_handler("order ord_1 exists and is paid",
                               lambda: seed_order("ord_1", status="paid", total_cents=4200))
                .state_handler("order ord_missing does not exist", lambda: None))

    verifier.verify_with_broker(
        broker_url=BROKER_URL,
        broker_token=BROKER_TOKEN,
        provider_base_url="https://orders-api.internal",
        provider_version=GIT_SHA,
        provider_version_branch=GIT_BRANCH,
        publish_verification_results=True,
    )
```

**CI gate before deploying:**

```bash
# consumer side
pact-broker publish ./pacts \
  --consumer-app-version="$GIT_SHA" \
  --branch="$GIT_BRANCH" \
  --broker-base-url="$PACT_BROKER_URL" --broker-token="$PACT_BROKER_TOKEN"

# may this consumer version go to production?
pact-broker can-i-deploy \
  --pacticipant checkout-web --version "$GIT_SHA" \
  --to-environment production \
  --broker-base-url="$PACT_BROKER_URL" --broker-token="$PACT_BROKER_TOKEN"
```

**OpenAPI breaking-change gate (schema-based alternative):**

```bash
npx oasdiff breaking openapi-main.json openapi-pr.json --fail-on ERR
# or
npx openapi-diff openapi-main.json openapi-pr.json --fail-on-incompatible
```

```yaml
# classify changes deliberately in review
# Breaking:      removing a field, narrowing a type, making an optional field required,
#                changing a status code, removing an enum value
# Compatible:    adding an optional response field, adding a new endpoint,
#                adding a new enum value IF consumers tolerate unknown values
```

**GraphQL schema compatibility:**

```bash
npx graphql-inspector diff schema.graphql schema-pr.graphql --rule suppressRemovalOfDeprecatedField
```

**Protobuf breaking-change check:**

```bash
buf breaking --against '.git#branch=main'
```

Field rules that proto enforces: never reuse a field number, never change a type, reserve removed numbers and names:

```proto
message Order {
  reserved 4, 7 to 9;
  reserved "old_status";
  string id = 1;
  int64 total_cents = 2;
  string currency = 3;
  // 5: status enum added later
}
```

## 8. Quality Standards

- Contracts capture only what the consumer reads; no exhaustive schema duplication.
- Matchers express type/format constraints rather than brittle literals, except where a specific value is the requirement.
- Error and edge-case interactions are covered (404, 422, empty lists, pagination links).
- Provider states are explicit, deterministic, and independent from each other.
- Verification publishes results and is required before deploy (`can-i-deploy` gate).
- Schema-based APIs fail CI on incompatible changes with a documented classification.
- Decommissioned consumer versions are removed from the broker.
- Contracts are versioned with the consumer that produced them.

## 9. Verification and Testing

- Deliberately break the provider (rename `total_cents` to `total`) and confirm provider verification fails.
- Verify the gate blocks a consumer deployment when the provider was not verified against the latest pact.
- Run provider verification against a fresh database with only the declared state handlers.
- Check that contract tests catch a status-code change (200 → 201).
- Confirm pact publication includes the branch and version metadata, so `can-i-deploy` is meaningful.

## 10. Security Considerations

- Broker tokens and credentials are secrets: inject from CI secret stores and never write them into pact files.
- Contract test data must be synthetic; no real customer identifiers or PII in pacts published to a shared broker.
- Provider states can seed databases—ensure they run only against ephemeral test instances.
- Pact files reveal internal endpoints and payload shapes; restrict broker access to the organization.
- Third-party API contracts may be subject to licensing; do not publish vendor payloads outside your org.

## 11. Failure Handling

- **Provider verification fails only in CI:** the verification environment differs (missing migration, config). Use the same container image as integration tests.
- **Pact and reality diverge for optional fields:** the consumer reads a field the provider only sends sometimes; make it explicit in the contract or handle absence in the consumer.
- **Too many brittle pacts:** literals in every field. Switch to matchers and only pin fields whose exact value is a requirement.
- **Broker unavailable during deploy:** fail closed on the gate, or use a documented manual override with an audit entry.
- **Provider pinned to dead consumers:** tag-based selection (`--to-environment`) plus removing stale versions.
- **Schema diff floods:** configure the tool to ignore description/example changes and fail only on structural incompatibility.

## 12. Expected Deliverables

1. Consumer/provider inventory and contract ownership.
2. Pact or schema artifacts with matcher conventions.
3. Provider state handlers.
4. Broker tagging and versioning strategy.
5. CI verification and deployment gates.
6. Breaking-change classification for schema-based APIs.
7. Contract retirement process.

## 13. References

- Pact documentation — https://docs.pact.io/
- Pact Broker `can-i-deploy` — https://docs.pact.io/pact_broker/can_i_deploy
- Pact consumer-driven contract testing guide — https://docs.pact.io/getting_started/how_pact_works
- OpenAPI Specification 3.1 — https://spec.openapis.org/oas/v3.1.0.html
- oasdiff — https://github.com/oasdiff/oasdiff
- openapi-diff — https://github.com/OpenAPITools/openapi-diff
- graphql-inspector — https://the-guild.dev/graphql/inspector
- buf breaking change detection — https://buf.build/docs/breaking/
- JSON Schema — https://json-schema.org/specification
