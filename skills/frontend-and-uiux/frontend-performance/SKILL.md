---
name: frontend-performance
description: Optimize Core Web Vitals—LCP, INP, CLS—through loading strategy, bundle reduction, image/font handling, and render-path discipline, measured on real devices.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Frontend Performance

## 1. Purpose

Deliver interfaces that feel fast on mid-range phones and unreliable networks. Frontend performance is dominated by bytes shipped, work on the main thread, and layout stability—not by micro-optimizations. This skill maps Core Web Vitals to concrete actions: LCP (loading strategy and critical path), INP (main-thread responsiveness), and CLS (stable layout), with measurement discipline using field data where available.

**Scope:** your own frontend and its assets. Third-party scripts are the most common cause of regressions—treat them as performance debt with an owner.

## 2. Activation Conditions

- Core Web Vitals fail or regress in the field.
- Slow first load, janky interaction, or layout jumps.
- Bundle size growth or many third-party scripts.
- Before a launch or SEO-sensitive change.
- Keywords: Core Web Vitals, LCP, INP, CLS, TTFB, bundle size, code splitting, lazy loading, preload, fonts, tree shaking, Lighthouse, RUM.

## 3. When Not to Use

- Backend latency dominates TTFB (fix the server first; use performance-optimization).
- Native app performance.
- Perceived-performance-only issues on an internal tool with no user impact.

## 4. Required Context

1. Field data (RUM) if available: LCP/INP/CLS by page and device class.
2. Lab tooling access (Lighthouse CI, WebPageTest).
3. Build setup and current bundle composition.
4. Third-party scripts inventory with owners.
5. CDN/caching configuration.

## 5. Operating Procedure

1. **Establish the baseline** with field data (75th percentile) and lab data on a throttled profile (mobile, 4G, 4× CPU).
2. **Fix TTFB and caching first**: CDN caching, compression (Brotli), and removing redirect chains.
3. **LCP**: identify the LCP element (image, heading, or video poster); preload it, serve responsive formats, avoid lazy-loading it, and eliminate render-blocking CSS/JS in its path.
4. **INP**: find long tasks (Performance panel; `PerformanceObserver` for `longtask`), split heavy work, defer non-critical hydration, virtualize long lists, and move work to workers.
5. **CLS**: set width/height or `aspect-ratio` on media, reserve space for ads/embeds, avoid inserting content above the fold, and use `font-display: swap` with matched metrics fallbacks.
6. **Reduce JS**: tree-shake, remove unused polyfills, split by route/feature, defer third parties, and prefer server rendering for content.
7. **Optimize fonts**: subset, `woff2`, `preload` the critical face, `size-adjust`/`ascent-override` fallbacks to reduce layout shift.
8. **Optimize images**: AVIF/WebP, correct `sizes`, `loading="lazy"` except above the fold, and a CDN resizer.
9. **Set budgets in CI** (Lighthouse CI assertions, bundle size limits) so regressions fail builds.
10. **Monitor field data continuously**; lab scores alone miss real-device variance.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Lab | Lighthouse, Lighthouse CI, WebPageTest, Chrome Performance |
| Field | `web-vitals` library + RUM endpoint, CrUX |
| Bundles | `vite-bundle-visualizer`, `webpack-bundle-analyzer`, `size-limit`, `bundlephobia` |
| Images | Sharp, Squoosh, CDN image resizing |
| Fonts | `fonttools` subsetting, `font-display`, `size-adjust` |
| Third parties | `partytown`, Tag Manager review, `requestIdleCallback` loading |
| Budgets | `lighthouse-ci` assertions, `bundlesize` |

## 7. Practical Implementation

**Field measurement with `web-vitals`:**

```ts
import {onCLS, onINP, onLCP, onTTFB, type Metric} from "web-vitals";

function send(metric: Metric) {
  const body = JSON.stringify({
    name: metric.name, value: metric.value, rating: metric.rating,
    id: metric.id, page: location.pathname, conn: (navigator as any).connection?.effectiveType,
  });
  navigator.sendBeacon("/rum/vitals", body);
}

onLCP(send); onINP(send); onCLS(send); onTTFB(send);
```

**Long-task observer (INP diagnosis):**

```ts
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.duration > 50) {
      console.debug("long task", Math.round(entry.duration), "ms", entry.name);
    }
  }
}).observe({type: "longtask", buffered: true});
```

**LCP image preload + responsive formats:**

```html
<link rel="preload" as="image" href="/img/hero-800.avif"
      imagesrcset="/img/hero-400.avif 400w, /img/hero-800.avif 800w, /img/hero-1600.avif 1600w"
      imagesizes="100vw" fetchpriority="high">
<img src="/img/hero-800.avif" width="1600" height="900" alt="…"
     srcset="/img/hero-400.avif 400w, /img/hero-800.avif 800w, /img/hero-1600.avif 1600w"
     sizes="100vw" fetchpriority="high" decoding="async">
```

**Font loading without layout shift:**

