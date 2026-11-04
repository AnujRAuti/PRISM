---
name: react-development
description: Build React applications correctly—component boundaries, state placement, effects discipline, memoization where measured, and accessibility-aware markup.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: medium
---

# React Development

## 1. Purpose

Write React code that stays maintainable as it grows: components with clear responsibilities, state placed at the right level, effects used only for synchronization with external systems, and performance work based on profiler evidence. This skill targets the recurring defects: derived state stored redundantly, effects doing work that belongs in event handlers, unstable keys, and prop drilling that should be context or composition.

**Scope:** React applications you own. Frontend code runs in users' browsers—treat all data from APIs, URLs, and `localStorage` as untrusted.

## 2. Activation Conditions

- Building or refactoring React components.
- State is duplicated, out of sync, or props are drilled through many levels.
- Effects fire too often or in the wrong order.
- List rendering causes remounts or lost input focus.
- Keywords: React, hooks, useEffect, useState, useMemo, useCallback, context, component, re-render, keys, Suspense, error boundary.

## 3. When Not to Use

- Next.js routing/server components (use nextjs-development) — though most React rules still apply.
- Framework-agnostic architecture decisions (use frontend-architecture).
- Visual design systems (use design-system-engineering).

## 4. Required Context

1. React version (18/19) and whether React Compiler is enabled.
2. State management in use (local state, context, Redux/Zustand/TanStack Query).
3. Rendering target: SPA, SSR, streaming.
4. Existing component conventions and file layout.
5. Accessibility requirements and supported browsers.

## 5. Operating Procedure

1. **Sketch the component tree** by responsibility, not by DOM structure.
2. **Place state at the lowest common owner**. Lift only when siblings must share; otherwise keep it local.
3. **Derive, don't duplicate**: compute values during render from props/state instead of storing copies in state.
4. **Use effects only to synchronize with external systems** (network subscriptions, DOM APIs, timers). Event handlers do user-triggered work.
5. **Keep effects honest**: correct dependency arrays, cleanup functions, and guards against race conditions (abort controllers, ignore flags).
6. **Use stable keys** (entity IDs), never array indices for reorderable/filterable lists.
7. **Compose rather than drill**: `children` slots and context for cross-cutting values.
8. **Memoize only measured hot paths** (`React.memo`, `useMemo`, `useCallback`); premature memoization adds noise.
9. **Handle all UI states**: loading, empty, error, success, and partial.
10. **Add error boundaries** at route/section level so a component crash does not blank the app.
11. **Verify with React DevTools Profiler** and fix the actual costly renders.

## 6. Tools and Technologies

| Concern | Tools |
|---|---|
| Scaffolding | Vite, Next.js |
| Data fetching | TanStack Query, SWR |
| State | `useState`/`useReducer`, Zustand, Redux Toolkit, Jotai |
| Forms | React Hook Form, Zod validation |
| Testing | Vitest + React Testing Library, Playwright |
| Lint | ESLint (`eslint-plugin-react-hooks`), TypeScript |
| Profiling | React DevTools Profiler, `<Profiler>` API |

## 7. Practical Implementation

**Derived state vs. duplicated state:**

```tsx
// BAD: duplicated state drifts out of sync
const [items, setItems] = useState<Item[]>([]);
const [count, setCount] = useState(0);

// GOOD: derive during render
const [items, setItems] = useState<Item[]>([]);
const count = items.length;
const total = items.reduce((s, i) => s + i.priceCents, 0);
```

**Effect with cleanup and race guard:**

```tsx
useEffect(() => {
  const controller = new AbortController();

  async function load() {
    try {
      const res = await fetch(`/api/orders?cursor=${cursor}`, {signal: controller.signal});
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setOrders((prev) => [...prev, ...(await res.json()).items]);
      setStatus("idle");
    } catch (err) {
      if ((err as Error).name !== "AbortError") setStatus("error");
    }
  }

  setStatus("loading");
  load();
  return () => controller.abort();          // cancels on unmount or cursor change
}, [cursor]);
```

**Custom hook that encapsulates the pattern:**

```tsx
function useOrders(cursor: string | null) {
  const [state, setState] = useState<{status: "idle" | "loading" | "error"; items: Order[]}>({
    status: "loading",
    items: [],
  });

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const url = cursor ? `/api/orders?cursor=${cursor}` : "/api/orders";
        const res = await fetch(url, {signal: controller.signal});
        if (!res.ok) throw new Error(String(res.status));
        const body = (await res.json()) as {items: Order[]};
        setState((s) => ({status: "idle", items: [...s.items, ...body.items]}));
      } catch (e) {
        if ((e as Error).name !== "AbortError") setState((s) => ({...s, status: "error"}));
      }
    })();
    return () => controller.abort();
  }, [cursor]);

  return state;
}
```

