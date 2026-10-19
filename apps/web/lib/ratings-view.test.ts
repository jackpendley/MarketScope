import { describe, expect, it } from "vitest";
import type { RatingRow } from "@marketscope/db";
import {
  isSyntheticVersion,
  playcallerTag,
  parseRatingsQuery,
  rankBy,
  rankTone,
  rankText,
  record,
  resolveWeek,
  signed,
  sortRatings,
  weekLabel,
} from "./ratings-view";

const row = (team: string, adjEmRank: number, extra: Partial<RatingRow> = {}) =>
  ({
    team,
    fullName: team,
    adjEmRank,
    adjDRank: 33 - adjEmRank,
    luckRank: adjEmRank,
    sosRank: null,
    ...extra,
  }) as RatingRow;

describe("parseRatingsQuery", () => {
  it("accepts known values and falls back on anything else", () => {
    expect(parseRatingsQuery({ season: "2025", week: "7", sort: "adjD", conf: "AFC" })).toEqual({
      season: 2025,
      week: 7,
      sort: "adjD",
      conference: "AFC",
    });
    expect(
      parseRatingsQuery({ season: "x", week: ["3", "4"], sort: "drop table", conf: "XFL" }),
    ).toEqual({
      season: null,
      week: 3,
      sort: "adjEm",
      conference: null,
    });
  });
});

describe("resolveWeek", () => {
  const weeks = [
    { season: 2025, week: 0 },
    { season: 2025, week: 22 },
    { season: 2026, week: 0 },
    { season: 2026, week: 5 },
  ];
  it("uses the exact snapshot, else the season's latest, else the latest overall", () => {
    expect(resolveWeek(weeks, { season: 2025, week: 0 })).toEqual({ season: 2025, week: 0 });
    expect(resolveWeek(weeks, { season: 2025, week: 9 })).toEqual({ season: 2025, week: 22 });
    expect(resolveWeek(weeks, { season: null, week: null })).toEqual({ season: 2026, week: 5 });
    expect(resolveWeek([], { season: null, week: null })).toBeNull();
  });
});

describe("sortRatings", () => {
  it("sorts by the column's rank, nulls last, ties broken by AdjEM rank", () => {
    const rows = [row("A", 2), row("B", 1), row("C", 3)];
    expect(sortRatings(rows, "adjEm").map((r) => r.team)).toEqual(["B", "A", "C"]);
    expect(sortRatings(rows, "adjD").map((r) => r.team)).toEqual(["C", "A", "B"]);
    expect(sortRatings(rows, "sos").map((r) => r.team)).toEqual(["B", "A", "C"]);
    expect(sortRatings(rows, "team").map((r) => r.team)).toEqual(["A", "B", "C"]);
  });
});

describe("formatting", () => {
  it("names weeks, including playoff rounds by era", () => {
    expect(weekLabel(2026, 0)).toBe("Preseason");
    expect(weekLabel(2026, 18)).toBe("Week 18");
    expect(weekLabel(2026, 19)).toBe("Wild Card");
    expect(weekLabel(2019, 18)).toBe("Wild Card");
    expect(weekLabel(2019, 21)).toBe("Super Bowl");
  });
  it("signs numbers with a real minus and shows missing as a dash", () => {
    expect(signed(3.04)).toBe("+3.0");
    expect(signed(-0.25, 2)).toBe("−0.25");
    expect(signed(null)).toBe("–");
    expect(record({ wins: 5, losses: 2, ties: 1 })).toBe("5-2-1");
  });
  it("shades the top and bottom eighths on a diverging scale", () => {
    expect(rankTone(1, 32)).toBe("bg-accent/30");
    expect(rankTone(16, 32)).toBe("");
    expect(rankTone(32, 32)).toBe("bg-danger/30");
    expect(rankTone(null, 32)).toBe("");
    expect(rankText(1, 32)).toBe("text-fg/85");
    expect(rankText(16, 32)).toBe("text-muted");
  });
  it("ranks values with ties sharing a rank", () => {
    const rows = [{ v: 3 }, { v: 1 }, { v: 3 }, { v: null }];
    const r = rankBy(rows, (x) => x.v, true);
    expect(rows.map((x) => r.get(x))).toEqual([1, 3, 1, null]);
  });
  it("detects synthetic model versions", () => {
    expect(isSyntheticVersion("synthetic-demo")).toBe(true);
    expect(isSyntheticVersion("ratings-v1")).toBe(false);
  });
});

describe("playcallerTag", () => {
  it("labels sourced, assumed and shared play-callers", () => {
    expect(playcallerTag("list", "offense")).toEqual({ label: "calls offense", note: null });
    expect(playcallerTag("rule", "defense").label).toBe("calls defense (assumed)");
    expect(playcallerTag("shared", "defense").label).toBe("calls defense (shared)");
    // A coach calling both sides: offense basis first, defense basis last.
    expect(playcallerTag("direct | rule", "offense").label).toBe("calls offense");
    expect(playcallerTag("direct | rule", "defense").label).toBe("calls defense (assumed)");
    expect(playcallerTag(null, "offense").label).toBe("calls offense");
  });
});
