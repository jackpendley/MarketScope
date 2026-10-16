import { describe, expect, it } from "vitest";
import type { HistoryObservation, LineChange } from "./history";
import { calculateBookDispersion, describeMovement, stateAt } from "./replay";

const H = 3_600_000;
const t0 = Date.parse("2026-10-14T00:00:00Z");
const at = (h: number) => new Date(t0 + h * H).toISOString();
const obs = (book: string, h: number, point: number, price = -110): HistoryObservation => ({
  bookmakerKey: book,
  observedAt: at(h),
  point,
  americanPrice: price,
  bookmakerUpdatedAt: null,
  isLive: false,
});

describe("stateAt", () => {
  const observations = [
    obs("dk", 0, -3),
    obs("dk", 6, -3.5),
    obs("dk", 12, -3.5),
    obs("fd", 0, -3),
    obs("mgm", 18, -4),
  ];

  it("returns each book's latest observation at or before T", () => {
    const state = stateAt(observations, at(7), { freshnessMinutes: 12 * 60 });
    expect(state.find((s) => s.bookmakerKey === "dk")).toMatchObject({
      status: "fresh",
      ageMinutes: 60,
    });
    expect(state.find((s) => s.bookmakerKey === "dk")!.observation!.point).toBe(-3.5);
  });

  it("never uses observations from after T", () => {
    const state = stateAt(observations, at(7), { freshnessMinutes: 12 * 60 });
    expect(state.find((s) => s.bookmakerKey === "mgm")).toMatchObject({
      status: "none",
      observation: null,
    });
  });

  it("marks books not observed within the freshness window as stale instead of carrying them forward", () => {
    const state = stateAt(observations, at(14), { freshnessMinutes: 12 * 60 });
    expect(state.find((s) => s.bookmakerKey === "fd")).toMatchObject({
      status: "stale",
      ageMinutes: 14 * 60,
    });
    expect(state.find((s) => s.bookmakerKey === "dk")!.status).toBe("fresh");
  });

  it("includes requested books with no data at all", () => {
    const state = stateAt(observations, at(7), {
      freshnessMinutes: 60,
      bookmakerKeys: ["dk", "williamhill_us"],
    });
    expect(state.map((s) => [s.bookmakerKey, s.status])).toEqual([
      ["dk", "fresh"],
      ["williamhill_us", "none"],
    ]);
  });

  it("rejects an invalid time", () => {
    expect(() => stateAt(observations, "later", { freshnessMinutes: 60 })).toThrow(RangeError);
  });
});

describe("calculateBookDispersion", () => {
  it("summarizes disagreement around the consensus", () => {
    expect(calculateBookDispersion([-3, -3, -3.5, -4], -3.25)).toEqual({
      books: 4,
      range: 1,
      stdDev: 0.41,
      meanAbsDeviation: 0.38,
      booksOffCenter: 1,
    });
  });

  it("counts books exactly at the threshold as off-center", () => {
    expect(calculateBookDispersion([-3, -3.5], -3)!.booksOffCenter).toBe(1);
  });

  it("needs at least two books", () => {
    expect(calculateBookDispersion([-3], -3)).toBeNull();
  });
});

describe("describeMovement", () => {
  const change = (
    fromPoint: number | null,
    toPoint: number | null,
    type: LineChange["type"] = "point",
  ): LineChange => ({
    bookmakerKey: "dk",
    type,
    intervalStart: at(0),
    intervalEnd: at(6),
    fromPoint,
    toPoint,
    fromPrice: -110,
    toPrice: -110,
    pointDelta: fromPoint !== null && toPoint !== null ? toPoint - fromPoint : null,
    acrossGap: false,
  });

  it("home spread -3.5 → -2.5 moves toward the away team", () => {
    expect(describeMovement(change(-3.5, -2.5), "spreads", "HOME")).toMatchObject({
      direction: "toward-away",
      keyNumbers: [{ signedKey: -3, kind: "crossed" }],
    });
  });

  it("home spread -2.5 → -3 moves toward the home team and lands on 3", () => {
    expect(describeMovement(change(-2.5, -3), "spreads", "HOME")).toMatchObject({
      direction: "toward-home",
      keyNumbers: [{ signedKey: -3, kind: "landed-on" }],
    });
  });

  it("flips orientation for away-side series so labels mean the same thing", () => {
    // Away +3.5 → +2.5 (away gets fewer points) is the same move as home -3.5 → -2.5:
    // the market moved toward the away team.
    expect(describeMovement(change(3.5, 2.5), "spreads", "AWAY").direction).toBe("toward-away");
    expect(describeMovement(change(-3.5, -2.5), "spreads", "HOME").direction).toBe("toward-away");
  });

  it("labels totals up/down and price-only changes", () => {
    expect(describeMovement(change(44.5, 45.5), "totals", "OVER").direction).toBe("total-up");
    expect(describeMovement(change(-3, -3, "price"), "spreads", "HOME")).toMatchObject({
      direction: "price-only",
      keyNumbers: [],
    });
    expect(describeMovement(change(null, null, "price"), "h2h", "HOME").direction).toBe(
      "price-only",
    );
  });
});
