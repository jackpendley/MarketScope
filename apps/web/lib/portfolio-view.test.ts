import type { PaperPositionRow } from "@marketscope/db";
import { describe, expect, it } from "vitest";
import {
  equityByDay,
  pairTeasers,
  straightUnits,
  STRATEGIES,
  strategyInfo,
  summarise,
} from "./portfolio-view";

let id = 0;
const row = (over: Partial<PaperPositionRow>): PaperPositionRow => ({
  id: ++id,
  strategy: "F1",
  mode: "live",
  gameId: `g${id}`,
  season: 2026,
  week: 8,
  kickoffUtc: "2026-10-25T17:00:00.000Z",
  homeTeam: "BUF",
  awayTeam: "KC",
  market: "spread",
  side: "BUF",
  line: 2.5,
  teasedLine: null,
  price: -110,
  bookmakerKey: "williamhill_us",
  quoteObservedAt: "2026-10-25T12:07:00.000Z",
  placedAt: "2026-10-25T12:20:00.000Z",
  result: null,
  closeLine: null,
  closeSource: null,
  clv: null,
  ...over,
});
const leg = (kickoff: string, side: string, result: PaperPositionRow["result"], week = 8) =>
  row({
    strategy: "wong-V0",
    market: "teaser_leg",
    price: null,
    teasedLine: 8.5,
    kickoffUtc: kickoff,
    side,
    result,
    week,
  });

describe("portfolio view", () => {
  it("prices straight positions at their recorded price", () => {
    expect(straightUnits({ result: "win", price: -110 })).toBeCloseTo(100 / 110);
    expect(straightUnits({ result: "push", price: -110 })).toBe(0);
    expect(straightUnits({ result: "loss", price: 120 })).toBe(-1);
    expect(straightUnits({ result: null, price: -110 })).toBeNull();
  });

  it("pairs teaser legs by week and kickoff, like the backtest", () => {
    const t = pairTeasers([
      leg("2026-10-25T20:25:00Z", "SF", "win"),
      leg("2026-10-25T17:00:00Z", "BUF", "win"),
      leg("2026-10-25T17:00:00Z", "ATL", "push"),
      leg("2026-10-25T17:00:00Z", "NYJ", "win", 9), // a different week: no partner
    ]);
    expect(t).toHaveLength(1);
    expect(t[0]!.legs.map((l) => l.side)).toEqual(["ATL", "BUF"]); // same kickoff: by team
    expect(t[0]!.units).toBe(-1); // a push loses the teaser
  });

  it("leaves a teaser open until both legs are graded, and pays -125 on two wins", () => {
    expect(
      pairTeasers([
        leg("2026-10-25T17:00:00Z", "A", "win"),
        leg("2026-10-25T18:00:00Z", "B", null),
      ])[0]!.units,
    ).toBeNull();
    expect(
      pairTeasers([
        leg("2026-10-25T17:00:00Z", "A", "win"),
        leg("2026-10-25T18:00:00Z", "B", "win"),
      ])[0]!.units,
    ).toBe(0.8);
  });

  it("summarises record, units, return and CLV per strategy, in catalogue order", () => {
    const s = summarise([
      row({ strategy: "F2", result: "win", clv: 0.5 }),
      row({ strategy: "F1", result: "loss", clv: -0.5 }),
      row({ strategy: "F1", result: "win", clv: 1.5 }),
      row({ strategy: "F1" }),
    ]);
    expect(s.map((x) => x.info.id)).toEqual(["F1", "F2"]);
    const f1 = s[0]!;
    expect([f1.positions, f1.open, f1.wins, f1.losses, f1.settled]).toEqual([3, 1, 1, 1, 2]);
    expect(f1.units).toBeCloseTo(100 / 110 - 1);
    expect(f1.roi).toBeCloseTo((100 / 110 - 1) / 2);
    expect(f1.meanClv).toBe(0.5);
  });

  it("builds a cumulative curve by day, starting each strategy at its first settlement", () => {
    const { points, strategies } = equityByDay([
      row({ strategy: "F1", result: "win", kickoffUtc: "2026-10-18T17:00:00Z" }),
      row({ strategy: "F2", result: "loss", kickoffUtc: "2026-10-25T17:00:00Z" }),
      row({ strategy: "F1", result: "loss", kickoffUtc: "2026-10-25T20:00:00Z" }),
    ]);
    expect(strategies).toEqual(["F1", "F2"]);
    expect(points).toEqual([
      { day: "2026-10-18", F1: 0.91, F2: null },
      { day: "2026-10-25", F1: -0.09, F2: -1 },
    ]);
  });

  it("knows every pre-registered strategy", () => {
    expect(STRATEGIES.map((s) => s.id)).toEqual([
      "wong-V0",
      "wong-V1",
      "wong-V2",
      "wong-model",
      "F1",
      "F2",
      "F3",
      "F4",
      "F5",
      "F6",
      "F7",
      "F8",
      "F9",
      "F10",
    ]);
    expect(strategyInfo("unknown").label).toBe("unknown");
  });
});
