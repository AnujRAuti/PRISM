---
name: typescript-frontend-engineering
description: Use TypeScript as a design tool on the frontend—strict config, discriminated unions for state, typed API boundaries, and type-safe patterns that eliminate whole bug classes.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# TypeScript Frontend Engineering

## 1. Purpose

Use the type system to make invalid states unrepresentable and integration errors compile-time failures. Frontend TypeScript is often degraded to `any` with optional props everywhere, which removes exactly the safety it was adopted for. This skill covers strict configuration, modelling UI state with discriminated unions, typed API contracts with runtime validation, generics that earn their place, and the escape hatches used responsibly.

**Scope:** your own TypeScript projects. Types are erased at runtime—anything from the network, storage, or user input still needs runtime validation.

## 2. Activation Conditions

- Setting up a TypeScript frontend project or tightening an existing one.
- `any` and non-null assertions (`!`) are spreading.
- UI shows impossible states (loading and error simultaneously).
- API responses drift from frontend expectations.
- Keywords: TypeScript, strict mode, discriminated union, generics, type guards, Zod, unknown, satisfies, type safety, tsconfig.

## 3. When Not to Use

- Plain JavaScript codebases where migration is out of scope (still apply runtime validation).
- Type gymnastics that do not catch real bugs (complex conditional types for their own sake).

## 4. Required Context

1. `tsconfig.json` current settings and compiler version.
2. Framework (React, Vue, Svelte) and its typing conventions.
3. API schema source (OpenAPI, GraphQL, handwritten).
4. Build tool (Vite, Next, tsc) and whether type-checking happens in CI.
5. Team conventions for types vs. interfaces, file layout.

## 5. Operating Procedure

1. **Enable strict mode fully**: `strict: true`, plus `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `verbatimModuleSyntax`.
2. **Model state as discriminated unions** so impossible combinations cannot be constructed.
3. **Use `unknown` at boundaries**, then narrow with a runtime validator; never `any`.
4. **Derive types from the source of truth**: `z.infer<typeof Schema>` for API payloads, `satisfies` for config objects.
5. **Make nullable and optional meaning distinct**: `field?: T` (may be absent) vs. `field: T | null` (present but null).
6. **Prefer precise unions over `string`** for identifiers and enumerated values.
7. **Write generics when they express a real relationship** between inputs and outputs; otherwise use concrete types.
8. **Avoid type assertions (`as`)**; when unavoidable, isolate them in a single parse/validate function.
9. **Add exhaustiveness checks** for union switches.
10. **Type-check in CI** with `tsc --noEmit` and lint rules that ban `any`/`!`.
11. **Document escape hatches** with a comment explaining why and a ticket to remove.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Compiler | TypeScript 5.x, `tsc --noEmit` |
| Runtime validation | Zod, Valibot, ArkType |
| API types | `openapi-typescript`, GraphQL codegen, `ts-rest` |
| Lint | typescript-eslint (`no-explicit-any`, `no-non-null-assertion`, `strict-boolean-expressions`) |
| Testing types | `expect-type`, `tsd`, `vitest` type tests |

## 7. Practical Implementation

**Strict `tsconfig.json` base:**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
```

**Discriminated union for request state:**

```ts
type RequestState<T> =
  | {status: "idle"}
  | {status: "loading"}
  | {status: "success"; data: T}
  | {status: "error"; error: string; retryable: boolean};

function render<T>(state: RequestState<T>, view: (data: T) => JSX.Element) {
  switch (state.status) {
    case "idle":    return <p>Ready</p>;
    case "loading": return <Spinner />;
    case "success": return view(state.data);
    case "error":   return <ErrorBox message={state.error} retryable={state.retryable} />;
    default: {
      const _exhaustive: never = state;      // compile error if a case is added but unhandled
      return _exhaustive;
    }
  }
}
```

**Runtime validation at the boundary with Zod:**

```ts
import { z } from "zod";

export const OrderSchema = z.object({
  id: z.string().uuid(),
  totalCents: z.number().int().nonnegative(),
  status: z.enum(["pending", "paid", "shipped", "cancelled"]),
  createdAt: z.string().datetime(),
});
export type Order = z.infer<typeof OrderSchema>;

export async function fetchOrder(id: string): Promise<Order> {
  const res = await fetch(`/api/orders/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json: unknown = await res.json();        // unknown, not any
  return OrderSchema.parse(json);                // throws on contract drift
}
```

**Branded types to stop ID mix-ups:**

```ts
declare const brand: unique symbol;
type Brand<T, B extends string> = T & {readonly [brand]: B};

