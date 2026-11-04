---
name: nextjs-development
description: Build Next.js applications with correct server/client boundaries—App Router conventions, data fetching and caching, streaming, server actions, and deployment-aware configuration.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: medium
---

# Next.js Development

## 1. Purpose

Use the Next.js App Router correctly: know what runs on the server, what ships to the browser, how caching actually behaves, and where mutations belong. The majority of Next.js bugs are boundary bugs—server-only secrets leaked into client bundles, stale data from misunderstood caches, or `"use client"` spread across an entire tree. This skill establishes those boundaries explicitly.

**Scope:** Next.js applications you own. Server code holds credentials; client code must be treated as public.

## 2. Activation Conditions

- Starting or restructuring a Next.js app.
- Data is stale after mutations; caches behave unexpectedly.
- Build output warns about client bundle size or secrets.
- Deciding between server components, client components, route handlers, and server actions.
- Keywords: Next.js, App Router, server components, use client, route handlers, server actions, revalidate, streaming, dynamic rendering, metadata, middleware.

## 3. When Not to Use

- Plain React SPAs (use react-development).
- Framework selection (use frontend-architecture).
- Static hosting with no server runtime (adapt: many features unavailable).

## 4. Required Context

1. Next.js version (App vs. Pages Router; caching semantics changed significantly across 13–15).
2. Rendering strategy: static, ISR, dynamic, streaming.
3. Data sources and their freshness requirements.
4. Auth model and where sessions are validated.
5. Deployment target (Vercel, Node server, container, edge).

## 5. Operating Procedure

1. **Default to server components.** Add `"use client"` only at leaf components that need state, effects, event handlers, or browser APIs.
2. **Fetch on the server** with `fetch`/database clients directly in server components; avoid client-side waterfalls unless interaction requires it.
3. **Define the caching contract per route**: static, revalidated (time-based or tag-based), or dynamic. Document it.
4. **Use tags for invalidation** and call `revalidateTag` after mutations instead of guessing TTLs.
5. **Use server actions for mutations** with authentication, authorization, validation, and idempotency inside the action—the client is not trusted.
6. **Route handlers** for external/webhook APIs, not as an internal data layer for server components.
7. **Stream heavy sections** with `loading.tsx` and Suspense boundaries so the shell renders fast.
8. **Keep the client bundle small**: check the build output, avoid importing server-only libraries into client components, and use dynamic imports for heavy widgets.
9. **Protect server-only modules** with `import "server-only"` and environment variable conventions (`NEXT_PUBLIC_` is public, everything else is server-only — but still never sent to the client unless passed explicitly).
10. **Set metadata and viewport** per route for SEO and social previews.
11. **Handle errors** with `error.tsx` boundaries and `not-found.tsx`.
12. **Verify** with a production build and a real deployment preview, not just `next dev`.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Framework | Next.js App Router (13.4+), Turbopack build |
| Data | native `fetch` with cache options, Prisma/Drizzle, TanStack Query in client components |
| Mutations | Server Actions, Route Handlers |
| Validation | Zod |
| Auth | Auth.js/NextAuth, Clerk, custom cookies + server validation |
| Testing | Vitest, Playwright, `next-test-api-route-handler` |
| Analysis | `@next/bundle-analyzer`, build output sizes |

## 7. Practical Implementation

**Server component with explicit caching:**

```tsx
// app/products/[slug]/page.tsx  (server component by default)
import { notFound } from "next/navigation";

async function getProduct(slug: string) {
  const res = await fetch(`${process.env.API_URL}/products/${encodeURIComponent(slug)}`, {
    next: {revalidate: 300, tags: [`product:${slug}`]},   // ISR + tag invalidation
  });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`product fetch failed: ${res.status}`);
  return res.json() as Promise<Product>;
}

export default async function ProductPage({params}: {params: Promise<{slug: string}>}) {
  const {slug} = await params;
  const product = await getProduct(slug);
  return (
    <main>
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <AddToCartButton productId={product.id} />   {/* client component */}
    </main>
  );
}
```

**Client component at the leaf:**

```tsx
"use client";
import { useState } from "react";

export function AddToCartButton({productId}: {productId: string}) {
  const [pending, setPending] = useState(false);
  async function add() {
    setPending(true);
    try {
      const res = await fetch("/api/cart", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({productId, quantity: 1}),
      });
      if (!res.ok) throw new Error("failed");
    } finally {
      setPending(false);
    }
  }
  return <button onClick={add} disabled={pending}>{pending ? "Adding…" : "Add to cart"}</button>;
}
```

**Server action with auth, validation, and revalidation:**

