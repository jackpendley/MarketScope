import { describe, expect, it } from "vitest";
import { describeSignal, type DescribableSignal } from "./signal-format";

const base: DescribableSignal = {
  type: "line_move",
  market: "spreads",
  selection: "HOME",
  bookmakerKey: "draftkings",
  value: -1,
  details: {},
  homeTeam: "Buffalo Bills",
  awayTeam: "Miami Dolphins",
};

describe("describeSignal", () => {
  it("describes each signal type in plain language", () => {
    expect(
      describeSignal({
        ...base,
        details: { fromPoint: -2.5, toPoint: -3.5, direction: "toward-home" },
      }),
    ).toBe("DraftKings: Bills spread -2.5 → -3.5 (-1.0 pts, toward Bills)");
    expect(
      describeSignal({
        ...base,
        type: "price_move",
        value: -10,
        details: { toPoint: -3, fromPrice: -110, toPrice: -120 },
      }),
    ).toBe("DraftKings: Bills -3 price -110 → -120 (-10¢)");
    expect(
      describeSignal({
        ...base,
        type: "key_number",
        value: -3,
        details: { kind: "crossed", fromPoint: -2.5, toPoint: -3.5 },
      }),
    ).toBe("DraftKings: Bills spread crossed -3 (-2.5 → -3.5)");
    expect(
      describeSignal({
        ...base,
        type: "book_divergence",
        value: -1,
        details: { point: -4, consensus: -3 },
      }),
    ).toBe("DraftKings: Bills -4 vs consensus -3 (-1.0 pts)");
    expect(
      describeSignal({
        ...base,
        type: "rapid_consensus_move",
        bookmakerKey: null,
        value: -1,
        details: { fromConsensus: -3, toConsensus: -4, minutes: 360 },
      }),
    ).toBe("Consensus Bills spread -3 → -4 in 6 h (-1.0 pts)");
    expect(
      describeSignal({
        ...base,
        type: "same_line_price_disagreement",
        bookmakerKey: null,
        selection: "AWAY",
        value: 13,
        details: {
          point: 3,
          best: { bookmakerKey: "draftkings", price: -105 },
          worst: { bookmakerKey: "fanduel", price: -118 },
        },
      }),
    ).toBe("Dolphins +3: DraftKings -105 vs FanDuel -118 (13¢ apart)");
  });

  it("describes totals and moneylines", () => {
    expect(
      describeSignal({
        ...base,
        market: "totals",
        selection: "OVER",
        value: 1,
        details: { fromPoint: 44.5, toPoint: 45.5, direction: "total-up" },
      }),
    ).toBe("DraftKings: total 44.5 → 45.5 (+1.0 pts)");
    expect(
      describeSignal({
        ...base,
        type: "price_move",
        market: "h2h",
        value: -20,
        details: { fromPrice: -150, toPrice: -170 },
      }),
    ).toBe("DraftKings: Bills moneyline price -150 → -170 (-20¢)");
  });
});
