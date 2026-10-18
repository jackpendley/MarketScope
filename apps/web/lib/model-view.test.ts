import { describe, expect, it } from "vitest";
import type { ScoredEstimate } from "@marketscope/db";
import {
  bootstrapMeanCi,
  contributionRows,
  excitement,
  favoriteText,
  gameQuality,
  MIN_CI_GAMES,
  noVigHomeProb,
  parseWeekQuery,
  resolveMatchupWeek,
  scorecard,
  spreadText,
  testRecordRows,
} from "./model-view";

const scored = (
  week: number,
  expectedMargin: number,
  homeFinal: number,
  awayFinal: number,
  extra: Partial<ScoredEstimate> = {},
): ScoredEstimate => ({
  gameId: `g${week}-${expectedMargin}-${homeFinal}`,
  season: 2026,
  week,
  kickoffUtc: "2026-09-13T17:00:00.000Z",
  homeTeam: "KC",
  awayTeam: "LV",
  homeFinal,
  awayFinal,
  predictedAt: "2026-09-12T13:00:00.000Z",
  expectedMargin,
  expectedTotal: 44,
  pHome: 0.5 + expectedMargin / 30,
  closeHomeSpread: -expectedMargin - 1,
  closeTotal: 45,
  closeHomeMoneyline: -150,
  closeAwayMoneyline: 130,
  ...extra,
});

describe("week selection", () => {
  const weeks = [
    { season: 2026, week: 5 },
    { season: 2026, week: 6 },
    { season: 2026, week: 7 },
  ];
  it("uses the requested week, else the current week, else the latest", () => {
    expect(parseWeekQuery({ season: "2026", week: ["5", "6"] })).toEqual({ season: 2026, week: 5 });
    expect(parseWeekQuery({ season: "x" })).toEqual({ season: null, week: null });
    const cur = { season: 2026, week: 6 };
    expect(resolveMatchupWeek(weeks, { season: 2026, week: 5 }, cur)).toEqual(weeks[0]);
    expect(resolveMatchupWeek(weeks, { season: 2026, week: 1 }, cur)).toEqual(cur);
    expect(resolveMatchupWeek(weeks, { season: null, week: null }, null)).toEqual(weeks[2]);
    expect(resolveMatchupWeek([], { season: null, week: null }, cur)).toBeNull();
  });
});

describe("formatting", () => {
  it("names the favorite from a home margin and keeps posted spread signs", () => {
    expect(favoriteText("KC", "LV", 3.46)).toBe("KC by 3.5");
    expect(favoriteText("KC", "LV", -7)).toBe("LV by 7.0");
    expect(favoriteText("KC", "LV", 0.01)).toBe("Even");
    expect(spreadText("KC", "LV", -3.5)).toBe("KC −3.5");
    expect(spreadText("KC", "LV", 2)).toBe("LV −2");
    expect(spreadText("KC", "LV", 0)).toBe("Pick'em");
  });

  it("orders contributions with known components first", () => {
    expect(contributionRows({ absences: -0.4, zeta: 1, ratings: 3, home: 0.3 })).toEqual([
      { key: "ratings", label: "Team ratings", value: 3 },
      { key: "home", label: "Home field", value: 0.3 },
      { key: "absences", label: "Other absences", value: -0.4 },
      { key: "zeta", label: "zeta", value: 1 },
    ]);
  });
});

describe("game quality and excitement", () => {
  it("scores two top teams highly and a mismatch as unexciting", () => {
    expect(gameQuality(1, 2, 32)).toBe(98);
    expect(gameQuality(32, 31, 32)).toBe(2);
    expect(gameQuality(null, 2, 32)).toBeNull();
    expect(excitement(98, 0.5)).toBe(98);
    expect(excitement(50, 0.9)).toBe(10);
    expect(excitement(null, 0.5)).toBeNull();
  });
});

