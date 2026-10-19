// Site accounts (MS-038): the few queries the account CLI needs. Sign-in, sessions and password
// changes go through Better Auth, which reads and writes these tables itself.

import { eq, or, sql } from "drizzle-orm";
import type { Database } from "../client";
import { authSessions, authUsers } from "../schema";

export type AccountRow = {
  username: string | null;
  email: string;
  createdAt: Date;
  activeSessions: number;
};

export async function listAccounts(db: Database): Promise<AccountRow[]> {
  return db
    .select({
      username: authUsers.displayUsername,
      email: authUsers.email,
      createdAt: authUsers.createdAt,
      activeSessions: sql<number>`(SELECT count(*)::int FROM auth_sessions s WHERE s.user_id = ${authUsers.id} AND s.expires_at > now())`,
    })
    .from(authUsers)
    .orderBy(authUsers.createdAt);
}

/** The account with this username or email (case-insensitive), or null. */
export async function findAccount(
  db: Database,
  who: string,
): Promise<{ id: string; username: string | null } | null> {
  const key = who.trim().toLowerCase();
  const [u] = await db
    .select({ id: authUsers.id, username: authUsers.username })
    .from(authUsers)
    .where(or(eq(authUsers.username, key), eq(authUsers.email, key)));
  return u ?? null;
}

/** Delete every session of a user; returns how many were removed. */
export async function deleteAccountSessions(db: Database, userId: string): Promise<number> {
  const gone = await db
    .delete(authSessions)
    .where(eq(authSessions.userId, userId))
    .returning({ id: authSessions.id });
  return gone.length;
}
