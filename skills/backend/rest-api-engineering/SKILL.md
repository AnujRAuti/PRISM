---
name: rest-api-engineering
description: Design HTTP APIs that are predictable and safe—resource modeling, correct status codes, stable pagination, RFC 9457 errors, idempotency, and versioning.
metadata:
  domain: backend
  version: 1.0.0
  risk: medium
---

# REST API Engineering

## 1. Purpose

Design HTTP APIs clients can rely on for years. Most API problems are contract problems: ambiguous status codes, inconsistent error shapes, offset pagination that duplicates rows, retries that double-charge, and breaking changes shipped as "minor". This skill covers resource modeling, status-code semantics per RFC 9110, cursor pagination, RFC 9457 problem details, idempotency, conditional requests, and deprecation.

**Scope:** your own API. Changing a public contract affects integrators—treat removal or renaming as a breaking change requiring a deprecation window and communication.

## 2. Activation Conditions

- Designing a new HTTP API or a new major version.
- Client complaints about inconsistent errors, pagination, or retry behavior.
- Money-moving or otherwise non-idempotent operations exposed over HTTP.
- Preparing to deprecate endpoints.
- Keywords: REST, HTTP semantics, status codes, pagination, cursor, idempotency key, problem details, ETag, versioning, OpenAPI, deprecation.

## 3. When Not to Use

- gRPC/GraphQL surfaces (use their own skills).
- Internal function calls that are not crossing a process boundary.
- Streaming media or file transfer protocols.

## 4. Required Context

1. Consumers: browsers, mobile, partners, internal services.
2. Data model and access patterns (list sizes, sort orders).
3. Non-idempotent operations (payments, sends, provisioning).
4. Compatibility policy and how long old versions live.
5. Documentation tooling (OpenAPI generator).

## 5. Operating Procedure

1. **Model resources, not actions**: nouns in paths (`/orders/{id}/refunds`), HTTP methods for semantics. Use an action sub-resource when the operation genuinely is not CRUD.
2. **Use status codes correctly**: `200/201/202/204`, `400` malformed, `401` unauthenticated, `403` unauthorized, `404` missing, `409` conflict, `412` precondition failed, `422` semantically invalid, `429` rate limited, `5xx` server-side.
3. **Return one error format everywhere**: RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, plus a `errors[]` extension for field validation.
4. **Paginate with cursors**, not offsets, for anything that changes; make the cursor opaque and signed.
5. **Support conditional requests**: `ETag`/`If-None-Match` for reads, `ETag`/`If-Match` for optimistic concurrency on writes.
6. **Add idempotency keys** for `POST` operations with side effects: client-supplied `Idempotency-Key`, stored with the response, replayed on repeat.
7. **Version explicitly** (`/v1`) and evolve additively within a version: new optional fields, no type changes, no removals.
8. **Deprecate with mechanics**: `Deprecation` indication, `Sunset` header (RFC 8594), `Link` to migration docs, and telemetry on old-version usage.
9. **Publish an OpenAPI document** generated from the code, with examples and error schemas, and diff it in CI.
10. **Test the contract**, not just handlers: status codes, schema validation, pagination stability, and idempotent replay.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Framework | FastAPI, Litestar, Django REST Framework, NestJS, Spring Boot |
| Schema | OpenAPI 3.1, `openapi-typescript`, `openapi-diff` |
| Validation | Pydantic v2, Zod, JSON Schema |
| Errors | RFC 9457 problem+json |
| Mocking | Prism, MSW |
| Contract tests | Schemathesis, Dredd, `pytest` + `httpx` |
| Docs | Scalar, Redoc, Swagger UI |

## 7. Practical Implementation

**Resource model:**

```
GET    /v1/orders?status=paid&limit=50&cursor=eyJpZCI6...
POST   /v1/orders                          -> 201 + Location
GET    /v1/orders/{order_id}
PATCH  /v1/orders/{order_id}               (If-Match: "<etag>")
POST   /v1/orders/{order_id}/refunds       (Idempotency-Key: <uuid>)
GET    /v1/orders/{order_id}/refunds
```

**Problem details error model (RFC 9457):**

```json
{
  "type": "https://api.example.com/problems/insufficient-funds",
  "title": "Insufficient funds",
  "status": 422,
  "detail": "The card ending 4242 was declined for 1,250.00 INR.",
  "instance": "/v1/orders/ord_8812/payments",
  "errors": [
    {"field": "amount", "code": "exceeds_limit", "message": "Amount exceeds the daily limit."}
  ],
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

**Emitting problem+json consistently (FastAPI):**

```python
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

