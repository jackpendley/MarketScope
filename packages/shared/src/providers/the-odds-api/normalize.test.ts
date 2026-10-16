import { describe, expect, it } from "vitest";
import { COLLECTED_BOOKMAKER_KEYS } from "../../bookmakers";
import type { NormalizationIssueCode, NormalizedQuote } from "../../domain";
import { SYNTHETIC_NFL_ODDS, SYNTHETIC_OBSERVED_AT } from "../../fixtures";
import { normalizeEventOdds } from "./normalize";
import { parseOddsResponse, type ProviderEventOdds } from "./schema";

const { events } = parseOddsResponse(SYNTHETIC_NFL_ODDS);
const opts = { observedAt: SYNTHETIC_OBSERVED_AT, targetBookmakers: COLLECTED_BOOKMAKER_KEYS };

function fixtureEvent(id: string): ProviderEventOdds {
  const event = events.find((e) => e.id === id);
  if (!event) throw new Error(`fixture event ${id} missing`);
  return event;
}

function find(
  quotes: NormalizedQuote[],
  book: string,
  market: NormalizedQuote["market"],
  selection: NormalizedQuote["selection"],
) {
  return quotes.find(
    (q) => q.bookmakerKey === book && q.market === market && q.selection === selection,
  );
}

function codes(issues: { code: NormalizationIssueCode }[]) {
  return issues.map((i) => i.code);
}

describe("parseOddsResponse", () => {
  it("parses every synthetic event", () => {
    expect(events).toHaveLength(3);
  });

  it("rejects structurally invalid events individually instead of failing the batch", () => {
    const good = fixtureEvent("synthetic-evt-001");
    const result = parseOddsResponse([good, { id: "broken", home_team: "X" }]);
    expect(result.events).toHaveLength(1);
    expect(result.rejected).toEqual([
      expect.objectContaining({ index: 1, providerEventId: "broken" }),
    ]);
  });

  it("throws when the payload is not an array", () => {
    expect(() => parseOddsResponse({ message: "error" })).toThrow();
  });
});

describe("normalizeEventOdds — synthetic-evt-001 (BUF home vs MIA)", () => {
  const { event, quotes, issues } = normalizeEventOdds(fixtureEvent("synthetic-evt-001"), opts);

  it("takes team orientation from the event, not alphabetical order", () => {
    // "Buffalo" < "Miami" alphabetically, but orientation must come from home_team.
    expect(event.homeTeam).toBe("Buffalo Bills");
    expect(event.awayTeam).toBe("Miami Dolphins");
    expect(find(quotes, "draftkings", "h2h", "HOME")?.americanPrice).toBe(-185);
    expect(find(quotes, "draftkings", "h2h", "AWAY")?.americanPrice).toBe(154);
  });

  it("preserves spread signs for both sides", () => {
    expect(find(quotes, "draftkings", "spreads", "HOME")?.point).toBe(-3.5);
    expect(find(quotes, "draftkings", "spreads", "AWAY")?.point).toBe(3.5);
    expect(find(quotes, "fanduel", "spreads", "HOME")?.point).toBe(-3);
  });

  it("maps Over/Under explicitly with their points", () => {
    expect(find(quotes, "draftkings", "totals", "OVER")).toMatchObject({
      point: 47.5,
      americanPrice: -110,
    });
    expect(find(quotes, "hardrockbet_az", "totals", "UNDER")).toMatchObject({ point: 48 });
  });

  it("always sets moneyline points to null", () => {
    const moneylines = quotes.filter((q) => q.market === "h2h");
    expect(moneylines.length).toBeGreaterThan(0);
    for (const q of moneylines) expect(q.point).toBeNull();
  });

  it("uses market-level last_update as the bookmaker timestamp and keeps observedAt separate", () => {
    const q = find(quotes, "fanduel", "spreads", "HOME")!;
    expect(q.bookmakerUpdatedAt).toBe("2026-10-15T17:40:31.000Z");
    expect(q.observedAt).toBe(SYNTHETIC_OBSERVED_AT);
  });

  it("marks a future game as pregame", () => {
    expect(quotes.every((q) => !q.isLive)).toBe(true);
  });

  it("reports the missing book and the missing market instead of inventing them", () => {
    expect(issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: "BOOKMAKER_MISSING", bookmakerKey: "williamhill_us" }),
        expect.objectContaining({
          code: "MARKET_MISSING",
          bookmakerKey: "betmgm",
          market: "totals",
        }),
      ]),
    );
    expect(quotes.some((q) => q.bookmakerKey === "williamhill_us")).toBe(false);
    expect(find(quotes, "betmgm", "totals", "OVER")).toBeUndefined();
  });

  it("produces 5 feeds × their available selections", () => {
    // DK 6 + FD 6 + MGM 4 (no totals) + Hard Rock AZ 6 + Hard Rock IN feed 6
    expect(quotes).toHaveLength(28);
  });
});

