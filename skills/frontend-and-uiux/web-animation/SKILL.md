---
name: web-animation
description: Implement purposeful web animation—CSS transitions, keyframes, the Web Animations API, and motion libraries—with performance, reduced-motion, and interruption handling.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Web Animation

## 1. Purpose

Use motion to explain change: where an element came from, what is happening, and what is interactive. Most web animation either does too much (distracting, slow) or is implemented on the wrong properties (layout-triggering animations that jank). This skill covers the motion vocabulary, choosing the right tool (CSS vs. WAAPI vs. library), animating only compositor-friendly properties, and respecting user preferences.

**Scope:** your own frontend. Animation is presentation; it must never gate functionality or hide state from assistive technology.

## 2. Activation Conditions

- Adding transitions, page transitions, micro-interactions, or reveal effects.
- Animations stutter, drop frames, or cause layout shift.
- Need to animate lists, dialogs, or drag interactions.
- `prefers-reduced-motion` support is required.
- Keywords: CSS transition, keyframes, animation, transform, opacity, will-change, requestAnimationFrame, Framer Motion, GSAP, Web Animations API, reduced motion, FLIP.

## 3. When Not to Use

- Animation would delay the user's task (mandatory waiting animations).
- Content that must be readable immediately (hero text fading in is a conversion risk).
- Complex 3D/scene animation (use threejs-development / webgl-engineering).

## 4. Required Context

1. What the motion must communicate (feedback, continuity, hierarchy).
2. Target devices and performance constraints (low-end mobile).
3. Existing animation library or design motion spec (duration/easing tokens).
4. Accessibility requirements.
5. Interaction triggers: hover, focus, click, route change, data change.

## 5. Operating Procedure

1. **Write the purpose** for each animation in one line ("confirm the item moved into the cart"). Delete animations without a purpose.
2. **Choose the mechanism**:
   - Simple state changes: CSS transitions.
   - Multi-step or looping: CSS `@keyframes`.
   - Interruption, sequencing, or dynamic values: Web Animations API or a library.
   - Layout/route transitions: View Transitions API where supported, with a fallback.
3. **Animate only `transform` and `opacity`** for continuous motion; these run on the compositor. Avoid animating `width`, `height`, `top`, `left`, `margin`, `box-shadow` (use transforms and pseudo-elements instead).
4. **Set duration and easing tokens**: micro-interactions 100–200 ms, transitions 200–300 ms, larger movements 300–500 ms; standard easing `cubic-bezier(0.2, 0, 0, 1)`.
5. **Honor `prefers-reduced-motion`** by replacing movement with an instant state change or a subtle fade.
6. **Handle interruption**: animations triggered mid-flight must not jump or snap; use `transition` for reversible interactions and WAAPI `commitStyles`/`cancel` correctly.
7. **Use FLIP for layout changes** (First, Last, Invert, Play) rather than animating layout properties.
8. **Keep JS off the hot path**: no per-frame React state updates; use refs and imperative animation, or `requestAnimationFrame`.
9. **Test on a low-end device** with CPU throttling and confirm 60 fps (16.7 ms frame budget).
10. **Provide a skip/instant path** for long sequences, and never block input during animation.

## 6. Tools and Technologies

| Need | Options |
|---|---|
| Declarative | CSS transitions, `@keyframes`, `@starting-style`, View Transitions API |
| Imperative | Web Animations API (`element.animate`) |
| Libraries | Motion (Framer Motion), GSAP, anime.js, AutoAnimate |
| React integration | `<Motion />`, layout animations, `useReducedMotion` |
| Scroll effects | `IntersectionObserver`, `scroll-timeline` (limited support) |
| Debugging | Chrome DevTools Performance/Animations panel, `will-change` inspection |

## 7. Practical Implementation

**Motion tokens as CSS custom properties:**

```css
:root {
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --dur-fast: 120ms;
  --dur-base: 220ms;
  --dur-slow: 400ms;
}

@media (prefers-reduced-motion: reduce) {
  :root { --dur-fast: 1ms; --dur-base: 1ms; --dur-slow: 1ms; }
}
```

**Compositor-friendly dialog transition:**

```css
.dialog {
  opacity: 0;
  transform: translateY(8px) scale(0.98);
  transition: opacity var(--dur-base) var(--ease-standard),
              transform var(--dur-base) var(--ease-standard);
}
.dialog[data-open="true"] { opacity: 1; transform: none; }

@media (prefers-reduced-motion: reduce) {
  .dialog { transition: opacity 1ms; transform: none; }
}
```

**Entry animation with `@starting-style` (modern, no JS):**

```css
.popover {
  opacity: 1;
  translate: 0 0;
  transition: opacity 200ms ease, translate 200ms ease, display 200ms allow-discrete;
}
@starting-style {
  .popover { opacity: 0; translate: 0 -6px; }
}
```

**WAAPI for interruptible, dynamic animation:**

```ts
export function slideTo(el: HTMLElement, x: number) {
  const current = el.getBoundingClientRect().left;
  const anim = el.animate(
    [{transform: `translateX(${current - x}px)`}, {transform: "translateX(0px)"}],
    {duration: 220, easing: "cubic-bezier(0.2, 0, 0, 1)", fill: "none"},
  );
  return anim.finished;                    // await if the caller must sequence
}
```

