---
name: visual-regression-testing
description: Catch unintended UI changes with deterministic screenshot testing—stable rendering, baselines, diff thresholds, and review workflow that avoids false-positive fatigue.
metadata:
  domain: frontend-and-uiux
  version: 1.0.0
  risk: low
---

# Visual Regression Testing

## 1. Purpose

Detect visual changes that unit tests cannot see: layout shifts, broken styles, overlapping text, and theme regressions. Visual tests are powerful but famously flaky—fonts, animations, dynamic data, and anti-aliasing produce noise. This skill covers making rendering deterministic, choosing the right tool, structuring the test matrix (components × themes × viewports), handling diffs, and keeping the review process trustworthy.

**Scope:** your own UI. Screenshots may capture real data—use fixtures and synthetic content.

## 2. Activation Conditions

- A design system or shared component library exists.
- CSS/Tailwind refactors risk unintended visual changes.
- Multiple themes or breakpoints must be verified.
- Reviewers keep finding visual bugs after merge.
- Keywords: visual regression, screenshot testing, Chromatic, Percy, Playwright screenshots, baseline, diff, pixelmatch, Storybook, flaky snapshots.

## 3. When Not to Use

- Rapidly evolving prototypes where baselines would change daily.
- Purely logical components with no visual output.
- When the team cannot commit to reviewing diffs—unreviewed baselines become meaningless.

## 4. Required Context

1. Component catalogue (Storybook or equivalent) and coverage gaps.
2. Rendering environments: local, CI container, hosted service.
3. Themes, locales, and viewports to cover.
4. Fonts and assets used (must load deterministically).
5. Existing CI runtime budget.

## 5. Operating Procedure

1. **Choose the approach**:
   - Component-level: Storybook + Chromatic/Playwright per story (fast, granular).
   - Page-level: Playwright against a seeded app (catches integration issues).
   - Both, with component tests as the primary signal.
2. **Make rendering deterministic**:
   - Fixed viewport and device scale factor.
   - Disable animations and caret; freeze time (`page.clock`).
   - Load fonts and wait for `document.fonts.ready`.
   - Use fixture data with fixed values (no random IDs, dates, avatars).
   - Disable third-party embeds or replace with placeholders.
3. **Define the matrix deliberately**: components × {light, dark} × {mobile 375, desktop 1280}; not every combination for every component.
4. **Capture and store baselines in version control or a hosted service** with explicit approval.
5. **Set comparison thresholds**: pixel diff tolerance for anti-aliasing; prefer per-region or perceptual diff over raw pixel count.
6. **Review every diff** before accepting a new baseline; a rubber-stamped baseline is worse than no test.
7. **Integrate into PRs** so the diff appears alongside code review.
8. **Keep runtime bounded**: run affected stories only (Chromatic does this natively), and parallelize shards.
9. **Quarantine flaky tests** and fix the determinism issue rather than widening thresholds.
10. **Track coverage**: which components/pages have visual tests, and the trend of escaped visual bugs.

## 6. Tools and Technologies

| Approach | Tools |
|---|---|
| Hosted component VRT | Chromatic (Storybook), Percy, Lost Pixel |
| Open source | Playwright `toHaveScreenshot`, `jest-image-snapshot`, reg-suit, BackstopJS |
| Storybook | `@storybook/test-runner` with screenshot addon |
| Diffing | pixelmatch, `odiff`, perceptual diff libraries |
| Determinism | Playwright clock API, CSS to disable animations, font preloading |

## 7. Practical Implementation

**Playwright component screenshot with determinism:**

```ts
import {test, expect} from "@playwright/test";

test.describe.configure({mode: "parallel"});

const VIEWPORTS = [{name: "mobile", width: 375, height: 812},
                   {name: "desktop", width: 1280, height: 900}];
const THEMES = ["light", "dark"] as const;

for (const theme of THEMES) {
  for (const vp of VIEWPORTS) {
    test(`Button matrix ${theme} ${vp.name}`, async ({page}) => {
      await page.setViewportSize({width: vp.width, height: vp.height});
      await page.emulateMedia({reducedMotion: "reduce", colorScheme: theme});
      await page.goto(`/iframe.html?id=components-button--all-variants&globals=theme:${theme}`);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator("#storybook-root")).toHaveScreenshot(
        `button-${theme}-${vp.name}.png`,
        {
          animations: "disabled",
          caret: "hide",
          maxDiffPixelRatio: 0.01,     // tolerate anti-aliasing
          threshold: 0.2,
          scale: "css",
        },
      );
    });
  }
}
```

**Global determinism styles for tests:**

```css
/* injected only in test/storybook environments */
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  scroll-behavior: auto !important;
}
.test-hide-caret { caret-color: transparent !important; }
```

**Playwright config with a locked environment:**