describe("normalizeEventOdds — synthetic-evt-002 (data-quality problems)", () => {
  const { quotes, issues } = normalizeEventOdds(fixtureEvent("synthetic-evt-002"), opts);

  it("rejects an invalid American price and flags the now-incomplete market", () => {
    expect(find(quotes, "draftkings", "h2h", "AWAY")).toBeUndefined();
    expect(find(quotes, "draftkings", "h2h", "HOME")?.americanPrice).toBe(-240);
    expect(codes(issues.filter((i) => i.bookmakerKey === "draftkings"))).toEqual(
      expect.arrayContaining(["INVALID_PRICE", "INCOMPLETE_MARKET"]),
    );
  });

  it("drops an outcome whose name doesn't exactly match either team", () => {
    expect(find(quotes, "fanduel", "h2h", "HOME")).toBeUndefined();
    expect(find(quotes, "fanduel", "h2h", "AWAY")?.americanPrice).toBe(195);
    expect(issues).toContainEqual(
      expect.objectContaining({ code: "UNKNOWN_OUTCOME", bookmakerKey: "fanduel" }),
    );
  });

  it("keeps but flags a spread whose two sides aren't opposite", () => {
    expect(find(quotes, "betmgm", "spreads", "AWAY")?.point).toBe(6);
    expect(issues).toContainEqual(
      expect.objectContaining({ code: "INCONSISTENT_SPREAD", bookmakerKey: "betmgm" }),
    );
  });

  it("stores an unparseable last_update as null and reports it", () => {
    expect(find(quotes, "betmgm", "totals", "OVER")?.bookmakerUpdatedAt).toBeNull();
    expect(issues).toContainEqual(
      expect.objectContaining({
        code: "INVALID_TIMESTAMP",
        bookmakerKey: "betmgm",
        market: "totals",
      }),
    );
  });

  it("ignores books that weren't requested, and reports them", () => {
    expect(quotes.some((q) => q.bookmakerKey === "bovada")).toBe(false);
    expect(issues).toContainEqual(
      expect.objectContaining({ code: "UNEXPECTED_BOOKMAKER", bookmakerKey: "bovada" }),
    );
  });

  it("reports both absent target books", () => {
    const missing = issues.filter((i) => i.code === "BOOKMAKER_MISSING").map((i) => i.bookmakerKey);
    expect(missing.sort()).toEqual(["hardrockbet_az", "williamhill_us"]);
  });
});

describe("normalizeEventOdds — synthetic-evt-003 (already started)", () => {
  it("marks every quote as live", () => {
    const { quotes } = normalizeEventOdds(fixtureEvent("synthetic-evt-003"), opts);
    expect(quotes.length).toBeGreaterThan(0);
    expect(quotes.every((q) => q.isLive)).toBe(true);
  });

  it("keeps the underdog home team's positive spread sign", () => {
    const { quotes } = normalizeEventOdds(fixtureEvent("synthetic-evt-003"), opts);
    expect(find(quotes, "draftkings", "spreads", "HOME")?.point).toBe(2.5);
    expect(find(quotes, "draftkings", "spreads", "AWAY")?.point).toBe(-2.5);
  });
});

describe("normalizeEventOdds — targeted edge cases", () => {
  const base = fixtureEvent("synthetic-evt-001");
  const withBook = (
    markets: ProviderEventOdds["bookmakers"][number]["markets"],
  ): ProviderEventOdds => ({
    ...base,
    bookmakers: [{ key: "draftkings", title: "DraftKings", markets }],
  });
  const dkOnly = { ...opts, targetBookmakers: ["draftkings"] };

  it("drops both outcomes when a selection appears twice", () => {
    const { quotes, issues } = normalizeEventOdds(
      withBook([
        {
          key: "spreads",
          outcomes: [
            { name: "Buffalo Bills", price: -110, point: -3.5 },
            { name: "Buffalo Bills", price: -120, point: -4 },
            { name: "Miami Dolphins", price: -110, point: 3.5 },
          ],
        },
      ]),
      { ...dkOnly, markets: ["spreads"] },
    );
    expect(quotes.map((q) => q.selection)).toEqual(["AWAY"]);
    expect(codes(issues)).toContain("DUPLICATE_SELECTION");
  });

  it("rejects spread outcomes with no point", () => {
    const { quotes, issues } = normalizeEventOdds(
      withBook([
        {
          key: "spreads",
          outcomes: [
            { name: "Buffalo Bills", price: -110 },
            { name: "Miami Dolphins", price: -110, point: 3.5 },
          ],
        },
      ]),
      { ...dkOnly, markets: ["spreads"] },
    );
    expect(quotes).toHaveLength(1);
    expect(codes(issues)).toContain("INVALID_POINT");
  });

  it("nulls a stray moneyline point and reports it", () => {
    const { quotes, issues } = normalizeEventOdds(
      withBook([
        {
          key: "h2h",
          outcomes: [
            { name: "Buffalo Bills", price: -185, point: 0 },
            { name: "Miami Dolphins", price: 154 },
          ],
        },
      ]),
      { ...dkOnly, markets: ["h2h"] },
    );
    expect(quotes.every((q) => q.point === null)).toBe(true);
    expect(codes(issues)).toContain("UNEXPECTED_POINT");
  });

  it("reports markets that weren't requested", () => {
    const { quotes, issues } = normalizeEventOdds(
      withBook([{ key: "player_pass_tds", outcomes: [{ name: "Over", price: -110, point: 1.5 }] }]),
      { ...dkOnly, markets: ["h2h"] },
    );
    expect(quotes).toHaveLength(0);
    expect(codes(issues)).toEqual(expect.arrayContaining(["UNEXPECTED_MARKET", "MARKET_MISSING"]));
  });

  it("rejects an invalid observedAt", () => {
    expect(() => normalizeEventOdds(base, { ...opts, observedAt: "yesterday" })).toThrow(
      RangeError,
    );
  });
});
