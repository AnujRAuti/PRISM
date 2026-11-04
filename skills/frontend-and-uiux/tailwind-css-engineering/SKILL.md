---
name: tailwind-css-engineering
description: Use Tailwind CSS as a design system—token configuration, component extraction, responsive and state variants, dark mode, and a build that ships only used CSS.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Tailwind CSS Engineering

## 1. Purpose

Use Tailwind to produce consistent UI with a constrained design language instead of ad-hoc utility soup. Tailwind's value comes from a small, intentional token set (spacing, color, typography) and component abstraction—not from writing 40 classes per element. This skill covers configuration as a design contract, extraction patterns, responsive strategy, dark mode, accessibility, and production build hygiene.

**Scope:** your own frontend. Utility classes are safe by nature; risks come from dynamic class construction and untrusted content inserted into `class` attributes.

## 2. Activation Conditions

- Setting up or refactoring a Tailwind project.
- Inconsistent spacing/colors across components.
- Class strings are unreadable or duplicated.
- Dark mode, responsive behavior, or RTL support needs structure.
- Keywords: Tailwind, utility classes, design tokens, `tailwind.config`, dark mode, responsive breakpoints, `@apply`, arbitrary values, PurgeCSS, JIT.

## 3. When Not to Use

- Projects with an established, working CSS architecture and no Tailwind.
- Heavy, bespoke visual effects where raw CSS/SVG is clearer.
- Component library development where a headless UI library plus tokens solves it better.

## 4. Required Context

1. Tailwind version (v4 changes configuration to CSS-first `@theme`).
2. Build tool (Vite, Next, PostCSS).
3. Design tokens available (brand colors, spacing scale, typography).
4. Component library or headless primitives in use.
5. Browser support and whether dark mode is required.

## 5. Operating Procedure

1. **Define tokens in configuration** (v4: `@theme` in CSS): brand colors, semantic colors (`surface`, `muted`, `danger`), spacing scale, radius, and font families. Do not invent colors inline.
2. **Use semantic names, not palette names, in components** (`bg-surface` not `bg-gray-50`) so theming is possible.
3. **Extract repeated patterns into components** (React/Vue), and only use `@apply` for true CSS-only cases or third-party HTML you cannot change.
4. **Responsive by default**: mobile-first breakpoints (`sm:`, `md:`, `lg:`), avoid fixed widths, test at 320 px and 1440 px.
5. **Handle states explicitly**: `hover:`, `focus-visible:`, `active:`, `disabled:`, `aria-*` variants for accessibility.
6. **Dark mode via a class or media strategy**, with tokens flipped once—not per component.
7. **Never build class names dynamically** (`bg-${color}-500`) — the scanner cannot see them; use full class maps instead.
8. **Constrain arbitrary values** (`w-[437px]`); if you need many, the design is drifting from the scale.
9. **Add content paths correctly** so unused CSS is purged in production.
10. **Audit the final CSS size** and verify no missing classes in production builds.
11. **Check contrast** for text on surfaces in both themes (WCAG AA 4.5:1 for body text).

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Build | Tailwind CLI, PostCSS, Vite plugin (`@tailwindcss/vite`), Next.js |
| Components | React/Vue components, `class-variance-authority` (CVA), `tailwind-merge`, `clsx` |
| Headless UI | Radix, Headless UI, Ark UI |
| Lint | `eslint-plugin-tailwindcss`, `prettier-plugin-tailwindcss` |
| Audit | `@tailwindcss/forms`, `@tailwindcss/typography`, browser devtools coverage |

## 7. Practical Implementation

**Tailwind v4 CSS-first theme:**

```css
/* app.css */
@import "tailwindcss";

@theme {
  --color-surface: oklch(99% 0.002 250);
  --color-surface-muted: oklch(96% 0.006 250);
  --color-content: oklch(22% 0.02 250);
  --color-content-muted: oklch(48% 0.02 250);
  --color-brand: oklch(58% 0.19 255);
  --color-brand-contrast: oklch(99% 0 0);
  --color-danger: oklch(55% 0.21 27);
  --radius-card: 0.75rem;
  --font-sans: "Inter var", system-ui, sans-serif;
}

@layer base {
  [data-theme="dark"] {
    --color-surface: oklch(20% 0.015 250);
    --color-surface-muted: oklch(26% 0.018 250);
    --color-content: oklch(96% 0.005 250);
    --color-content-muted: oklch(72% 0.012 250);
  }
  html { color-scheme: light dark; }
  body { @apply bg-surface text-content font-sans antialiased; }
}
```

**Tailwind v3 `tailwind.config.ts` equivalent:**

```ts
import type {Config} from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx,html}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        surface: "rgb(var(--surface) / <alpha-value>)",
        content: "rgb(var(--content) / <alpha-value>)",
        brand: {DEFAULT: "rgb(var(--brand) / <alpha-value>)", contrast: "rgb(var(--brand-contrast) / <alpha-value>)"},
      },
      borderRadius: {card: "0.75rem"},
      fontFamily: {sans: ["Inter var", "system-ui", "sans-serif"]},
    },
  },
  plugins: [],
} satisfies Config;
```

