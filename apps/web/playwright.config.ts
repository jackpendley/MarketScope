import { defineConfig, devices } from "@playwright/test";

// End-to-end smoke tests against a production build, served from a database seeded with
// SYNTHETIC history (see e2e/global-setup.ts). Run `pnpm build` first.
const E2E_DATABASE_URL =
  process.env.E2E_DATABASE_URL ?? "postgres://localhost:5432/marketscope_e2e_test";
const PORT = 3200;

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1400, height: 1000 } },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
      testMatch: /(mobile|screenshots)\.spec\.ts/,
    },
  ],
  webServer: {
    command: `pnpm exec next start -p ${PORT}`,
    // Readiness must not depend on the database: Playwright starts the server before
    // globalSetup has created and seeded it.
    url: `http://localhost:${PORT}/api/health/live`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    // Process env wins over apps/web/.env.local, so the server reads the e2e database.
    env: { DATABASE_URL: E2E_DATABASE_URL },
  },
});
