import { describe, expect, it } from "vitest";
import type { ProjectionRow } from "@marketscope/db";
import { groupByDivision, oddsText, oddsTone, winRange } from "./projections-view";

const row = (team: string, division: string, playoffP: number) =>
  ({ team, division, playoffP, meanWins: 8 }) as ProjectionRow;

describe("oddsText", () => {
  it("keeps precision at the extremes and never implies a clinch", () => {
    expect(oddsText(0)).toBe("0%");
    expect(oddsText(0.0004)).toBe("<0.1%");
    expect(oddsText(0.004)).toBe("0.4%");
    expect(oddsText(0.456)).toBe("46%");
    expect(oddsText(0.996)).toBe("99.6%");
    expect(oddsText(0.9996)).toBe(">99.9%");
    expect(oddsText(1)).toBe("100%");
    expect(oddsTone(0.95)).toBe("bg-accent/30");
    expect(oddsTone(0.3)).toBe("");
  });
});

describe("groupByDivision", () => {
  it("orders divisions conventionally and teams by playoff odds, with a conference filter", () => {
    const rows = [
      row("DAL", "NFC East", 0.4),
      row("KC", "AFC West", 0.9),
      row("BUF", "AFC East", 0.7),
      row("MIA", "AFC East", 0.8),
      row("BAL", "AFC North", 0.2),
    ];
    const g = groupByDivision(rows, null);
    expect(g.map((d) => d.division)).toEqual(["AFC East", "AFC North", "AFC West", "NFC East"]);
    expect(g[0]!.rows.map((r) => r.team)).toEqual(["MIA", "BUF"]);
    expect(groupByDivision(rows, "NFC").map((d) => d.division)).toEqual(["NFC East"]);
  });
});

describe("winRange", () => {
  it("finds the mode and the middle 80% of the distribution", () => {
    const dist = Array.from({ length: 18 }, () => 0);
    dist[8] = 0.2;
    dist[9] = 0.4;
    dist[10] = 0.3;
    dist[11] = 0.1;
    expect(winRange(dist)).toEqual({ mode: 9, low: 8, high: 10 });
  });
});