**FLIP for list reordering (no layout animation):**

```ts
export function flip(nodes: HTMLElement[]) {
  const first = new Map(nodes.map((n) => [n, n.getBoundingClientRect()]));
  return () => {
    for (const n of nodes) {
      const f = first.get(n)!;
      const l = n.getBoundingClientRect();
      const dx = f.left - l.left;
      const dy = f.top - l.top;
      if (!dx && !dy) continue;
      n.animate(
        [{transform: `translate(${dx}px, ${dy}px)`}, {transform: "translate(0,0)"}],
        {duration: 250, easing: "cubic-bezier(0.2, 0, 0, 1)"},
      );
    }
  };
}
// usage: const play = flip([...list.children]); renderNewOrder(); play();
```

**Reduced-motion hook (React):**

```tsx
import {useEffect, useState} from "react";

export function useReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );
  useEffect(() => {
    const mq = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}
```

**Motion (Framer Motion) with layout animation and reduced motion:**

```tsx
import {AnimatePresence, motion, useReducedMotion} from "motion/react";

export function Toast({open, text}: {open: boolean; text: string}) {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          role="status"
          initial={reduce ? {opacity: 0} : {opacity: 0, y: 12}}
          animate={reduce ? {opacity: 1} : {opacity: 1, y: 0}}
          exit={reduce ? {opacity: 0} : {opacity: 0, y: 8}}
          transition={{duration: reduce ? 0.001 : 0.22, ease: [0.2, 0, 0, 1]}}
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-surface px-4 py-2 shadow-lg"
        >
          {text}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

**View Transitions with fallback:**

```tsx
function navigateWithTransition(update: () => void) {
  if (!document.startViewTransition) { update(); return; }
  document.startViewTransition(update);
}
```

**Performance measurement:**

```ts
// Detect long frames during animation (DevTools Performance panel is primary; this is a smoke test)
let last = performance.now();
let longFrames = 0;
function tick(now: number) {
  if (now - last > 24) longFrames++;      // > 24 ms suggests dropped frames on 60 Hz
  last = now;
  if (running) requestAnimationFrame(tick);
}
```

## 8. Quality Standards

- Every animation has a documented purpose and a duration from the token scale.
- Only `transform`, `opacity`, and filter effects animate during interaction; layout properties never animate.
- Reduced motion is respected everywhere, including scroll-triggered and library-driven animations.
- Animations are interruptible and never block input or navigation.
- No animation gates content reveal for assistive technology (content is in the DOM and accessible immediately).
- 60 fps on mid-tier mobile with 4× CPU throttling; no long tasks > 50 ms during transitions.
- No layout shift (CLS) caused by animations.

## 9. Verification and Testing

- Chrome DevTools Performance recording during interaction: check for dropped frames and forced reflows.
- Lighthouse/CLS: confirm no layout shift introduced.
- Toggle OS reduced-motion and confirm animations collapse to instant/subtle.
- Keyboard test: interact during an animation; input is never blocked.
- Visual regression snapshots at animation end state (not mid-flight, which is flaky).
- Playwright: assert final styles/visibility rather than timing.

## 10. Security Considerations

- Animation libraries are dependencies: pin versions and check maintenance status.
- Never animate content into view that should be hidden for security reasons—`opacity: 0` content is still in the DOM and readable.
- Avoid `will-change: transform` on many elements (memory blowup) and never on `body` permanently.
- Scroll-jacking and forced animations can be an accessibility and seizure risk; avoid rapid flashing (>3 flashes/second).
- Inline styles set from user input must be validated (CSS injection via `style` attributes).

## 11. Failure Handling

- **Stutter on scroll animations:** use `IntersectionObserver` with a root margin and animate compositor properties; avoid reading layout in scroll handlers.
- **Snap on interrupted transitions:** CSS transitions handle reversal automatically; WAAPI animations need `cancel()` and a re-measure, not stacked fills.
- **Animation library janks on large lists:** animate a container, not per-item; or use CSS with `@starting-style`.
- **Layout shift after animation:** ensure `fill: "forwards"` is not used where final layout differs; keep the final state in CSS and animate to it.
- **Animations run in tests and break snapshots:** disable via a test flag (`data-test-animations="off"`) and reduced-motion emulation in Playwright.

## 12. Expected Deliverables

1. Motion principles and token scale (duration/easing).
2. Implemented animations with purpose notes.
3. Reduced-motion variants.
4. Performance measurement results.
5. Interruption/sequencing behavior description.
6. Tests updated for final-state assertions.

## 13. References

- MDN CSS transitions & animations — https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_transitions
- Web Animations API — https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API
- `prefers-reduced-motion` — https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion
- View Transitions API — https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API
- Motion documentation — https://motion.dev/docs
- GSAP documentation — https://gsap.com/docs/
- "FLIP" technique (Paul Lewis) — https://aerotwist.com/blog/flip-your-animations/
- WCAG 2.3.3 Animation from Interactions — https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html
