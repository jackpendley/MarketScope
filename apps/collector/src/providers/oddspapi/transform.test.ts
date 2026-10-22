import { describe, expect, it } from "vitest";
import {
  bookCandidates,
  deriveObservations,
  instantMs,
  snapshotTimes,
  withoutGhosts,
  type Candidate,
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

describe("withoutGhosts", () => {
  const T = Date.parse("2026-10-18T16:00:00Z");
  const line = (handicap: number, price1: number, price2: number, at: string, active = true) => {
    const series = (price: number) => ({
      times: [Date.parse(at)],
      entries: [e(at, price, active)],
    });
    return { handicap, side1: series(price1), side2: series(price2) } satisfies Candidate;
  };
  const handicaps = (cs: Candidate[]) => cs.map((c) => c.handicap);

  it("drops the staler of two near-even lines whose prices barely differ (Caesars' -10 ghost)", () => {
    const ghost = line(-10, 1.87, 1.87, "2026-09-01T02:24:00Z");
    const real = line(-7, 1.909, 1.926, "2026-10-18T13:30:00Z");
    expect(handicaps(withoutGhosts([ghost, real], T))).toEqual([-7]);
  });

  it("keeps a real main line that has sat unchanged for days beside repriced alternates", () => {
    // FanDuel: +1.5 untouched since Oct 13 is still the main line; -1.5 is 5.7 points away.
    const main = line(1.5, 1.82, 2.0, "2026-10-13T10:59:00Z");
    const alt = line(-1.5, 2.02, 1.77, "2026-10-17T22:17:00Z");
    const far = line(-6.5, 3.4, 1.3, "2026-10-17T14:45:00Z");
    expect(handicaps(withoutGhosts([main, alt, far], T))).toEqual([1.5, -1.5]);
  });

  it("drops far-tail and junk markets, so a suspended board has no main line", () => {
    const tail = line(64.5, 13.4, 1.01, "2026-10-15T17:07:00Z");
    const junk = line(25, 1.077, 1.286, "2026-10-18T15:00:00Z"); // a 70% margin
    const suspended = line(39.5, 1.893, 1.926, "2026-10-18T04:14:00Z", false);
    expect(withoutGhosts([tail, junk, suspended], T)).toEqual([]);
  });

  it("ignores direction: a ladder labelled the other way round is not a ghost", () => {
    const a = line(-3.5, 1.95, 1.87, "2026-09-02T09:02:00Z");
    const b = line(-5.5, 1.74, 2.06, "2026-09-02T10:10:00Z");
    expect(handicaps(withoutGhosts([a, b], T))).toEqual([-3.5, -5.5]);
  });

  it("keeps equal prices on adjacent half points (less than 2 points apart)", () => {
    const a = line(-6.5, 1.909, 1.909, "2026-10-17T10:00:00Z");
    const b = line(-7, 1.909, 1.909, "2026-10-18T10:00:00Z");
    expect(handicaps(withoutGhosts([a, b], T))).toEqual([-6.5, -7]);
  });
});

describe("instantMs", () => {
  it("compares offsets as instants and rejects timestamps without a zone", () => {
    const kick = instantMs(KICKOFF);
    expect(instantMs("2026-10-11T16:30:00-01:00")).toBeGreaterThan(kick); // 17:30Z
    expect(instantMs("2026-10-11T17:30:00+01:00")).toBeLessThan(kick); // 16:30Z
    expect(instantMs("2026-10-11T17:00:00+00:00")).toBe(kick);
    expect(() => instantMs("2026-10-11T16:30:00")).toThrow(/without a time zone/);
    expect(() => instantMs("not a timeZ")).toThrow(/unparseable/);
  });
});

describe("bookCandidates timestamps", () => {
  const markets = new Map([[100, meta(100, "spreads", -3, ["1", "2"])]]);
  const book = (entries1: OddsPapiEntry[]) => ({
    markets: {
      "100": {
        outcomes: {
          "100": { players: { "0": entries1 } },
          "101": { players: { "0": [e("2026-10-10T08:00:00.000Z", 1.91)] } },
        },
      },
    },
  });

  it("filters at kickoff by instant and sorts by instant, not text", () => {
    const { spreads } = bookCandidates(
      book([
        e("2026-10-11T17:30:00+01:00", 1.8), // 16:30Z: pregame
        e("2026-10-10T09:00:00.000Z", 1.95),
        e("2026-10-11T16:30:00-01:00", 1.7), // 17:30Z: in-play
        e("2026-10-11T17:00:00+00:00", 1.6), // kickoff itself: in-play
      ]),
      markets,
      instantMs(KICKOFF),
    );
    expect(spreads[0]!.side1.entries.map((x) => x.price)).toEqual([1.95, 1.8]);
  });

  it("keeps the provider's order for equal times and refuses zone-less input", () => {
    const tied = bookCandidates(
      book([e("2026-10-10T09:00:00.000Z", 1.9), e("2026-10-10T09:00:00.000Z", 2.0)]),
      markets,
      instantMs(KICKOFF),
    );
    expect(tied.spreads[0]!.side1.entries.map((x) => x.price)).toEqual([1.9, 2.0]);
    expect(() =>
      bookCandidates(book([e("2026-10-10T09:00:00", 1.9)]), markets, instantMs(KICKOFF)),
    ).toThrow(/without a time zone/);
  });
});
