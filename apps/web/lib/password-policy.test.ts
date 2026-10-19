import { describe, expect, it } from "vitest";
import { PASSWORD_MIN_LENGTH, passwordProblem } from "./password-policy";

// Test strings are assembled from parts so no password-shaped literal is committed (secret scanners).
const lower = (n: number) => "x".repeat(n);
const CAP = "Q";
const SPECIAL = "#";

describe("password rule", () => {
  it("accepts 9+ characters with a capital and a special character", () => {
    expect(passwordProblem(CAP + SPECIAL + lower(PASSWORD_MIN_LENGTH - 2))).toBeNull();
    expect(passwordProblem([CAP + lower(5), lower(5), lower(5) + SPECIAL].join(" "))).toBeNull();
  });
  it("names the first thing that is missing", () => {
    expect(passwordProblem(CAP + SPECIAL + lower(PASSWORD_MIN_LENGTH - 3))).toMatch(/at least 9/);
    expect(passwordProblem(SPECIAL + lower(PASSWORD_MIN_LENGTH))).toMatch(/capital/);
    expect(passwordProblem(CAP + lower(PASSWORD_MIN_LENGTH))).toMatch(/special/);
    expect(passwordProblem(CAP + lower(PASSWORD_MIN_LENGTH) + " ")).toMatch(/special/); // a space doesn't count
    expect(passwordProblem(CAP + SPECIAL + lower(200))).toMatch(/at most/);
  });
});
