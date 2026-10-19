import { describe, expect, it } from "vitest";
import { newPasswordProblem, signInErrorMessage } from "./auth-messages";

// Built from parts so no password-shaped literal is committed (secret scanners).
const ok = (tag: string) => `Q#${tag}`.padEnd(12, "x");

describe("auth messages", () => {
  it("never says which of username or password was wrong", () => {
    expect(signInErrorMessage(401)).toBe(signInErrorMessage(400));
    expect(signInErrorMessage(401)).not.toMatch(/not found|no account|unknown user/i);
    expect(signInErrorMessage(429)).toMatch(/Too many attempts/);
  });
  it("checks a new password before sending it", () => {
    expect(newPasswordProblem("Q#x", "Q#x", "old")).toMatch(/at least 9/);
    expect(newPasswordProblem("#".padEnd(12, "x"), "#".padEnd(12, "x"), "old")).toMatch(/capital/);
    expect(newPasswordProblem(ok("a"), ok("b"), "x")).toMatch(/don't match/);
    expect(newPasswordProblem(ok("s"), ok("s"), ok("s"))).toMatch(/different/);
    expect(newPasswordProblem(ok("n"), ok("n"), "old")).toBeNull();
  });
});
