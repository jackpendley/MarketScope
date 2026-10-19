import { randomBytes } from "node:crypto";
import { defineConfig, devices } from "@playwright/test";
import { STORAGE_STATE } from "./e2e/e2e-user";

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
    // Signs in once (e2e/auth.setup.ts); every other project reuses the saved session.
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1400, height: 1000 },
        storageState: STORAGE_STATE,
      },
      dependencies: ["setup"],
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"], storageState: STORAGE_STATE },
      dependencies: ["setup"],
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
    // A throwaway auth secret for the local e2e server, generated per run.
    env: {
      DATABASE_URL: E2E_DATABASE_URL,
      BETTER_AUTH_SECRET: (process.env.E2E_AUTH_SECRET ??= randomBytes(32).toString("hex")),
    },
  },
});
