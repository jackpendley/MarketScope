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
    onnotice: () => {},
  });
  // Drizzle's postgres-js driver returns timestamp columns as strings (mode: "string"),
  // so no implicit local-time Date conversion happens on the way out.
  const db = drizzle({ client: sql, schema, casing: "snake_case" });
  return { db, sql, close: () => sql.end({ timeout: 5 }) };
}
