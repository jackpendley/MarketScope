import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globalSetup: ["./src/test-global-setup.ts"],
    // Integration tests share one database; run files one at a time.
    fileParallelism: false,
  },
});
