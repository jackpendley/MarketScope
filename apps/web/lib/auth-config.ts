// Site accounts (MS-038, ADR-049): Better Auth with username or email + password, sessions stored
// in our Postgres, invite-only (no sign-up endpoint). This module has no "server-only" import so
// the account CLI (scripts/users.ts) and the e2e setup can build the same configuration; the web
// app goes through lib/server/auth.ts.

import { betterAuth } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { nextCookies } from "better-auth/next-js";
import { username } from "better-auth/plugins";
import {
  authAccounts,
  authRateLimits,
  authSessions,
  authUsers,
  authVerifications,
  type Database,
} from "@marketscope/db";
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordProblem } from "./password-policy";

export const SESSION_DAYS = 30;
/** Failed and successful sign-ins share this budget per IP address. */
export const SIGN_IN_LIMIT = { window: 60, max: 5 };

/** Hosts the site answers on. Requests for any other Host are rejected by Better Auth, and the
 * same-origin check compares each request's Origin with its (allowed) host. */
export const DEFAULT_ALLOWED_HOSTS = [
  "marketscope-delta.vercel.app",
  "marketscope-*-jackpendley9-8442s-projects.vercel.app", // preview deployments
  "localhost:3000", // pnpm dev
  "localhost:3200", // e2e
];

export function allowedHosts(env: Record<string, string | undefined>): string[] {
  const extra = (env.BETTER_AUTH_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);
  return [...DEFAULT_ALLOWED_HOSTS, ...extra];
}

export function createAuth(db: Database, env: Record<string, string | undefined> = process.env) {
  return betterAuth({
    secret: env.BETTER_AUTH_SECRET,
    baseURL: env.BETTER_AUTH_URL ?? { allowedHosts: allowedHosts(env) },
    database: drizzleAdapter(db, {
      provider: "pg",
      schema: {
        user: authUsers,
        session: authSessions,
        account: authAccounts,
        verification: authVerifications,
        rateLimit: authRateLimits,
      },
    }),
    emailAndPassword: {
      enabled: true,
      disableSignUp: true, // invite-only: accounts come from scripts/users.ts
      minPasswordLength: PASSWORD_MIN_LENGTH,
      maxPasswordLength: PASSWORD_MAX_LENGTH,
      revokeSessionsOnPasswordReset: true,
    },
    session: {
      expiresIn: SESSION_DAYS * 24 * 60 * 60,
      updateAge: 24 * 60 * 60, // slide the expiry at most once a day
      // A signed cookie caches the session for 5 minutes, so most requests need no database
      // lookup. Trade-off: a revoked session can keep working for up to 5 minutes.
      cookieCache: { enabled: true, maxAge: 5 * 60 },
    },
    rateLimit: {
      enabled: true,
      storage: "database", // shared by every serverless instance
      customRules: { "/sign-in/email": SIGN_IN_LIMIT, "/sign-in/username": SIGN_IN_LIMIT },
    },
    // Better Auth only checks length; the capital/special-character rule is enforced here for
    // every endpoint that sets a password (the CLI checks it before calling the adapter).
    hooks: {
      before: createAuthMiddleware(async (ctx) => {
        if (ctx.path !== "/change-password" && ctx.path !== "/reset-password") return;
        const problem = passwordProblem(
          String((ctx.body as { newPassword?: unknown })?.newPassword ?? ""),
        );
        if (problem)
          throw new APIError("BAD_REQUEST", { message: problem, code: "PASSWORD_POLICY" });
      }),
    },
    // Better Auth skips its origin (CSRF) check when NODE_ENV is "test"; state it explicitly so
    // the check runs everywhere, including the integration tests that prove it.
    advanced: { disableOriginCheck: false },
    plugins: [username(), nextCookies()],
  });
}

export type Auth = ReturnType<typeof createAuth>;

/**
 * Create an account with a credential password (the only way accounts are made). Returns the
 * user id. Throws if the email or username is taken.
 */
export async function createAccount(
  auth: Auth,
  input: { username: string; email: string; name?: string; password: string },
): Promise<string> {
  const ctx = await auth.$context;
  const problem = passwordProblem(input.password);
  if (problem) throw new Error(problem);
  const email = input.email.trim().toLowerCase();
  if (await ctx.internalAdapter.findUserByEmail(email))
    throw new Error(`${email} already has an account.`);
  const user = await ctx.internalAdapter.createUser(
    {
      email,
      name: input.name ?? input.username,
      username: input.username.trim().toLowerCase(),
      displayUsername: input.username.trim(),
      emailVerified: true, // invited by an admin; there is no email flow yet
    },
    { method: "admin" },
  );
  await ctx.internalAdapter.linkAccount({
    userId: user.id,
    providerId: "credential",
    accountId: user.id,
    password: await ctx.password.hash(input.password),
  });
  return user.id;
}

/** Set a new password and sign the user out everywhere. */
export async function resetPassword(auth: Auth, userId: string, password: string): Promise<void> {
  const ctx = await auth.$context;
  const problem = passwordProblem(password);
  if (problem) throw new Error(problem);
  await ctx.internalAdapter.updatePassword(userId, await ctx.password.hash(password));
  await ctx.internalAdapter.deleteUserSessions(userId);
}
