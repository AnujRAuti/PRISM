---
name: javascript-engineering
description: Write modern JavaScript with confidence—ES modules, async correctness, event-loop awareness, ESM/CJS interop, and Node runtime discipline.
metadata:
  domain: programming-languages
  version: 1.0.0
  risk: medium
---

# JavaScript Engineering

## 1. Purpose

Write JavaScript that is predictable across environments and does not melt under async load. The recurring problems are well known: floating promises, `var`-scoped loops, `this` binding surprises, mutation of shared objects, `==` coercion, and dependencies pulled in for four lines of code. This skill covers modern syntax and modules, async patterns on both browser and Node, event-loop realities, error handling, and dependency hygiene.

**Scope:** your own code and packages. `npm install` runs lifecycle scripts that execute arbitrary code: pin versions (lockfile), review new dependencies, disable install scripts where possible, and never install from an unvetted tarball.

## 2. Activation Conditions

- New JS codebase, library, CLI, or Node service.
- Unhandled promise rejections, race conditions, or callback spaghetti.
- ESM/CommonJS interop errors (`ERR_REQUIRE_ESM`, `require() of ES Module`).
- Bundle size or dependency count concerns.
- Keywords: JavaScript, ES modules, ESM, CommonJS, async/await, promise, event loop, microtask, Node.js, npm, pnpm, floating promises, optional chaining, AbortController.

## 3. When Not to Use

- TypeScript-first codebases (use typescript-frontend-engineering) except for quick scripts.
- Browser UI architecture (use frontend-architecture / react-development).
- Compiled-to-JS ecosystems that deserve their own tooling review.

## 4. Required Context

1. Runtime targets: browsers (which ones), Node version, edge runtimes.
2. Module system in use and build tooling.
3. Package manager and lockfile policy.
4. Async surfaces: HTTP, file system, streaming.
5. Existing lint/format configuration.

## 5. Operating Procedure

1. **Use ES modules everywhere** (`"type": "module"` in `package.json`) and `import`/`export`; understand that CommonJS interop requires `createRequire` when unavoidable.
2. **Declare with `const` by default**, `let` only when reassigned, and never `var`.
3. **Always handle promises**: `await` inside `try/catch`, `.catch()` on fire-and-forget with intent, and a global `unhandledRejection` handler that logs and exits for services.
4. **Never use `forEach` with async callbacks**: it ignores returned promises. Use `for...of` for sequential work or `Promise.all` with bounded concurrency for parallel work.
5. **Cancel asynchronous work**: `AbortController` for fetch and long operations; clear timers and listeners on teardown.
6. **Understand the event loop**: microtasks (promises) run before macrotasks (timers/I/O); never do CPU-heavy work on the main thread or the request loop — use workers or chunk the work.
7. **Compare with `===`**; use `Object.is` for edge cases; avoid truthiness tricks that treat `0`/`""` as absence when the value is meaningful.
8. **Avoid shared mutable state**: prefer pure functions, immutable updates (`structuredClone` for deep copies when needed), and `Object.freeze` for constants.
9. **Bound concurrency** for bulk async work (do not `Promise.all` over 10,000 items).
10. **Keep dependencies minimal**: check bundle/install size, prefer platform APIs (`fetch`, `AbortSignal`, `crypto.randomUUID`), and audit for vulnerabilities.
11. **Configure one linter** (ESLint flat config) and a formatter (Prettier/Biome); run in CI with `--max-warnings=0`.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Runtime | Node.js LTS, Deno, Bun, edge runtimes |
| Packages | npm, pnpm, yarn; `npm ci` for reproducible installs |
| Lint/format | ESLint (flat config), Prettier, Biome |
| Test | `node:test`, vitest, jest |
| Async helpers | `AbortController`, `p-limit`, `Promise.allSettled` |
| Type checking (JS) | JSDoc + `tsc --checkJs` |
| Bundling | esbuild, Rollup, Vite |
| Security | `npm audit`, `osv-scanner`, Socket.dev |

## 7. Practical Implementation

**`package.json` with ESM, engines, and scripts:**

```json
{
  "name": "@acme/orders-cli",
  "version": "1.4.0",
  "type": "module",
  "engines": {"node": ">=20.11 <23"},
  "exports": {".": "./dist/index.js", "./types": "./dist/index.d.ts"},
  "files": ["dist"],
  "scripts": {
    "lint": "eslint . --max-warnings=0",
    "format:check": "prettier --check .",
    "test": "node --test --experimental-test-coverage",
    "build": "esbuild src/index.js --bundle --platform=node --format=esm --outfile=dist/index.js",
    "audit": "npm audit --audit-level=high && osv-scanner --lockfile=package-lock.json"
  }
}
```

