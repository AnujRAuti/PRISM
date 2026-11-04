---
name: api-documentation
description: Produce API reference docs developers can build against—OpenAPI as source of truth, curated reference pages, runnable examples, and drift checks in CI.
metadata:
  domain: research-and-documentation
  version: 1.0.0
  risk: low
---

# API Documentation

## 1. Purpose

Let an external developer make a successful first request and a correct second one. API docs fail when they are generated but unreadable (a schema dump), when examples are wrong or missing, when authentication and error handling are undocumented, and when the docs drift from the implementation. This skill covers treating OpenAPI as the contract, curating the reference, writing quickstarts, documenting errors, and enforcing drift checks.

**Scope:** your own API documentation. Public reference pages expose your surface area; never publish internal-only endpoints or environments in the public spec.

## 2. Activation Conditions

- Launching or versioning a public or partner API.
- Support tickets show clients misusing endpoints or misunderstanding errors.
- Generated docs exist but developers still ask basic questions.
- Spec and implementation have diverged.
- Keywords: API docs, OpenAPI, Swagger, Redoc, Scalar, quickstart, authentication docs, error codes, changelog, SDK, examples, sandbox, drift.

## 3. When Not to Use

- Internal service-to-service contracts with no external consumer (contract tests suffice).
- Pure documentation of a UI (use technical-writing).
- Conceptual architecture explanation (use technical-diagramming / rfc-and-design-docs).

## 4. Required Context

1. Audience: third-party developers, partners, or internal teams.
2. Spec source: code-generated, hand-written, or design-first.
3. Auth model to document (API keys, OAuth flows, scopes).
4. Environments: production plus a sandbox with seeded data.
5. SDKs and client libraries supported.

## 5. Operating Procedure

1. **Make the OpenAPI document the source of truth** and generate it from code (or validate code against it). Keep one canonical file per version.
2. **Curate every operation's prose**: a one-line purpose, when to use it, prerequisites, and side effects. Schema descriptions are necessary but not sufficient.
3. **Write a quickstart that reaches a successful response in under five minutes**: obtain a key, make one call, show the exact response.
4. **Document authentication completely**: how to get credentials, how to send them, token lifetimes, scopes, rotation, and common failure modes.
5. **Document every error**: the problem type, HTTP status, when it occurs, whether it is retryable, and what the developer should do.
6. **Provide runnable examples per operation** in curl plus at least one SDK language, using realistic values and a sandbox base URL.
7. **Explain pagination, idempotency, rate limits, and versioning** in dedicated guides, referenced from each operation.
8. **Publish per-version docs** and mark deprecated operations inline with a sunset date and migration link.
9. **Add a drift check in CI**: the committed spec must match the generated one, and examples must pass schema validation.
10. **Provide a changelog** for the API and RSS/email notification for breaking changes.
11. **Test the docs like code**: run the quickstart end to end against sandbox in CI weekly.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Spec generation | FastAPI/Pydantic, NestJS Swagger, Springdoc, `zod-to-openapi` |
| Rendering | Scalar, Redoc, Swagger UI, Mintlify, Docusaurus + plugin |
| Validation | Spectral (lint rules), `openapi-diff`/`oasdiff` |
| Example testing | Schemathesis, Prism (mock), `curl` scripts in CI |
| SDK generation | `openapi-generator`, `openapi-typescript`, Speakeasy |
| Changelog | Keep a Changelog format, API-specific release notes |

## 7. Practical Implementation

**Spec curation in code (FastAPI, with descriptions and examples):**

