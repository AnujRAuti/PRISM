---
name: cross-browser-and-device-testing
description: Verify the app across the browsers and devices that matter—matrix selection from analytics, Playwright multi-browser runs, feature detection, and costly-engine quirk handling.
metadata:
  domain: testing-and-debugging
  version: 1.0.0
  risk: low
---

# Cross-Browser and Device Testing

## 1. Purpose

Catch the failures that only appear in a specific engine, viewport, or input type—Safari's date inputs and focus behavior, iOS viewport quirks, Android keyboard resizes, Firefox's form restoration, and font metric differences. Teams either test one browser and ship blind, or run an enormous matrix that costs more than it finds. This skill covers selecting the matrix from real usage, structuring multi-browser tests, distinguishing feature detection from UA sniffing, and triaging engine-specific defects.

**Scope:** your own application and test hardware. Device-farm usage may be metered and share infrastructure—keep runs bounded and clean up sessions.

## 2. Activation Conditions

- Launching to a market with differing browser share (iOS-heavy, Android-heavy).
- Users report issues that "work fine for me".
- Safari/WebKit-specific defects (layout, storage, autoplay, dates).
- Mobile keyboard, viewport, or touch interaction failures.
- Keywords: cross-browser testing, WebKit, Safari, Firefox, Chromium, Playwright projects, device farm, BrowserStack, responsive, viewport, touch, feature detection, polyfill, `@supports`, iPhone Safari.

## 3. When Not to Use

- The app is internal and constrained to one managed browser (document the exception).
- Pure logic defects (unit tests catch those).
- Visual-only differences acceptable by product decision (still capture them in visual regression).

## 4. Required Context

1. Analytics: browser/OS/device share for your actual traffic.
2. Supported matrix stated in policy (tiers: fully supported, works-but-untested, unsupported).
3. Feature usage: WebSockets, WebRTC, storage quota, service workers, `Intl`, payment APIs.
4. Budget for real devices and device farms.
5. Known engine differences that affect your code paths.

## 5. Operating Procedure

1. **Derive the matrix from analytics**, covering ~95% of sessions: typically Chromium (desktop + Android), WebKit (Safari desktop + iOS), Firefox (desktop). Add a real iOS device; emulation does not reproduce iOS Safari behavior.
2. **Define support tiers in writing**: Tier 1 (blocking, tested in CI), Tier 2 (smoke-tested pre-release), Tier 3 (best effort).
3. **Test engines, not brands**: Playwright runs Chromium, Firefox, and WebKit; the three engine families catch most issues.
4. **Use feature detection** (`'showPicker' in HTMLInputElement.prototype`, `CSS.supports`, `typeof ResizeObserver`) rather than user-agent parsing; UA strings lie and change.
5. **Run a focused cross-browser subset in PR CI** and the full matrix nightly or pre-release; do not multiply runtime where the signal is redundant.
6. **Add real-device smoke tests** for iOS Safari and a mid-tier Android for each release.
7. **Handle known engine differences explicitly** with documented shims: date input behavior, `:focus-visible`, `dvh`, `scrollbar-gutter`, storage partitioning, autoplay policies.
8. **Capture engine-specific artifacts** (screenshots, video, console) with the project name in the filename.
9. **Triage by engine and version**, then ask whether the difference is a bug in your code (most common), a missing polyfill, or an unavoidable platform difference to document.
10. **Keep the matrix current** quarterly: remove browsers below 0.5% share and add emerging ones.

## 6. Tools and Technologies

| Concern | Options |
|---|---|
| Multi-engine automation | Playwright projects (chromium/firefox/webkit) |
| Real devices | BrowserStack, Sauce Labs, LambdaTest, in-house device lab |
| Mobile emulation | Playwright device descriptors, Chrome DevTools device mode |
| Feature detection | `CSS.supports`, `in` operator, `HTMLScriptElement.supports` |
| Polyfills | core-js, `polyfill.io` alternatives (self-hosted), `@oddbird/css-anchor-positioning` etc. |
| Compatibility data | MDN browser-compat-data, caniuse |
| Visual cross-engine | Playwright screenshots per project + visual-regression-testing |

## 7. Practical Implementation

**Playwright projects per engine with a focused subset:**