**Component extraction with CVA (variants instead of conditionals):**

```tsx
import {cva, type VariantProps} from "class-variance-authority";
import {clsx} from "clsx";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 " +
  "disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      intent: {
        primary: "bg-brand text-brand-contrast hover:bg-brand/90",
        secondary: "bg-surface-muted text-content hover:bg-surface-muted/70",
        danger: "bg-danger text-white hover:bg-danger/90",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
      },
    },
    defaultVariants: {intent: "primary", size: "md"},
  },
);

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>;

export function Button({intent, size, className, ...props}: ButtonProps) {
  return <button className={clsx(button({intent, size}), className)} {...props} />;
}
```

**Dynamic class safety (map, do not interpolate):**

```tsx
// WRONG: Tailwind cannot see `bg-${tone}-500`
const cls = `bg-${tone}-500`;

// RIGHT: complete class names present in source
const TONE = {
  neutral: "bg-surface-muted text-content",
  success: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
  warning: "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
} as const;

function Badge({tone = "neutral"}: {tone?: keyof typeof TONE}) {
  return <span className={clsx("rounded-full px-2 py-0.5 text-xs", TONE[tone])}>{/* */}</span>;
}
```

**Merging external class names with `tailwind-merge`:**

```tsx
import {twMerge} from "tailwind-merge";
export const cx = (...inputs: (string | undefined | false)[]) => twMerge(clsx(inputs));

// <Card className="p-8" /> overrides the base p-4 instead of both applying unpredictably
```

**Responsive layout pattern:**

```tsx
<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:gap-6">
  {items.map((item) => <Card key={item.id} item={item} />)}
</div>
```

**Accessible focus and state variants:**

```tsx
<a href="/orders" className="rounded-md px-3 py-2 text-content-muted transition
    hover:text-content focus-visible:outline-none focus-visible:ring-2
    focus-visible:ring-brand aria-[current=page]:text-content aria-[current=page]:font-semibold">
  Orders
</a>
```

**Typography plugin for long-form content:**

```css
@plugin "@tailwindcss/typography";
```

```tsx
<article className="prose prose-slate max-w-prose dark:prose-invert">{/* markdown html */}</article>
```

**Production build check:**

```bash
npx tailwindcss -i ./src/app.css -o ./dist/app.css --minify
ls -lh dist/app.css
grep -c "class" dist/app.css
```

## 8. Quality Standards

- Tokens defined once; components use semantic names.
- No dynamic class interpolation; all class strings are literal or mapped.
- Repeated patterns extracted to components with variants.
- Mobile-first responsive classes; verified from 320 px upward.
- Focus states visible on every interactive element.
- Dark mode implemented via tokens, not per-component overrides.
- Production CSS is purged and within a stated size budget.
- Contrast meets WCAG AA in both themes.

## 9. Verification and Testing

- Visual regression snapshots (see visual-regression-testing) at three breakpoints and both themes.
- axe/Lighthouse accessibility pass with no contrast violations.
- Production build: assert expected classes exist (`grep 'lg:grid-cols-3' dist/app.css`).
- Manual keyboard test: tab through interactive elements, focus is always visible.
- CSS size check in CI against a budget.

## 10. Security Considerations

- Tailwind classes come from source, not user input; if user-supplied class names are ever inserted, they can reference arbitrary utilities (including `hidden` to hide warnings) — validate against an allowlist.
- `@apply` with values from dynamic config is not a runtime risk but can break the purge scanner; keep it static.
- Arbitrary values (`bg-[url(...)]`) can load remote resources—restrict in a CSP.
- Do not rely on `hidden` classes for access control; hidden content is still in the DOM.

## 11. Failure Handling

- **Styles missing in production:** a dynamic class name or a content path not covered—make the class literal or extend `content`.
- **Conflicting classes:** `p-4 p-8` both present—use `tailwind-merge` or fix the component API.
- **Dark mode flashes on load:** apply the theme class in a blocking inline script before paint.
- **Bundle size grows:** check for unused plugins, safelisted patterns, and arbitrary values that create one-off utilities.
- **Specificity fights with a component library:** use the `important` strategy or layer components properly, not `!` everywhere.

## 12. Expected Deliverables

1. Token/theme configuration.
2. Component primitives with variants.
3. Class-composition helper (`cx`) with merge semantics.
4. Responsive and dark-mode conventions.
5. Production CSS size report.
6. Accessibility verification results.

## 13. References

- Tailwind CSS documentation — https://tailwindcss.com/docs
- Tailwind v4 theme variables — https://tailwindcss.com/docs/theme
- `class-variance-authority` — https://cva.style/docs
- `tailwind-merge` — https://github.com/dcastil/tailwind-merge
- `eslint-plugin-tailwindcss` — https://github.com/francoismassart/eslint-plugin-tailwindcss
- WCAG 2.2 contrast — https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- Radix primitives — https://www.radix-ui.com/primitives
