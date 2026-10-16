# Authorization Scope Classification — 2026-10-17

Scope: every route whose guard is a resource-less `require(action)` — i.e. a guard that proves
the caller holds a permission **in any scope** and nothing more — plus the publication-policy
family and `POST /projects`. Companion to
[`Backend Acceptance Audit Register — 2026-10-16.md`](Backend%20Acceptance%20Audit%20Register%20—%202026-10-16.md)
§8, which records the findings as register rows.

Method and limits of this document are stated up front, because a classification inherited from a
heuristic is not evidence.

## 1. The policy being applied

Owner-approved 2026-10-17. Four rules, in order:

- **P1 — Project resources.** Access is constrained to projects the principal is authorized to
  access. A permission grant for project A never reads project B's rows.
- **P2 — Organization resources.** Access is constrained to the principal's organization unless an
  explicitly granted platform-wide (GLOBAL) permission permits more.
- **P3 — Global configuration.** May be globally readable **only** where the product deliberately
  defines it as global and the authorization contract says so. The contract is the code path that
  grants it, not a comment.
- **P4 — Creation and ownership assignment.** A caller cannot grant ownership or access to itself
  or another party merely by supplying an id in the request body. Ownership derives from the
  authenticated principal; delegated ownership requires explicit authorization.

Verdicts used: **SCOPED** (a principal-derived predicate restricts rows somewhere in the call
chain), **SELF-SCOPED** (restricted to the caller's own identity — a correct form of P1/P2 for
personal data), **GLOBAL-OK** (P3 satisfied with a documented reason), **GAP** (P1/P2/P3/P4 not
satisfied), **GAP-SCHEMA** (a scope predicate is not currently expressible because the table lacks
the column).

## 2. How the candidate list was produced, and why the count is not a finding count

`scope_blind_lists.py` (scratch) reports **23** GET routes satisfying two conditions: the guard is
`require(action)` with `resource_type=None`, and *the endpoint's own module* never mentions
`visible_project_ids` / `filter_by_project_scope` / `filter_graph_edges`.

That second test is deliberately crude and it over-reports: a route is correctly scoped if the
predicate lives in a service or repository module, and the scanner cannot see across module
boundaries. Each of the 23 was therefore read individually and its final SQLAlchemy filter quoted
(`route_guard_inventory.py`, `anon_probe.py` and per-module reads; all harnesses and outputs in
`D:/CODING/Scratch/deploy1`).

**Result, with the arithmetic stated exactly: of the 23 candidates, 11 are already scoped, 1
(`/metrics`) is global telemetry with a documented reason, and 11 are gaps.** One route is listed in
§3 although the scanner never reported it — `/retention/operations`, guarded by `require_global`, a
different guard name, so it did not enter the 23. `/metrics` is adjudicated in §5, item 4.
The number 23 must not be quoted as a vulnerability count.

## 3. Already scoped — no action

| Route | Where the row predicate lives | Class |
|---|---|---|
| `GET /auth/organizations` | `auth.py:311` `visible = auth_service.visible_organization_ids(...)` → `auth.py:315` `Organization.id.in_(visible)`; empty set returns zero rows (`:313-314`) | P2 |
| `GET /auth/users/{user_id}/roles` | rows pass `services/authorization.py:698` `if can(actor, "role.manage", target).allowed` | P2 (see §5.1 caveat) |
| `GET /field/assignments` | `field_operations.py:197` `visible_project_ids` → `repositories/field_operations.py:132-137` `FieldAssignment.project_id.in_(project_ids)`, `false()` when empty | P1 |
| `GET /field/assignments/{assignment_id}` | `field_operations.py:373-376` `if visible is not None and str(row.project_id) not in visible: raise FieldOperationError(404, ...)` | P1 |
| `GET /field/operations` | `repositories/field_operations.py:352-359` same project-id set on `FieldCaptureOperation` | P1 |
| `GET /field/captures/{client_operation_id}` | `repositories/field_operations.py:307-310` `FieldCaptureOperation.user_id == user_id` from `_require_principal` | SELF |
| `GET /field/work` | `repositories/field_operations.py:128-129` `FieldAssignment.user_id == principal_id` | SELF |
| `GET /notifications` | `repositories/notification.py:74` `Notification.recipient_id == recipient_id` | SELF |
| `GET /notifications/unread-count` | `repositories/notification.py:100-102` `recipient_id` + `status == "UNREAD"` | SELF |
| `GET /notifications/preferences` | `repositories/notification.py:250` `NotificationPreference.user_id == user_id` | SELF |
| `GET /notifications/{id}` | `notification.py:175-176` `if str(item.recipient_id) != uid and not is_admin: 404` | SELF (see §5.2 caveat) |
| `GET /retention/operations` | guard is `require_global("retention.read")` (`retention.py:621`), i.e. GLOBAL grant required | GLOBAL-OK (see §5.3) |

