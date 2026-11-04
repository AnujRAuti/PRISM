---
name: frontend-architecture
description: Structure large frontend applications—module boundaries, feature folders, state ownership, data layer, routing, and build topology that scale with teams.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: medium
---

# Frontend Architecture

## 1. Purpose

Organize a frontend so that many developers can work without stepping on each other and features can be added or deleted cleanly. Frontend codebases rot through three patterns: everything imports everything (no boundaries), state scattered across layers with unclear ownership, and one giant bundle. This skill defines boundaries, ownership, the data layer, and build topology, with enforcement rather than convention.

**Scope:** your own application. Architectural choices affect security boundaries too—decide where trusted code runs (server vs. browser).

## 2. Activation Conditions

- App is growing past a small team, or multiple teams contribute.
- Circular imports, tangled modules, or "change one file, break five".
- State management debates (Context vs. Redux vs. server state).
- Bundle size or build time problems.
- Keywords: frontend architecture, feature-sliced, module boundaries, monorepo, micro-frontends, state management, data layer, routing, code splitting.

## 3. When Not to Use

- Small apps under ~10k lines with one team (use simpler conventions).
- Framework-specific mechanics (use react-development or nextjs-development).
- Backend architecture (use system-architecture).

## 4. Required Context

1. Team size, structure, and deployment cadence.
2. Product areas (features) and their dependencies.
3. Rendering model: SPA, SSR, hybrid.
4. State types in play: server data, UI state, URL state, form state, auth.
5. Build tooling and monorepo constraints.

## 5. Operating Procedure

1. **Define layers and their allowed dependencies**, e.g. `app` (routing/composition) → `features` → `entities` → `shared`. Arrows point one way only.
2. **Organize by feature (vertical slices)**, with each feature exposing a public API (`index.ts`) and keeping internals private.
3. **Assign state ownership per type**:
   - Server data → data-fetching library cache (TanStack Query) with a single source of truth.
   - URL → route params/search params for anything shareable.
   - UI state → local component state; lift only when shared.
   - Cross-cutting client state (theme, session) → a small global store.
4. **Centralize the data layer**: typed API client, request/response validation (Zod), error normalization, and auth token handling in one place.
5. **Route = composition root**: pages assemble features; they do not contain business logic.
6. **Enforce boundaries with tooling**, not documentation: ESLint `import/no-restricted-paths`, or `dependency-cruiser` rules.
7. **Split at route and feature boundaries**; keep the initial bundle minimal and preload on intent.
8. **Decide monorepo vs. polyrepo** by shared code volume and release cadence; use workspace tooling with per-package exports.
9. **For multi-team scale, prefer module federation or independently deployed apps only when the organizational need is real** (independent deploys, different release cycles).
10. **Document the architecture** with a dependency diagram and a "where do I put this?" decision table.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Boundaries | `eslint-plugin-boundaries`, `import/no-restricted-paths`, `dependency-cruiser` |
| Monorepo | pnpm workspaces, Turborepo, Nx |
| Data | TanStack Query, SWR, tRPC, GraphQL codegen |
| State | Zustand, Redux Toolkit, Jotai, Context |
| Routing | React Router, TanStack Router, Next.js App Router |
| Module federation | Vite Module Federation, Webpack 5 MF |
| Diagramming | `madge --image`, Mermaid |

## 7. Practical Implementation

**Folder structure (feature-sliced, pragmatic):**

```
src/
├── app/                 # providers, router, global styles
│   ├── providers.tsx
│   └── router.tsx
├── pages/               # route-level composition only
│   ├── OrdersPage.tsx
│   └── OrderDetailPage.tsx
├── features/            # vertical slices
│   ├── checkout/
│   │   ├── api.ts         (feature-specific calls, uses shared client)
│   │   ├── components/    (internal)
│   │   ├── hooks.ts
│   │   └── index.ts       (public API only)
│   └── order-filters/
├── entities/            # domain models + reusable domain UI
│   ├── order/
│   │   ├── model.ts
│   │   ├── ui/OrderStatusBadge.tsx
│   │   └── index.ts
├── shared/              # framework-agnostic utilities, UI kit, api client
│   ├── api/client.ts
│   ├── ui/Button.tsx
│   └── lib/format.ts
└── styles/
```

**Public API per feature:**

```ts
// features/checkout/index.ts
export {CheckoutButton} from "./components/CheckoutButton";
export {useCheckout} from "./hooks";
// internals (api.ts, sub-components) intentionally not exported
```

**Boundary enforcement (ESLint):**

```json
{
  "rules": {
    "import/no-restricted-paths": ["error", {
      "zones": [
        {"target": "./src/shared", "from": "./src/features", "message": "shared cannot import features"},
        {"target": "./src/shared", "from": "./src/entities", "message": "shared cannot import entities"},
        {"target": "./src/entities", "from": "./src/features", "message": "entities cannot import features"},
        {"target": "./src/features", "from": "./src/pages", "message": "features cannot import pages"}
      ]
    }]
  }
}
```

**Dependency graph check (CI):**