```css
@font-face {
  font-family: "Inter";
  src: url("/fonts/inter-latin-var.woff2") format("woff2-variations");
  font-weight: 100 900;
  font-display: swap;
  unicode-range: U+0000-00FF, U+0131, U+2000-206F;
}
@font-face {
  font-family: "Inter Fallback";
  src: local("Arial");
  size-adjust: 107%;
  ascent-override: 90%;
  descent-override: 22%;
  line-gap-override: 0%;
}
body { font-family: "Inter", "Inter Fallback", system-ui, sans-serif; }
```

**Route-level code splitting (React example):**

```tsx
import {lazy, Suspense} from "react";
const Reports = lazy(() => import("./pages/Reports"));   // heavy chart library inside

<Suspense fallback={<Skeleton />}>
  <Reports />
</Suspense>
```

**Deferring third-party scripts:**

```html
<script src="https://cdn.example.com/chat.js" defer
        onload="window.__chatReady = true"></script>
<!-- Or load after interaction/idle -->
<script>
  const loadChat = () => import("/chat-loader.js");
  addEventListener("pointerdown", loadChat, {once: true});
  addEventListener("scroll", loadChat, {once: true, passive: true});
</script>
```

**Moving heavy computation off the main thread:**

```ts
const worker = new Worker(new URL("./search.worker.ts", import.meta.url), {type: "module"});
worker.postMessage({query, limit: 50});
worker.onmessage = (e) => renderResults(e.data);
```

**Reserve space for late content (CLS):**

```css
.ad-slot { min-height: 250px; content-visibility: auto; contain-intrinsic-size: 250px; }
.skeleton { aspect-ratio: 16 / 9; background: var(--color-surface-muted); border-radius: 0.5rem; }
```

**Lighthouse CI budget:**

```json
{
  "ci": {
    "assert": {
      "assertions": {
        "categories:performance": ["error", {"minScore": 0.9}],
        "largest-contentful-paint": ["error", {"maxNumericValue": 2500}],
        "cumulative-layout-shift": ["error", {"maxNumericValue": 0.1}],
        "total-blocking-time": ["warn", {"maxNumericValue": 200}]
      }
    }
  }
}
```

**Bundle size gate:**

```bash
npx size-limit
```

```json
{
  "size-limit": [
    {"name": "entry", "path": "dist/assets/index-*.js", "limit": "120 kB"},
    {"name": "vendor", "path": "dist/assets/vendor-*.js", "limit": "180 kB"}
  ]
}
```

## 8. Quality Standards

- LCP ≤ 2.5 s, CLS ≤ 0.1, INP ≤ 200 ms at p75 on mobile.
- Total JS transferred for the entry route within a stated budget.
- No render-blocking third-party scripts.
- All media declare dimensions; no CLS from images, fonts, or embeds.
- Field monitoring is in place; lab scores are not the only evidence.
- Performance budgets are enforced in CI.

## 9. Verification and Testing

```bash
npx lighthouse https://staging.example.com --preset=desktop --output=json --output-path=./lh.json
npx lighthouse https://staging.example.com --form-factor=mobile --throttling-method=simulate
npx lhci autorun
npx webpack-bundle-analyzer dist/stats.json   # or vite-bundle-visualizer
```

Checks: compare LCP element and its request waterfall before/after; verify the LCP image is not lazy-loaded; confirm the main thread has no long tasks during first interaction; run on a real mid-range Android over throttled 4G.

## 10. Security Considerations

- Third-party scripts execute with full page privileges; a single compromised tag can exfiltrate data. Use SRI, CSP, and a vendor review process.
- `sendBeacon` RUM payloads must not include PII or tokens.
- Preloading user-specific URLs can leak information through the request path; preload only static assets.
- Performance shortcuts must not skip input sanitization or auth checks.
- Service workers caching sensitive responses need explicit cache-control and logout purge.

## 11. Failure Handling

- **LCP element changes after fixes:** the new LCP is a text block blocked by fonts—preload the font and use a metric-matched fallback.
- **INP regressions after adding a feature:** a heavy render on interaction—split state updates, use `startTransition`, or move work to a worker.
- **CLS from ads/embeds:** reserve fixed space and load in an iframe with a set height.
- **Bundle grows after a dependency:** find it with the analyzer; prefer a lighter alternative or dynamic import.
- **Lab great, field poor:** device/network/third-party differences—use field data by device class and test on real hardware.

## 12. Expected Deliverables

1. Baseline: field (p75) and lab metrics.
2. LCP element identification and loading strategy.
3. INP analysis with long-task attribution.
4. CLS fixes with reserved-space evidence.
5. Bundle analysis and splitting plan.
6. Font and image optimization changes.
7. CI budgets and monitoring configuration.

## 13. References

- web.dev Core Web Vitals — https://web.dev/articles/vitals
- `web-vitals` library — https://github.com/GoogleChrome/web-vitals
- Lighthouse CI — https://github.com/GoogleChrome/lighthouse-ci
- Chrome DevTools performance panel — https://developer.chrome.com/docs/devtools/performance/
- `size-limit` — https://github.com/ai/size-limit
- web.dev font best practices — https://web.dev/articles/font-best-practices
- HTTP Archive Web Almanac (performance) — https://almanac.httparchive.org/
