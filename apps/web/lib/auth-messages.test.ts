import { describe, expect, it } from "vitest";
import { newPasswordProblem, signInErrorMessage } from "./auth-messages";

describe("auth messages", () => {
  it("never says which of username or password was wrong", () => {
    expect(signInErrorMessage(401)).toBe(signInErrorMessage(400));
    expect(signInErrorMessage(401)).not.toMatch(/not found|no account|unknown user/i);
    expect(signInErrorMessage(429)).toMatch(/Too many attempts/);
  });
  it("checks a new password before sending it", () => {
    expect(newPasswordProblem("short", "short", "old-password-1", 12)).toMatch(/at least 12/);
    expect(newPasswordProblem("long-enough-pass", "different-pass!", "x", 12)).toMatch(
      /don't match/,
    );
    expect(newPasswordProblem("same-password-1", "same-password-1", "same-password-1", 12)).toMatch(
      /different/,
    );
    expect(newPasswordProblem("a-brand-new-pass", "a-brand-new-pass", "old", 12)).toBeNull();
  });
});
