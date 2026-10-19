import { describe, expect, it } from "vitest";
import { deriveLineMoves, lineAt, type LineMove } from "./line-moves";
import {
  deriveObservations,
  type OddsPapiEntry,
  type OddsPapiHistory,
  type OddsPapiMarketMeta,
} from "./transform";

const KICKOFF = "2026-10-11T17:00:00.000Z";
const e = (createdAt: string, price: number, active = true, limit?: number): OddsPapiEntry => ({
  createdAt,
  price,
  active,
  limit: limit ?? null,
});

const meta = (
  marketId: number,
  marketType: string,
  handicap: number,
  names: [string, string],
): OddsPapiMarketMeta => ({
  marketId,
  marketType,
  handicap,
  period: "result",
  playerProp: false,
  outcomes: [
    { outcomeId: marketId, outcomeName: names[0] },
    { outcomeId: marketId + 1, outcomeName: names[1] },
  ],
});

const MARKETS = new Map<number, OddsPapiMarketMeta>(
  [
    meta(100, "spreads", -3, ["1", "2"]),
    meta(110, "spreads", -3.5, ["1", "2"]),
    meta(200, "totals", 44.5, ["Over", "Under"]),
    meta(141, "moneyline", 0, ["1", "2"]),
  ].map((m) => [m.marketId, m]),
);

function market(id: number, side1: OddsPapiEntry[], side2: OddsPapiEntry[]) {
  return {
    [String(id)]: {
      outcomes: {
        [String(id)]: { players: { "0": side1 } },
        [String(id + 1)]: { players: { "0": side2 } },
      },
    },
  };
}

const history: OddsPapiHistory = {
  bookmakers: {
    pinnacle: {
      markets: {
        // -3 is the main line; at Oct 10 12:00 the book moves to -3.5 (alternate lines are
        // rewritten 200 ms apart, so the move should be ONE row, after the burst settles).
        ...market(
          100,
          [e("2026-10-09T10:00:00Z", 1.91, true, 5000), e("2026-10-10T12:00:00.000Z", 1.67)],
          [e("2026-10-09T10:00:00Z", 1.91, true, 5000), e("2026-10-10T12:00:00.000Z", 2.25)],
        ),
        ...market(
          110,
          [e("2026-10-09T10:00:00Z", 2.2), e("2026-10-10T12:00:00.200Z", 1.909, true, 7500)],
          [e("2026-10-09T10:00:00Z", 1.7), e("2026-10-10T12:00:00.200Z", 1.909, true, 7500)],
        ),
        // Total: a 20 s blip (ignored) and a 10-minute suspension that reopens at the same
        // price (recorded as off, then on again).
        ...market(
          200,
          [
            e("2026-10-09T10:00:00Z", 1.952),
            e("2026-10-10T08:00:00Z", 1.952, false),
            e("2026-10-10T08:00:20Z", 1.952),
            e("2026-10-11T09:00:00Z", 1.952, false),
            e("2026-10-11T09:10:00Z", 1.952),
          ],
          [
            e("2026-10-09T10:00:00Z", 1.87),
            e("2026-10-10T08:00:00Z", 1.87, false),
            e("2026-10-10T08:00:20Z", 1.87),
            e("2026-10-11T09:00:00Z", 1.87, false),
            e("2026-10-11T09:10:00Z", 1.87),
          ],
        ),
        // Moneyline: repeated identical prices, a change, and in-play entries after kickoff.
        ...market(
          141,
          [
            e("2026-10-09T10:00:00Z", 1.5),
            e("2026-10-09T11:00:00Z", 1.5),
            e("2026-10-11T16:59:00Z", 1.45),
            e("2026-10-11T17:30:00Z", 1.1),
          ],
          [
            e("2026-10-09T10:00:00Z", 2.75),
            e("2026-10-09T11:00:00Z", 2.75),
            e("2026-10-11T16:59:00Z", 2.9),
            e("2026-10-11T17:30:00Z", 7.0),
          ],
        ),
      },
    },
    betmgm: {
      markets: {
        ...market(100, [e("2026-10-09T10:00:00Z", 1.91)], [e("2026-10-09T10:00:00Z", 1.91)]),
      },
    },
  },
};

const BOOKS = { pinnacle: "pinnacle" };
const moves = deriveLineMoves(history, MARKETS, { kickoff: KICKOFF, bookMap: BOOKS });
const of = (market: string) => moves.filter((m) => m.market === market);

