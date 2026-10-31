# BE-007 — Exact Endpoint Contracts

This section is normative.

Copilot must implement the endpoints exactly as defined below.

Do not rename routes, add alternate route shapes, change field names, or introduce additional CRUD endpoints without an explicit requirement.

All endpoints are under:

```text
/api/v1
```

---

# 1. Project Endpoints

## POST `/api/v1/projects`

Create a project.

### Request

```json
{
  "name": "Pune Municipal Road Project",
  "owner_id": "uuid"
}
```

### Fields

| Field | Type | Required | Rules |
|---|---|---:|---|
| `name` | string | yes | 1–256 characters |
| `owner_id` | UUID | yes | Must reference an existing user |

### Response — `201 Created`

```json
{
  "id": "uuid",
  "name": "Pune Municipal Road Project",
  "owner_id": "uuid",
  "created_at": "2026-09-14T00:00:00Z"
}
```

### Errors

- `422` — invalid request body / invalid UUID
- `404` — owner does not exist

---

## GET `/api/v1/projects`

List projects.

### Query parameters

```text
owner_id: UUID | optional
limit: integer | optional, default=50, maximum=100
offset: integer | optional, default=0
```

### Response — `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Pune Municipal Road Project",
      "owner_id": "uuid",
      "created_at": "2026-09-14T00:00:00Z"
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 1
}
```

---

## GET `/api/v1/projects/{project_id}`

Retrieve one project.

### Path parameter

```text
project_id: UUID
```

### Response — `200 OK`

```json
{
  "id": "uuid",
  "name": "Pune Municipal Road Project",
  "owner_id": "uuid",
  "created_at": "2026-09-14T00:00:00Z"
}
```

### Errors

- `404` — project not found
- `422` — invalid UUID

---

## PATCH `/api/v1/projects/{project_id}`

Update project name.

Only the project name is mutable in BE-007.

### Request

```json
{
  "name": "Pune Municipal Road Rehabilitation Project"
}
```

### Fields

| Field | Type | Required | Rules |
|---|---|---:|---|
| `name` | string | yes | 1–256 characters |

`owner_id` must not be changed by this endpoint.

### Response — `200 OK`

```json
{
  "id": "uuid",
  "name": "Pune Municipal Road Rehabilitation Project",
  "owner_id": "uuid",
  "created_at": "2026-09-14T00:00:00Z"
}
```

### Errors

- `404` — project not found
- `422` — invalid request

---

# 2. Activity Endpoints

Activities are always project-scoped.

## POST `/api/v1/projects/{project_id}/activities`

Create an activity.

### Request

```json
{
  "actor_id": "uuid",
  "verb": "evidence_uploaded",
  "details": {
    "evidence_id": "uuid"
  }
}
```

### Fields

| Field | Type | Required | Rules |
|---|---|---:|---|
| `actor_id` | UUID/null | no | Must reference an existing user when supplied |
| `verb` | string | yes | 1–128 characters |
| `details` | object/null | no | JSON object |

`project_id` comes exclusively from the path.

### Response — `201 Created`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "actor_id": "uuid",
  "verb": "evidence_uploaded",
  "details": {
    "evidence_id": "uuid"
  },
  "created_at": "2026-09-14T00:00:00Z"
}
```

### Errors

- `404` — project not found
- `404` — actor not found
- `422` — invalid request

---

## GET `/api/v1/projects/{project_id}/activities`

List activities for a project.

### Query parameters

```text
limit: integer | optional, default=50, maximum=100
offset: integer | optional, default=0
```

### Response — `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "project_id": "uuid",
      "actor_id": "uuid",
      "verb": "evidence_uploaded",
      "details": {
        "evidence_id": "uuid"
      },
      "created_at": "2026-09-14T00:00:00Z"
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 1
}
```

Return activities ordered by:

```text
created_at DESC
```

### Errors

- `404` — project not found
- `422` — invalid UUID/pagination

---

## GET `/api/v1/projects/{project_id}/activities/{activity_id}`

Retrieve one activity.

### Response — `200 OK`

Same activity representation as above.

The activity must belong to the requested project.

### Errors

- `404` — project not found
- `404` — activity not found under that project
- `422` — invalid UUID

---

# 3. Claim Endpoints

Claims are always project-scoped.

## POST `/api/v1/projects/{project_id}/claims`

Create a claim.

### Request

```json
{
  "claimant_id": "uuid",
  "title": "Road construction completed",
  "description": "The contractor reports that the road rehabilitation work is complete."
}
```

### Fields

| Field | Type | Required | Rules |
|---|---|---:|---|
| `claimant_id` | UUID/null | no | Must reference an existing user when supplied |
| `title` | string | yes | 1–512 characters |
| `description` | string/null | no | Free text |

### Response — `201 Created`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "claimant_id": "uuid",
  "title": "Road construction completed",
  "description": "The contractor reports that the road rehabilitation work is complete.",
  "created_at": "2026-09-14T00:00:00Z"
}
```

### Errors

- `404` — project not found
- `404` — claimant not found
- `422` — invalid request

---

## GET `/api/v1/projects/{project_id}/claims`

