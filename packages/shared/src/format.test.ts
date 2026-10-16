import { describe, expect, it } from "vitest";
import { formatAmericanOdds, formatPoint } from "./format";

describe("formatAmericanOdds", () => {
  it("adds a plus sign to positive prices", () => {
    expect(formatAmericanOdds(150)).toBe("+150");
    expect(formatAmericanOdds(100)).toBe("+100");
  });

  it("keeps the minus sign on negative prices", () => {
    expect(formatAmericanOdds(-110)).toBe("-110");
  });
});

describe("formatPoint", () => {
  it("preserves spread signs", () => {
    expect(formatPoint(-3.5, "spreads")).toBe("-3.5");
    expect(formatPoint(3.5, "spreads")).toBe("+3.5");
  });

  it("renders a zero spread as PK", () => {
    expect(formatPoint(0, "spreads")).toBe("PK");
  });

  it("renders totals without a sign", () => {
    expect(formatPoint(47.5, "totals")).toBe("47.5");
  });

  it("renders nothing for moneylines", () => {
    expect(formatPoint(null, "h2h")).toBe("");
  });
});