export type UserId = Brand<string, "UserId">;
export type OrderId = Brand<string, "OrderId">;

export const asUserId = (v: string): UserId => v as UserId;   // only at validated boundaries

function getOrder(userId: UserId, orderId: OrderId) { /* ... */ }
// getOrder(orderId, userId) -> compile error
```

**`satisfies` for config without widening:**

```ts
const ROUTES = {
  home: "/",
  orders: "/orders",
  orderDetail: (id: string) => `/orders/${encodeURIComponent(id)}`,
} satisfies Record<string, string | ((...a: never[]) => string)>;

type RouteKey = keyof typeof ROUTES;   // "home" | "orders" | "orderDetail"
```

**Precise optionality:**

```ts
type Profile = {
  name: string;
  nickname?: string;          // may be omitted entirely
  deletedAt: string | null;   // always present; null means "not deleted"
};
```

**Type-level tests:**

```ts
import { expectTypeOf } from "expect-type";

expectTypeOf(OrderSchema.parse).returns.toEqualTypeOf<Order>();
expectTypeOf<RequestState<number>["status"]>().toEqualTypeOf<"idle" | "loading" | "success" | "error">();
```

**CI enforcement:**

```bash
npx tsc --noEmit
npx eslint . --max-warnings=0
```

```json
{
  "rules": {
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/no-non-null-assertion": "error",
    "@typescript-eslint/consistent-type-imports": "error"
  }
}
```

## 8. Quality Standards

- Strict mode plus the additional safety flags are enabled.
- No `any` in application code; `unknown` at boundaries with runtime validation.
- Impossible states are unrepresentable (discriminated unions).
- Types derive from schemas, not hand-written duplicates.
- Assertions are isolated and documented.
- Union switches are exhaustive.
- CI fails on type errors and banned patterns.

## 9. Verification and Testing

- `tsc --noEmit` passes with zero errors.
- Type tests (`expect-type`) cover critical inference relationships.
- Runtime validation tests: malformed API payloads are rejected with clear errors.
- Deliberate break test: change a schema field and confirm consumers fail to compile (proving the type is actually used).
- Lint run shows no `any`/`!` in `src`.

## 10. Security Considerations

- Types do not validate at runtime—always parse untrusted data (network, `localStorage`, `postMessage`, URL params).
- Do not use types to model authorization ("admin" in a union is not a permission check); enforce on the server.
- `as` casts on API responses hide contract drift that may include unexpected fields; use strict schemas with `additionalProperties` handling.
- `eval`/`Function` constructors and `dangerouslySetInnerHTML` bypass type safety entirely.
- Keep dependencies typed and pinned; `@types/*` packages are supply-chain surface.

## 11. Failure Handling

- **Too many errors after enabling strict:** migrate file-by-file with a `// @ts-expect-error` count dashboard (and a rule to keep the count falling).
- **Type is huge and slow:** simplify with `interface` for public shapes, and avoid deep conditional types in hot paths; profile with `tsc --extendedDiagnostics`.
- **Library types conflict:** align dependency versions, use `skipLibCheck`, and isolate the integration behind a narrow adapter.
- **`noUncheckedIndexedAccess` is noisy:** use `.at()` with explicit checks, or `Map`/records with defined keys.
- **Third-party untyped libs:** write a minimal `.d.ts` with only the API you use, rather than `declare module "x": any`.

## 12. Expected Deliverables

1. Strict `tsconfig` and lint configuration.
2. Typed domain models with discriminated unions.
3. Boundary validation schemas and parse functions.
4. Generated API types (if applicable).
5. Type tests for critical relationships.
6. Migration notes and remaining escape hatches.

## 13. References

- TypeScript handbook — https://www.typescriptlang.org/docs/handbook/intro.html
- `tsconfig` reference — https://www.typescriptlang.org/tsconfig
- Zod — https://zod.dev/
- typescript-eslint — https://typescript-eslint.io/rules/
- `openapi-typescript` — https://github.com/openapi-ts/openapi-typescript
- Matt Pocock, Total TypeScript — https://www.totaltypescript.com/
- "Making Impossible States Impossible" (Richard Feldman) — https://www.youtube.com/watch?v=IcgmSRJHu_8
