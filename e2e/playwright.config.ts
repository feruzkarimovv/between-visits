import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end smoke (WS0 R10) against a running `make demo` (DEMO_MODE=1, replay scenarios, no external keys).
 * Playwright is not a frontend dependency: this folder has its own package.json and lockfile.
 *
 *   cd e2e && npm ci && npx playwright install chromium
 *   BASE_URL=http://localhost:3000 npx playwright test
 *
 * Environment:
 *   BASE_URL           the dashboard (default http://localhost:3000, the `make demo` port). Any host or port works,
 *                      for example a frontend on :3137 whose NEXT_PUBLIC_API_BASE_URL points at a backend on :8137,
 *                      or the public demo URL. The browser talks to whatever backend that dashboard was built with.
 *   E2E_SCENARIO       replay scenario for the serious-event journey (default rosa_es_urgent)
 *   E2E_REPLAY_SPEED   replay speed, 1 | 2 | 4 (default 4)
 *
 * Both journeys create new records (a check-in, a serious-event report, a site query), so the suite can run again
 * against the same server without a reseed.
 */
const BASE_URL = (process.env.BASE_URL || "http://localhost:3000").replace(/\/$/, "");

export default defineConfig({
  testDir: ".",
  testMatch: "smoke.spec.ts",
  // The two journeys share one demo backend: run them one after the other.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // A 4x replay of the 166 s scenario plus the post-call pipeline and first-visit page compiles under `next dev`.
  timeout: 300_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [["list"], ["github"], ["html", { open: "never" }]] : [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: BASE_URL,
    actionTimeout: 20_000,
    navigationTimeout: 60_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 1000 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } }],
});