**Correct async handling (no floating promises):**

```javascript
// BAD: forEach ignores the promise; errors vanish into unhandled rejections
items.forEach(async (item) => {
  await save(item);
});

// GOOD: sequential when order matters or the downstream is fragile
for (const item of items) {
  await save(item);
}

// GOOD: parallel with bounded concurrency
async function saveAll(items, {concurrency = 8} = {}) {
  const queue = [...items];
  const workers = Array.from({length: concurrency}, async () => {
    while (queue.length > 0) {
      const item = queue.shift();
      if (item === undefined) return;
      await save(item);
    }
  });
  await Promise.all(workers);
}

// GOOD: independent failures do not abort the batch
const results = await Promise.allSettled(items.map((i) => save(i)));
const failures = results.filter((r) => r.status === "rejected");
if (failures.length > 0) {
  console.error(`${failures.length} saves failed`, failures.map((f) => f.reason?.message));
}
```

**Cancellation with `AbortController` and timeouts:**

```javascript
export async function fetchQuote(sku, {timeoutMs = 2000, signal} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error("timeout")), timeoutMs);
  const onAbort = () => controller.abort(signal.reason);
  signal?.addEventListener("abort", onAbort, {once: true});

  try {
    const res = await fetch(`/quotes/${encodeURIComponent(sku)}`, {signal: controller.signal});
    if (!res.ok) {
      throw new Error(`quote failed: ${res.status} ${await res.text().catch(() => "")}`);
    }
    return await res.json();
  } finally {
    clearTimeout(timer);                     // always clean up the timer
    signal?.removeEventListener("abort", onAbort);
  }
}
```

**Error handling at the process boundary (Node service):**

```javascript
process.on("unhandledRejection", (reason) => {
  console.error(JSON.stringify({event: "unhandled_rejection", message: String(reason)}));
  // A service with an unknown broken promise is unsafe to keep serving.
  process.exitCode = 1;
  shutdown("unhandledRejection");
});

process.on("uncaughtException", (err) => {
  console.error(JSON.stringify({event: "uncaught_exception", message: err.message, stack: err.stack}));
  shutdown("uncaughtException");
});

async function shutdown(reason) {
  clearTimeout(shutdown.timer);
  await server.close();
  await pool.end();
  process.exit(1);
}

// Graceful shutdown on signals with a hard deadline
for (const sig of ["SIGTERM", "SIGINT"]) {
  process.on(sig, () => {
    shutdown.timer = setTimeout(() => process.exit(1), 25_000);
    shutdown(sig);
  });
}
```

**Event-loop awareness (avoid blocking the request path):**

```javascript
// BAD: CPU-bound JSON work on the main thread blocks every request
function expensiveNormalize(rows) {
  return rows.map((r) => ({...r, key: r.name.toLowerCase().replaceAll(" ", "-")}));
}

// GOOD: move heavy work to a worker thread, keep the loop responsive
import {Worker} from "node:worker_threads";

export function normalizeInWorker(rows) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./normalize.worker.js", import.meta.url), {
      workerData: rows,
    });
    worker.once("message", resolve);
    worker.once("error", reject);
    worker.once("exit", (code) => {
      if (code !== 0) reject(new Error(`worker exited with ${code}`));
    });
  });
}

// When parallelism is not needed, yield between chunks of large work
async function processChunked(items, chunk = 500) {
  for (let i = 0; i < items.length; i += chunk) {
    handle(items.slice(i, i + chunk));
    await new Promise((r) => setImmediate(r));   // let I/O and timers run
  }
}
```

**ESM/CommonJS interop (when a dependency is CJS-only):**

```javascript
import {createRequire} from "node:module";
const require = createRequire(import.meta.url);
const legacy = require("some-cjs-only-package");   // isolated to one module
```

**Equality, optional chaining, and defensive access:**

```javascript
// Avoid coercion: 0, "", false, and NaN have meaning
if (value === null || value === undefined) return defaultValue;

// Optional chaining + nullish coalescing, not truthiness
const status = order?.payment?.status ?? "unknown";

// Structured clone for deep copies of data (not functions/classes)
const snapshot = structuredClone(order);

// Freeze exported constants to prevent accidental mutation
export const LIMITS = Object.freeze({maxLines: 100, maxQuantity: 999});
```

**ESLint flat config enforcing the important rules:**

