import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Integration tests run against the shared test database (TEST_DATABASE_URL).
    globalSetup: ["../../packages/db/src/test-global-setup.ts"],
    fileParallelism: false,
  },
});
