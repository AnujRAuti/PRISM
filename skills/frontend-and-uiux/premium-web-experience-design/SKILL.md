---
name: premium-web-experience-design
description: Craft high-end web experiences—typography, spacing rhythm, motion discipline, image quality, and detail work—without sacrificing performance or accessibility.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Premium Web Experience Design

## 1. Purpose

Produce interfaces that feel considered and expensive: confident typography, generous and consistent spacing, restrained color, purposeful motion, and flawless detail at every breakpoint. Premium quality is not decoration—it is consistency, restraint, and finish. This skill converts "make it feel high-end" into specific, testable decisions about type, space, color, imagery, motion, and micro-interaction.

**Scope:** your own product. Premium design must still meet accessibility, performance, and privacy requirements—elegance never justifies unreadable contrast or megabytes of hero video.

## 2. Activation Conditions

- Marketing site, product landing page, or flagship product surface.
- Redesign intended to raise perceived quality or brand positioning.
- Interface feels "cheap" or inconsistent despite working correctly.
- Keywords: premium design, high-end, typography, whitespace, visual hierarchy, brand, polish, micro-interactions, editorial layout, craft.

## 3. When Not to Use

- Dense internal tools where efficiency beats elegance (use design-system-engineering for consistency).
- Time-critical emergency fixes.
- When performance budgets cannot accommodate heavy media—premium feel must be achieved within budget.

## 4. Required Context

1. Brand guidelines: fonts, colors, logo usage, tone.
2. Audience and context of use (device, environment, intent).
3. Performance budget (LCP, total page weight).
4. Accessibility target (contrast, motion, keyboard).
5. Competitive references and what "premium" means for this category.

## 5. Operating Procedure

1. **Choose the type system first**: one display face and one text face (or a single well-crafted variable font). Define a modular scale, line heights, and optical sizes.
2. **Set the space system**: an 8-point (or 4-point) scale with generous defaults—section padding on desktop typically 96–160 px, paragraph width 60–75 characters.
3. **Constrain the palette**: one primary, one accent, a neutral ramp, and semantic colors. Premium interfaces use fewer colors with more careful contrast.
4. **Establish hierarchy with size, weight, and space** rather than color and borders.
5. **Use photography/illustration with intention**: consistent art direction, correct crops, compressed modern formats, and meaningful alt text.
6. **Add motion sparingly** (150–400 ms, ease-out on entrance, ease-in on exit) and only where it clarifies hierarchy or state.
7. **Design the details**: focus states, hover transitions, empty states, loading skeletons, error messages, and microcopy in the brand voice.
8. **Check every breakpoint** and both themes; premium design collapses first at awkward widths and in dark mode.
9. **Verify with performance and accessibility budgets**; a slow or unreadable page is not premium.
10. **Hold a critique** with 3 specific questions: is the hierarchy obvious, is anything decorative without purpose, is anything inconsistent?

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Type | Variable fonts (`woff2`), Fontshare/Google Fonts, fonttools subsetting |
| Layout | CSS Grid, `clamp()`, container queries, `text-wrap: balance/pretty` |
| Color | OKLCH for perceptual palettes, contrast checkers |
| Imagery | AVIF/WebP, art-directed `<picture>`, CDN resizing |
| Motion | CSS transitions, Motion, View Transitions |
| Quality checks | Lighthouse, axe, visual regression, design critique |

## 7. Practical Implementation

**Editorial type scale with fluid sizing:**

```css
:root {
  --font-display: "Fraunces", Georgia, serif;
  --font-text: "Inter", system-ui, sans-serif;

  --step--1: clamp(0.875rem, 0.85rem + 0.12vw, 0.9375rem);
  --step-0:  clamp(1rem, 0.96rem + 0.2vw, 1.125rem);
  --step-1:  clamp(1.25rem, 1.15rem + 0.5vw, 1.5rem);
  --step-2:  clamp(1.5625rem, 1.37rem + 0.96vw, 2.25rem);
  --step-3:  clamp(1.953rem, 1.6rem + 1.76vw, 3.375rem);
  --step-4:  clamp(2.44rem, 1.82rem + 3.1vw, 5.06rem);

  --space-xs: 0.5rem;
  --space-s: 0.75rem;
  --space-m: 1.25rem;
  --space-l: 2rem;
  --space-xl: 3.5rem;
  --space-2xl: clamp(4rem, 8vw, 10rem);
}

h1 {
  font-family: var(--font-display);
  font-size: var(--step-4);
  font-weight: 600;
  line-height: 1.02;
  letter-spacing: -0.02em;
  text-wrap: balance;
  max-width: 20ch;
}

.lede {
  font-size: var(--step-1);
  line-height: 1.55;
  color: var(--color-content-muted);
  max-width: 58ch;
}

.prose p {
  font-size: var(--step-0);
  line-height: 1.65;
  max-width: 68ch;
  text-wrap: pretty;
}
```

**Perceptual color palette with OKLCH:**

```css
:root {
  --color-brand-500: oklch(0.62 0.16 258);
  --color-brand-600: oklch(0.55 0.17 258);
  --color-neutral-50: oklch(0.98 0.004 258);
  --color-neutral-900: oklch(0.21 0.012 258);
  --color-accent-500: oklch(0.74 0.16 55);      /* warm accent against cool brand */
  --color-content: var(--color-neutral-900);
  --color-surface: var(--color-neutral-50);
  --color-content-muted: oklch(0.48 0.01 258);
}
```

**Hero with art direction and no layout shift:**

