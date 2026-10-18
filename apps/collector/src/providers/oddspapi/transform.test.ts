import { describe, expect, it } from "vitest";
import {
  deriveObservations,
  snapshotTimes,
  type OddsPapiEntry,
  type OddsPapiHistory,
  type OddsPapiMarketMeta,
} from "./transform";

const KICKOFF = "2026-10-11T17:00:00.000Z";
const e = (createdAt: string, price: number, active = true): OddsPapiEntry => ({
  createdAt,
  price,
  active,
});

const meta = (
  marketId: number,
  marketType: string,
  handicap: number,
  names: [string, string],
  period = "result",
): OddsPapiMarketMeta => ({
  marketId,
  marketType,
  handicap,
  period,
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
    meta(120, "spreads", -7, ["1", "2"]), // alternate line, far from even
    meta(200, "totals", 44.5, ["Over", "Under"]),
    meta(141, "moneyline", 0, ["1", "2"]),
    meta(300, "spreads", -1.5, ["1", "2"], "p1+p2"), // first half: ignored
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
    draftkings: {
      markets: {
        // -3 is the main line until Oct 10 12:00, when -3.5 becomes the balanced one.
        ...market(
          100,
          [e("2026-10-09T10:00:00Z", 1.91), e("2026-10-10T12:00:00Z", 1.67)],
          [e("2026-10-09T10:00:00Z", 1.91), e("2026-10-10T12:00:00Z", 2.25)],
        ),
        ...market(
          110,
          [e("2026-10-09T10:00:00Z", 2.2), e("2026-10-10T12:00:00Z", 1.909)],
          [e("2026-10-09T10:00:00Z", 1.7), e("2026-10-10T12:00:00Z", 1.909)],
        ),
        ...market(120, [e("2026-10-09T10:00:00Z", 3.4)], [e("2026-10-09T10:00:00Z", 1.3)]),
        ...market(200, [e("2026-10-09T10:00:00Z", 1.952)], [e("2026-10-09T10:00:00Z", 1.87)]),
        ...market(
          141,
          [
            e("2026-10-09T10:00:00Z", 1.5),
            e("2026-10-11T16:59:00Z", 1.45),
            e("2026-10-11T17:30:00Z", 1.1),
          ],
          [
            e("2026-10-09T10:00:00Z", 2.75),
            e("2026-10-11T16:59:00Z", 2.9),
            e("2026-10-11T17:30:00Z", 7.0),
          ],
        ),
        ...market(300, [e("2026-10-09T10:00:00Z", 1.91)], [e("2026-10-09T10:00:00Z", 1.91)]),
      },
    },
    betmgm: {
      markets: {
        ...market(100, [e("2026-10-09T10:00:00Z", 1.91)], [e("2026-10-09T10:00:00Z", 1.91)]),
      },
    },
    fanduel: {
      // Spread suspended (inactive) from Oct 10 18:00.
      markets: {
        ...market(
          100,
          [e("2026-10-09T10:00:00Z", 1.91), e("2026-10-10T18:00:00Z", 1.91, false)],
          [e("2026-10-09T10:00:00Z", 1.91), e("2026-10-10T18:00:00Z", 1.91, false)],
        ),
      },
    },
  },
};

const derive = () =>
  deriveObservations(history, MARKETS, {
    kickoff: KICKOFF,
    bookMap: { draftkings: "draftkings", fanduel: "fanduel" }, // betmgm deliberately unmapped
  });
const find = (
  rows: ReturnType<typeof derive>,
  book: string,
  market: string,
  selection: string,
  at: string,
) =>
  rows.find(
    (r) =>
      r.bookmakerKey === book &&
      r.market === market &&
      r.selection === selection &&
      r.observedAt === at,
  );

describe("snapshotTimes", () => {
  it("uses 6-hour UTC slots after the first entry plus a near-close snapshot", () => {
    expect(snapshotTimes("2026-10-10T07:00:00Z", KICKOFF)).toEqual([
      "2026-10-10T12:00:00.000Z",
      "2026-10-10T18:00:00.000Z",
      "2026-10-11T00:00:00.000Z",
      "2026-10-11T06:00:00.000Z",
      "2026-10-11T12:00:00.000Z",
      "2026-10-11T16:55:00.000Z",
    ]);
  });

  it("caps history at the window before kickoff", () => {
    const times = snapshotTimes("2026-07-28T00:00:00Z", KICKOFF, { windowDays: 2 });
    expect(times[0]).toBe("2026-10-09T18:00:00.000Z");
  });
});

describe("deriveObservations", () => {
  const rows = derive();

  it("picks the line priced closest to even as the main line, point-in-time", () => {
    expect(find(rows, "draftkings", "spreads", "HOME", "2026-10-10T06:00:00.000Z")).toMatchObject({
      point: -3,
      americanPrice: -110,
    });
    expect(find(rows, "draftkings", "spreads", "HOME", "2026-10-10T18:00:00.000Z")).toMatchObject({
      point: -3.5,
      americanPrice: -110,
    });
  });

  it("stores the away side as the negated home line, with the price change time", () => {
    expect(find(rows, "draftkings", "spreads", "AWAY", "2026-10-10T18:00:00.000Z")).toMatchObject({
      point: 3.5,
      americanPrice: -110,
      bookmakerUpdatedAt: "2026-10-10T12:00:00.000Z",
    });
  });

  it("converts decimal prices to American for totals and moneylines", () => {
    expect(find(rows, "draftkings", "totals", "OVER", "2026-10-10T06:00:00.000Z")).toMatchObject({
      point: 44.5,
      americanPrice: -105,
    });
    expect(find(rows, "draftkings", "totals", "UNDER", "2026-10-10T06:00:00.000Z")).toMatchObject({
      americanPrice: -115,
    });
    expect(find(rows, "draftkings", "h2h", "HOME", "2026-10-10T06:00:00.000Z")).toMatchObject({
      point: null,
      americanPrice: -200,
    });
    expect(find(rows, "draftkings", "h2h", "AWAY", "2026-10-10T06:00:00.000Z")).toMatchObject({
      americanPrice: 175,
    });
  });

  it("captures the near-close price and ignores anything after kickoff", () => {
    expect(find(rows, "draftkings", "h2h", "HOME", "2026-10-11T16:55:00.000Z")).toMatchObject({
      americanPrice: -200,
    });
    expect(rows.every((r) => Date.parse(r.observedAt) < Date.parse(KICKOFF))).toBe(true);
    expect(rows.some((r) => r.americanPrice === -1000)).toBe(false); // the in-play 1.1 price
  });

  it("drops a book's market once it is deactivated (never carries a suspended line)", () => {
    expect(find(rows, "fanduel", "spreads", "HOME", "2026-10-10T12:00:00.000Z")).toBeDefined();
    expect(find(rows, "fanduel", "spreads", "HOME", "2026-10-10T18:00:00.000Z")).toBeUndefined();
  });

  it("ignores unmapped books (BetMGM is excluded) and non-full-game markets", () => {
    expect(rows.some((r) => r.bookmakerKey === "betmgm")).toBe(false);
    expect(rows.some((r) => r.point === -1.5)).toBe(false);
  });

  it("never produces two rows for one book/market/selection/snapshot", () => {
    const keys = rows.map((r) => `${r.bookmakerKey}|${r.market}|${r.selection}|${r.observedAt}`);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
