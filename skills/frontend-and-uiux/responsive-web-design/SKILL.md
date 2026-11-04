---
name: responsive-web-design
description: Build layouts that work from 320px to ultrawide—fluid grids, container queries, responsive images, touch targets, and safe-area handling without layout shift.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Responsive Web Design

## 1. Purpose

Deliver a usable interface across the real range of viewports, input modes, and text-zoom settings—not just "mobile and desktop". This skill covers fluid layout primitives, container queries, responsive images with correct `sizes`, touch target sizing, viewport and safe-area handling, and the failure modes that cause horizontal scroll, clipped content, and layout shift.

**Scope:** your own frontend. Verify on real devices where possible; emulation misses touch, font boosting, and browser chrome behavior.

## 2. Activation Conditions

- New layout or redesign of an existing one.
- Horizontal scrollbars, overlapping content, or clipped text at some widths.
- Images cause layout shift or load oversized files.
- Content must adapt to its container (cards in different slots).
- Keywords: responsive design, breakpoints, media queries, container queries, fluid typography, clamp, srcset, aspect-ratio, touch targets, safe-area-inset, zoom.

## 3. When Not to Use

- Fixed-canvas rendering (games, embedded 3D) where the canvas is managed separately.
- Print stylesheets (different concern).

## 4. Required Context

1. Supported viewport range and browsers (including older Safari).
2. Design breakpoints or the intent behind them.
3. Content types: text-heavy, media, data tables, forms.
4. Input modes: touch, mouse, keyboard.
5. Image/asset pipeline (CDN with resizing, formats available).

## 5. Operating Procedure

1. **Start at 320 px**, then expand until the design breaks—derive breakpoints from content, not device names.
2. **Use layout primitives**: CSS Grid for two-dimensional layout, flexbox for one-dimensional flow, and `min()`/`max()`/`clamp()` for fluid sizing.
3. **Prefer `minmax()` + `auto-fit` grids** over fixed column counts where content should fill available space.
4. **Adopt container queries** for components that appear in different-sized slots; use media queries for page-level layout.
5. **Set fluid type with `clamp()`**, but keep body text ≥ 16 px and respect user font-size settings (use `rem`, not `px`, for text).
6. **Serve responsive images**: `srcset`/`sizes` with correct `sizes` math, modern formats (AVIF/WebP), explicit dimensions or `aspect-ratio` to prevent CLS.
7. **Design for touch**: targets ≥ 24×24 CSS px (44×44 recommended), spacing between targets, no hover-only affordances.
8. **Handle viewport chrome**: `viewport-fit=cover` + `env(safe-area-inset-*)` for notches, `100dvh` instead of `100vh` for mobile browser bars.
9. **Make tables scrollable** (`overflow-x: auto` on a wrapper) rather than shrinking text; consider card layout at small widths for critical data.
10. **Test at 320/375/768/1024/1440/2560**, with 200% zoom, and with long translated strings.
11. **Avoid horizontal overflow**: audit with a script that finds elements wider than the viewport.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Layout | CSS Grid, Flexbox, `clamp()`, `min()`, `max()` |
| Components | Container queries (`@container`), `:has()` for state-driven layout |
| Images | `srcset`/`sizes`, `loading="lazy"`, `fetchpriority`, AVIF/WebP, `aspect-ratio` |
| Units | `rem`, `svh/lvh/dvh`, `cqw/cqh`, `%` |
| Testing | DevTools device mode, Playwright viewport tests, BrowserStack |
| Overflow audit | Custom JS snippet, `eslint-plugin` checks |

## 7. Practical Implementation

**Fluid grid without media queries:**

```css
.card-grid {
  display: grid;
  gap: clamp(0.75rem, 2vw, 1.5rem);
  grid-template-columns: repeat(auto-fit, minmax(min(18rem, 100%), 1fr));
}
```

**Container query for a card used in narrow and wide slots:**

```css
.card-slot { container-type: inline-size; container-name: card; }

.card { display: grid; gap: 0.75rem; grid-template-columns: 1fr; }

@container card (min-width: 28rem) {
  .card { grid-template-columns: 8rem 1fr; align-items: start; }
}
```

**Fluid type scale:**

```css
:root {
  --step-0: clamp(1rem, 0.95rem + 0.25vw, 1.125rem);
  --step-1: clamp(1.25rem, 1.15rem + 0.5vw, 1.5rem);
  --step-2: clamp(1.5rem, 1.3rem + 1vw, 2rem);
}
body { font-size: var(--step-0); line-height: 1.5; }
h1 { font-size: var(--step-2); line-height: 1.2; text-wrap: balance; }
p { max-width: 68ch; text-wrap: pretty; }
```

**Responsive image with correct `sizes`:**

```html
<img
  src="/img/hero-800.avif"
  srcset="/img/hero-400.avif 400w,
          /img/hero-800.avif 800w,
          /img/hero-1600.avif 1600w"
  sizes="(min-width: 64rem) 50vw, 100vw"
  width="1600" height="900"
  alt="Warehouse workers scanning parcels"
  loading="eager" fetchpriority="high" decoding="async">
```