```python
from fastapi import APIRouter, Header, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["Orders"])

class OrderLineIn(BaseModel):
    product_id: int = Field(..., examples=[7], description="Catalog product identifier.")
    quantity: int = Field(..., ge=1, le=100, examples=[2],
                          description="Units to purchase, 1–100.")

class OrderCreate(BaseModel):
    customer_id: int = Field(..., examples=[42], description="Must be an active customer.")
    lines: list[OrderLineIn] = Field(..., min_length=1, max_length=100,
                                     description="Order lines; at least one required.")

    model_config = {
        "json_schema_extra": {
            "examples": [{"customer_id": 42,
                          "lines": [{"product_id": 7, "quantity": 2}]}]
        }
    }

class OrderCreated(BaseModel):
    id: str = Field(..., examples=["ord_8812a1"])
    status: str = Field(..., examples=["draft"])
    total_cents: int = Field(..., examples=[339800],
                             description="Sum of line totals in minor units.")
    currency: str = Field(..., examples=["INR"])

@router.post(
    "/orders",
    response_model=OrderCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an order",
    description=(
        "Creates an order in `draft` status. Inventory is not reserved until payment.\n\n"
        "**Idempotency:** send an `Idempotency-Key`; replaying the same key with an "
        "identical body returns the original response.\n\n"
        "**Rate limit:** 60 requests/minute per key; see `Retry-After` on `429`."
    ),
    responses={
        201: {"description": "Order created", "headers": {"Location": {"schema": {"type": "string"}}}},
        409: {"description": "Duplicate idempotency key with a different body"},
        422: {"description": "Validation failure (problem+json with `errors[]`)"},
        429: {"description": "Rate limited; retry after the value in `Retry-After`"},
    },
)
async def create_order(payload: OrderCreate,
                       idempotency_key: str = Header(alias="Idempotency-Key",
                                                     min_length=8, max_length=64)):
    ...
```

**Quickstart page (the five-minute path):**

```markdown
# Quickstart

Create your first order in about three minutes.

### Step 1 — Get an API key
Sign in to the dashboard → **Developers** → **API keys** → **Create key**.
Copy it now; it is shown once.

### Step 2 — Make your first request

```bash
export ORDERS_KEY="sk_test_..."          # use the sandbox key for this guide

curl -sS -X POST https://sandbox.api.example.com/v1/orders \
  -H "Authorization: Bearer $ORDERS_KEY" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":42,"lines":[{"product_id":7,"quantity":2}]}'
```

```json
{
  "id": "ord_8812a1",
  "status": "draft",
  "total_cents": 339800,
  "currency": "INR"
}
```

### Step 3 — Verify the order
```bash
curl -sS https://sandbox.api.example.com/v1/orders/ord_8812a1 \
  -H "Authorization: Bearer $ORDERS_KEY"
```

## Next steps
- [Authentication and scopes](/auth)
- [Errors and retries](/errors)
- [Pagination](/pagination)
- [Going live: sandbox → production](/going-live)
```

**Error reference table (the page developers bookmark):**

```markdown
| Status | `type` suffix | When it happens | Retryable | What to do |
|---|---|---|---|---|
| 400 | `/malformed-request` | Body is not valid JSON | No | Fix the payload |
| 401 | `/invalid-key` | Key missing, revoked, or malformed | No | Re-check the key; rotate if revoked |
| 403 | `/insufficient-scope` | Key lacks the required scope | No | Request `orders:write` scope |
| 404 | `/not-found` | Resource does not exist or is outside your tenant | No | Verify the ID and your environment |
| 409 | `/idempotency-mismatch` | Same key, different body | No | Use a new key for a different request |
| 422 | `/validation` | Field-level constraint violated | No | Read `errors[].field` and correct it |
| 429 | `/rate-limited` | Per-key or per-account limit exceeded | Yes | Wait `Retry-After` seconds, then retry with backoff |
| 503 | `/temporarily-unavailable` | Dependency outage | Yes | Retry with exponential backoff and jitter |
```

**Spectral lint of the spec (CI):**

```yaml
# .spectral.yaml
extends: ["spectral:oas"]
rules:
  operation-operationId: error
  operation-description: error
  operation-summary: error
  operation-tags: error
  oas3-schema: error
  no-$ref-siblings: error
  info-contact: warn
  info-license: warn
  example-value-or-externalValue: error
  operation-success-response: error
  request-body-object: error
```

```bash
npx @stoplight/spectral-cli lint openapi.json --fail-severity=error
```

**Drift check (committed spec must match generated):**

```bash
python - <<'PY'
import json, subprocess, sys
from app.main import app          # generates OpenAPI from the running app

generated = app.openapi()
committed = json.load(open("openapi.json"))
if generated != committed:
    print("openapi.json is out of date; run `make openapi` and commit.", file=sys.stderr)
    sys.exit(1)
PY
```

**Validate documented examples against the schema:**

