---
name: web-accessibility
description: Build and audit accessible web interfaces—semantics, keyboard operation, focus management, ARIA used sparingly, forms, and screen-reader tested behavior to WCAG 2.2 AA.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Web Accessibility

## 1. Purpose

Make interfaces usable by people who use keyboards, screen readers, magnification, voice control, and reduced-motion settings—and meet WCAG 2.2 AA where required by law or contract. Accessibility is mostly a semantics problem: correct elements, labels, and focus order solve most issues, while ARIA added carelessly creates new ones. This skill provides a build checklist plus an audit procedure with tooling and manual verification.

**Scope:** your own product. Automated tools catch ~30–40% of issues; the rest require keyboard and screen-reader testing.

## 2. Activation Conditions

- Building new UI components (dialogs, menus, comboboxes, tables, forms).
- Preparing for an accessibility audit or legal compliance requirement (EAA, ADA, Section 508, India RPwD).
- Automated audit reports a backlog of violations.
- Users report keyboard or screen-reader problems.
- Keywords: accessibility, a11y, WCAG, ARIA, keyboard navigation, focus trap, screen reader, contrast, semantic HTML, axe, NVDA, VoiceOver.

## 3. When Not to Use

- Backend-only work with no user interface.
- Purely visual marketing graphics with alternative text already handled at a different layer.

## 4. Required Context

1. Compliance target (WCAG 2.2 A/AA/AAA) and legal context.
2. Component library and its accessibility baseline.
3. Supported browsers and assistive technology (AT) combinations.
4. Design system color tokens and typography scale.
5. Existing audit reports and known issues.

## 5. Operating Procedure

1. **Start with native semantics**: `button`, `a`, `input`, `label`, `table`, `dialog` where possible; add ARIA only to fill gaps.
2. **Guarantee keyboard operation**: every interactive element reachable by Tab, operable with Enter/Space/arrows as appropriate, and no keyboard traps.
3. **Manage focus**: move focus into dialogs on open, trap it while open, restore it on close; use `:focus-visible` styling that is clearly visible.
4. **Provide names**: every control has an accessible name (`<label>`, `aria-label`, or `aria-labelledby`), including icon-only buttons.
5. **Announce dynamic changes** with appropriate live regions (`aria-live="polite"` for updates, `role="alert"` for errors) and avoid over-announcing.
6. **Structure content**: one `h1`, logical heading order, landmarks (`header/nav/main/footer`), skip link.
7. **Forms**: labels tied to inputs, instructions before fields, errors associated via `aria-describedby` and `aria-invalid`, no placeholder-as-label.
8. **Color and contrast**: 4.5:1 for body text, 3:1 for large text and UI components; never use color alone to convey meaning.
9. **Motion**: respect `prefers-reduced-motion`; avoid autoplay; provide pause controls.
10. **Media**: captions for video, transcripts for audio, meaningful alt text (empty `alt=""` for decorative).
11. **Test with keyboard only**, then with a screen reader (NVDA+Firefox or VoiceOver+Safari), then run automated tools.
12. **Record and remediate** findings, then re-test.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Automated | axe DevTools, Lighthouse, `jest-axe`/`vitest-axe`, Pa11y |
| Screen readers | NVDA (Windows), VoiceOver (macOS/iOS), TalkBack (Android), Orca (Linux) |
| Browser inspection | Chrome DevTools accessibility pane, Accessibility Tree |
| Contrast | WebAIM Contrast Checker, `polished` for programmatic checks |
| Lint | `eslint-plugin-jsx-a11y` |
| Manual | Keyboard-only pass, zoom 200%, Windows High Contrast Mode |

## 7. Practical Implementation

**Semantic button vs. div (the most common bug):**

```tsx
// BAD: not focusable, no role, no keyboard activation
<div className="btn" onClick={save}>Save</div>

// GOOD
<button type="button" onClick={save}>Save</button>

// Icon-only button needs an accessible name
<button type="button" aria-label="Close dialog" onClick={close}>
  <CloseIcon aria-hidden="true" />
</button>
```

**Accessible dialog with focus management:**

```tsx
import {useEffect, useRef} from "react";

export function Modal({open, onClose, title, children}: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();     // native focus trap + Esc handling
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="modal-title"
            className="rounded-card p-6 backdrop:bg-black/40">
      <h2 id="modal-title" className="text-lg font-semibold">{title}</h2>
      {children}
      <form method="dialog" className="mt-4">
        <button className="rounded-lg bg-brand px-4 py-2 text-brand-contrast">Close</button>
      </form>
    </dialog>
  );
}
```

**Accessible form with error association:**