PROBLEM = "application/problem+json"

class ProblemError(Exception):
    def __init__(self, status_code: int, type_: str, title: str, detail: str, errors: list | None = None):
        self.status_code, self.type_, self.title, self.detail, self.errors = status_code, type_, title, detail, errors

def problem(status_code: int, type_: str, title: str, detail: str, instance: str | None = None) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status_code, "detail": detail}
    if instance:
        body["instance"] = instance
    return JSONResponse(status_code=status_code, content=body, media_type=PROBLEM)

app = FastAPI()

@app.exception_handler(ProblemError)
async def on_problem(_: Request, exc: ProblemError) -> JSONResponse:
    body = {"type": exc.type_, "title": exc.title, "status": exc.status_code, "detail": exc.detail}
    if exc.errors:
        body["errors"] = exc.errors
    return JSONResponse(exc.status_code, body, media_type=PROBLEM)

@app.exception_handler(RequestValidationError)
async def on_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]),
               "code": e["type"], "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status.HTTP_422_UNPROCESSABLE_ENTITY,
                        {"type": "https://api.example.com/problems/validation",
                         "title": "Request validation failed", "status": 422,
                         "detail": f"{len(errors)} field(s) failed validation", "errors": errors},
                        media_type=PROBLEM)
```

**Cursor pagination with a stable sort key:**

```python
import base64, json

def encode_cursor(row) -> str:
    payload = {"k": row.created_at.isoformat(), "id": row.id}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()

def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode() + b"=="))
        return data["k"], data["id"]
    except Exception as exc:
        raise ValueError("invalid cursor") from exc

# SQL: ORDER BY (created_at, id) DESC  -- (k, id) ordering with strict comparison
# WHERE (created_at, id) < (:k, :id)
```

```json
{
  "data": [{"id": "ord_8812", "status": "paid"}],
  "page": {"next_cursor": "eyJrIjoiMjAyNi0xMS0wNFQxMDowMDowMFoiLCJpZCI6Im9yZF84ODEyIn0", "has_more": true},
  "meta": {"limit": 50}
}
```

**Idempotent POST with stored responses (Postgres):**

```sql
CREATE TABLE idempotency_key (
  key            text PRIMARY KEY,
  route          text        NOT NULL,
  request_hash   bytea       NOT NULL,
  status_code    int,
  response_body  jsonb,
  created_at     timestamptz NOT NULL DEFAULT now(),
  locked_until   timestamptz
);
CREATE INDEX ON idempotency_key (created_at);
```

```python
import hashlib, json

async def handle_idempotent(conn, key: str, route: str, body: dict, produce):
    request_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).digest()

    async with conn.transaction():
        row = await conn.fetchrow(
            """INSERT INTO idempotency_key (key, route, request_hash, locked_until)
               VALUES ($1, $2, $3, now() + interval '30 seconds')
               ON CONFLICT (key) DO NOTHING
               RETURNING key""",
            key, route, request_hash,
        )
        if row is None:                              # key exists
            existing = await conn.fetchrow(
                "SELECT request_hash, status_code, response_body, locked_until FROM idempotency_key WHERE key = $1 FOR UPDATE",
                key,
            )
            if existing["request_hash"] != request_hash:
                raise ProblemError(422, "https://api.example.com/problems/idempotency-mismatch",
                                   "Idempotency key reused with a different body",
                                   "Reuse a key only for an identical request.")
            if existing["status_code"] is None:
                raise ProblemError(409, "https://api.example.com/problems/request-in-progress",
                                   "Request in progress", "Retry after a short delay.")
            return existing["response_body"], existing["status_code"]

    result = await produce()                          # do the side effect once

    await conn.execute(
        "UPDATE idempotency_key SET status_code = $2, response_body = $3, locked_until = NULL WHERE key = $1",
        key, result.status_code, result.body,
    )
    return result.body, result.status_code
```

**Optimistic concurrency with ETag:**

```python
@router.get("/orders/{order_id}")
async def get_order(order_id: str, response: Response, svc: OrderService = Depends(get_svc)):
    order = await svc.get(order_id)
    etag = f'W/"{order.version}"'
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    return OrderResponse.model_validate(order)

