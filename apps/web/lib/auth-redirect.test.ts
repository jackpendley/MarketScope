import { describe, expect, it } from "vitest";
import { safeNext } from "./auth-redirect";

describe("safeNext", () => {
  it("keeps same-site paths with their query", () => {
    expect(safeNext("/teams/KC?season=2025")).toBe("/teams/KC?season=2025");
  });
  it("rejects off-site and odd targets", () => {
    for (const bad of [
      "https://evil.example",
      "//evil.example",
      "/\\evil.example",
      "javascript:alert(1)",
      "",
      undefined,
      null,
    ])
      expect(safeNext(bad)).toBe("/nfl");
  });
  it("never bounces back to the login page or an API route", () => {
    expect(safeNext("/login?next=/nfl")).toBe("/nfl");
    expect(safeNext("/api/games")).toBe("/nfl");
  });
  it("takes the first value of a repeated parameter", () => {
    expect(safeNext(["/ratings", "https://evil.example"])).toBe("/ratings");
  });
});