describe("market probabilities and bootstrap", () => {
  it("removes the vig proportionally", () => {
    expect(noVigHomeProb(-110, -110)).toBeCloseTo(0.5);
    expect(noVigHomeProb(-200, 170)).toBeCloseTo(0.6667 / (0.6667 + 0.3704), 3);
    expect(noVigHomeProb(null, 120)).toBeNull();
  });

  it("is reproducible and brackets the mean", () => {
    const xs = Array.from({ length: 40 }, (_, i) => (i % 7) - 3);
    const [lo, hi] = bootstrapMeanCi(xs);
    expect(bootstrapMeanCi(xs)).toEqual([lo, hi]);
    const m = xs.reduce((s, x) => s + x, 0) / xs.length;
    expect(lo).toBeLessThan(m);
    expect(hi).toBeGreaterThan(m);
  });
});

describe("scorecard", () => {
  it("computes paired metrics against the close, by week and cumulatively", () => {
    const rows = [
      scored(1, 3, 24, 20), // model err 1, close (−4 → 4) err 0
      scored(1, -2, 17, 20), // model err 1, close (1 → −1) err 2
      scored(2, 6, 20, 20, { closeHomeSpread: null }), // a tie; no close
    ];
    const s = scorecard(rows);
    expect(s.games).toBe(3);
    expect(s.modelMarginMae).toBeCloseTo((1 + 1 + 6) / 3);
    expect(s.margin).toMatchObject({ games: 2, model: 1, close: 1, diff: 0, ci: null });
    expect(s.favoriteWon).toEqual({ won: 2, decided: 2 });
    expect(s.weeks).toHaveLength(2);
    expect(s.weeks[0]).toMatchObject({ week: 1, games: 2, modelMae: 1, closeMae: 1 });
    expect(s.weeks[1]).toMatchObject({ week: 2, games: 1, modelMae: 6, closeMae: null });
    expect(s.weeks[1]!.cumulativeModelMae).toBeCloseTo(8 / 3);
    expect(s.weeks[1]!.cumulativeCloseMae).toBe(1);
    expect(s.total).toMatchObject({ games: 3, model: (0 + 7 + 4) / 3, close: (1 + 8 + 5) / 3 });
    expect(s.calibration).toBeNull();
  });

  it("adds CIs and calibration once enough games are final", () => {
    const rows = Array.from({ length: Math.max(MIN_CI_GAMES, 50) }, (_, i) =>
      scored(1 + (i % 5), (i % 9) - 4, 20 + (i % 11), 20),
    );
    const s = scorecard(rows);
    expect(s.margin!.ci).not.toBeNull();
    expect(s.brier!.ci).not.toBeNull();
    expect(s.calibration!.reduce((n, b) => n + b.games, 0)).toBe(rows.length);
  });

  it("handles an empty forward test", () => {
    const s = scorecard([]);
    expect(s).toMatchObject({ games: 0, modelMarginMae: null, margin: null, weeks: [] });
  });
});

describe("testRecordRows", () => {
  it("orders the version first and the close last, with paired differences", () => {
    const rows = testRecordRows(
      {
        "nflverse close": { margin_mae: 9.67, d_margin_mae: 0, brier: 0.21 },
        "Elo (538)": {
          margin_mae: 10.19,
          margin_mae_lo: 9.3,
          margin_mae_hi: 11.1,
          total_mae: null,
        },
        "ratings-v1": {
          margin_mae: 10.06,
          d_margin_mae: 0.39,
          d_margin_mae_lo: 0.07,
          d_margin_mae_hi: 0.7,
        },
        paired_vs_benchmarks: {
          "Elo (538)": { d_margin_mae: -0.13, d_margin_mae_lo: -0.42, d_margin_mae_hi: 0.17 },
        },
        cover_log_loss: 0.71,
      },
      "ratings-v1",
    );
    expect(rows.map((r) => r.model)).toEqual(["ratings-v1", "Elo (538)", "nflverse close"]);
    expect(rows[0]!.vsClose).toEqual({ value: 0.39, lo: 0.07, hi: 0.7 });
    expect(rows[0]!.versionVs).toBeNull();
    expect(rows[1]!.versionVs).toEqual({ value: -0.13, lo: -0.42, hi: 0.17 });
    expect(rows[1]!.totalMae).toBeNull();
    expect(rows[2]!.vsClose).toBeNull();
  });
});