## 4. Gaps

### 4.1 Retention read family — P1/P2 violated (Critical before real multi-project data)

| Route | Evidence |
|---|---|
| `GET /retention/policies` | `retention.py:170-171` `db.query(RetentionPolicy).order_by(RetentionPolicy.created_at, RetentionPolicy.id).all()` — no predicate of any kind |
| `GET /retention/policies/{policy_id}` | `retention.py:148` handler, fetch at `:153` → `repositories/retention.py:26` `filter(RetentionPolicy.id == policy_id)` — fetch by caller id, no ownership check |
| `GET /retention/policies/{policy_id}/history` | `retention.py:216` existence-only probe, then `repositories/retention.py:44-50` `filter(RetentionPolicyVersion.policy_id == policy_id)` |
| `GET /retention/holds` | `repositories/retention.py:126-132` filters on `project_id` **only if the caller supplies it**; omitting the parameter yields `db.query(RetentionHold)` |
| `GET /retention/holds/{hold_id}` | `repositories/retention.py:118-119` `filter(RetentionHold.id == hold_id)` — fetch by caller id |

The decisive evidence is internal inconsistency, not judgement: **the write paths in the same file
already do this correctly.** `retention.py:90-105` `_enforce_policy_scope` loads the policy and
enforces its `project_id`/`organization_id`, and `retention.py:434-446` `_enforce_hold_row` reads
`row.project_id`/`row.organization_id` — neither helper is called from any of the five GETs above.
So a project-A reviewer holding `retention.read` for project A reads project B's policies,
versions, holds and hold details.

Schema readiness: `RetentionPolicy` (`models.py:1666`) has nullable `organization_id:1675`,
`organizational_unit_id:1676-1678`, `project_id:1679` plus `scope_type:1674` ∈ {GLOBAL,
ORGANIZATION, ORGANIZATIONAL_UNIT, PROJECT} (mutual exclusivity enforced in
`services/retention.py:144-155`, e.g. *"GLOBAL policies must not carry scope identifiers"*).
`RetentionHold` (`models.py:1770`) has nullable `project_id:1778` **and** `organization_id:1781`
with `scope` ∈ {RESOURCE, PROJECT, CASE, CLAIM, ORGANIZATION} (`:1793-1796`).
`RetentionPolicyVersion` (`models.py:1702`) has **no** scope column — history must be scoped by
joining its parent policy.

**Fix rule (P1/P2/P3 in one sentence):** a `scope_type='GLOBAL'` policy is global configuration and
readable by any holder of `retention.read`; every other row is readable only if its own scope is
within the caller's grants — which is exactly the check `_enforce_policy_scope` already performs per
row, so the fix is to apply it (and its hold equivalent) to reads instead of only to writes. Note
that `resolve_resource_scope` has **no** `retention_policy`/`retention_hold` branch today
(verified: only the permission names at `services/authorization.py:78-83` mention retention), so a
retention resource type would have to be added or the existing manual `enforce` pattern reused.

### 4.2 Integration read family — P1/P2 violated (High)

All five are `require(action)` with no resource and no principal-derived predicate; their only
filters are caller-supplied query parameters, which is not a scope check — it is the caller picking
which project to read.

| Route | Evidence | Scope column available |
|---|---|---|
| `GET /integrations/clients` | `repositories/integration.py:77-80` `db.query(ApiClient)` + optional `status` from the caller | `ApiClient.project_id:1605` (nullable) — P1 possible; no `organization_id`, no creator column |
| `GET /integrations/systems` | `repositories/integration.py:47-51` filters on `organization_id` only when supplied (`integration.py:96`) | `ExternalSystem.organization_id:2054` (nullable) — P2 possible; `resolve_resource_scope` **already supports** `"external_system"` (`services/authorization.py:1031`) |
| `GET /integrations/webhooks` | `repositories/integration.py:276-280` `WebhookSubscription.external_system_id`/`status` only | no scope column on `WebhookSubscription:2175` — scope via its `ExternalSystem`; `"webhook_subscription"` already supported (`:1042`, org via join) |
| `GET /integrations/events` | `repositories/integration.py:423-431` `project_id` filtered only when the caller supplies it (`integration.py:716`) | `IntegrationEvent.project_id:2274` is a **plain nullable UUID with no FK** — P1 needs an FK/validity decision first |
| `GET /integrations/references` | `repositories/integration.py:162-168` all three filters caller-supplied | **GAP-SCHEMA**: `ExternalReference:2103` has only `external_system_id`, `resource_type`, `resource_id` (polymorphic, no FK) — no project/org/client/creator column, so a direct scope predicate is not expressible; scope must derive from the owning `ExternalSystem` |