@router.patch("/orders/{order_id}")
async def patch_order(order_id: str, patch: OrderPatch, if_match: str = Header(alias="If-Match"),
                      svc: OrderService = Depends(get_svc)):
    try:
        updated = await svc.patch(order_id, patch, expected_version=parse_etag(if_match))
    except VersionConflict:
        raise HTTPException(412, "stale ETag; refetch and retry")
    return OrderResponse.model_validate(updated)
```

**Deprecation response:**

```http
HTTP/1.1 200 OK
Deprecation: @1782864000
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
Link: <https://docs.example.com/migrate/orders-v2>; rel="deprecation"; type="text/html"
```

**Contract test with Schemathesis:**

```bash
schemathesis run https://staging.example.com/openapi.json \
  --checks all --hypothesis-max-examples=50 --base-url https://staging.example.com
```

**OpenAPI diff gate in CI:**

```bash
npx openapi-diff old-openapi.json new-openapi.json --fail-on incompatible
```

## 8. Quality Standards

- Every endpoint documented in OpenAPI with request/response examples and error schemas.
- Status codes match RFC 9110 semantics; no `200` with `{"success": false}`.
- A single error envelope across every endpoint and every gateway.
- Lists are cursor-paginated with a total ordering; page size capped (e.g. ≤ 100).
- Non-idempotent POSTs require `Idempotency-Key`; replays return the original response.
- Writes use `ETag`/`If-Match` where concurrent edits are possible.
- No breaking change ships inside a version; deprecations have a sunset date and telemetry.

## 9. Verification and Testing

- Schemathesis/Prism fuzzing of every operation against the schema.
- Explicit tests for: 401 vs 403 semantics, 404 for both missing and unauthorized resources where appropriate, 409 on duplicate create, 412 on stale ETag, 429 with `Retry-After`.
- Pagination test: insert a row between page fetches; the cursor must not duplicate or skip.
- Idempotency test: send the same key twice concurrently; exactly one side effect occurs.
- `openapi-diff` in CI with a break/fail policy.

## 10. Security Considerations

- Authorize per object, not per route: `GET /orders/{id}` must verify the caller owns `id`. Return `404` rather than `403` when existence itself is sensitive.
- Never accept client-supplied fields that map to internal state (role, tenant_id, status) — use explicit input schemas.
- Idempotency keys are client-controlled: scope them per authenticated principal and route so one tenant cannot replay another's.
- Rate-limit and cap payloads (body size, array lengths, pagination limits) to prevent resource exhaustion.
- Cursors must be opaque and integrity-protected (sign or encrypt); never expose raw primary keys if they are enumerable.
- Require HTTPS; set `Cache-Control: private, no-store` on authenticated responses to prevent shared-cache leakage.
- Do not put secrets or tokens in URLs (they land in logs and Referer headers).

## 11. Failure Handling

- **Clients retry on 5xx and duplicate writes:** add idempotency keys and document retry semantics.
- **Pagination duplicates/skips:** your sort key is not unique—use `(created_at, id)` and strict tuple comparison.
- **Breaking change already shipped:** support both shapes for a deprecation window, detect old clients via `User-Agent`/version header, and communicate a sunset date.
- **Error format drift between services:** centralize the problem-details middleware and test it in contract tests.
- **Slow list endpoints:** keyset pagination plus the right composite index; avoid `OFFSET` on large tables.

## 12. Expected Deliverables

1. Resource and endpoint table with methods and status codes.
2. OpenAPI 3.1 document with examples and error schemas.
3. Error catalog (problem types, codes, retryability).
4. Pagination, filtering, and sorting conventions.
5. Idempotency and concurrency policy.
6. Versioning and deprecation policy.
7. Contract test suite.

## 13. References

- RFC 9110 HTTP Semantics — https://www.rfc-editor.org/rfc/rfc9110
- RFC 9457 Problem Details for HTTP APIs — https://www.rfc-editor.org/rfc/rfc9457
- RFC 8594 The Sunset HTTP Header — https://www.rfc-editor.org/rfc/rfc8594
- IETF draft: Idempotency-Key HTTP header field — https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
- OpenAPI 3.1 specification — https://spec.openapis.org/oas/v3.1.0.html
- Schemathesis — https://schemathesis.readthedocs.io/
- Google API design guide — https://cloud.google.com/apis/design
- Microsoft REST API guidelines — https://github.com/microsoft/api-guidelines
