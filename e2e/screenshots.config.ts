import { defineConfig, devices } from "@playwright/test";

/**
 * README and deck screenshots (WS3 F19) and the 390 px width check, against a running `make demo DEMO_PROD=1`
 * (the production frontend build: no Next.js dev badge). Same package as the R10 smoke; its own config so the smoke
 * keeps `testMatch: "smoke.spec.ts"`.
 *
 *   cd e2e && npm ci && npx playwright install chromium
 *   BASE_URL=http://localhost:3000 npx playwright test --config screenshots.config.ts
 *
 * Writes docs/screenshots/*.png (1280 x 800 viewport, synthetic data only). Run it against a freshly seeded demo
 * backend: it replays one scenario, signs and sends one serious-event report and answers one site query.
 * Environment: BASE_URL, E2E_SCENARIO (default rosa_es_urgent), E2E_REPLAY_SPEED (default 4), SHOTS_DIR.
 */
const BASE_URL = (process.env.BASE_URL || "http://localhost:3000").replace(/\/$/, "");

export default defineConfig({
  testDir: ".",
  testMatch: "screenshots.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 360_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: BASE_URL,
    actionTimeout: 20_000,
    navigationTimeout: 60_000,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 },
    },
  ],
});
