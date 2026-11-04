---
name: api-testing
description: Test HTTP and GraphQL APIs thoroughly—schema validation, status/error semantics, auth boundaries, pagination, idempotency, and property-based fuzzing.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: medium
---

# API Testing

## 1. Purpose

Verify an API's observable contract under both expected and adversarial input. API tests fail to catch real bugs when they only check `status == 200`, when they run against mocks rather than the real stack, and when nobody tests authorization boundaries. This skill covers schema-validated assertions, error semantics, auth matrices, pagination and idempotency verification, and property-based fuzzing driven by the OpenAPI document.

**Scope:** your own APIs and test environments. Security-oriented API testing must stay within systems you own or are authorized in writing to assess; never fuzz third-party endpoints.

## 2. Activation Conditions

- New or changed endpoints, request/response models, or error formats.
- Auth/authz changes, new roles, or tenant features.
- Client teams report contract mismatches.
- Preparing for a public API launch or version bump.
- Keywords: API testing, OpenAPI, JSON Schema, Schemathesis, Dredd, contract, status codes, problem details, authz matrix, pagination, idempotency, fuzz, property-based testing, GraphQL.

## 3. When Not to Use

- Browser-level journeys (use end-to-end-testing).
- Provider/consumer coupling between teams (use contract-testing).
- Load and capacity questions (use performance-and-load-testing).

## 4. Required Context

1. API specification (OpenAPI 3.1 / GraphQL SDL) and version.
2. Auth model: sessions, bearer tokens, scopes, roles, tenants.
3. Error format (problem+json or custom).
4. Data model for pagination, filtering, sorting.
5. Environments: ephemeral stack per run, tokens with limited scope.

## 5. Operating Procedure

1. **Drive tests from the spec where possible**: validate every response against the schema, and fuzz from the same document so coverage tracks the contract.
2. **Assert semantics, not just status**: `Location` on 201, `ETag` on reads, `Retry-After` on 429, `Allow` on 405, problem+json bodies on 4xx/5xx.
3. **Test the authorization matrix explicitly**: for each endpoint × role × ownership × tenant, assert allow/deny — and that denials do not leak data in the body or timing.
4. **Test validation boundaries**: missing fields, wrong types, extra fields, oversized arrays, unicode, and null vs. absent.
5. **Verify pagination stability**: insert rows between pages; cursors must not duplicate or skip.
6. **Verify idempotency**: same `Idempotency-Key` twice → identical response, one side effect; different body with the same key → 422.
7. **Verify concurrency control**: `If-Match` with a stale ETag → 412.
8. **Exercise rate limits and payload caps** and confirm the documented response shape.
9. **Cover the unhappy paths you actually support**: 404 vs. 403 semantics, 409 on conflict, 422 on semantic violations.
10. **Fuzz with sanitized data**: property-based tests must not create unbounded records; use a dedicated test tenant and clean up.
11. **Run the suite against the real stack** (real DB, real middleware) with only third parties faked.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| HTTP client | `httpx`, `requests`, supertest, `curl` |
| Schema validation | Schemathesis, `jsonschema`, OpenAPI response validators |
| Fuzzing | Hypothesis + HTTP strategies, Schemathesis stateful testing |
| GraphQL | `gql`, `graphql-core`, GraphQL Inspector |
| Auth matrix | pytest parametrization with token fixtures |
| Assertions | `jsonschema` + custom problem-details helpers |
| Reporting | JUnit XML, Allure |

## 7. Practical Implementation

**Fixture-based client with scoped tokens:**

```python
# tests/api/conftest.py
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.auth import issue_token

@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://api.test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
def token_for():
    def _make(*, user_id="u1", tenant="t1", roles=("viewer",)):
        return issue_token({"sub": user_id, "tenant_id": tenant, "roles": list(roles)}, ttl=300)
    return _make
```

**Schema-validated response assertion (no drift):**

```python
import jsonschema

ORDER_SCHEMA = {
    "type": "object",
    "required": ["id", "status", "total_cents", "currency", "links"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^ord_[a-z0-9]{8,}$"},
        "status": {"enum": ["draft", "placed", "paid", "shipped", "cancelled"]},
        "total_cents": {"type": "integer", "minimum": 0},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
        "links": {"type": "object", "required": ["self"]},
    },
}

async def test_get_order_matches_contract(client, token_for, persisted_order):
    r = await client.get(f"/v1/orders/{persisted_order.id}",
                         headers={"Authorization": f"Bearer {token_for()}"})
    assert r.status_code == 200
    jsonschema.validate(r.json(), ORDER_SCHEMA)
    assert r.headers["etag"].startswith('W/"')
```

**Assert full HTTP semantics:**

