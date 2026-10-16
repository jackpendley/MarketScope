import "server-only";
import { createDb, type Database } from "@marketscope/db";

// One connection pool per server process. In development, Next re-evaluates modules on
// every edit, so the pool is cached on globalThis to avoid leaking connections.
const globalForDb = globalThis as unknown as { marketscopeDb?: ReturnType<typeof createDb> };

export class DatabaseNotConfiguredError extends Error {
  override name = "DatabaseNotConfiguredError";
}

export function getDb(): Database {
  if (!globalForDb.marketscopeDb) {
    const url = process.env.DATABASE_URL;
    if (!url) {
      throw new DatabaseNotConfiguredError(
        "DATABASE_URL is not set. Copy apps/web/.env.example to apps/web/.env.local.",
      );
    }
    // Serverless (Vercel) runs many short-lived instances: one connection each, and let
    // the pooler fan out. Long-running servers keep a small pool.
    globalForDb.marketscopeDb = createDb(url, { max: process.env.VERCEL ? 1 : 5 });
  }
  return globalForDb.marketscopeDb.db;
}

export function quoteFreshnessMinutes(): number {
  const value = Number(process.env.QUOTE_FRESHNESS_MINUTES ?? 15);
  return Number.isFinite(value) && value > 0 ? value : 15;
}