```bash
npx madge src --circular --extensions ts,tsx
npx depcruise --config .dependency-cruiser.js src
```

**Centralized API client with validation:**

```ts
// shared/api/client.ts
import {z} from "zod";

const BASE = import.meta.env.VITE_API_URL ?? "";

export async function apiGet<S extends z.ZodTypeAny>(path: string, schema: S): Promise<z.infer<S>> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {Accept: "application/json"},
    credentials: "include",
  });
  if (!res.ok) {
    throw new ApiError(res.status, await safeMessage(res));
  }
  return schema.parse(await res.json());
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function safeMessage(res: Response): Promise<string> {
  try { return ((await res.json()) as {message?: string}).message ?? res.statusText; }
  catch { return res.statusText; }
}
```

**State ownership in practice:**

```tsx
// Server state: the query cache is the source of truth
const {data: orders, isPending, error} = useQuery({
  queryKey: ["orders", {status: filters.status}],
  queryFn: () => apiGet(`/orders?status=${filters.status}`, z.array(OrderSchema)),
  staleTime: 30_000,
});

// URL state: filters live in the URL so they survive refresh and sharing
const [params, setParams] = useSearchParams();
const filters = {status: params.get("status") ?? "all"};

// Local UI state: only what this component owns
const [expanded, setExpanded] = useState<string | null>(null);
```

**Lazy route with preload on intent:**

```tsx
const ReportsPage = lazy(() => import("../pages/ReportsPage"));

// Preload when the user hovers the nav link
<Link to="/reports" onMouseEnter={() => import("../pages/ReportsPage")}>Reports</Link>
```

**Workspace package exports (monorepo):**

```json
{
  "name": "@acme/ui",
  "type": "module",
  "exports": {
    ".": {"types": "./dist/index.d.ts", "import": "./dist/index.js"},
    "./styles.css": "./dist/styles.css"
  },
  "sideEffects": ["*.css"]
}
```

**"Where does this go?" decision table:**

| Thing | Location |
|---|---|
| Reusable button | `shared/ui` |
| Order status badge used by 3 features | `entities/order/ui` |
| Checkout-specific form | `features/checkout/components` |
| API call for checkout | `features/checkout/api.ts` |
| Route wiring | `pages/OrdersPage.tsx` |
| Theme provider | `app/providers.tsx` |

## 8. Quality Standards

- Dependency direction is enforced by lint/CI; zero circular imports.
- Features expose a public API; internals are not imported across slices.
- Server data has one owner (the query cache); no duplicated copies in a global store.
- Shareable state lives in the URL.
- The initial bundle contains only what the first route needs.
- Each boundary rule has a rationale; exceptions are documented and few.
- New team members can place code correctly using the decision table.

## 9. Verification and Testing

- `madge --circular` returns no cycles; `depcruise` reports no violations.
- Bundle analysis shows route-level splits with no duplicate dependencies.
- A test asserts that a feature's internals are not importable from outside (lint rule test).
- Adding a new feature requires no edits to unrelated features (verify by implementing one).
- Deleted features leave no orphaned imports (`knip`, `ts-prune`).

## 10. Security Considerations

- Server-only code (secrets, DB access) must never be reachable from client bundles; enforce with `server-only` imports and bundle scans.
- The API client is the single place for auth handling—avoid ad-hoc `fetch` calls that skip token refresh or CSRF headers.
- Client-side route guards are UX, not security; the server must authorize every request.
- Micro-frontends multiply supply-chain and trust boundaries: each remote can run arbitrary code in your page—require integrity, CSP, and version pinning.
- Environment variables prefixed for the client are public; audit before build.
- Third-party widgets loaded at runtime should be sandboxed in iframes where possible.

## 11. Failure Handling

- **Boundary violations feel bureaucratic:** tighten only where churn is high; allow a documented escape hatch for urgent fixes with a cleanup ticket.
- **Global store becomes a dumping ground:** move server data to the query cache and UI state to components; keep the store to a handful of slices.
- **Duplicate dependencies in bundles:** align versions in the workspace and dedupe; check with the analyzer.
- **Micro-frontend overhead exceeds benefit:** consolidate into a modular monolith; independent deploys are rarely worth the runtime cost.
- **Feature flags create dead code:** schedule removal after full rollout (`knip` detects unused exports).

## 12. Expected Deliverables

1. Layer diagram and dependency rules.
2. Folder structure with feature slices.
3. State ownership matrix.
4. Data layer implementation (client, validation, errors).
5. Boundary enforcement configuration in CI.
6. Bundle splitting strategy and analysis.
7. Architecture decision record and onboarding doc.

## 13. References

- Feature-Sliced Design — https://feature-sliced.design/
- `eslint-plugin-boundaries` — https://github.com/javierbrea/eslint-plugin-boundaries
- `dependency-cruiser` — https://github.com/sverweij/dependency-cruiser
- madge — https://github.com/pahen/madge
- TanStack Query — https://tanstack.com/query/latest/docs/framework/react/overview
- Nx module boundaries — https://nx.dev/features/enforce-module-boundaries
- "Frontend Architecture for Design Systems" (Micah Godbolt).
