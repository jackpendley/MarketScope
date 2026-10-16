import {
  MARKETS,
  COLLECTED_BOOKMAKERS,
  COLLECTED_BOOKMAKER_KEYS,
  normalizeEventOdds,
  parseOddsResponse,
} from "@marketscope/shared";
import { SYNTHETIC_NFL_ODDS, SYNTHETIC_OBSERVED_AT } from "@marketscope/shared/fixtures";
import { describe, expect, it } from "vitest";
import { buildCoverageReport, renderCoverageMarkdown } from "./coverage";

const { events, rejected } = parseOddsResponse(SYNTHETIC_NFL_ODDS);
const results = events.map((e) =>
  normalizeEventOdds(e, {
    observedAt: SYNTHETIC_OBSERVED_AT,
    targetBookmakers: COLLECTED_BOOKMAKER_KEYS,
  }),
);
const report = buildCoverageReport({
  results,
  rejectedCount: rejected.length,
  books: COLLECTED_BOOKMAKERS,
  markets: MARKETS,
  usage: { requestsRemaining: 497, requestsUsed: 3, requestsLast: 3 },
  durationMs: 420,
  receivedAt: SYNTHETIC_OBSERVED_AT,
});

describe("buildCoverageReport", () => {
  it("counts events and started games", () => {
    expect(report.eventsReturned).toBe(3);
    expect(report.eventsLive).toBe(1);
  });

  it("counts only complete markets per book", () => {
    const dk = report.books.find((b) => b.key === "draftkings")!;
    // DK's GB/CHI moneyline lost its away side to an invalid price.
    expect(dk.completeMarkets).toEqual({ h2h: 2, spreads: 3, totals: 3 });
    const caesars = report.books.find((b) => b.key === "williamhill_us")!;
    expect(caesars.eventsWithData).toBe(0);
  });

  it("builds a per-game market matrix", () => {
    const bufMia = report.matrix.find((m) => m.matchup === "Miami Dolphins @ Buffalo Bills")!;
    expect(bufMia.cells).toMatchObject({ draftkings: "MST", betmgm: "MS", williamhill_us: "—" });
  });
});

describe("renderCoverageMarkdown", () => {
  const md = renderCoverageMarkdown(report);

  it("includes credits and the book table", () => {
    expect(md).toContain("remaining 497");
    expect(md).toContain("| Caesars (`williamhill_us`) | 0 |");
  });

  it("never includes prices", () => {
    expect(md).not.toMatch(/[+-]1\d\d\b/);
  });
});