```ts
import {defineConfig, devices} from "@playwright/test";

const engines = [
  {name: "chromium", use: {...devices["Desktop Chrome"]}},
  {name: "firefox", use: {...devices["Desktop Firefox"]}},
  {name: "webkit", use: {...devices["Desktop Safari"]}},
  {name: "ios", use: {...devices["iPhone 14"], isMobile: true, hasTouch: true}},
  {name: "android", use: {...devices["Pixel 7"], isMobile: true, hasTouch: true}},
];

export default defineConfig({
  projects: engines.map((e) => ({
    ...e,
    grep: process.env.FULL_MATRIX ? /.*/ : /@cross-browser/,   // tag the subset
  })),
  use: {baseURL: process.env.BASE_URL ?? "http://localhost:3000",
        trace: "on-first-retry", screenshot: "only-on-failure"},
});
```

```ts
// Tag only the tests that genuinely need engine coverage
test.describe("checkout @cross-browser", () => {
  test("saved card flow completes", async ({page}) => { /* ... */ });
});

test("admin bulk import", async ({page}) => {
  test.skip(({browserName}) => browserName !== "chromium", "chromium-only back office");
  // ...
});
```

```bash
# PR: subset across engines
npx playwright test --project=chromium --project=webkit --project=firefox

# Nightly / pre-release: everything on every engine
FULL_MATRIX=1 npx playwright test
```

**Feature detection instead of UA sniffing:**

```ts
// BAD: user agents are unreliable and frozen in some browsers
const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

// GOOD: ask the platform what it supports
export const supports = {
  datePicker: "showPicker" in HTMLInputElement.prototype,
  popover: "showPopover" in HTMLElement.prototype,
  viewTransition: "startViewTransition" in document,
  dvh: CSS.supports("height", "100dvh"),
  scrollbarGutter: CSS.supports("scrollbar-gutter", "stable"),
  containerQueries: CSS.supports("container-type", "inline-size"),
  webShare: typeof navigator.share === "function",
};
```

```ts
export function pickDateInput(el: HTMLInputElement) {
  if (supports.datePicker) {
    el.showPicker();                        // Chromium/WebKit modern
  } else {
    el.focus();                             // Firefox: native focus opens the picker
  }
}
```

```css
/* Progressive enhancement with @supports rather than browser hacks */
.hero { min-height: 100vh; }
@supports (height: 100dvh) {
  .hero { min-height: 100dvh; }             /* stable when mobile browser bars hide */
}
```

**Known engine differences: a documented table in the repo**

```markdown
| Area                     | Chromium                | WebKit (Safari/iOS)                  | Firefox                    | Our handling                         |
|--------------------------|-------------------------|--------------------------------------|----------------------------|--------------------------------------|
| `<input type="date">`    | Native picker, ISO value| iOS wheel picker, locale display     | Text input + calendar icon | `showPicker()` + ISO parse fallback  |
| `:focus-visible`         | Good                    | Good (14.4+), older differs          | Good                       | Never style `:focus` away entirely   |
| Viewport height on scroll| `100vh` stable          | Toolbar collapse changes `vh`        | Stable                     | `dvh` with `vh` fallback             |
| Back/forward form restore| Restores values         | Restores, `pageshow` semantics differ| Restores aggressively      | `pageshow` handler to re-sync state  |
| Storage partitioning     | Third-party partitioned | ITP-friendly, aggressive expiry      | Partitioned                | No cross-site storage dependence     |
| Autoplay media           | Muted allowed           | Stricter, requires gesture           | Muted allowed              | Never autoplay audio; poster + click |
| `Intl` formatting        | Full                    | Full on modern versions              | Full                       | Test `en-IN` formatting explicitly   |
```

**Handling iOS Safari specifics that break tests:**

```ts
test("sticky header stays put while the keyboard is open (iOS)", async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== "ios", "iOS-specific keyboard behavior");
  await page.goto("/messaging");
  await page.getByRole("textbox", {name: "Message"}).focus();
  await page.keyboard.type("hello");
  // Assert layout invariant rather than exact pixels
  const header = page.getByRole("banner");
  await expect(header).toBeVisible();
  const box = await header.boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(0);
});
```

**Responsive × touch matrix (separate from engines):**

```ts
const viewports = [
  {name: "mobile", width: 375, height: 812, hasTouch: true, isMobile: true},
  {name: "tablet", width: 820, height: 1180, hasTouch: true, isMobile: true},
  {name: "desktop", width: 1280, height: 900, hasTouch: false, isMobile: false},
];

for (const vp of viewports) {
  test(`primary nav is reachable at ${vp.name} @cross-browser`, async ({page}) => {
    await page.setViewportSize({width: vp.width, height: vp.height});
    await page.goto("/");
    if (vp.width < 768) {
      await page.getByRole("button", {name: "Open menu"}).click();
    }
    await expect(page.getByRole("navigation", {name: "Primary"})).toBeVisible();
  });
}
```

**Real-device smoke script (device farm, bounded and tagged):**