List claims belonging to a project.

### Query parameters

```text
limit: integer | optional, default=50, maximum=100
offset: integer | optional, default=0
```

### Response — `200 OK`

```json
{
  "items": [
    {
      "id": "uuid",
      "project_id": "uuid",
      "claimant_id": "uuid",
      "title": "Road construction completed",
      "description": "The contractor reports that the road rehabilitation work is complete.",
      "created_at": "2026-09-14T00:00:00Z"
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 1
}
```

---

## GET `/api/v1/projects/{project_id}/claims/{claim_id}`

Retrieve one claim.

The claim must belong to the requested project.

### Response — `200 OK`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "claimant_id": "uuid",
  "title": "Road construction completed",
  "description": "The contractor reports that the road rehabilitation work is complete.",
  "created_at": "2026-09-14T00:00:00Z"
}
```

### Errors

- `404` — project not found
- `404` — claim not found under project
- `422` — invalid UUID

---

## PATCH `/api/v1/projects/{project_id}/claims/{claim_id}`

Update claim content.

Only `title` and `description` are mutable.

### Request

```json
{
  "title": "Road rehabilitation completed",
  "description": "Updated claim description."
}
```

Both fields are optional individually, but at least one must be supplied.

`project_id` and `claimant_id` cannot be changed through this endpoint.

### Response — `200 OK`

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "claimant_id": "uuid",
  "title": "Road rehabilitation completed",
  "description": "Updated claim description.",
  "created_at": "2026-09-14T00:00:00Z"
}
```

---

# 4. Existing Evidence Upload Contract

BE-007 must preserve the existing BE-003 endpoint:

## POST `/api/v1/evidence`

This remains the existing multipart image-upload endpoint.

Do not replace it with a new project-specific upload endpoint.

Current contract:

```text
Content-Type: multipart/form-data
file: image/jpeg | image/png | image/webp
```

### Response — `201 Created`

```json
{
  "evidence_id": "uuid",
  "status": "uploaded",
  "storage_key": "quarantine/...",
  "content_type": "image/jpeg",
  "size": 123456
}
```

BE-007 must not break this contract.

The existing implementation currently creates Evidence with no project/claim association.

---

# 5. Evidence Context Association

## PATCH `/api/v1/evidence/{evidence_id}/context`

Associate existing evidence with a project and optionally a claim.

### Request

```json
{
  "project_id": "uuid",
  "claim_id": "uuid"
}
```

### Rules

`project_id`:

- required
- must reference an existing project

`claim_id`:

- optional
- must reference an existing claim when supplied
- claim must belong to the supplied `project_id`

The following must be rejected:

```text
project_id = Project B
claim_id   = Claim belonging to Project A
```

### Response — `200 OK`

```json
{
  "evidence_id": "uuid",
  "project_id": "uuid",
  "claim_id": "uuid"
}
```

This endpoint must not modify:

```text
filename
content_type
storage_key
file_size
status
sha256
phash
location
created_at
```

### Errors

- `404` — evidence not found
- `404` — project not found
- `404` — claim not found
- `409` — claim belongs to a different project
- `422` — invalid UUID/request

---

# 6. Evidence Location Contract

## PATCH `/api/v1/evidence/{evidence_id}/location`

Set or replace the geographic location of evidence.

### Request

```json
{
  "latitude": 18.5204,
  "longitude": 73.8567
}
```

### Fields

| Field | Type | Required | Rules |
|---|---|---:|---|
| `latitude` | number | yes | `-90 <= latitude <= 90` |
| `longitude` | number | yes | `-180 <= longitude <= 180` |

Reject:

```text
NaN
Infinity
-Infinity
```

### Response — `200 OK`

```json
{
  "evidence_id": "uuid",
  "location": {
    "latitude": 18.5204,
    "longitude": 73.8567
  }
}
```

The database value must be a real PostGIS:

```text
POINT
SRID 4326
```

The API does not expose WKT/WKB as the public contract.

### Errors

- `404` — evidence not found
- `422` — invalid coordinates

Invalid coordinates must not modify the existing location.

---

# 7. Nearby Evidence Contract

## GET `/api/v1/evidence/nearby`

Find evidence near a geographic point.

### Query parameters

```text
latitude: number        required
longitude: number       required
radius: number          required, meters
limit: integer          optional, default=50, maximum=100
offset: integer         optional, default=0
```

Example:

```text
GET /api/v1/evidence/nearby?latitude=18.5204&longitude=73.8567&radius=1000
```

### Validation

```text
-90 <= latitude <= 90
-180 <= longitude <= 180
radius > 0
radius <= 100000
limit: 1..100
offset >= 0
```

`radius` is measured in **meters**.

### Response — `200 OK`

```json
{
  "items": [
    {
      "evidence_id": "uuid",
      "project_id": "uuid",
      "claim_id": "uuid",
      "latitude": 18.5205,
      "longitude": 73.8568,
      "distance_meters": 15.72
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 1
}
```

### Required ordering

Results must be ordered:

```text
distance_meters ASC
```

### Important implementation requirement