```python
async def test_create_order_sets_location_and_returns_201(client, token_for):
    r = await client.post("/v1/orders", headers={"Authorization": f"Bearer {token_for(roles=('buyer',))}"},
                          json={"lines": [{"product_id": 7, "quantity": 1}]})
    assert r.status_code == 201
    assert r.headers["location"] == f"/v1/orders/{r.json()['id']}"
    assert r.headers["content-type"].startswith("application/json")

async def test_unsupported_method_returns_allow_header(client, token_for):
    r = await client.delete("/v1/orders/ord_12345678",
                            headers={"Authorization": f"Bearer {token_for()}"})
    assert r.status_code in (405, 403)
    if r.status_code == 405:
        assert "GET" in r.headers.get("allow", "")
```

**Validation boundary matrix:**

```python
import pytest

@pytest.mark.parametrize(
    "body, expected_field",
    [
        ({}, "lines"),
        ({"lines": []}, "lines"),
        ({"lines": [{"product_id": "seven", "quantity": 1}]}, "lines.0.product_id"),
        ({"lines": [{"product_id": 7, "quantity": 0}]}, "lines.0.quantity"),
        ({"lines": [{"product_id": 7, "quantity": 1e9}]}, "lines.0.quantity"),
        ({"lines": [{"product_id": 7, "quantity": 1, "bogus": True}]}, "lines.0.bogus"),
    ],
)
async def test_create_order_rejects_invalid_body(client, token_for, body, expected_field):
    r = await client.post("/v1/orders", json=body,
                          headers={"Authorization": f"Bearer {token_for(roles=('buyer',))}"})
    assert r.status_code == 422
    assert r.headers["content-type"] == "application/problem+json"
    fields = [e["field"] for e in r.json()["errors"]]
    assert expected_field in fields, r.json()
```

**Authorization matrix (the test class that prevents breaches):**

```python
CASES = [
    # (role, tenant_of_resource, expected)
    ("viewer", "t1", 200),
    ("viewer", "t2", 404),       # cross-tenant must not disclose existence
    ("support", "t2", 404),
    ("admin", "t2", 200),
]

@pytest.mark.parametrize("role, resource_tenant, expected", CASES)
async def test_order_read_authorization(client, token_for, seed_order, role, resource_tenant, expected):
    token = token_for(roles=(role,), tenant="t1")
    order = seed_order(tenant_id=resource_tenant, owner_user_id="someone-else")
    r = await client.get(f"/v1/orders/{order.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == expected
    if expected != 200:
        assert "total_cents" not in r.text          # no partial leakage in error bodies
```

**Pagination stability under concurrent insertion:**

```python
async def test_cursor_pagination_does_not_duplicate_or_skip(client, token_for, seed_orders):
    seed_orders(count=30, tenant_id="t1")
    seen, cursor = [], None
    for _ in range(10):
        params = {"limit": 5, **({"cursor": cursor} if cursor else {})}
        r = await client.get("/v1/orders", params=params,
                             headers={"Authorization": f"Bearer {token_for()}"})
        body = r.json()
        seen.extend(o["id"] for o in body["data"])
        if not body["page"]["has_more"]:
            break
        cursor = body["page"]["next_cursor"]
        seed_orders(count=3, tenant_id="t1")      # insert between pages

    assert len(seen) == len(set(seen)), "duplicate rows across pages"
```

**Idempotency and concurrency semantics:**

```python
async def test_idempotent_replay_returns_original_response(client, token_for, persisted_order):
    headers = {"Authorization": f"Bearer {token_for(roles=('buyer',))}",
               "Idempotency-Key": "idem-0001-abcdef"}
    first = await client.post(f"/v1/orders/{persisted_order.id}/refunds", json={"amount_cents": 500},
                              headers=headers)
    second = await client.post(f"/v1/orders/{persisted_order.id}/refunds", json={"amount_cents": 500},
                               headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]        # same refund, not a second one

async def test_stale_etag_returns_412(client, token_for, persisted_order):
    r = await client.patch(f"/v1/orders/{persisted_order.id}", json={"note": "hi"},
                           headers={"Authorization": f"Bearer {token_for(roles=('buyer',))}",
                                    "If-Match": 'W/"1"'})
    assert r.status_code == 412
```

**Property-based fuzzing from the OpenAPI document:**

```bash
schemathesis run https://staging.example.com/openapi.json \
  --checks all \
  --hypothesis-max-examples=40 \
  --header "Authorization: Bearer $TEST_TOKEN" \
  --exclude-tag=admin \
  --stateful=links
```

```python
# Programmatic, with allowlisted stateful operations only
import schemathesis
from hypothesis import settings, HealthCheck

schema = schemathesis.from_uri("https://staging.example.com/openapi.json",
                               headers={"Authorization": f"Bearer {TOKEN}"})

@schema.parametrize(endpoint="/v1/orders", method="POST")
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_orders_post_never_5xx(case):
    case.headers = {"Authorization": f"Bearer {TOKEN}"}
    response = case.call()
    case.validate_response(response)          # schema conformance
    assert response.status_code < 500, response.text
```

