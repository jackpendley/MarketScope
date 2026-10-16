import { describe, expect, it } from "vitest";
import { compareIdenticalMarketPrices } from "./compare";
import type { NormalizedQuote } from "./domain";

function quote(overrides: Partial<NormalizedQuote>): NormalizedQuote {
  return {
    providerEventId: "evt",
    bookmakerKey: "draftkings",
    market: "spreads",
    selection: "HOME",
    point: -3.5,
    americanPrice: -110,
    bookmakerUpdatedAt: null,
    observedAt: "2026-10-15T18:00:00Z",
    isLive: false,
    ...overrides,
  };
}

describe("compareIdenticalMarketPrices", () => {
  it("never compares different spread points", () => {
    const groups = compareIdenticalMarketPrices([
      quote({ bookmakerKey: "draftkings", point: -3.5, americanPrice: -110 }),
      quote({ bookmakerKey: "fanduel", point: -3, americanPrice: -118 }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups.every((g) => !g.comparable)).toBe(true);
  });

  it("picks the best price among books at the identical line", () => {
    const [group] = compareIdenticalMarketPrices([
      quote({ bookmakerKey: "draftkings", americanPrice: -110 }),
      quote({ bookmakerKey: "betmgm", americanPrice: -105 }),
      quote({ bookmakerKey: "hardrockbet_az", americanPrice: -108 }),
    ]);
    expect(group).toMatchObject({
      comparable: true,
      bestPrice: -105,
      bestBookmakerKeys: ["betmgm"],
    });
  });

  it("treats +100 as better than −105", () => {
    const [group] = compareIdenticalMarketPrices([
      quote({ bookmakerKey: "draftkings", americanPrice: -105 }),
      quote({ bookmakerKey: "fanduel", americanPrice: 100 }),
    ]);
    expect(group?.bestBookmakerKeys).toEqual(["fanduel"]);
  });

  it("reports every book tied for best", () => {
    const [group] = compareIdenticalMarketPrices([
      quote({ bookmakerKey: "draftkings", market: "h2h", point: null, americanPrice: 150 }),
      quote({ bookmakerKey: "fanduel", market: "h2h", point: null, americanPrice: 150 }),
      quote({ bookmakerKey: "betmgm", market: "h2h", point: null, americanPrice: 140 }),
    ]);
    expect(group?.bestBookmakerKeys).toEqual(["draftkings", "fanduel"]);
  });

  it("separates selections and markets", () => {
    const groups = compareIdenticalMarketPrices([
      quote({ selection: "HOME", point: -3.5 }),
      quote({ selection: "AWAY", point: 3.5 }),
      quote({ market: "totals", selection: "OVER", point: 47.5 }),
      quote({ market: "totals", selection: "UNDER", point: 47.5 }),
    ]);
    expect(groups).toHaveLength(4);
  });

  it("marks a single-book line as not comparable", () => {
    const [group] = compareIdenticalMarketPrices([quote({})]);
    expect(group?.comparable).toBe(false);
  });
});
