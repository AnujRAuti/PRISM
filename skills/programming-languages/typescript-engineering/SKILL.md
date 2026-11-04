---
name: typescript-engineering
description: Write TypeScript that is type-safe at the edges—strict mode, discriminated unions, no unsafe casts, runtime validation, and sound generics.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: medium
---

# TypeScript Engineering

## 1. Purpose

Use TypeScript to eliminate whole classes of runtime bugs, not to decorate JavaScript with annotations that lie. The common failure mode is a codebase that compiles under `strict: false`, is riddled with `as`, `any`, and `!`, and still crashes on `undefined` because the types describe an API contract nobody validated. This skill covers strict configuration, union modelling, safe narrowing, runtime validation at boundaries, and generic design that stays readable.

**Scope:** your own source and type packages. `@types/*` and build plugins execute at install/build time: pin and audit dependencies, and never install a typings package from an untrusted scope.

## 2. Activation Conditions

- New TypeScript service, library, CLI, or frontend.
- Type errors suppressed with `any`/`as`/`@ts-ignore`.
- `undefined is not a function` at runtime despite a clean compile.
- API responses typed by hand and drifting from reality.
- Migrating JavaScript to TypeScript incrementally.
- Keywords: TypeScript, tsconfig, strict, noUncheckedIndexedAccess, discriminated union, satisfies, unknown, zod, generics, type guards, declaration files, project references, `as const`.

## 3. When Not to Use

- Plain JavaScript with no build step and no team-wide type discipline (adding TS partially can be worse than not at all).
- Type-level puzzles that cost more comprehension than they save (prefer simpler types plus tests).
- Framework-specific rendering questions (use the frontend skills).

## 4. Required Context

1. Runtime: Node version, browser targets, bundler, or edge runtime.
2. Module system (ESM/CJS) and build pipeline (`tsc`, `tsup`, `esbuild`, `vite`).
3. Existing tsconfig and strictness.
4. Boundary sources: HTTP APIs, env vars, JSON files, `postMessage`, storage.
5. Testing framework and type-testing setup.

## 5. Operating Procedure

1. **Enable full strictness** in `tsconfig.json`: `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `noUnusedLocals`/`Parameters`.
2. **Ban escape hatches by lint rule**: `@typescript-eslint/no-explicit-any`, `no-non-null-assertion`, `consistent-type-assertions`, and `@ts-ignore` (allow `@ts-expect-error` with a written reason).
3. **Model states as discriminated unions**, not as objects with many optional fields and booleans.
4. **Validate at every runtime boundary** with a schema library (zod, valibot, arktype) and derive types from the schema—one source of truth.
5. **Use `unknown` for untrusted data**, then narrow with type guards or schema parsing; never `any`.
6. **Prefer narrowing to casting**: `in`, `typeof`, `instanceof`, `Array.isArray`, and user-defined type predicates.
7. **Use `satisfies` for config objects** to check shape without widening the inferred literal types.
8. **Keep generics honest**: constrain them (`<T extends { id: string }>`), avoid type parameters used once, and prefer inference over explicit instantiation.
9. **Make exports explicit** with `exports` maps, and publish declaration files (`declaration: true`) for libraries.
10. **Use project references / `isolatedDeclarations`** for large repos to keep build and type-check times sane.
11. **Type-test the tricky parts** with `expect-type` or `tsd`, and run `tsc --noEmit` in CI.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Compiler | `tsc` 5.x, `tsc --build` project references |
| Schema validation | zod, valibot, arktype, TypeBox |
| Linting | ESLint + `typescript-eslint` (typed rules), Biome |
| Formatting | Prettier, Biome |
| Build | `tsup`/`esbuild`, `vite`, `tsc` for libraries |
| Type tests | `expect-type`, `tsd`, `vitest` type assertions |
| Runtime tests | Vitest, Jest, `node --test` |
| API typing | OpenAPI → `openapi-typescript`, GraphQL codegen |

## 7. Practical Implementation

**Strict `tsconfig.json` (Node 22 + ESM, with a browser override):**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noPropertyAccessFromIndexSignature": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": "src",
    "resolveJsonModule": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["dist", "node_modules"]
}
```

**Discriminated unions instead of optional-field soup:**

```ts
// BAD: every caller must remember which fields are valid together
// type Order = { status: string; paidAt?: Date; declineCode?: string; refundedAt?: Date };

export type Order =
  | { readonly status: "draft"; readonly id: string }
  | { readonly status: "placed"; readonly id: string; readonly placedAt: Date }
  | { readonly status: "paid"; readonly id: string; readonly placedAt: Date; readonly paidAt: Date }
  | { readonly status: "declined"; readonly id: string; readonly declineCode: string }
  | { readonly status: "refunded"; readonly id: string; readonly refundedAt: Date };

const MS_PER_DAY = 86_400_000;

export function ageInDays(order: Order, now: Date): number {
  switch (order.status) {
    case "draft":
      return 0;
    case "placed":
      return Math.floor((now.getTime() - order.placedAt.getTime()) / MS_PER_DAY);
    case "paid":
    case "refunded":
      return Math.floor((now.getTime() - order.placedAt.getTime()) / MS_PER_DAY);
    case "declined":
      return -1;
    default: {
      // Exhaustiveness check: adding a variant becomes a compile error here.
      const never: never = order;
      throw new Error(`unhandled status: ${JSON.stringify(never)}`);
    }
  }
}
```

