import { defineConfig } from "@playwright/test";

/**
 * End-to-end tests run against the real API (with its database, seeded by `scripts/e2e.sh`), serving
 * the built app at /app/. Journeys change data and depend on each other, so they run one at a time.
 *
 * Locally the machine's own Chrome is used (nothing to download); CI installs Chromium.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:8002";
const channel = process.env.CI || process.env.E2E_BUNDLED ? undefined : "chrome";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    channel,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    {
      name: "tablet",
      testMatch: /responsive\.spec\.ts/,
      use: { viewport: { width: 768, height: 1024 } },
    },
    {
      name: "phone",
      testMatch: /responsive\.spec\.ts/,
      use: { viewport: { width: 390, height: 844 }, hasTouch: true },
    },
    {
      name: "wide",
      testMatch: /responsive\.spec\.ts/,
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: "small-phone",
      testMatch: /responsive\.spec\.ts/,
      use: { viewport: { width: 360, height: 740 }, hasTouch: true },
    },
    {
      name: "laptop",
      testMatch: /responsive\.spec\.ts/,
      use: { viewport: { width: 1024, height: 768 } },
    },
  ],
});
