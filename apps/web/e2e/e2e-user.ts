import { randomUUID } from "node:crypto";

// The synthetic e2e account, created fresh in the e2e database on every run. Its password is
// generated per run in the Playwright main process (which loads this file first) and inherited by
// the worker processes through the environment, so no credential is committed.
process.env.E2E_USER_PASSWORD ??= `E2e!-${randomUUID()}`; // capital + special: meets the rule

export const E2E_USER = {
  username: "e2e_tester",
  email: "e2e@example.com",
  password: process.env.E2E_USER_PASSWORD,
};
export const STORAGE_STATE = "e2e/.auth/user.json";
