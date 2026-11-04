---
name: api-design
description: Design HTTP and event APIs that are consistent, versioned, paginated, idempotent, and safe—with machine-readable contracts and evolutions that do not break clients.
metadata:
  domain: software-engineering
  version: 1.0.0
  risk: medium
---

# API Design

## 1. Purpose

Produce an API contract that clients can integrate against without guesswork, and evolve it without breaking them. This skill covers resource modeling, URL and method semantics, status codes, error formats, pagination, filtering, idempotency, versioning, rate limiting, and contract-first workflows (OpenAPI). It solves the recurring problems of inconsistent responses, ambiguous errors, unbounded lists, and breaking changes discovered only when clients fail.

## 2. Activation Conditions

- Designing a new public, partner, or internal service API.
- Adding endpoints or fields to an existing API.
- Inconsistencies reported by client teams ("some endpoints return arrays, others return `{data: ...}`").
- Before implementing a gateway/BFF or SDK generation.
- Keywords: API design, REST, endpoint, OpenAPI, pagination, versioning, idempotency, error contract, backward compatible.

## 3. When Not to Use

- Internal function-level interfaces (that is code design).
- Pure gRPC/protobuf work where the schema language already enforces the contract (adapt principles, not syntax).
- When an approved API style guide exists; follow it and only report deviations.
- Event-only systems—use AsyncAPI and the messaging parts of this skill.

## 4. Required Context

1. Consumers (web, mobile, partner, internal services) and their constraints (mobile clients lag upgrades by months).
2. Existing API conventions in the organization (style guide, error envelope, auth scheme).
3. Auth model: OAuth2 scopes, API keys, mTLS, session cookies.
4. Scale: expected RPS, payload sizes, list sizes.
5. Domain model and ownership rules.
6. Compatibility policy: how long clients must be supported.

## 5. Operating Procedure

1. **Model resources, not actions.** Nouns with stable IDs. Use verbs only for genuine non-CRUD operations (`POST /payments/{id}/capture`).
2. **Assign URLs** with plural nouns, kebab-case path segments, no verbs in paths, nesting ≤ 2 levels.
3. **Map methods to semantics**: GET safe and idempotent, PUT idempotent replace, PATCH partial update, POST create/action, DELETE idempotent.
4. **Define the response envelope** once and use it everywhere. Include a stable resource `id`, timestamps in RFC 3339 UTC, and money as integer minor units with `currency`.
5. **Specify errors** with a single schema: `type`, `title`, `status`, `detail`, `instance`, plus `errors[]` for field validation. Use RFC 9457 problem details.
6. **Paginate every collection** with cursor-based pagination (`?limit=&cursor=`); return `next_cursor`. Never return unbounded lists.
7. **Define filtering and sorting** with an allowlist of fields. Reject unknown sort fields with 400.
8. **Make retries safe:** accept `Idempotency-Key` on POST for money-moving operations; store key → response for ≥ 24 h.
9. **Decide versioning** up front: URL major version (`/v1`) is simplest and most visible; additive changes do not bump the version.
10. **Specify rate limits** and return `429` with `Retry-After` and `RateLimit-*` headers.
11. **Write the OpenAPI 3.1 document first**, lint it, generate/validate server stubs.
12. **Publish examples**: request/response for success and each error class.
13. **Define the deprecation policy**: `Deprecation`/`Sunset` headers, minimum notice period, and migration guide.

## 6. Tools and Technologies

| Tool | Use |
|---|---|
| OpenAPI 3.1 + `openapi-spec-validator` | Contract definition and validation |
| Redocly CLI / Spectral | Linting and style rules |
| `openapi-generator`, `orval` | Client/SDK generation |
| FastAPI / NestJS / SpringDoc | Server-side contract generation |
| Prism / Mockoon | Contract-first mocking |
| Schemathesis | Property-based API conformance testing |
| RFC 9457 problem details | Standard error format |
| AsyncAPI | Event contracts |

## 7. Practical Implementation

**OpenAPI fragment with list, error, and idempotency:**

