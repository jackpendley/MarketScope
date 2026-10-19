// Site accounts against the test database, through Better Auth's real request handler:
// hashing, sign-in by username or email, generic failures, rate limiting, disabled sign-up,
// and password resets that sign the user out everywhere.
import { authAccounts, authSessions, createDb } from "@marketscope/db";
import { resetDatabase, TEST_DATABASE_URL } from "@marketscope/db/testing";
import { randomBytes, randomUUID } from "node:crypto";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createAccount, createAuth, resetPassword, SIGN_IN_LIMIT } from "@/lib/auth-config";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());

const ORIGIN = "http://localhost:3200";
// Credentials are generated per run: nothing credential-shaped is committed (secret scanners).
const secret = () => `pw-${randomUUID()}`;
const auth = createAuth(db, {
  BETTER_AUTH_SECRET: randomBytes(32).toString("hex"),
  BETTER_AUTH_URL: ORIGIN,
});
const WRONG = secret();
const NEW_PASSWORD = secret();
const USER = { username: "Jack_P", email: "Jack@Example.com", password: secret() };

let ip = 0;
function post(path: string, body: unknown, clientIp = `203.0.113.${++ip}`) {
  return auth.handler(
    new Request(`${ORIGIN}/api/auth${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: ORIGIN, "x-forwarded-for": clientIp },
      body: JSON.stringify(body),
    }),
  );
}

describe("site accounts", () => {
  let userId: string;
  beforeEach(async () => {
    await resetDatabase(sql);
    userId = await createAccount(auth, USER);
  });

  it("stores only a salted hash of the password", async () => {
    const [acct] = await db.select().from(authAccounts);
    expect(acct!.providerId).toBe("credential");
    expect(acct!.password).not.toContain(USER.password);
    expect(acct!.password!.length).toBeGreaterThan(60);
  });

  it("signs in by username (any case) or email and sets an httpOnly session cookie", async () => {
    const byName = await post("/sign-in/username", { username: "jack_p", password: USER.password });
    expect(byName.status).toBe(200);
    const cookie = byName.headers.get("set-cookie") ?? "";
    expect(cookie).toMatch(/session_token=/);
    expect(cookie).toMatch(/HttpOnly/i);
    expect(
      (await post("/sign-in/email", { email: "jack@example.com", password: USER.password })).status,
    ).toBe(200);
    expect(await db.$count(authSessions)).toBe(2);
  });

  it("answers a wrong password and an unknown user the same way", async () => {
    const wrong = await post("/sign-in/username", {
      username: "jack_p",
      password: WRONG,
    });
    const unknown = await post("/sign-in/username", {
      username: "nobody",
      password: WRONG,
    });
    expect(wrong.status).toBe(unknown.status);
    expect(wrong.status).toBe(401);
  });

  it(`rate-limits sign-in to ${SIGN_IN_LIMIT.max} attempts a minute per address`, async () => {
    const statuses = [];
    for (let i = 0; i <= SIGN_IN_LIMIT.max; i++)
      statuses.push(
        (
          await post(
            "/sign-in/username",
            { username: "jack_p", password: `${WRONG}-${i}` },
            "198.51.100.9",
          )
        ).status,
      );
    expect(statuses.slice(0, SIGN_IN_LIMIT.max).every((s) => s === 401)).toBe(true);
    expect(statuses.at(-1)).toBe(429);
    // Another address is unaffected.
    expect(
      (await post("/sign-in/username", { username: "jack_p", password: USER.password })).status,
    ).toBe(200);
  });

  it("has no working sign-up endpoint", async () => {
    const res = await post("/sign-up/email", {
      email: "intruder@example.com",
      password: secret(),
      name: "x",
    });
    expect(res.status).toBeGreaterThanOrEqual(400);
    expect(await db.$count(authAccounts)).toBe(1);
  });

  it("Better Auth itself refuses an email sign-in from another origin", async () => {
    // (The username sign-in has no such check inside Better Auth; the proxy's same-origin guard
    // covers every /api/auth/* mutation: lib/same-origin.ts and e2e/auth.spec.ts.)
    const res = await auth.handler(
      new Request(`${ORIGIN}/api/auth/sign-in/email`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          origin: "https://evil.example",
          "x-forwarded-for": "192.0.2.1",
        },
        body: JSON.stringify({ email: "jack@example.com", password: USER.password }),
      }),
    );
    expect(res.status).toBe(403);
  });

  it("a password reset replaces the password and ends every session", async () => {
    await post("/sign-in/username", { username: "jack_p", password: USER.password });
    await resetPassword(auth, userId, NEW_PASSWORD);
    expect(await db.$count(authSessions)).toBe(0);
    expect(
      (await post("/sign-in/username", { username: "jack_p", password: USER.password })).status,
    ).toBe(401);
    expect(
      (await post("/sign-in/username", { username: "jack_p", password: NEW_PASSWORD })).status,
    ).toBe(200);
  });

  it("refuses short passwords and duplicate emails", async () => {
    await expect(
      createAccount(auth, { username: "x_y", email: "x@example.com", password: "x".repeat(5) }),
    ).rejects.toThrow(/at least 12/);
    await expect(createAccount(auth, { ...USER, username: "other" })).rejects.toThrow(
      /already has an account/,
    );
  });
});