```python
# scripts/device_smoke.py — runs only on release candidates
JOURNEYS = [
    ("iPhone 14 · Safari", "Safari", "15", "/checkout"),
    ("Pixel 7 · Chrome", "chrome", None, "/checkout"),
    ("iPad Air · Safari", "Safari", "16", "/dashboard"),
]
# For each: start session, run the three-step journey, capture video,
# mark the build "release-blocking" if any journey fails; always release sessions.
```

**Detecting engine-specific console errors during the run:**

```ts
test.afterEach(async ({page}, testInfo) => {
  const errors = testInfo.attachments.filter((a) => a.name === "console-error");
  if (errors.length) testInfo.attach("console-errors.json", {body: JSON.stringify(errors.map(String))});
});

test.beforeEach(async ({page}, testInfo) => {
  page.on("console", (msg) => {
    if (msg.type() === "error") void testInfo.attach("console-error", {body: msg.text()});
  });
  page.on("pageerror", (err) => void testInfo.attach("console-error", {body: err.message}));
});
```

**Matrix cost control:**

```bash
# Estimate before running the full grid
TESTS=$(npx playwright test --list --reporter=json | jq '[.. | .tests? // empty] | length')
echo "tests=$TESTS projects=5 -> $((TESTS * 5)) runs"
```

## 8. Quality Standards

- The supported matrix is written down and derived from analytics, with tiers and owners.
- Tier 1 engines run in CI on every PR for a tagged subset, and nightly in full.
- Real iOS Safari and mid-tier Android hardware are smoke-tested each release.
- No user-agent sniffing for capability decisions; feature detection or `@supports` only.
- Engine differences are documented in a maintained table with the handling strategy.
- Failures are triaged as bug/polyfill/acceptable-difference, and acceptable differences are recorded.
- Device-farm sessions are always released; runs are budgeted.
- Visual baselines exist per engine where rendering differs legitimately.

## 9. Verification and Testing

- Confirm the subset actually runs on all Tier 1 engines in CI (check the report matrix, not the config).
- Introduce a deliberate WebKit-only CSS bug (e.g. `aspect-ratio` misuse) and confirm the WebKit project catches it.
- Verify feature-detection fallbacks by stubbing the API away (`delete HTMLInputElement.prototype.showPicker`).
- Compare visual baselines across engines; differences must be explainable, not "expected".
- Validate device-farm runs report pass/fail to the release gate.

## 10. Security Considerations

- Device-farm and browser-testing services receive test credentials and sometimes full page content: use scoped test accounts and review the vendor's data handling.
- Public tunnel tools expose local ports to the internet—rotate keys, restrict to specific paths, and close tunnels after the session.
- Cross-origin iframes, third-party scripts, and payment forms often behave differently per engine; never disable a security control (CSP, SRI) to make a test pass in one browser.
- Browser storage partitioning affects auth flows; test that session handling is secure across engines, not merely working.
- Do not install untrusted browser extensions or drivers in CI runners used for release builds.

## 11. Failure Handling

- **Fails only on WebKit in CI:** often timing or font differences; check trace, and never paper over it with a longer timeout before verifying the actual cause.
- **Works in emulation, fails on a real iPhone:** emulate real hardware for Tier 1 smoke; emulation misses touch, safe areas, and iOS storage behavior.
- **Matrix runtime explodes:** tag tests intentionally, shard, and run full coverage nightly rather than per PR.
- **A quirk appears in a new browser version:** pin test browser versions in CI while triaging, and add the case to the engine-difference table.
- **Polyfill breaks another engine:** self-host the polyfill, feature-detect its need, and test the polyfilled path explicitly.

## 12. Expected Deliverables

1. Support matrix with tiers, derived from analytics.
2. Playwright project configuration per engine and viewport.
3. Tagged cross-browser subset and its CI job.
4. Feature-detection utilities and `@supports` fallbacks.
5. Engine-difference table with handling strategy.
6. Real-device smoke checklist per release.
7. Matrix cost report and refresh cadence.

## 13. References

- Playwright browsers and projects — https://playwright.dev/docs/test-projects
- Playwright emulation (devices, isMobile) — https://playwright.dev/docs/emulation
- MDN browser compatibility data — https://github.com/mdn/browser-compat-data
- caniuse — https://caniuse.com/
- web.dev, "Viewport units and `dvh`" — https://web.dev/blog/viewport-units
- Safari release notes (WebKit) — https://webkit.org/blog/
- Firefox release notes — https://www.mozilla.org/firefox/releases/
- MDN `CSS.supports` — https://developer.mozilla.org/en-US/docs/Web/API/CSS/supports_static