```html
<picture>
  <source media="(min-width: 64rem)"
          srcset="/img/hero-wide-1600.avif 1600w, /img/hero-wide-2400.avif 2400w"
          sizes="100vw" type="image/avif">
  <source srcset="/img/hero-tall-800.avif 800w, /img/hero-tall-1200.avif 1200w"
          sizes="100vw" type="image/avif">
  <img src="/img/hero-fallback-1200.jpg" width="2400" height="1350"
       alt="A courier scanning a parcel at a warehouse door" fetchpriority="high">
</picture>
```

```css
.hero-media { aspect-ratio: 16 / 9; overflow: hidden; }
.hero-media img { width: 100%; height: 100%; object-fit: cover; }
@media (max-width: 64rem) { .hero-media { aspect-ratio: 4 / 5; } }
```

**Restrained section rhythm:**

```css
.section { padding-block: var(--space-2xl); }
.section + .section { border-top: 1px solid color-mix(in oklch, var(--color-content) 8%, transparent); }
.container { width: min(100% - 2 * var(--space-m), 76rem); margin-inline: auto; }
.section-header { display: grid; gap: var(--space-m); max-width: 46rem; }
```

**Detail work: focus, hover, loading, empty, error:**

```css
:where(a, button, input, [tabindex]):focus-visible {
  outline: 2px solid var(--color-brand-600);
  outline-offset: 3px;
  border-radius: 0.25rem;
}
.card { transition: transform 180ms ease-out, box-shadow 180ms ease-out; }
.card:hover { transform: translateY(-2px); box-shadow: 0 12px 28px -12px oklch(0 0 0 / 0.28); }
@media (prefers-reduced-motion: reduce) { .card { transition: none; } }
```

```tsx
export function EmptyState({title, body, action}: {title: string; body: string; action: React.ReactNode}) {
  return (
    <div className="grid place-items-center gap-3 rounded-card border border-dashed p-12 text-center">
      <h3 className="text-lg font-medium">{title}</h3>
      <p className="max-w-[42ch] text-content-muted">{body}</p>
      {action}
    </div>
  );
}
```

**Microcopy in brand voice (specific, not generic):**

```text
Generic:  "An error occurred."
Premium:  "We couldn't reach the payment provider. Your card was not charged —
           try again in a moment, or use a different method."

Generic:  "No results."
Premium:  "No invoices match 'October' yet. Invoices appear here within an hour of billing."
```

**Critique checklist:**

```text
1. Squint test: is the primary message the only thing that stands out at 5% zoom?
2. Density: does each section have one clear job?
3. Consistency: are the same 3 shadows/radii/weights reused, not 12?
4. Contrast: does every text/background pair pass AA?
5. Performance: LCP ≤ 2.5 s, page weight within budget on 4G.
```

## 8. Quality Standards

- One display and one text face, loaded as `woff2` with `font-display: swap` and preloaded critical weights.
- Spacing derives from a single scale; no arbitrary pixel values.
- Palette is small (≤ 8 core colors) and contrast-checked in both themes.
- Every section has a single purpose; hierarchy is obvious at a glance.
- Motion is subtle, purposeful, and respects reduced motion.
- All states designed: loading, empty, error, success, disabled.
- Microcopy is specific and human, in the brand voice.
- Performance and accessibility budgets are met—not traded for aesthetics.

## 9. Verification and Testing

- Lighthouse: performance ≥ 90 mobile, accessibility 100 where achievable, CLS < 0.05.
- Manual squint/blur test and a 5-second test with someone unfamiliar.
- Contrast check for every text/background pair (including muted text and hover states).
- Visual regression across 320/768/1440 and both themes.
- Font-loading check with slow network throttling (no invisible text, no reflow).
- Review on a real phone in daylight brightness.

## 10. Security Considerations

- Custom fonts from third parties can be a tracking or supply-chain vector; self-host with `preconnect` avoided where unnecessary.
- Hero videos and embeds must not autoplay with sound or capture permissions.
- Premium pages often add analytics and A/B scripts—review third-party scripts for data collection and performance impact.
- Avoid "scroll hijacking" and forced parallax; they break keyboard and assistive navigation.
- Decorative CSS from user content is an injection vector; never accept raw style strings.

## 11. Failure Handling

- **Feels generic:** typography is the usual culprit—increase scale contrast (display vs. body), reduce color usage, and increase whitespace around the key message.
- **Feels heavy:** too many shadows, borders, and gradients; choose one elevation system.
- **Slow hero:** replace video with a still + subtle motion, compress to AVIF, and lazy-load below-the-fold media.
- **Inconsistent spacing:** audit computed styles and replace with scale tokens; if a value is repeated ad hoc, add it to the scale.
- **Dark mode looks flat:** rethink elevation with surface tints rather than shadows.

## 12. Expected Deliverables

1. Type and space scale documentation.
2. Palette with contrast evidence.
3. Section-by-section layout with hierarchy rationale.
4. Motion specification (durations, easing, triggers).
5. State designs (loading/empty/error).
6. Microcopy set.
7. Performance/accessibility results.

## 13. References

- "Refactoring UI" (Adam Wathan & Steve Schoger) — https://www.refactoringui.com/
- Practical Typography (Matthew Butterick) — https://practicaltypography.com/
- OKLCH color picker — https://oklch.com/
- WCAG 2.2 contrast — https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- web.dev performance — https://web.dev/explore/fast
- Google Fonts knowledge (typography) — https://fonts.google.com/knowledge
- "Designing for the Digital Age" (Kim Goodwin).