**Stable keys and correct list mutation:**

```tsx
function OrderList({orders}: {orders: Order[]}) {
  return (
    <ul aria-label="Orders">
      {orders.map((o) => <OrderRow key={o.id} order={o} />)}   {/* id, not index */}
    </ul>
  );
}

// Updating one item without replacing the whole array's identity
setOrders((prev) => prev.map((o) => (o.id === updated.id ? updated : o)));
```

**Reducer for related state transitions:**

```tsx
type State = {status: "idle" | "submitting" | "done" | "error"; error?: string};
type Action = {type: "submit"} | {type: "success"} | {type: "failure"; message: string};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "submit":   return {status: "submitting"};
    case "success":  return {status: "done"};
    case "failure":  return {status: "error", error: action.message};
  }
}
```

**Error boundary:**

```tsx
import { Component, type ReactNode } from "react";

export class SectionBoundary extends Component<{children: ReactNode; fallback: ReactNode},
                                              {failed: boolean}> {
  state = {failed: false};
  static getDerivedStateFromError() { return {failed: true}; }
  componentDidCatch(error: Error, info: {componentStack: string}) {
    reportError({message: error.message, stack: info.componentStack});  // your telemetry
  }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
```

**Profiler usage:**

```tsx
<Profiler id="OrderList" onRender={(id, phase, actualDuration) => {
  if (actualDuration > 16) console.debug("slow render", id, phase, actualDuration.toFixed(1));
}}>
  <OrderList orders={orders} />
</Profiler>
```

**Testing a component's behavior (not internals):**

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

test("submits the form and shows a confirmation", async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(<CheckoutForm onSubmit={onSubmit} />);
  await userEvent.type(screen.getByLabelText(/email/i), "a@example.com");
  await userEvent.click(screen.getByRole("button", {name: /pay/i}));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({email: "a@example.com"}));
  expect(await screen.findByRole("status")).toHaveTextContent(/confirmed/i);
});
```

## 8. Quality Standards

- No state that can be derived is stored.
- Effects have correct dependencies and cleanup; no "run once" hacks with empty arrays when data is involved.
- Lists use stable keys; no index keys on reorderable data.
- Components render all relevant states (loading/empty/error).
- Accessibility: semantic elements, labels, focus management, keyboard operation.
- Memoization exists only where profiling justified it.
- No `dangerouslySetInnerHTML` without sanitization.
- TypeScript props are explicit; no `any` in component APIs.

## 9. Verification and Testing

```bash
npm run lint && npx tsc --noEmit && npm test -- --run
npx playwright test tests/e2e/checkout.spec.ts
```

Tests: user-visible behavior via Testing Library (roles/labels, not class names); effect cancellation covered by unmount during a pending fetch; error boundary tested with a throwing child; render-count assertions only where performance matters; a11y checks with `jest-axe`/`vitest-axe`.

## 10. Security Considerations

- Never inject untrusted HTML; if unavoidable, sanitize with DOMPurify and a strict allowlist.
- Do not put secrets or tokens in client bundles, `localStorage`, or URLs; prefer `HttpOnly` cookies for session tokens.
- Escape user content in attributes and URLs (`javascript:` URLs are an XSS vector).
- Validate redirect targets (open-redirect) before `window.location` changes.
- Third-party scripts run with full page privileges; use SRI and a CSP.
- Treat API responses as untrusted: validate with a schema (Zod) before rendering.

## 11. Failure Handling

- **Infinite render loop:** setState in render or an effect without stable dependencies—move logic to handlers or memoize.
- **Stale data after navigation:** missing abort/cleanup; use cancellation and cache invalidation (TanStack Query).
- **Input loses focus on every keystroke:** component identity changes—check keys and component definitions inside render.
- **StrictMode double-effects:** expected in development; ensure effects are idempotent and clean up properly.
- **Slow list rendering:** virtualize (`@tanstack/react-virtual`) rather than micro-memoizing.

## 12. Expected Deliverables

1. Component tree and state placement notes.
2. Implemented components with typed props.
3. Custom hooks for shared logic.
4. Tests covering states and interactions.
5. Profiler evidence for any memoization.
6. Accessibility notes (roles, labels, focus).

## 13. References

- React documentation — https://react.dev/
- "You Might Not Need an Effect" — https://react.dev/learn/you-might-not-need-an-effect
- React DevTools Profiler — https://react.dev/learn/react-developer-tools
- Testing Library — https://testing-library.com/docs/react-testing-library/intro/
- TanStack Query — https://tanstack.com/query/latest/docs/framework/react/overview
- WCAG 2.2 — https://www.w3.org/TR/WCAG22/
