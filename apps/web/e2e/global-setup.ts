import { execFileSync } from "node:child_process";
import path from "node:path";
import { createDb } from "@marketscope/db";
import { E2E_USER } from "./e2e-user";

/**
 * Seed the e2e database with deterministic synthetic history through the real collector, then
 * create the e2e account through the real account CLI. The seed script refuses database names
 * without "e2e"/"demo".
 */
export default async function globalSetup() {
  const url = process.env.E2E_DATABASE_URL ?? "postgres://localhost:5432/marketscope_e2e_test";
  const root = path.resolve(import.meta.dirname, "../../..");
  execFileSync("pnpm", ["--filter", "@marketscope/collector", "seed:synthetic", "--reset"], {
    cwd: root,
    env: { ...process.env, DATABASE_URL: url },
    stdio: "inherit",
  });
  const { sql, close } = createDb(url, { max: 1 });
  await sql`DELETE FROM auth_users WHERE email = ${E2E_USER.email}`;
  await sql`DELETE FROM auth_rate_limits`;
  await close();
  execFileSync(
    "pnpm",
    [
      "--filter",
      "@marketscope/web",
      "-s",
      "users",
      "create",
      "--username",
      E2E_USER.username,
      "--email",
      E2E_USER.email,
      "--password-stdin",
      "--yes",
    ],
    {
      cwd: root,
      env: { ...process.env, DATABASE_URL: url },
      input: E2E_USER.password,
      stdio: ["pipe", "inherit", "inherit"],
    },
  );
}
