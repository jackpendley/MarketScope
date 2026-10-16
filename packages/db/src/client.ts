import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

export type Database = ReturnType<typeof createDb>["db"];

/**
 * Create a Drizzle client over postgres.js. Call `close()` when a script finishes,
 * or the open connection pool keeps the Node process alive.
 */
export function createDb(url: string, options: { max?: number } = {}) {
  const sql = postgres(url, {
    max: options.max ?? 5,
    // Always encrypt connections to remote databases (e.g. Supabase); local Postgres
    // doesn't need it. An explicit ?sslmode=… in the URL takes precedence.
    ssl: requiresTls(url) ? "require" : false,
    onnotice: () => {},
  });
  // Drizzle's postgres-js driver returns timestamp columns as strings (mode: "string"),
  // so no implicit local-time Date conversion happens on the way out.
  const db = drizzle({ client: sql, schema, casing: "snake_case" });
  return { db, sql, close: () => sql.end({ timeout: 5 }) };
}

/** True for any non-local host unless the URL sets its own sslmode. */
export function requiresTls(url: string): boolean {
  const parsed = new URL(url);
  if (parsed.searchParams.has("sslmode")) return false;
  return !["localhost", "127.0.0.1", "::1", "[::1]"].includes(parsed.hostname);
}