```ts
"use server";
import { z } from "zod";
import { revalidateTag } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";           // throws if unauthenticated
import { db } from "@/lib/db";

const Input = z.object({productId: z.string().uuid(), quantity: z.number().int().min(1).max(10)});

export async function addToCart(raw: unknown) {
  const user = await requireUser();                  // session validated on the server
  const input = Input.safeParse(raw);
  if (!input.success) return {ok: false, error: "invalid_input"};

  await db.cartItems.upsert({
    where: {userId_productId: {userId: user.id, productId: input.data.productId}},
    update: {quantity: {increment: input.data.quantity}},
    create: {userId: user.id, ...input.data},
  });

  revalidateTag(`cart:${user.id}`);
  return {ok: true};
}
```

**Streaming with Suspense:**

```tsx
// app/dashboard/page.tsx
import { Suspense } from "react";

export default function Dashboard() {
  return (
    <section>
      <h1>Dashboard</h1>
      <Suspense fallback={<RevenueSkeleton />}>
        <Revenue />        {/* async server component: streams when ready */}
      </Suspense>
      <Suspense fallback={<TableSkeleton />}>
        <RecentOrders />
      </Suspense>
    </section>
  );
}
```

**Route handler for webhooks (not for internal reads):**

```ts
// app/api/webhooks/stripe/route.ts
import { headers } from "next/headers";

export async function POST(req: Request) {
  const body = await req.text();                       // raw body for signature check
  const sig = (await headers()).get("stripe-signature");
  if (!sig || !verifySignature(body, sig, process.env.STRIPE_WEBHOOK_SECRET!)) {
    return new Response("invalid signature", {status: 400});
  }
  const event = JSON.parse(body) as {type: string; data: {object: {id: string}}};
  await enqueue(event);                                // idempotent processing
  return new Response(null, {status: 204});
}
```

**Server-only guard:**

```ts
// lib/db.ts
import "server-only";          // build error if imported into a client component
export const db = createClient(process.env.DATABASE_URL!);
```

**Route-level error and not-found:**

```tsx
// app/products/[slug]/error.tsx
"use client";
export default function Error({error, reset}: {error: Error; reset: () => void}) {
  return (
    <div role="alert">
      <p>Something went wrong loading this product.</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

**Verification commands:**

```bash
npm run build            # catch client/server boundary errors and bundle size
npx @next/bundle-analyzer
grep -rn "process.env" .next/static | head   # confirm no secrets in client output
```

## 8. Quality Standards

- `"use client"` appears only where required, at leaves.
- Server-only modules import `server-only`.
- Every route has a documented caching strategy; mutations invalidate by tag.
- Server actions validate input and enforce authorization.
- No secrets in `NEXT_PUBLIC_*` or client components.
- Loading and error states exist per route segment.
- Build passes with no hydration warnings; bundle sizes reviewed.

## 9. Verification and Testing

- `npm run build` succeeds and the build output shows expected static/dynamic routes.
- Search the client bundle for secrets and server-only imports.
- Playwright test: page renders server-rendered content with JS disabled for marketing pages.
- Mutation test: server action updates the DB and the page reflects it after revalidation.
- Hydration test: no mismatch warnings in the console on key routes.

## 10. Security Considerations

- Server actions are public HTTP endpoints: authenticate, authorize, validate, and rate-limit every one.
- Never trust `params`, search params, headers, or form data without validation.
- Environment variables without `NEXT_PUBLIC_` are server-only, but any value passed as a prop to a client component is public.
- Middleware runs on every request: keep it fast and never use it as the only authorization layer for data access.
- Use `HttpOnly`, `Secure`, `SameSite` cookies for sessions; rotate on login.
- Set a Content Security Policy; Next.js inline scripts require nonces/hashes.
- Image optimization and remote image domains are an SSRF surface—allowlist hosts.

## 11. Failure Handling

- **Data never updates after mutation:** fetch is cached without a tag or `revalidatePath`/`revalidateTag` is missing.
- **"Event handlers cannot be passed to Client Components":** mark the receiving component `"use client"` or move the handler inside a client component.
- **`window is not defined`:** browser API used in a server component; move to `useEffect` in a client component or guard with `typeof window`.
- **Hydration mismatch:** non-deterministic output (dates, random values) rendered on both sides—compute on the server and pass down, or render after mount.
- **Slow pages:** blocking `await`s in a server component—split into Suspense boundaries.

## 12. Expected Deliverables

1. Route structure with rendering strategy per route.
2. Server/client boundary map.
3. Data fetching and caching configuration with invalidation tags.
4. Server actions with validation and authorization.
5. Error/loading/not-found handling.
6. Build output and bundle analysis.
7. Security checklist results.

## 13. References

- Next.js documentation — https://nextjs.org/docs
- App Router caching — https://nextjs.org/docs/app/building-your-application/caching
- Server Actions — https://nextjs.org/docs/app/building-your-application/data-fetching/server-actions-and-mutations
- `server-only` package — https://www.npmjs.com/package/server-only
- Next.js security — https://nextjs.org/docs/app/guides/security
- React Server Components RFC — https://github.com/reactjs/rfcs/blob/main/text/0188-server-components.md
