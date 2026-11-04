---
name: design-system-engineering
description: Build a design system that scales—design tokens, headless primitives, documented components, versioning, and adoption tooling shared across teams.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Design System Engineering

## 1. Purpose

Create a shared component and token layer that makes consistent UI the path of least resistance. A design system is an API: tokens are its data types, components are its functions, and documentation is its contract. This skill covers the token architecture, component API design, headless primitives, documentation, versioning, and the governance that keeps a system from fragmenting again.

**Scope:** your organization's system. Breaking changes ripple across product teams—versioning and migration guides are mandatory.

## 2. Activation Conditions

- Multiple products/teams duplicating components and drifting visually.
- Rebranding or theming requirements (multi-brand, white-label).
- Building a component library or moving to one.
- Need to standardize accessibility and interaction behavior.
- Keywords: design system, design tokens, component library, theming, Storybook, headless UI, variants, versioning, adoption, Figma tokens.

## 3. When Not to Use

- Single small app with a handful of screens (local components suffice).
- No team capacity to maintain it—an abandoned design system is worse than none.
- Premature generalization before two real consumers exist.

## 4. Required Context

1. Number of consuming products/teams and their frameworks.
2. Design source of truth (Figma libraries) and how tokens are exported.
3. Theming requirements: light/dark, brands, density.
4. Accessibility standard to enforce.
5. Release/distribution model (npm package, monorepo, CDN).

## 5. Operating Procedure

1. **Inventory existing components** across products: frequency, variance, and pain points. Start with the highest-frequency, highest-variance primitives (Button, Input, Select, Dialog, Table).
2. **Establish a token architecture in tiers**:
   - Primitive: raw values (`blue-600`, `space-4`, `radius-md`).
   - Semantic: purpose (`color-text-muted`, `color-surface`, `color-danger`).
   - Component: scoped overrides (`button-primary-bg`) only when necessary.
3. **Export tokens from a single source** (Figma variables → JSON → CSS custom properties + TS types) so design and code cannot diverge silently.
4. **Build components on headless primitives** (Radix, Headless UI, React Aria) for behavior and accessibility; style them with your tokens.
5. **Design component APIs deliberately**: variants via a closed set, boolean props minimized, `asChild`/polymorphic patterns used sparingly, `className` escape hatch documented.
6. **Write documentation per component**: purpose, do/don't, code examples, accessibility notes, and props table generated from types.
7. **Add interaction tests and visual regression** per component.
8. **Version semantically**; ship breaking changes in majors with codemods or migration notes.
9. **Measure adoption** (import counts, duplicate local components) and run regular office hours/audits.
10. **Govern contributions**: a clear RFC process for new components, and a rule that a component enters the system only after two consumers need it.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Tokens | Style Dictionary, Figma variables, Tailwind `@theme`, CSS custom properties |
| Primitives | Radix UI, React Aria, Headless UI, Ark UI |
| Styling | Tailwind, CSS Modules, vanilla-extract, Stitches |
| Docs | Storybook, Ladle, Histoire |
| Testing | Testing Library, Playwright, Chromatic/Percy |
| Release | Changesets, semantic-release, npm/GHCR registry |
| Monorepo | pnpm workspaces, Turborepo, Nx |

## 7. Practical Implementation

**Token source (JSON) → generated CSS variables:**

```json
{
  "color": {
    "primitive": {"blue600": "#2563eb", "gray900": "#111827", "gray50": "#f9fafb"},
    "semantic": {
      "surface": {"value": "{color.primitive.gray50}"},
      "content": {"value": "{color.primitive.gray900}"},
      "brand": {"value": "{color.primitive.blue600}"}
    }
  },
  "space": {"1": "0.25rem", "2": "0.5rem", "4": "1rem", "8": "2rem"},
  "radius": {"md": "0.5rem", "card": "0.75rem"}
}
```

```css
/* generated — do not edit by hand */
:root {
  --ds-color-surface: #f9fafb;
  --ds-color-content: #111827;
  --ds-color-brand: #2563eb;
  --ds-space-4: 1rem;
  --ds-radius-card: 0.75rem;
}
[data-theme="dark"] {
  --ds-color-surface: #0f172a;
  --ds-color-content: #e5e7eb;
}
```

**Component built on a headless primitive:**