**Runtime validation at the boundary; derive the type from the schema:**

```ts
import { z } from "zod";

const OrderLineSchema = z.object({
  productId: z.number().int().positive(),
  quantity: z.number().int().positive().max(999),
  unitPriceCents: z.number().int().nonnegative(),
});

export const OrderSchema = z.object({
  id: z.string().uuid(),
  status: z.enum(["draft", "placed", "paid", "declined", "refunded"]),
  createdAt: z.coerce.date(),
  lines: z.array(OrderLineSchema).min(1).max(200),
});
export type Order = z.infer<typeof OrderSchema>;

// HTTP boundary: unknown JSON -> validated domain object or a typed error
export async function fetchOrder(id: string, signal: AbortSignal): Promise<Order> {
  const res = await fetch(`https://api.example.com/v1/orders/${encodeURIComponent(id)}`, { signal });
  if (!res.ok) throw new HttpError(res.status, await res.text());

  const raw: unknown = await res.json();       // untrusted: keep it unknown
  const parsed = OrderSchema.safeParse(raw);
  if (!parsed.success) {
    throw new ContractError("order response failed validation", parsed.error.issues);
  }
  return parsed.data;                          // typed and verified at runtime
}

export class HttpError extends Error {
  constructor(readonly status: number, readonly body: string) {
    super(`HTTP ${status}`);
    this.name = "HttpError";
  }
}

export class ContractError extends Error {
  constructor(message: string, readonly issues: z.ZodIssue[]) {
    super(`${message}: ${issues.map((i) => i.path.join(".")).join(", ")}`);
    this.name = "ContractError";
  }
}
```

**`unknown` + type predicates instead of `any` and casts:**

```ts
type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

// Narrowing helper: no cast, works on untrusted input
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function getString(source: unknown, key: string): string | undefined {
  if (!isRecord(source)) return undefined;
  const value = source[key];
  return typeof value === "string" ? value : undefined;
}

// BAD: silently trusts the shape and crashes later
// const order = (await res.json()) as Order;

// GOOD: prove the shape before use
export function assertHasId(value: unknown): asserts value is { id: string } {
  if (!isRecord(value) || typeof value["id"] !== "string" || value["id"] === "") {
    throw new TypeError("expected an object with a non-empty string id");
  }
}
```

**`satisfies` for config without losing literal types:**

```ts
const ROUTES = {
  orders: "/v1/orders",
  payments: "/v1/payments",
} as const satisfies Record<string, `/${string}`>;

type RouteName = keyof typeof ROUTES;      // "orders" | "payments"
export function urlFor(name: RouteName): string {
  return `https://api.example.com${ROUTES[name]}`;
}

// env parsing: validated once at startup, typed everywhere after
const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().min(1).max(65535).default(8080),
  DATABASE_URL: z.string().url(),
  REQUEST_TIMEOUT_MS: z.coerce.number().int().positive().default(3000),
});
export type Env = z.infer<typeof EnvSchema>;

export function loadEnv(source: NodeJS.ProcessEnv = process.env): Env {
  const parsed = EnvSchema.safeParse(source);
  if (!parsed.success) {
    throw new Error(`invalid environment: ${parsed.error.issues.map((i) => i.path.join(".")).join(", ")}`);
  }
  return parsed.data;
}
```

**Generics that stay readable and constrained:**

```ts
// Constrained generic with a mapped return type; no `any`, no lost inference
export async function mapById<T extends { id: string }, R>(
  items: readonly T[],
  fn: (item: T) => Promise<R>,
  concurrency = 8,
): Promise<Map<string, R>> {
  const results = new Map<string, R>();
  const queue = [...items];

  async function worker(): Promise<void> {
    for (;;) {
      const item = queue.shift();
      if (item === undefined) return;
      results.set(item.id, await fn(item));
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, () => worker()),
  );
  return results;
}

// Result type for expected failures instead of exceptions everywhere
export type Result<T, E = Error> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly error: E };

export async function attempt<T>(fn: () => Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, value: await fn() };
  } catch (error: unknown) {
    return { ok: false, error: error instanceof Error ? error : new Error(String(error)) };
  }
}
```

**Package `exports` map so consumers cannot deep-import internals:**

```json
{
  "name": "@acme/orders",
  "type": "module",
  "engines": { "node": ">=20.11" },
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    },
    "./testing": {
      "types": "./dist/testing.d.ts",
      "import": "./dist/testing.js"
    }
  },
  "types": "./dist/index.d.ts",
  "sideEffects": false
}
```

**Type tests that fail the build when inference regresses:**

```ts
// tests/types.test-d.ts
import { expectTypeOf } from "expect-type";
import { OrderSchema, type Order } from "../src/order.js";

