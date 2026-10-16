import { describe, expect, it } from "vitest";
import { calculateConsensusSpread } from "./consensus";
import type { NormalizedQuote } from "./domain";

function homeSpread(bookmakerKey: string, point: number): NormalizedQuote {
  return {
    providerEventId: "evt",
    bookmakerKey,
    market: "spreads",
    selection: "HOME",
    point,
    americanPrice: -110,
    bookmakerUpdatedAt: null,
    observedAt: "2026-10-16T01:00:00Z",
    isLive: false,
  };
}

describe("calculateConsensusSpread", () => {
  it("takes the median home spread", () => {
    const result = calculateConsensusSpread([
      homeSpread("draftkings", -3.5),
      homeSpread("fanduel", -3),
      homeSpread("betmgm", -3.5),
    ]);
    expect(result).toEqual({ homePoint: -3.5, bookmakerKeys: ["betmgm", "draftkings", "fanduel"] });
  });

  it("is robust to one outlier book", () => {
    const result = calculateConsensusSpread([
      homeSpread("draftkings", -3),
      homeSpread("fanduel", -3),
      homeSpread("betmgm", -7),
    ]);
    expect(result.homePoint).toBe(-3);
  });

  it("averages the middle two with an even number of books", () => {
    const result = calculateConsensusSpread([
      homeSpread("a", -3.5),
      homeSpread("b", -3),
      homeSpread("c", -3),
      homeSpread("d", -3.5),
    ]);
    expect(result.homePoint).toBe(-3.25);
  });

  it("refuses to claim consensus with too few books", () => {
    const result = calculateConsensusSpread([homeSpread("a", -3.5), homeSpread("b", -3)]);
    expect(result).toMatchObject({ homePoint: null, bookmakerKeys: ["a", "b"] });
    if (result.homePoint === null) expect(result.reason).toContain("2 of the required 3");
  });

  it("ignores away spreads, moneylines, and totals", () => {
    const away: NormalizedQuote = { ...homeSpread("x", 3.5), selection: "AWAY" };
    const total: NormalizedQuote = {
      ...homeSpread("y", 47.5),
      market: "totals",
      selection: "OVER",
    };
    const result = calculateConsensusSpread([away, total, homeSpread("a", -1)], { minBooks: 1 });
    expect(result).toEqual({ homePoint: -1, bookmakerKeys: ["a"] });
  });

  it("keeps the home orientation for home underdogs", () => {
    const result = calculateConsensusSpread([
      homeSpread("a", 2.5),
      homeSpread("b", 3),
      homeSpread("c", 2.5),
    ]);
    expect(result.homePoint).toBe(2.5);
  });

  it("rejects two quotes from the same book", () => {
    expect(() => calculateConsensusSpread([homeSpread("a", -3), homeSpread("a", -3.5)])).toThrow(
      RangeError,
    );
  });
});