Single-object integration routes are already correct and show the intended pattern, e.g.
`integration.py:230` `require("integration.read", "api_client", "client_id")` and
`integration.py:658` `require("webhook.manage", "webhook_subscription", "subscription_id")`.
`revoke_credential_endpoint` (`integration.py:276`) is resource-less `require("credential.manage")`
and should be reviewed in the same pass.

### 4.3 Publication policies — P3 boundary not enforced (scope decision recorded below)

This closes the "is it global or per-project?" question with the code's own answer:

- `PublicationPolicy` (`models.py:2753-2770`) has columns `id, name, description, created_at,
  updated_at` and **no** project/organization column; `PublicationPolicyVersion` (`:2781`) carries
  the rules. Per-project policies are not expressible today.
- `services/authorization.py:1090-1093` states the intent: *"policies are administrative
  configuration, not scoped domain objects. They resolve to a bare resource so only GLOBAL
  assignments can manage them."*

Classification: **global configuration (P3)**. The defect is therefore not a missing project filter
— it is that three guards on the same rows disagree with each other:

| Route | Guard | Effective requirement |
|---|---|---|
| `GET /publications/policies/{policy_id}` (`publication.py:351`) | `require("publication.read", "publication_policy", "policy_id")` → bare `Resource` | **GLOBAL grant only** |
| `GET /publications/policies` (`publication.py:369-380`) | `get_current_principal` + inline `if not is_development_bypass(principal): if "publication.read" not in principal.permissions: 403` (`:374-377`) | **any scope** |
| `POST /publications/policies` (`publication.py:303`) | `require("publication.policy.manage")` | **any scope** |

Consequences: a project-scoped reviewer can enumerate the entire policy catalogue but is refused
each policy by id, and a caller holding `publication.policy.manage` at *project* scope can create
global configuration that the item-read path says only GLOBAL may manage. The create route is
unambiguously wrong under either reading of P3.

**Decision required (owner):** Option B (recommended) — administrative configuration: add
`require_global`-equivalent GLOBAL enforcement to the list route and GLOBAL to create, leaving the
item read as the model. Option A — reviewer-visible configuration: keep the list open to
`publication.read` in any scope and relax the item read to match. Either is coherent; the current
mix is not. Data-shape note: Option A as literally "per-project policies" would require new
columns and a migration, which is out of scope for either option today.

### 4.4 `POST /projects` — P4 violated (High)

`backend/schemas/context.py:1-32` defines `ProjectCreate{name, owner_id: UUID}` with `owner_id`
**required and caller-chosen**; `ProjectUpdate` carries `name` only. The handler
(`context.py:55-63`, route decorator at `:55`) does `_require_user(request.owner_id, db, "Owner")`
— and `_require_user` (`context.py:50-53`) is existence-only:

```python
def _require_user(user_id: UUID | None, db: Session, label: str) -> None:
    if user_id is not None and db.query(User).filter(User.id == str(user_id)).one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
```

So any caller with `project.create` in any scope can park a project under another user's id. That
is not attribution forgery — it is **ownership assignment by supplied id**, which P4 forbids, and it
is the one place where the caller can grant access rather than the system. The route also writes no
audit event, so the creation is unrecorded.

Owner-approved fix direction (P4, applied): derive the owner from the authenticated principal by
default; keep delegated ownership available only through an explicitly authorized operation
(validated target scope, recorded event). A client-principal `POST /projects` needs the same
decision as `activities.actor_id` — API clients have no `users` row, so a client-created project
must either name an owner through the authorized delegation path or be refused.

### 4.5 Notification deliveries — P1/P2 not expressible directly (Medium)