```javascript
// eslint.config.js
import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {ecmaVersion: 2024, sourceType: "module"},
    rules: {
      "no-var": "error",
      "prefer-const": "error",
      eqeqeq: ["error", "always"],
      "no-floating-decimal": "error",
      "no-return-await": "error",
      "require-atomic-updates": "error",
      "no-await-in-loop": "warn",         // intentional sequential loops get a disable + reason
      "no-unused-vars": ["error", {argsIgnorePattern: "^_"}],
      "no-console": ["warn", {allow: ["error", "warn"]}],
    },
  },
];
```

## 8. Quality Standards

- ES modules with explicit `type: "module"`; no mixed module systems in one package.
- `const` by default; no `var`; `===` for all comparisons.
- No floating promises: every promise is awaited, returned, or explicitly `.catch`-handled.
- Async loops use `for...of` or bounded `Promise.all`; `Array.forEach` never receives an async callback.
- Every long-running async operation accepts an `AbortSignal` and cleans up timers/listeners.
- CPU-heavy work runs in a worker or is chunked with yields.
- Lint and format pass in CI with zero warnings.
- Dependencies are locked, minimal, and audited in CI.
- Node services handle `unhandledRejection`/`uncaughtException` and shut down gracefully within a deadline.

## 9. Verification and Testing

```bash
node --test                       # built-in test runner
node --test --experimental-test-coverage
npm ci && npm audit --audit-level=high
npx eslint . --max-warnings=0 && npx prettier --check .
node --trace-warnings app.js       # surfaces poorly chained promises
```

- Test that an aborted request rejects and does not leave timers running (`process._getActiveHandles()` in a test).
- Load test an endpoint with heavy JSON to confirm the event loop is not blocked (measure event-loop lag).
- Verify ESM imports resolve in a clean install (`npm ci` in a container, run the built artifact).
- `node --check` on files during a fast pre-commit pass.

## 10. Security Considerations

- `npm install` executes lifecycle scripts: set `ignore-scripts=true` where possible, review new packages, and use a lockfile plus `npm ci`.
- Prototype pollution: never merge untrusted objects into `Object.prototype`; validate with a schema and use `Object.create(null)` for maps keyed by input.
- Avoid `eval`, `new Function`, and `innerHTML` with untrusted data; sanitize HTML with a library (e.g. DOMPurify) when rendering is required.
- `child_process.exec` with interpolated input is command injection; use `execFile`/`spawn` with argument arrays.
- `Math.random()` is not cryptographic: use `crypto.randomUUID()` / `crypto.getRandomValues`.
- Path traversal: resolve and verify paths stay within an allowed root before reading or writing files.
- Dependency confusion and typosquatting: use scoped names, a private registry for internal packages, and `npm audit`/`osv-scanner` in CI.
- Do not log tokens, cookies, or request bodies; redact structured logs.

## 11. Failure Handling

- **`ERR_REQUIRE_ESM`:** the package is ESM and the consumer uses `require`; upgrade the consumer or wrap with `createRequire`, and never mix within one module graph.
- **Silent failures in a batch:** an async callback inside `forEach` — convert to a bounded `Promise.all` and inspect `Promise.allSettled` results.
- **Event loop lag / timeouts under load:** CPU-bound synchronous work; move to a worker or chunk.
- **Memory growth:** unremoved listeners, unbounded caches, or accumulating promises; check with `--inspect` and heap snapshots.
- **Floating promise warnings in production logs:** `--trace-warnings` maps them to their origin; fix at the call site.

## 12. Expected Deliverables

1. `package.json` with ESM, engines, and scripts.
2. Lockfile and dependency policy.
3. Async conventions (await, cancellation, bounded concurrency).
4. Lint/format configuration enforced in CI.
5. Process-level error handling and graceful shutdown.
6. Worker offloading for CPU-heavy paths.
7. Security-audit and dependency-review pipeline.

## 13. References

- ECMAScript specification — https://tc39.es/ecma262/
- MDN JavaScript guide — https://developer.mozilla.org/en-US/docs/Web/JavaScript
- Node.js documentation — https://nodejs.org/docs/latest/api/
- Node.js event loop guide — https://nodejs.org/en/learn/asynchronous-work/event-loop-timelines
- ESLint flat config — https://eslint.org/docs/latest/use/configure/configuration-files
- `node:test` — https://nodejs.org/api/test.html
- WHATWG Fetch and AbortController — https://developer.mozilla.org/en-US/docs/Web/API/AbortController
- `worker_threads` — https://nodejs.org/api/worker_threads.html
- OWASP Node.js security cheat sheet — https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html
