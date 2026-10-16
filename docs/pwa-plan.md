# PoA Progressive Web App (PWA) Plan

**Project:** Proof-Of-Action (PoA)  
**Purpose:** Implementation plan for the installable, mobile-friendly PoA web application.  
**Delivery constraint:** 48-hour release window  
**Priority:** Secure, deployed Reviewer journey first. The full Field Officer offline app is a later phase.  
**Status:** Plan only. Verify current repository code before treating any capability as implemented.  

---

## 1. Product and Scope

### 1.1 What we are building now
Build one responsive Next.js / React web application that can be installed as a Progressive Web App (PWA) where supported. It will provide the first-release Reviewer workflow:
1. Sign in using pre-provisioned Supabase Auth accounts.
2. View the cases the authenticated reviewer is authorized to access.
3. Open a case and inspect its details and associated evidence.
4. Upload evidence from inside a case, through FastAPI.
5. Retrieve evidence only after backend authorization.
6. See real analysis, integrity, and provenance states without fabricated results.
7. Submit a human decision with a meaningful rationale.
8. Verify the persisted decision and append-only workflow history.

### 1.2 What is not part of the 48-hour scope
- A complete Field Officer offline-first workflow.
- Native Android/iOS applications.
- Offline evidence capture and background synchronization.
- Interactive map and evidence graph.
- Automatic vision analysis unless the deployed worker and models are verified.
- In-app role and project-scope administration.
- Public signup or public evidence uploads.
- Fake/demo-only API responses in the acceptance journey.

> [!IMPORTANT]
> “PWA” means the web application can offer installability and app-like navigation. It does not automatically mean the application is offline-capable, secure offline evidence storage is implemented, or background sync works.

---

## 2. Locked Architecture

### Frontend
- React / Next.js with static build / export.
- TanStack Query for short-lived in-memory server-state caching.
- React Hook Form for forms.
- Zod for runtime validation of critical API responses and user input.
- Official Supabase browser client for authentication/session management only.
- PWA manifest and icons; service worker only for safe static assets and explicitly approved behavior.

### Backend
- FastAPI is the only business-data gateway.
- All case, evidence, analysis, decision, and workflow-history operations go through the API.
- Supabase JWTs must be verified by FastAPI using trusted JWKS, issuer, audience, expiry, and accepted algorithm checks.
- Every protected request resolves the active PoA identity and current database-backed role, permissions, and project scope.
- Authorization failures are fail-closed.

### Persistence and Hosting
- Supabase PostgreSQL for authoritative application records.
- Private Cloudflare R2 bucket for evidence objects, conditional on verifying account limits and connectivity.
- Cloudflare Pages for the static frontend, conditional on validating static export and direct-link behavior.
- Render free Docker web service for FastAPI, conditional on deployed smoke tests.
- Redis and a separate analysis worker are optional; defer live orchestration if a reliable free deployment cannot be verified.

### Trust Boundaries
- The browser must never connect directly to PostgreSQL for business operations.
- The browser must never receive R2 credentials or other privileged secrets.
- The browser must not choose trusted project/claim ownership for uploaded evidence.
- The backend derives project and claim associations from an authorized case record.
- A case UUID is an identifier, not authorization.
- The frontend hiding a button is not an authorization control.

---

## 3. Navigation and Screen Inventory

### 3.1 Authentication
- **Route:** `/login`
- **Elements:**
  - Product identity and short description.
  - Email/password sign-in if enabled for the provisioned Supabase accounts.
  - Loading state.
  - Invalid-credentials message.
  - Network/provider unavailable message.
  - Session-expired handling.
  - No public signup link.
  - No role selector.
- **Acceptance:**
  - Only provisioned accounts can sign in.
  - The frontend does not grant roles.
  - Protected pages call the API and respect backend authorization.

### 3.2 Reviewer Queue
- **Route:** `/review`
- Show only real cases returned by the authorized API.
- **Fields:**
  - Case identifier/reference.
  - Case title or claim summary.
  - Actual workflow status.
  - Evidence completeness, only if supplied or computed reliably.
  - Last activity, only if available.
  - Review priority with transparent reasons, not as a fraud verdict.
- **Required states:** Loading, Empty queue, API unavailable, Forbidden, Error with safe retry for reads, Unknown case status.
- Avoid inventing case counts, risk scores, timestamps, or analysis results.

### 3.3 Case Workspace
- **Route contract:** `/review/case?id=UUID` (preserve query-parameter route contract; also support direct URL/deep-links).
- **Sections:**
  1. Overview
  2. Evidence
  3. Intelligence
  4. Timeline / workflow history
  5. Decision
- **Requirements:**
  - Fetch case data from FastAPI.
  - Validate response with Zod.
  - Handle invalid/missing IDs.
  - Handle not-found and forbidden states without leaking cross-project information.
  - Support direct navigation, refresh, and opening in a new tab on the deployed static host.
  - Never assume a UUID grants access.

### 3.4 Evidence Section
- **Show:** Evidence metadata returned by API, association with current case, upload/ingestion status, quarantine status, integrity results only when persisted, analysis state/timestamp, authorized view/download action.
- **Upload:** Only from authorized case context; preserve selected file if outcome uncertain; enforce 10 MiB limit in UI and FastAPI; show accepted file types based on backend validation; reconcile if request outcome unknown.
- **Quarantine:** Show metadata and true integrity state; do not display quarantined content unless backend policy explicitly permits.

### 3.5 Intelligence Section
- Show only actual backend output: analysis state, run timestamp, model/method version where available, explainable signals and sources, limitations/unknowns.
- If worker/model unavailable: display "Analysis unavailable" or real pending/failure state. Do not generate placeholder findings that look real.