**GraphQL API test with operation and limits:**

```python
async def test_refund_mutation_returns_user_errors_instead_of_500(gql_client, token_for):
    mutation = """
      mutation($in: RefundInput!) {
        refund(input: $in) { refund { id } errors { field code message } }
      }
    """
    r = await gql_client.post("/graphql", json={
        "query": mutation,
        "variables": {"in": {"orderId": "ord_test", "amountCents": 0, "reason": "test"}},
    }, headers={"Authorization": f"Bearer {token_for(roles=('support',))}"})

    assert r.status_code == 200
    body = r.json()
    assert "errors" not in body                      # no transport-level GraphQL error
    assert body["data"]["refund"]["refund"] is None
    assert body["data"]["refund"]["errors"][0]["code"] == "INVALID_AMOUNT"
```

**Rate-limit and payload-cap behavior:**

```python
async def test_large_payload_rejected(client, token_for):
    body = {"note": "x" * (2 * 1024 * 1024)}
    r = await client.patch("/v1/orders/ord_12345678", json=body,
                           headers={"Authorization": f"Bearer {token_for()}"})
    assert r.status_code in (413, 422)

async def test_rate_limit_returns_retry_after(client, token_for):
    headers = {"Authorization": f"Bearer {token_for()}"}
    responses = [await client.get("/v1/orders", headers=headers) for _ in range(120)]
    limited = [r for r in responses if r.status_code == 429]
    if limited:
        assert "retry-after" in limited[0].headers
```

## 8. Quality Standards

- Every response is schema-validated; `additionalProperties: false` where the contract is closed.
- Status codes, headers, and error bodies are asserted, not only the JSON payload.
- The authorization matrix covers role × ownership × tenant for every resource.
- Denials return no partial data and consistent shapes.
- Pagination, filtering, and sorting are tested under concurrent writes.
- Idempotency and optimistic concurrency have explicit replay and stale-ETag tests.
- Fuzzing runs in CI with bounded examples and a dedicated test tenant.
- Tests hit the real middleware stack with only third parties faked.

## 9. Verification and Testing

- Point oasdiff/graphql-inspector at the spec in CI to catch breaking changes (belt and braces with contract tests).
- Run the fuzz suite nightly; any 5xx is a bug (or a spec violation to fix).
- Verify that a deliberate auth regression (remove a `tenant_id` filter) makes the matrix test fail.
- Confirm the suite works against a fresh database (no hidden seed dependency).
- Measure API suite runtime; keep under 5 minutes in parallel.

## 10. Security Considerations

- Only test APIs you own or have written authorization to assess; fuzzing third-party endpoints is not permitted.
- Keep fuzzing away from destructive endpoints (DELETE, admin) or use an allowlist; a stateful fuzzer can delete real data.
- Use tokens scoped to a test tenant and short TTLs; never use production user tokens.
- Assert that error responses never include stack traces, SQL, internal hostnames, or other users' identifiers.
- Include negative tests for mass assignment (attempting to set `tenant_id`, `role`, `status`) and confirm rejection.
- Test that authentication failure paths don't reveal whether an account exists.
- Clean up fuzz-created data; unbounded creation can exhaust quotas or storage.

## 11. Failure Handling

- **Tests pass against mocks but fail in production:** the mock drifted — run against the real stack and add contract verification.
- **Fuzzer finds 5xx from a null field:** the schema said optional but the handler assumed presence; fix the handler and tighten the schema.
- **Idempotency test flakes:** concurrent requests race on the key (unique constraint not enforced); add the DB constraint and retry logic.
- **Pagination test fails after a release:** cursor encodes a field that changed format; version the cursor and handle legacy values.
- **Auth matrix too large to maintain:** generate the matrix from the permission catalog rather than hand-writing every combination.

## 12. Expected Deliverables

1. API test suite organized by resource.
2. JSON Schema/property assertions per response model.
3. Authorization matrix tests.
4. Error-semantics tests (problem+json).
5. Pagination/idempotency/concurrency tests.
6. Fuzz configuration and allowlist.
7. Spec-diff gate in CI.

## 13. References

- Schemathesis — https://schemathesis.readthedocs.io/
- OpenAPI 3.1 specification — https://spec.openapis.org/oas/v3.1.0.html
- RFC 9457 Problem Details — https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 HTTP Semantics — https://www.rfc-editor.org/rfc/rfc9110
- JSON Schema — https://json-schema.org/specification
- httpx — https://www.python-httpx.org/
- OWASP API Security Top 10 — https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- GraphQL Testing — https://graphql.org/learn/testing/