```yaml
paths:
  /v1/orders:
    get:
      operationId: listOrders
      parameters:
        - {name: limit, in: query, schema: {type: integer, minimum: 1, maximum: 100, default: 20}}
        - {name: cursor, in: query, schema: {type: string}}
        - {name: status, in: query, schema: {type: string, enum: [pending, paid, shipped]}}
      responses:
        "200":
          description: A page of orders
          content:
            application/json:
              schema:
                type: object
                required: [data, next_cursor]
                properties:
                  data: {type: array, items: {$ref: '#/components/schemas/Order'}}
                  next_cursor: {type: [string, "null"]}
        "400": {$ref: '#/components/responses/Problem'}
    post:
      operationId: createOrder
      parameters:
        - {name: Idempotency-Key, in: header, required: true, schema: {type: string, minLength: 8}}
      requestBody:
        required: true
        content: {application/json: {schema: {$ref: '#/components/schemas/OrderCreate'}}}
      responses:
        "201": {description: Created}
        "409": {description: Idempotency key reused with a different body}
components:
  responses:
    Problem:
      description: RFC 9457 problem details
      content:
        application/problem+json:
          schema:
            type: object
            required: [type, title, status]
            properties:
              type: {type: string, format: uri}
              title: {type: string}
              status: {type: integer}
              detail: {type: string}
              instance: {type: string}
              errors:
                type: array
                items:
                  type: object
                  properties:
                    field: {type: string}
                    message: {type: string}
```

**Consistent error body:**

```json
{
  "type": "https://api.example.com/problems/insufficient-stock",
  "title": "Insufficient stock",
  "status": 409,
  "detail": "Item SKU-991 has 2 units, 5 requested.",
  "instance": "/v1/orders/9f1c",
  "errors": [{"field": "items[0].quantity", "message": "exceeds available stock"}]
}
```

**Cursor pagination in SQL (opaque cursor, stable ordering):**

```sql
SELECT id, created_at
FROM orders
WHERE tenant_id = $1
  AND (created_at, id) < ($2::timestamptz, $3::uuid)  -- cursor decode
ORDER BY created_at DESC, id DESC
LIMIT $4;
```

**Spectral rule for path naming:**

```yaml
rules:
  path-kebab-case:
    given: $.paths
    severity: warn
    then:
      field: "@key"
      function: pattern
      functionOptions:
        match: "^/(v[0-9]+/)?([a-z0-9{}-]+)(/[a-z0-9{}-]+)*$"
```

## 8. Quality Standards

- Consistent resource naming and envelope across all endpoints.
- Every collection is paginated with a bounded `limit`.
- Every error uses the same schema and never leaks stack traces.
- Status codes are semantically correct (201 + `Location` on create; 204 on delete).
- Idempotency keys required for non-idempotent money/state-changing POSTs.
- No breaking change without a version bump and deprecation window.
- Contract lints clean; generated clients compile.

## 9. Verification and Testing

```bash
redocly lint openapi.yaml
openapi-spec-validator openapi.yaml
schemathesis run https://api.example.com/openapi.json --checks all --hypothesis-max-examples=50
```

Manual checks: create with the same idempotency key twice → identical response, one resource; request `limit=1000` → 400; unknown sort → 400; expired cursor → 400 with guidance; 429 includes `Retry-After`.

## 10. Security Considerations

- Encrypt in transit (TLS 1.2+); never accept credentials in URLs.
- Authorize every endpoint by resource ownership, not just authentication; object-level checks are mandatory.
- Implement rate limiting per principal and per IP; protect expensive queries.
- Validate and bound all inputs: payload size, array lengths, string lengths, enum allowlists; reject unknown fields on strict endpoints.
- Never expose internal IDs that leak sequence information; use UUIDs/ULIDs where enumeration is a risk.
- CORS: explicit origin allowlist, no wildcard with credentials.
- Avoid `$filter`-style free-form query languages unless parsed safely; SQL injection risk.
- Log security events (auth failures, admin actions) with correlation IDs; never log tokens or full PII payloads.

## 11. Failure Handling

- **Field name disagreement mid-project:** decide once, record in style guide, migrate with aliases for one version.
- **Breaking change needed:** add the new field/endpoint, deprecate the old with a sunset date, monitor client usage before removal.
- **Pagination inconsistency:** cursor must be opaque; rotate implementation without changing the contract.
- **Idempotency store unavailable:** fail closed with 503 rather than risk duplicate charges.
- **Contract drift between spec and server:** add conformance tests (schemathesis) in CI against the deployed spec.

## 12. Expected Deliverables

1. OpenAPI 3.1 document, lint-clean.
2. Error format specification with examples.
3. Pagination, filtering, sorting, and rate-limit conventions.
4. Versioning and deprecation policy.
5. Security notes: authn/authz per endpoint, input limits.
6. Example requests/responses and a generated client (if requested).
7. Conformance test results.

## 13. References

- OpenAPI Specification 3.1 — https://spec.openapis.org/oas/latest.html
- RFC 9457 Problem Details for HTTP APIs — https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 HTTP Semantics — https://www.rfc-editor.org/rfc/rfc9110
- Microsoft REST API Guidelines — https://github.com/microsoft/api-guidelines
- Google AIPs — https://google.aip.dev/
- Spectral — https://stoplight.io/open-source/spectral
- Schemathesis — https://schemathesis.readthedocs.io/