The geographic filtering and distance calculation must execute in PostgreSQL/PostGIS.

Do not:

```text
SELECT all evidence
→ Python distance calculation
→ Python filtering
```

The database must perform the spatial operation.

---

# 8. Project-Scoped Nearby Evidence Contract

## GET `/api/v1/projects/{project_id}/evidence/nearby`

Find evidence belonging to a project and located within a geographic radius.

### Query parameters

```text
latitude: number        required
longitude: number       required
radius: number          required, meters
limit: integer          optional, default=50, maximum=100
offset: integer         optional, default=0
```

Example:

```text
GET /api/v1/projects/{project_id}/evidence/nearby?latitude=18.5204&longitude=73.8567&radius=1000
```

### Response — `200 OK`

```json
{
  "items": [
    {
      "evidence_id": "uuid",
      "project_id": "uuid",
      "claim_id": "uuid",
      "latitude": 18.5205,
      "longitude": 73.8568,
      "distance_meters": 15.72
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 1
}
```

Every returned record must satisfy both:

```text
Evidence.project_id == {project_id}
```

and:

```text
distance <= radius
```

Both conditions must be enforced by the database query.

### Errors

- `404` — project not found
- `422` — invalid UUID/query parameters

---

# 9. HTTP Error Contract

Use FastAPI's standard error response shape:

```json
{
  "detail": "human-readable error"
}
```

Expected status codes:

| Status | Meaning |
|---|---|
| `200` | Successful retrieval/update |
| `201` | Resource created |
| `404` | Referenced resource does not exist |
| `409` | Valid resources conflict, e.g. cross-project claim association |
| `422` | Request validation failure |
| `500` | Unexpected server error through existing global handler |

Do not return `200` for failed operations.

Do not silently ignore invalid foreign keys.

---

# 10. Response Representation Rules

UUIDs are serialized as strings.

Timestamps use ISO-8601 format with timezone information.

Example:

```text
2026-09-14T00:00:00Z
```

Nullable database values remain JSON `null`.

Do not fabricate values.

For evidence without a location:

```json
{
  "location": null
}
```

Do not return:

```json
{
  "latitude": 0,
  "longitude": 0
}
```

unless the actual stored location is exactly `(0, 0)`.

---

# 11. Route Ordering Requirement

Because FastAPI path parameters can conflict with static paths, register static evidence routes before parameterized routes.

For example:

```text
/evidence
/evidence/nearby
/evidence/{evidence_id}/context
/evidence/{evidence_id}/location
```

The `/evidence/nearby` route must not be interpreted as:

```text
evidence_id = "nearby"
```

---

# 12. Exact BE-007 Endpoint Set

BE-007 implementation is limited to these endpoints:

```text
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/{project_id}
PATCH  /api/v1/projects/{project_id}

POST   /api/v1/projects/{project_id}/activities
GET    /api/v1/projects/{project_id}/activities
GET    /api/v1/projects/{project_id}/activities/{activity_id}

POST   /api/v1/projects/{project_id}/claims
GET    /api/v1/projects/{project_id}/claims
GET    /api/v1/projects/{project_id}/claims/{claim_id}
PATCH  /api/v1/projects/{project_id}/claims/{claim_id}

POST   /api/v1/evidence
PATCH  /api/v1/evidence/{evidence_id}/context
PATCH  /api/v1/evidence/{evidence_id}/location

GET    /api/v1/evidence/nearby
GET    /api/v1/projects/{project_id}/evidence/nearby
```

Do not add:

```text
DELETE endpoints
bulk endpoints
search endpoints
graph endpoints
claim verification endpoints
risk endpoints
fraud endpoints
temporal endpoints
vision endpoints
review endpoints
authentication endpoints
```

Those are outside BE-007.

---

# 13. Contract-Level Tests

Every endpoint must have API-level tests covering:

### Success

- valid request
- correct status code
- correct response schema
- persisted database state

### Validation

- missing required fields
- malformed UUID
- invalid coordinate
- invalid radius
- invalid pagination

### Referential integrity

- nonexistent owner
- nonexistent project
- nonexistent actor
- nonexistent claimant
- nonexistent claim
- nonexistent evidence

### Cross-project integrity

Explicitly test:

```text
Project A
Claim A

Project B
Evidence B
```

Attempt:

```text
Evidence B → Claim A
```

Expected:

```text
409 Conflict
```

and the database must remain unchanged.

### Geospatial correctness

Create multiple real evidence records:

```text
Point A → inside radius
Point B → inside radius
Point C → outside radius
Point D → no location
```

Verify the API returns only the correct records.

Verify ordering by actual PostGIS-computed distance.

---

# 14. Contract Freeze

Once BE-007 implementation begins, these endpoint paths and field names are considered frozen for the milestone.

Copilot must not:

- rename fields for convenience;
- introduce alternate aliases;
- create duplicate routes;
- change `radius` from meters to another unit;
- expose PostGIS geometry internals as the public API;
- move `project_id` from path to request body where the contract specifies a path parameter;
- silently accept cross-project relationships;
- return fabricated geographic data.

Any required deviation must be reported as a blocker rather than silently changing the contract.