```tsx
import * as Dialog from "@radix-ui/react-dialog";
import {cx} from "./cx";

export function Modal({trigger, title, children}: {
  trigger: React.ReactNode; title: string; children: React.ReactNode;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm" />
        <Dialog.Content className={cx("fixed left-1/2 top-1/2 w-[min(90vw,32rem)] -translate-x-1/2",
                                     "-translate-y-1/2 rounded-card bg-surface p-6 shadow-xl")}>
          <Dialog.Title className="text-lg font-semibold text-content">{title}</Dialog.Title>
          <div className="mt-2 text-content">{children}</div>
          <Dialog.Close asChild>
            <button className="mt-4 rounded-lg bg-brand px-4 py-2 text-brand-contrast">Close</button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

**Closed variant API with types:**

```tsx
const buttonVariants = {
  intent: {
    primary: "bg-brand text-brand-contrast hover:bg-brand/90",
    secondary: "bg-surface-muted text-content hover:bg-surface-muted/70",
    ghost: "bg-transparent text-content hover:bg-surface-muted",
  },
  size: {sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm", lg: "h-12 px-6 text-base"},
} as const;

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  intent?: keyof typeof buttonVariants.intent;
  size?: keyof typeof buttonVariants.size;
};

export function Button({intent = "primary", size = "md", className, ...props}: ButtonProps) {
  return <button className={cx(BASE, buttonVariants.intent[intent], buttonVariants.size[size],
                               className)} {...props} />;
}
```

**Storybook story with interaction test:**

```tsx
import type {Meta, StoryObj} from "@storybook/react";
import {expect, userEvent, within} from "@storybook/test";
import {Button} from "./Button";

const meta = {title: "Components/Button", component: Button,
              args: {children: "Save", intent: "primary"}} satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Clickable: Story = {
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", {name: "Save"}));
    await expect(canvas.getByRole("button")).toBeEnabled();
  },
};

export const Danger: Story = {args: {intent: "danger", children: "Delete"}};
```

**Changesets for versioning:**

```bash
npx changeset add         # select package + bump type + summary
npx changeset version
npx changeset publish
```

```markdown
---
"@acme/ui": minor
---

Add `Table` component with sortable headers and sticky first column (keyboard accessible).
```

**Adoption check (detect local duplicates):**

```bash
# Count local re-implementations of primitives that should come from the system
rg -l "function Button|const Button" --glob '!packages/ui/**' | wc -l
```

## 8. Quality Standards

- Tokens are generated from one source and consumed via semantic names.
- Components are built on accessible primitives and pass a11y tests.
- Every component has documentation, examples, and a visual regression baseline.
- Public API changes are semver-managed with migration notes.
- No component enters the system with a single consumer.
- Theming is supported without forking components.
- Adoption is measurable and reviewed quarterly.

## 9. Verification and Testing

```bash
pnpm test            # behavior tests per component
pnpm chromatic       # visual regression
pnpm build && pnpm size   # bundle budget per component
```

Checks: keyboard and screen-reader pass per interactive component; visual snapshots for light/dark and three breakpoints; token changes propagate to snapshots (proving the pipeline works); a breaking change fails the semver check.

## 10. Security Considerations

- Component packages are dependencies for many teams: publish with provenance (npm `--provenance`), sign releases, and pin CI.
- Avoid `dangerouslySetInnerHTML` inside system components; if a component must render HTML, require sanitization at the call site and document it.
- Icon sets and font packages are supply-chain surface—vendor or pin them.
- Do not include internal-only components (admin tools, debug panels) in the public package.
- Storybook deployments must not expose internal env vars or unpublished designs; protect with auth if internal.

## 11. Failure Handling

- **Design and code diverge:** tokens must be generated, not hand-copied; add a CI check comparing Figma export to committed tokens.
- **Teams fork components:** interview why (missing variant, styling rigidity); add the variant or a documented escape hatch.
- **Breaking change blocks adoption:** ship codemods and a deprecation window; support two majors briefly.
- **Visual regressions flaky:** disable animations in test mode and pin fonts; compare with a threshold, not pixel-exact, for text-heavy components.
- **Bundle size grows:** per-component entry points and tree-shaking; measure with `size-limit`.

## 12. Expected Deliverables

1. Token architecture and generated outputs.
2. Component inventory and prioritized roadmap.
3. Implemented components with types and docs.
4. Storybook with stories and interaction tests.
5. Visual regression baselines.
6. Versioning/release configuration.
7. Adoption metrics and governance process.

## 13. References

- Style Dictionary — https://styledictionary.com/
- Radix UI primitives — https://www.radix-ui.com/primitives
- React Aria — https://react-spectrum.adobe.com/react-aria/
- Storybook — https://storybook.js.org/docs
- Changesets — https://github.com/changesets/changesets
- W3C Design Tokens Community Group — https://www.w3.org/community/design-tokens/
- "Design Systems" (Alla Kholmatova).
