import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname),
      "server-only": path.resolve(import.meta.dirname, "tests/server-only-stub.ts"),
    },
  },
  test: {
    // API route tests run against the shared test database.
    globalSetup: ["../../packages/db/src/test-global-setup.ts"],
    fileParallelism: false,
    // Playwright specs live in e2e/ and run with `pnpm test:e2e`.
    exclude: ["e2e/**", "node_modules/**"],
    env: {
      DATABASE_URL: process.env.TEST_DATABASE_URL ?? "postgres://localhost:5432/marketscope_test",
    },
  },
});