describe("deriveLineMoves", () => {
  it("records a main-line switch once, after the burst settles, with its limits", () => {
    expect(of("spreads")).toEqual([
      {
        bookmakerKey: "pinnacle",
        market: "spreads",
        changedAt: "2026-10-09T10:00:00.000Z",
        point: -3,
        price1: -110,
        price2: -110,
        limit1: 5000,
        limit2: 5000,
      },
      {
        bookmakerKey: "pinnacle",
        market: "spreads",
        changedAt: "2026-10-10T12:00:00.200Z",
        point: -3.5,
        price1: -110,
        price2: -110,
        limit1: 7500,
        limit2: 7500,
      },
    ]);
  });

  it("records suspensions of a minute or more, and ignores shorter blips", () => {
    expect(of("totals").map((m) => [m.changedAt, m.point, m.price1, m.price2])).toEqual([
      ["2026-10-09T10:00:00.000Z", 44.5, -105, -115],
      ["2026-10-11T09:00:00.000Z", null, null, null],
      ["2026-10-11T09:10:00.000Z", 44.5, -105, -115],
    ]);
  });

  it("emits value changes only, pregame only, with no point for moneylines", () => {
    expect(of("h2h").map((m) => [m.changedAt, m.point, m.price1, m.price2])).toEqual([
      ["2026-10-09T10:00:00.000Z", null, -200, 175],
      ["2026-10-11T16:59:00.000Z", null, -222, 190],
    ]);
  });

  it("ignores unmapped books", () => {
    expect(moves.every((m) => m.bookmakerKey === "pinnacle")).toBe(true);
  });

  it("keeps the line in effect at the window start, then every change after it", () => {
    const windowed = deriveLineMoves(history, MARKETS, {
      kickoff: KICKOFF,
      bookMap: BOOKS,
      windowDays: 1,
    }).filter((m) => m.market === "h2h");
    // Window starts Oct 10 17:00: the Oct 9 price was still in effect, so it stays.
    expect(windowed.map((m) => m.changedAt)).toEqual([
      "2026-10-09T10:00:00.000Z",
      "2026-10-11T16:59:00.000Z",
    ]);
    const spreads = deriveLineMoves(history, MARKETS, {
      kickoff: KICKOFF,
      bookMap: BOOKS,
      windowDays: 1,
    }).filter((m) => m.market === "spreads");
    expect(spreads.map((m) => m.point)).toEqual([-3.5]); // -3 was replaced before the window
  });

  it("records a suspension that lasts until kickoff", () => {
    const pulled: OddsPapiHistory = {
      bookmakers: {
        pinnacle: {
          markets: market(
            141,
            [e("2026-10-11T10:00:00Z", 1.5), e("2026-10-11T16:30:00Z", 1.5, false)],
            [e("2026-10-11T10:00:00Z", 2.75), e("2026-10-11T16:30:00Z", 2.75, false)],
          ),
        },
      },
    };
    const rows = deriveLineMoves(pulled, MARKETS, { kickoff: KICKOFF, bookMap: BOOKS });
    expect(rows.map((m) => [m.changedAt, m.price1])).toEqual([
      ["2026-10-11T10:00:00.000Z", -200],
      ["2026-10-11T16:30:00.000Z", null],
    ]);
  });
});

describe("cross-check with the snapshot transform", () => {
  it("the line in effect at every derived snapshot matches that snapshot", () => {
    // With no settling, no suspension threshold and an unlimited window, the event log must
    // reproduce every snapshot deriveObservations produces from the same history.
    const exact = deriveLineMoves(history, MARKETS, {
      kickoff: KICKOFF,
      bookMap: BOOKS,
      windowDays: 365,
      settleMs: 0,
      minSuspensionMs: 0,
    });
    const snapshots = deriveObservations(history, MARKETS, {
      kickoff: KICKOFF,
      bookMap: BOOKS,
      windowDays: 365,
    });
    expect(snapshots.length).toBeGreaterThan(20);
    for (const s of snapshots) {
      const row = lineAt(exact, s.bookmakerKey, s.market, s.observedAt) as LineMove;
      const away = s.selection === "AWAY" || s.selection === "UNDER";
      expect(away ? row.price2 : row.price1).toBe(s.americanPrice);
      if (s.market === "totals" || s.selection === "HOME") expect(row.point).toBe(s.point);
      if (s.market === "spreads" && s.selection === "AWAY")
        expect(row.point === 0 ? 0 : -row.point!).toBe(s.point);
    }
  });

  it("is suspended exactly when a snapshot has no quote", () => {
    const exact = deriveLineMoves(history, MARKETS, {
      kickoff: KICKOFF,
      bookMap: BOOKS,
      settleMs: 0,
      minSuspensionMs: 0,
    });
    expect(lineAt(exact, "pinnacle", "totals", "2026-10-11T09:05:00Z")?.price1).toBeNull();
    expect(lineAt(exact, "pinnacle", "totals", "2026-10-11T09:15:00Z")?.price1).toBe(-105);
  });
});
