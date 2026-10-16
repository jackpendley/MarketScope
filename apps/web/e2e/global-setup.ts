import { execFileSync } from "node:child_process";
import path from "node:path";

/**
 * Seed the e2e database with deterministic synthetic history through the real collector.
 * The seed script refuses database names without "e2e"/"demo".
 */
export default function globalSetup() {
  const url = process.env.E2E_DATABASE_URL ?? "postgres://localhost:5432/marketscope_e2e_test";
  execFileSync("pnpm", ["--filter", "@marketscope/collector", "seed:synthetic", "--reset"], {
    cwd: path.resolve(import.meta.dirname, "../../.."),
    env: { ...process.env, DATABASE_URL: url },
    stdio: "inherit",
  });
}
