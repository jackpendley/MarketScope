// Helpers for integration tests that run against a real PostgreSQL database.
import type { Sql } from "postgres";
import { runMigrations } from "./migrate";

export const TEST_DATABASE_URL =
  process.env.TEST_DATABASE_URL ?? "postgres://localhost:5432/marketscope_test";

if (!/test/.test(new URL(TEST_DATABASE_URL).pathname)) {
  // Guard against truncating a real database by accident.
  throw new Error(
    `Refusing to run tests against non-test database: ${new URL(TEST_DATABASE_URL).pathname}`,
  );
}

/** Vitest globalSetup hook: migrate the test database once per run. */
export async function setupTestDatabase(): Promise<void> {
  await runMigrations(TEST_DATABASE_URL);
}

/** Empty every data table (bookmakers are re-seeded by the collector or tests as needed). */
export async function resetDatabase(sql: Sql): Promise<void> {
  await sql`TRUNCATE market_signals, odds_observations, ingestion_payloads, ingestion_runs, events RESTART IDENTITY CASCADE`;
}