expectTypeOf<Order["status"]>().toEqualTypeOf<"draft" | "placed" | "paid" | "declined" | "refunded">();
expectTypeOf(OrderSchema.parse({})).not.toBeAny();
```

```bash
npx tsc --noEmit                       # type-check everything
npx tsc --build --clean && npx tsc --build   # project references
npx vitest --typecheck                 # run type tests alongside unit tests
npx eslint . --report-unused-disable-directives
```

## 8. Quality Standards

- `strict: true` plus `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`; no per-file `// @ts-nocheck`.
- Zero `any`; `@ts-expect-error` only with an adjacent justification comment, never `@ts-ignore`.
- No non-null assertions (`!`) on values that can genuinely be absent; narrow or validate instead.
- Every runtime boundary (HTTP, env, storage, message bus) is parsed by a schema.
- Domain state is modelled with discriminated unions; exhaustive `switch` with a `never` check.
- Type assertions (`as`) are limited to justified narrowing where a guard is impossible, and carry a comment.
- Public library APIs export types, use `exports` maps, and have declaration files.
- Generics are constrained and used more than once; no type-parameter puzzles without type tests.
- `tsc --noEmit` and typed lint rules pass in CI with zero errors.

## 9. Verification and Testing

```bash
npx tsc --noEmit && npx eslint . && npx vitest run --coverage && npx vitest --typecheck
```

- Unit tests for logic; schema tests for boundary parsing with valid, invalid, and adversarial payloads.
- Type tests (`expect-type`) for inferred return types and union narrowing.
- Contract test: replay recorded API responses through the schema and fail on drift.
- Negative test: confirm invalid env vars and malformed payloads produce actionable errors at startup/request time, not deep in business logic.
- Check emitted `.d.ts` output for accidental `any` leaks: `grep -r '\bany\b' dist/*.d.ts`.

## 10. Security Considerations

- Types are erased at runtime: never rely on a TypeScript type to sanitize user input, enforce authorization, or validate a request body without runtime checks.
- Prototype pollution: reject `__proto__`/`constructor` keys when merging untrusted objects; prefer `Object.create(null)` maps or `Map`.
- `eval`, `new Function`, and `Object.assign` on untrusted data are code-injection vectors; avoid them.
- Never render unvalidated strings as HTML; sanitize with a vetted library (DOMPurify) or use text nodes/framework escaping.
- Dependencies: `npm audit`/`osv-scanner` in CI, lockfile committed, `--ignore-scripts` for installs where feasible, and scoped registry allowlists.
- Secrets must not be baked into client bundles: anything referenced by frontend code is public; keep server-only env reads in server modules.
- Validate and bound payload sizes before schema parsing to avoid CPU/memory exhaustion on deeply nested JSON.
- Avoid `sourceMappingURL` exposure of source in production if it reveals internal logic or secrets.

## 11. Failure Handling

- **Property is possibly `undefined` everywhere after enabling `noUncheckedIndexedAccess`:** this is real risk from array/index access; handle it with `.at()` checks, non-empty tuple types, or explicit guards rather than reverting the flag.
- **`any` leaks through third-party typings:** wrap the library in a small typed adapter module with schema validation at the boundary; keep the `any` in one audited place.
- **Slow `tsc`:** enable `skipLibCheck`, use project references, split large unions, and check for pathological type inference with `--diagnostics`.
- **`TS2589: Type instantiation is excessively deep`:** simplify the generic (fewer recursive conditional types) or add explicit annotations at the call site.
- **Compiles but crashes at runtime:** an `as` or a missing boundary validation; add a schema at the entry point and delete the cast.

## 12. Expected Deliverables

1. `tsconfig.json` with full strictness and project-reference structure.
2. ESLint/typed-lint configuration banning unsafe casts and `any`.
3. Schema definitions for every runtime boundary with derived types.
4. Domain model expressed as discriminated unions with exhaustive handling.
5. Package `exports` map and declaration files for libraries.
6. Type tests plus unit/integration tests.
7. Dependency and bundle hygiene checks in CI.

## 13. References

- TypeScript handbook — https://www.typescriptlang.org/docs/handbook/intro.html
- `tsconfig` reference — https://www.typescriptlang.org/tsconfig/
- Typescript-eslint typed rules — https://typescript-eslint.io/rules/
- Zod documentation — https://zod.dev/
- `satisfies` operator — https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-9.html
- Node.js `exports` field — https://nodejs.org/api/packages.html#package-entry-points
- `expect-type` — https://github.com/mmkal/expect-type
- TypeScript performance wiki — https://github.com/microsoft/TypeScript/wiki/Performance
- OWASP prototype pollution guidance — https://cheatsheetseries.owasp.org/