```python
import json, jsonschema
from app.main import app

spec = app.openapi()

def test_documented_examples_match_schemas():
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            for status, resp in op.get("responses", {}).items():
                content = resp.get("content", {}).get("application/json", {})
                for example in content.get("examples", {}).values():
                    schema_ref = content.get("schema", {})
                    schema = resolve_ref(spec, schema_ref)
                    jsonschema.validate(example["value"], schema)
```

**Pagination and idempotency guides referenced from operations:**

```markdown
## Pagination

Lists return at most 100 items per page and use opaque cursors.

```json
{"data": [...], "page": {"next_cursor": "eyJrIjoi...", "has_more": true}}
```

To fetch the next page, pass `cursor={{page.next_cursor}}`. When `has_more` is
`false`, stop. Cursors expire after 24 hours; an expired cursor returns
`400 /invalid-cursor` — restart from the first page.

**Do not** construct cursors yourself; they encode a signed sort position.
```

**Versioning and deprecation notice:**

```markdown
> **Deprecated:** `POST /v1/orders/legacy` — sunset **2027-01-31**.
> Use [`POST /v1/orders`](/reference/orders/create) instead. Migration guide:
> [legacy → v1](/migrate/orders-legacy).
```

## 8. Quality Standards

- OpenAPI is generated from or validated against code, and CI fails on drift.
- Every operation has a summary, description, at least one example, and documented errors.
- The quickstart reaches a successful response in under five minutes with copy-paste commands.
- Authentication, errors, pagination, idempotency, rate limits, and versioning each have a dedicated guide.
- Error documentation states retryability and the corrective action.
- Examples use sandbox credentials and realistic values; no fake `"string"` placeholders.
- Deprecated operations carry a sunset date and a migration link.
- Spec passes Spectral lint with zero errors.

## 9. Verification and Testing

- Run the quickstart exactly as written against sandbox in a scheduled CI job.
- Validate every documented example against its response schema.
- Lint the spec; fail the build on errors.
- Compare the published spec to the deployment's live spec (`/openapi.json`) per environment.
- Usability check: give the quickstart to a developer unfamiliar with the API and time to first success.
- Confirm error examples are reachable in sandbox (trigger a 422 and a 429 deliberately).

## 10. Security Considerations

- Never publish internal, admin, or debug endpoints, or a spec that lists internal hostnames.
- Sandbox keys must be clearly separate and revocable; never embed real production keys in examples or screenshots.
- Do not document security weaknesses or bypasses; document the intended controls and their limits.
- Scrub real customer data from examples and from generated sample responses.
- Rate-limit and scope documentation must match the implementation; a mismatch creates false expectations.
- Ensure the spec endpoint itself is not an unauthenticated information leak in production if the API is private.

## 11. Failure Handling

- **Docs drift from implementation:** generate from code, add the CI drift check, and make spec changes part of the definition of done.
- **Generated docs are unreadable:** add hand-curated descriptions, summaries, and examples at the source; do not build a separate doc site by hand.
- **Developers still ask questions:** review support tickets monthly and add a guide for each recurring question; link it from the relevant operation.
- **Examples fail:** they are validated in CI; fix within the same PR that broke them.
- **Major version release:** publish a side-by-side migration guide with before/after requests for every renamed or removed field.

## 12. Expected Deliverables

1. Canonical OpenAPI document with curated descriptions.
2. Rendered reference site per version.
3. Quickstart with copy-paste commands.
4. Authentication, errors, pagination, idempotency, rate-limit, versioning guides.
5. Per-operation examples in curl and one SDK.
6. CI checks: Spectral lint, drift detection, example validation.
7. API changelog with deprecation notices.

## 13. References

- OpenAPI Specification 3.1 — https://spec.openapis.org/oas/v3.1.0.html
- OpenAPI Initiative guidance — https://www.openapis.org/
- Spectral (OpenAPI linter) — https://stoplight.io/open-source/spectral
- Redoc — https://redocly.com/docs/redoc
- Scalar API reference — https://scalar.com/
- RFC 9457 Problem Details — https://www.rfc-editor.org/rfc/rfc9457
- Google API design guide — https://cloud.google.com/apis/design
- Microsoft REST API guidelines — https://github.com/microsoft/api-guidelines
- openapi-diff — https://github.com/OpenAPITools/openapi-diff
