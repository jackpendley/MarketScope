import type { LatestQuoteRow } from "@marketscope/db";
import { describe, expect, it } from "vitest";
import { computeCoverage, feedCoverage, toApiQuotes } from "./game-data";

const OLD = "2026-10-16T01:00:00.000Z";
const NEW = "2026-10-16T07:00:00.000Z";
const row = (
  bookmakerKey: string,
  observedAt: string,
  market: LatestQuoteRow["market"] = "spreads",
): LatestQuoteRow => ({
  eventId: "e1",
  bookmakerKey,
  market,
  selection: market === "totals" ? "OVER" : "HOME",
  point: market === "h2h" ? null : -3.5,
  americanPrice: -110,
  bookmakerUpdatedAt: null,
  observedAt,
  isLive: false,
  source: "the-odds-api",
});

const rows = [
  row("draftkings", NEW),
  row("draftkings", NEW, "totals"),
  row("fanduel", OLD),
  row("fanduel", OLD, "h2h"),
];

describe("computeCoverage", () => {
  it("treats feeds missing from the newest snapshot as missing", () => {
    expect(computeCoverage(rows)).toEqual({
      latestObservedAt: NEW,
      feedsInLatestSnapshot: ["draftkings"],
      feedsMissing: ["fanduel", "betmgm", "williamhill_us", "hardrockbet_az", "hardrockbet"],
    });
  });

  it("handles a game with no quotes", () => {
    expect(computeCoverage([])).toMatchObject({
      latestObservedAt: null,
      feedsInLatestSnapshot: [],
    });
  });
});

describe("feedCoverage", () => {
  const coverage = feedCoverage(rows);
  const byKey = (k: string) => coverage.find((c) => c.bookmakerKey === k)!;

  it("classifies current, stale, and never-returned feeds", () => {
    expect(byKey("draftkings")).toMatchObject({
      status: "current",
      markets: ["spreads", "totals"],
      lastObservedAt: NEW,
    });
    expect(byKey("fanduel")).toMatchObject({
      status: "stale",
      markets: ["h2h", "spreads"],
      lastObservedAt: OLD,
    });
    expect(byKey("betmgm")).toMatchObject({ status: "absent", markets: [], lastObservedAt: null });
  });

  it("lists every collected feed", () => {
    expect(coverage).toHaveLength(6);
  });
});

describe("toApiQuotes", () => {
  it("flags stale quotes and labels freshness against now", () => {
    const quotes = toApiQuotes(rows, new Date("2026-10-16T07:10:00.000Z"), 15);
    const dk = quotes.find((q) => q.bookmakerKey === "draftkings")!;
    const fd = quotes.find((q) => q.bookmakerKey === "fanduel")!;
    expect(dk.freshness).toMatchObject({
      collectionAgeMinutes: 10,
      label: "recent",
      stale: false,
      bookUpdateAgeMinutes: null,
    });
    expect(fd.freshness).toMatchObject({
      collectionAgeMinutes: 370,
      label: "snapshot",
      stale: true,
    });
  });
});