```css
img { max-width: 100%; height: auto; }
.media { aspect-ratio: 16 / 9; overflow: hidden; }   /* prevents CLS */
```

**Mobile viewport with safe areas:**

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
```

```css
.app-header {
  padding-top: max(0.75rem, env(safe-area-inset-top));
  padding-inline: max(1rem, env(safe-area-inset-left), env(safe-area-inset-right));
}
.hero { min-height: 100svh; }   /* small viewport height: stable when browser bars hide */
```

**Touch targets and spacing:**

```css
.icon-button {
  min-width: 44px; min-height: 44px;      /* WCAG 2.2 target size */
  display: inline-flex; align-items: center; justify-content: center;
}
.nav-list { display: flex; gap: 0.5rem; flex-wrap: wrap; }
```

**Scrollable table wrapper:**

```css
.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.table-scroll table { min-width: 40rem; }
```

**Layout that respects long text and zoom:**

```css
.prose { max-width: 68ch; overflow-wrap: anywhere; hyphens: auto; }
:root { font-size: 100%; }   /* never set html font-size in px; it blocks user zoom */
```

**Overflow audit snippet:**

```js
// Paste in DevTools to find elements causing horizontal overflow
const vw = document.documentElement.clientWidth;
[...document.querySelectorAll("*")]
  .filter((el) => el.getBoundingClientRect().right > vw + 1)
  .slice(0, 20)
  .forEach((el) => console.log(el, el.getBoundingClientRect().right, vw));
```

**Playwright viewport test:**

```ts
import {test, expect} from "@playwright/test";

for (const width of [320, 375, 768, 1024, 1440]) {
  test(`no horizontal overflow at ${width}px`, async ({page}) => {
    await page.setViewportSize({width, height: 800});
    await page.goto("/");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
}
```

## 8. Quality Standards

- No horizontal scrolling at 320 px for any page.
- Text remains readable at 200% zoom without loss of content or function.
- Breakpoints derive from content behavior; no "iPhone 14" breakpoints.
- Images declare dimensions or `aspect-ratio`; CLS from media is zero.
- Touch targets meet 44×44 px where feasible and are never smaller than 24×24 px.
- Layout uses logical properties (`margin-inline`, `padding-block`) for RTL readiness.
- Components adapt to their container, not only to the viewport.
- Tables and code blocks scroll rather than break layout.

## 9. Verification and Testing

- Playwright/Chrome matrix at 320/375/768/1024/1440/2560 with overflow assertions.
- 200% browser zoom and 150% OS text scaling pass.
- Lighthouse CLS = 0 on key pages; image weight within budget.
- Real device test on a low-end Android for touch and font boosting.
- Long-string test: swap in German/Portuguese translations and recheck layout.
- RTL test with `dir="rtl"` on a sample page.

## 10. Security Considerations

- Responsive images served from a resizing service can be an SSRF/abuse vector; restrict allowed sources and sizes.
- Very large images without dimension caps can exhaust memory on mobile; enforce max dimensions server-side.
- Safe-area and viewport handling must not obscure security-sensitive UI (e.g. a logout button under a notch).
- Do not hide security notices or consent text with `display: none` at small widths—reflow instead.
- Content pulled from third parties into responsive layouts still needs sanitization.

## 11. Failure Handling

- **Horizontal scroll on one page:** find the offending element with the audit snippet; usually a fixed width, a negative margin, or an absolutely positioned decoration. Wrap with `overflow-x: clip` only as a last resort.
- **Text too small on mobile:** browser font boosting distorts layout; set explicit `font-size` on the body and use `rem` consistently.
- **`100vh` jumps on mobile:** use `dvh`/`svh`, or measure with JS if supporting old browsers.
- **Images squashed:** missing `height: auto` alongside `max-width: 100%`, or a fixed-height container.
- **Container queries not applying:** the container needs `container-type` on an ancestor, not the element itself.
- **Grid columns overflow with long words:** add `min-width: 0` to grid children.

## 12. Expected Deliverables

1. Layout primitives and breakpoint rationale.
2. Fluid typography and spacing scales.
3. Responsive image markup with `srcset`/`sizes`.
4. Container-query components.
5. Test matrix results with overflow and CLS evidence.
6. Notes on touch targets and safe areas.
7. RTL/zoom verification.

## 13. References

- MDN Responsive design — https://developer.mozilla.org/en-US/docs/Learn/CSS/CSS_layout/Responsive_Design
- MDN Container queries — https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries
- Responsive images (MDN `srcset`) — https://developer.mozilla.org/en-US/docs/Web/HTML/Guides/Responsive_images
- WCAG 2.2 Target Size — https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- web.dev CLS — https://web.dev/articles/cls
- `env()` safe area insets — https://developer.mozilla.org/en-US/docs/Web/CSS/env
- Every Layout (layout primitives) — https://every-layout.dev/