### 3.6 Decision Section
- **Supported outcomes:** `SUPPORTED`, `CONTRADICTED`, `INCONCLUSIVE`, `INSUFFICIENT_EVIDENCE`.
- **Flow:**
  1. Select an outcome.
  2. Enter meaningful rationale (20-character minimum enforced in UI).
  3. Character counter and uncertainty prompt.
  4. Review confirmation summary.
  5. Submit once.
  6. Show success only after API confirms persistence.
  7. Refresh case state and history from server.
- If write times out: preserve rationale, show "Outcome unknown; checking server state", fetch authoritative case/history; do not blindly resubmit.
- Backend derives actor from authenticated principal, not client-supplied user ID.

### 3.7 Workflow History
- Show real persisted events: event/decision type, actor identity (as authorized), timestamp, rationale/summary. Never fabricate history.

### 3.8 Optional Supervisor View
- Only after Reviewer acceptance gate passes (read-only, backend-enforced scopes, no decision controls).

---

## 4. Target Frontend Structure
Adapt to the current repository. Do not create a second application or replace existing working components without first inspecting the code.

```text
frontend/
  src/
    components/
      auth/             # Supabase Auth, login forms
      common/           # Header, Sidebar, Layout, PrismLogo, LoadingSplash
      case/             # Case overview, evidence section, decision form, history
      reviews/          # Review queue table, filters
    lib/
      api/              # Centralized fetch client, error normalization
      schemas/          # Zod validation schemas
      supabase/         # Supabase browser client & session helper
    pages/              # Route views (/login, /review, /review/case)
    styles/             # GovTech CSS design system tokens
  public/
    icons/              # PWA icons (192x192, 512x512, maskable)
    manifest.webmanifest
```

---

## 5. API Client Contract
- Read public `VITE_API_BASE_URL` (or `NEXT_PUBLIC_API_BASE_URL`).
- Attach current Supabase access token (`Bearer <token>`) to protected requests.
- Validate critical responses with Zod schemas.
- Normalize error categories: `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `CONFLICT`, `RATE_LIMITED`, `SERVICE_UNAVAILABLE`, `UNKNOWN`.
- Handle one session refresh and one retry after 401; never refresh repeatedly; treat 403 as forbidden.
- Never log bearer tokens, signed URLs, evidence bytes, or sensitive metadata.

---

## 6. Authentication and Authorization Checklist
- [ ] Use official Supabase browser client.
- [ ] No public signup or role selector.
- [ ] Obtain current access token through supported session API.
- [ ] Send bearer token only to configured API origin.
- [ ] Refresh once after 401, then require sign-in if still unauthorized.
- [ ] Clear query caches on sign-out/account changes.
- [ ] Do not persist evidence data or signed URLs in local storage.
- [ ] Do not expose service-role keys or R2 credentials in frontend bundles.

---

## 7. PWA Requirements
- [ ] Web app manifest (`manifest.webmanifest` / `manifest.json`).
- [ ] Application name ("PRISM - Proof of Action") and short name ("PRISM").
- [ ] `start_url` and `scope` set to `/`.
- [ ] `display: standalone`, `theme_color`, and `background_color`.
- [ ] Sized icons: 192×192, 512×512, and maskable 512×512.
- [ ] Service worker policy: cache only safe static assets; network-only for authenticated API calls; do not cache case data, evidence bytes, or signed URLs.

---

## 8. 48-Hour Execution Sequence

### Phase 1: Baseline and Repository Audit (Hours 0–3)
- Inspect current frontend and backend directories.
- Run existing test suite (`npm test`).
- Identify exact API contracts.
- Verify production build (`npm run build`).
- Record blockers before changing code.

### Phase 2: Security and Backend Blockers (Hours 3–12)
- Supabase JWT verification in FastAPI.
- Map identities to active PoA users with role/project scope.
- Fix evidence association and audit attribution.
- Align upload status and response contract.
- Verify decision actor attribution and persistence.

### Phase 3: Reviewer PWA Frontend (Hours 12–28)
- Implement Supabase Auth integration in frontend.
- Implement `/review` queue and `/review/case?id=UUID` workspace.
- Implement evidence list, upload (10 MiB limit), and authorized retrieval.
- Truthful intelligence section (no synthetic hallucinations).
- Implement decision submission flow with 20-character minimum rationale.
- Add PWA manifest, service worker registration, and icons.

### Phase 4: Deployment and Provisioning (Hours 28–36)
- Provision restricted Supabase Auth accounts.
- Configure managed secrets (R2, Supabase JWKS, CORS).
- Deploy static frontend (Cloudflare Pages) and FastAPI (Render/Docker).
- Verify direct case URLs and CORS.

### Phase 5: Acceptance and Cutover (Hours 36–48)
- Run deployed smoke test and negative authorization tests.
- Verify persistence after restart.
- Prepare tested local Compose fallback.

---

## 9. Final Acceptance Gate
1. Deployed Reviewer sign-in uses real Supabase Auth.
2. FastAPI verifies Supabase JWTs correctly (fail-closed).
3. Active PoA identity and current project scopes enforced.
4. Cross-project and wrong-role requests denied.
5. Evidence uploads associated through authorized case context.
6. Evidence objects remain private in R2.
7. Authorized retrieval works.
8. Quarantine policy respected.
9. Audit actor and project attribution correct.
10. Human decisions persist with rationale.
11. Workflow history remains available after reload.
12. Direct case navigation and refresh work on deployed host.
13. No secrets exposed in frontend bundle or logs.
14. Smoke test passes on deployed stack.