`GET /notifications/{id}/deliveries` (`notification.py:222`) is resource-less
`require("notification.admin")`, and `repositories/notification.py:191` filters only on
`NotificationDelivery.notification_id == notification_id`: no recipient/org predicate, `_user_id`
is never called, and the parent notification's existence is not checked (an unknown id returns an
empty `200`). `NotificationDelivery` (`models.py:1937`) has **no** scope column — only
`notification_id:1942-1944` — so scoping requires a join to `Notification`, which *does* have
`recipient_id:1907`, `organization_id:1908` and `project_id:1909`, and `resolve_resource_scope`
already supports `"notification"` (`services/authorization.py:1026`).

## 5. Caveats on routes classified as scoped

1. `GET /auth/users/{user_id}/roles` — the **rows** are scoped but the guard and the existence probe
   (`auth.py:542` `if auth_repo.get_user(db, str(user_id)) is None`, repository unfiltered) are not:
   `role.manage` in any scope can confirm that an arbitrary user id exists in another organization.
   Low severity, worth a target check when `role.manage` is next touched.
2. `GET /notifications/{id}` — the recipient check has an `is_admin` escape (`notification.py:174`)
   satisfied by `notification.admin` in **any** scope, which is P2-in-any-scope rather than GLOBAL.
   Correct shape, wrong scope granularity.
3. `GET /retention/operations` — passes only because `require_global` demands a GLOBAL grant
   (`security/authorization.py:255-257`); the repository applies no principal predicate
   (`repositories/retention.py:155-169`) and `RetentionOperation` (`models.py:1807-1836`) has no
   scope columns. Reason: operational audit of the retention engine, a platform-administrator
   surface. Keep the GLOBAL requirement; do not "fix" it into a project filter.
4. `GET /metrics` — behind `require("metrics.read")` (register 5.2). It returns the whole registry,
   so it is global by design: labels are bounded vocabularies (`route` is the **template**, never the
   raw path — `main.py:61` and the docstring at `observability/metrics.py:47-49`; governance and
   publication metric files both state "never user_id, project_id, evidence_id, claim_id, or
   dispute_id"). One latent risk: the webhook counters **declare** an id-bearing `subscription_id`
   label (`observability/metrics.py:212-215, 218-221, 236-239, 243-246, 249-252`). No call site
   records them today — `record_http_request` at `main.py:63` is the only `get_metrics().record_*`
   caller in `backend/` — so nothing is emitted. Reason: global aggregate telemetry, no cross-scope
   row data. **Constraint for future work: do not wire the `subscription_id` label without a
   scope-aware surface.**

## 6. Not covered by this classification

`/api/v1/auth/me` reports as authn-only in `route_guard_inventory.txt` and is correct: it returns the
caller's own principal. The seven `/api/v1/public/*` routes are anonymous by design and
publication-state-gated (register 1.1 / BE-022). This document classifies read scope only; the
write-actor question was settled separately in stage 02 (register 1.4/1.9) and the claim there
should be read as *"the recorded actor is principal-derived everywhere"* — `auth.py`,
`integration.py`, `notification.py`, `publication.py`, `field.py` and `retention.py`'s `_actor()`
never read a body actor field at all, so they are safe by a different mechanism than `derive_actor`.

Still open and out of scope here (register rows): **2.1** evidence bound to caller-supplied
`project_id`, **2.2** uploader identity (`POST /evidence` at `evidence.py:18-50` does not pass the
principal into `ingest_evidence`), **2.3** quarantine lifecycle (#215), **2.6** idempotency (#216).

## 7. Verification artifacts

| Artifact | Content |
|---|---|
| `route_guard_inventory.py` → `route_guard_inventory.txt` | static guard inventory of the committed app: 185 route/method entries = 146 AUTHZ-GUARD, 21 AUTHZ-LOCAL, 2 AUTHN-ONLY, 12 ANONYMOUS, 4 FRAMEWORK |
| `anon_probe.py` → `anon_probe.txt` | every route requested with **no credential** under `AUTH_MODE=enforcing`, `AUTH_DEV_TOKENS_ENABLED=false`, `AUTH_OIDC_ENABLED=false`: 181 pairs, 169 refused 401/403, the 12 non-refusals being the 5 health probes + 7 `/public/*` |
| `scope_blind_lists.py` → `scope_blind_output.txt` | the 23-candidate list this document adjudicates |
| `stage02_identity.patch` | `git show 61762341`, 2876 lines, 28 files, +1918/−113 — the identity + attribution milestone |

The runtime probe answers "is authentication required"; it does **not** answer "is the returned row
set restricted to the caller's scope", which is what this document is about — an anonymous request
401s on all of §4 regardless.