```tsx
export function EmailField({value, onChange, error}: {
  value: string; onChange: (v: string) => void; error?: string;
}) {
  const id = "email";
  const errorId = `${id}-error`;
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">Email address</label>
      <p id={`${id}-hint`} className="text-sm text-content-muted">We use this for receipts only.</p>
      <input
        id={id}
        name="email"
        type="email"
        autoComplete="email"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${errorId} ${id}-hint` : `${id}-hint`}
        className="mt-1 rounded-md border px-3 py-2 aria-[invalid=true]:border-danger"
      />
      {error && (
        <p id={errorId} role="alert" className="mt-1 text-sm text-danger">{error}</p>
      )}
    </div>
  );
}
```

**Live region for async status (avoid spamming):**

```tsx
<div aria-live="polite" aria-atomic="true" className="sr-only">
  {status === "saving" ? "Saving changes" : status === "saved" ? "Changes saved" : ""}
</div>
```

**Skip link and landmarks:**

```tsx
<a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4
    focus:rounded-md focus:bg-surface focus:px-4 focus:py-2">Skip to main content</a>
<header>…</header>
<nav aria-label="Primary">…</nav>
<main id="main" tabIndex={-1}>…</main>
```

**Reduced motion:**

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

**Data table with proper headers:**

```tsx
<table>
  <caption className="sr-only">Orders placed in the last 30 days</caption>
  <thead>
    <tr><th scope="col">Order</th><th scope="col">Total</th><th scope="col">Status</th></tr>
  </thead>
  <tbody>
    {orders.map((o) => (
      <tr key={o.id}>
        <th scope="row">{o.id}</th>
        <td>{formatMoney(o.totalCents)}</td>
        <td>{o.status}</td>
      </tr>
    ))}
  </tbody>
</table>
```

**Automated test with axe in CI:**

```ts
import {render} from "@testing-library/react";
import {axe, toHaveNoViolations} from "jest-axe";
expect.extend(toHaveNoViolations);

test("checkout form has no detectable a11y violations", async () => {
  const {container} = render(<CheckoutForm onSubmit={async () => {}} />);
  expect(await axe(container)).toHaveNoViolations();
});
```

## 8. Quality Standards

- All interactive controls are native elements or fully ARIA-equivalent and keyboard operable.
- Every control has an accessible name; icon-only controls use `aria-label`.
- Focus is always visible and logically ordered; dialogs trap and restore focus.
- Errors are programmatically associated with fields and announced.
- Contrast meets AA in both themes.
- Content reflows at 320 px and 200% zoom without loss of function.
- Motion respects `prefers-reduced-motion`.
- Automated checks are in CI; manual keyboard + screen-reader passes are documented.

## 9. Verification and Testing

```bash
npx axe https://localhost:3000 --exit          # if using axe CLI against a running app
npx lighthouse https://localhost:3000 --only-categories=accessibility --output=json
npx pa11y-ci
```

Manual protocol per component: Tab through (order and visibility), Shift+Tab back, activate with Enter/Space, open/close dialogs with Esc and check focus return, run NVDA/VoiceOver and confirm names/roles/states, zoom to 200%, and test Windows High Contrast mode. Record results and any residual issues.

## 10. Security Considerations

- Accessibility overlays are not a fix and can introduce script injection; remediate the source.
- Screen-reader-only text is still in the DOM—do not put secrets or internal notes in `sr-only` blocks.
- `aria-label` overrides visible text; keep them consistent so voice-control users can say what they see ("click Email" must match the visible label).
- User-generated content rendered with `dangerouslySetInnerHTML` can break semantics and inject scripts; sanitize and preserve headings/links.
- Autoplay audio and flashing content are both an accessibility and safety issue.

## 11. Failure Handling

- **Tab order jumps:** DOM order does not match visual order—fix the DOM, do not use positive `tabindex`.
- **Dialog focus escapes:** use native `<dialog>` or a tested focus-trap library; verify restore-to-trigger.
- **Screen reader announces "button" without a name:** missing accessible name—add visible text or `aria-label`.
- **Live region too chatty:** debounce and only announce final state, not every keystroke.
- **Custom select is unusable:** replace with a library that implements the ARIA combobox pattern correctly rather than hand-rolling.
- **Contrast fails only in dark mode:** token-level fix, not per-component overrides.

## 12. Expected Deliverables

1. Component-level accessibility checklist results.
2. Fixed markup with semantics and ARIA where necessary.
3. Keyboard and screen-reader test notes.
4. Automated test integration (axe in unit/CI, Lighthouse budget).
5. Contrast report for both themes.
6. Residual issues list with owners.

## 13. References

- WCAG 2.2 — https://www.w3.org/TR/WCAG22/
- WAI-ARIA Authoring Practices Guide — https://www.w3.org/WAI/ARIA/apg/
- MDN Accessibility — https://developer.mozilla.org/en-US/docs/Web/Accessibility
- WebAIM contrast checker — https://webaim.org/resources/contrastchecker/
- `jest-axe` — https://github.com/nickcolley/jest-axe
- Deque axe-core — https://github.com/dequelabs/axe-core
- The A11Y Project checklist — https://www.a11yproject.com/checklist/