```ts
import {defineConfig, devices} from "@playwright/test";

export default defineConfig({
  testDir: "./tests/visual",
  expect: {toHaveScreenshot: {maxDiffPixels: 150}},
  use: {
    baseURL: "http://127.0.0.1:6006",
    deviceScaleFactor: 1,
    locale: "en-US",
    timezoneId: "UTC",
    colorScheme: "light",
    ...devices["Desktop Chrome"],
  },
  webServer: {command: "npm run storybook -- --ci --quiet", url: "http://127.0.0.1:6006",
              reuseExistingServer: !process.env.CI, timeout: 120_000},
});
```

**Freeze time and random data:**

```ts
test("invoice table", async ({page}) => {
  await page.clock.install({time: new Date("2026-11-04T10:00:00Z")});
  await page.route("**/api/invoices*", (route) =>
    route.fulfill({json: {items: [
      {id: "inv_001", amount: 4200, currency: "INR", status: "paid", due: "2026-11-10"},
      {id: "inv_002", amount: 1999, currency: "INR", status: "overdue", due: "2026-10-01"},
    ]}}),
  );
  await page.goto("/invoices");
  await expect(page.getByRole("table")).toHaveScreenshot("invoice-table.png");
});
```

**Component-level story with fixed args (Storybook):**

```tsx
export const AllVariants: Story = {
  render: () => (
    <div className="grid gap-4 p-6">
      <Button intent="primary">Save</Button>
      <Button intent="secondary">Cancel</Button>
      <Button intent="danger" disabled>Delete</Button>
    </div>
  ),
  parameters: {chromatic: {viewports: [375, 1280]}},
};
```

**Hosted service CI integration (Chromatic):**

```yaml
- name: Publish to Chromatic
  uses: chromaui/action@v11
  with:
    projectToken: ${{ secrets.CHROMATIC_PROJECT_TOKEN }}
    onlyChanged: true
    exitZeroOnChanges: true      # report changes without blocking until reviewed
```

**Baseline review checklist for reviewers:**

```text
[ ] Diff is explainable by the code change in this PR
[ ] No unintended layout shift, truncation, or overlap
[ ] Contrast and focus states unchanged unless intended
[ ] Both themes checked
[ ] Mobile width checked for text wrapping
```

**Handling intentional changes:**

```bash
npx playwright test --update-snapshots   # after reviewing the diff locally
git add tests/visual/**/*.png            # commit with a message explaining the change
```

## 8. Quality Standards

- Rendering is deterministic: no animation, caret, random data, or live network.
- Baselines are reviewed before acceptance; reviewers see the diff in the PR.
- Thresholds are tight enough to catch real regressions and justified per component.
- The matrix covers light/dark and at least mobile/desktop for shared components.
- Fonts and assets are loaded before capture (no FOUT snapshots).
- Flaky tests are fixed at the source, not silenced.
- Coverage of shared components is measured and prioritized.

## 9. Verification and Testing

- Seed a deliberate visual change (e.g. change a token) and confirm the suite fails with a visible diff.
- Re-run the same suite twice on the same commit; zero diffs (determinism check).
- Run in CI and locally; results must match (container parity).
- Verify fonts: a screenshot must not show fallback metrics.
- Check runtime: suite duration within the CI budget.

## 10. Security Considerations

- Screenshots can capture PII or secrets (tokens in URLs, customer data)—use synthetic fixtures and redact.
- Hosted services upload screenshots: confirm data residency and retention terms before enabling.
- Baseline images are binary artifacts in git; large volumes slow clones—use a hosted service or LFS.
- Do not run VRT against production with real accounts; use isolated environments.
- Storybook deployments must be access-controlled when they include unreleased UI.

## 11. Failure Handling

- **Diff on every run (flaky):** fonts not loaded, animations running, or GPU anti-aliasing differences between local and CI—run only in a container with the same image.
- **Huge diffs from a small change:** the component has unstable layout (dynamic timestamps) — fix fixtures first.
- **Snapshot tests slow:** reduce the matrix, use `onlyChanged`, and shard across runners.
- **Reviewers approve blindly:** require a written note per accepted change and limit baseline churn per PR.
- **Windows/macOS local mismatch:** capture only in CI (Docker) and treat local screenshots as advisory.

## 12. Expected Deliverables

1. Tooling choice and rationale.
2. Determinism configuration (fonts, clock, animations, fixtures).
3. Test matrix definition.
4. Baseline set committed/uploaded and reviewed.
5. CI integration and PR reporting.
6. Coverage report and flake log.

## 13. References

- Playwright visual comparisons — https://playwright.dev/docs/test-snapshots
- Chromatic — https://www.chromatic.com/docs/
- Percy — https://www.browserstack.com/docs/percy
- Storybook test-runner — https://storybook.js.org/docs/writing-tests/test-runner
- pixelmatch — https://github.com/mapbox/pixelmatch
- Playwright clock API — https://playwright.dev/docs/clock
