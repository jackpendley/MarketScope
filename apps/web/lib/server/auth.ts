import "server-only";
import { createAuth, type Auth } from "@/lib/auth-config";
import { getDb } from "./db";

const globalForAuth = globalThis as unknown as { marketscopeAuth?: Auth };

/** The site's Better Auth instance (one per server process). */
export function getAuth(): Auth {
  globalForAuth.marketscopeAuth ??= createAuth(getDb());
  return globalForAuth.marketscopeAuth;
}

/** Fail closed: on Vercel, a missing secret must never leave the site open or sessions forgeable. */
export function authConfigured(env: Record<string, string | undefined> = process.env): boolean {
  return !env.VERCEL || Boolean(env.BETTER_AUTH_SECRET && env.BETTER_AUTH_SECRET.length >= 32);
}
