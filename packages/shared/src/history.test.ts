import { describe, expect, it } from "vitest";
import { buildBookSeries, buildSeriesByBook, type HistoryObservation } from "./history";

const H = 3_600_000;
const t0 = Date.parse("2026-10-14T00:00:00Z");
const at = (hours: number) => new Date(t0 + hours * H).toISOString();

function obs(
  hours: number,
  point: number | null,
  americanPrice: number,
  bookmakerKey = "draftkings",
): HistoryObservation {
  return {
    bookmakerKey,
    observedAt: at(hours),
    point,
    americanPrice,
    bookmakerUpdatedAt: null,
    isLive: false,
  };
}

describe("buildBookSeries", () => {
  it("does not count unchanged observations as changes", () => {
    const s = buildBookSeries([obs(0, -3, -110), obs(6, -3, -110), obs(12, -3, -110)]);
    expect(s.changes).toEqual([]);
    expect(s.observations).toBe(3);
    // "changes" resolution keeps only first and last.
    expect(s.points.map((p) => p.kinds)).toEqual([["first"], ["last"]]);
  });

  it("classifies price-only, point-only, and combined changes", () => {
    const s = buildBookSeries([
      obs(0, -3, -110),
      obs(6, -3, -125), // price only: -3 (-110) → -3 (-125)
      obs(12, -3.5, -125), // point only
      obs(18, -3, -110), // both
    ]);
    expect(s.changes.map((c) => c.type)).toEqual(["price", "point", "both"]);
  });

  it("reports changes as intervals between observations, with the point delta", () => {
    const s = buildBookSeries([obs(0, -2.5, -110), obs(6, -3.5, -105)]);
    expect(s.changes[0]).toMatchObject({
      intervalStart: at(0),
      intervalEnd: at(6),
      fromPoint: -2.5,
      toPoint: -3.5,
      pointDelta: -1,
      acrossGap: false,
    });
  });

  it("home spread moving -3.5 → -2.5 is a +1.0 delta (toward the away side)", () => {
    const s = buildBookSeries([obs(0, -3.5, -110), obs(6, -2.5, -110)]);
    expect(s.changes[0]!.pointDelta).toBe(1);
  });

  it("detects gaps longer than the threshold and keeps both edges", () => {
    const s = buildBookSeries(
      [obs(0, -3, -110), obs(6, -3, -110), obs(30, -3, -110), obs(36, -3, -110)],
      {
        gapMinutes: 12 * 60,
      },
    );
    expect(s.gaps).toEqual([{ from: at(6), to: at(30), minutes: 24 * 60 }]);
    expect(s.points.map((p) => [p.observedAt, p.kinds])).toEqual([
      [at(0), ["first"]],
      [at(6), ["gap-start"]],
      [at(30), ["gap-end"]],
      [at(36), ["last"]],
    ]);
  });

  it("flags a change detected across a gap", () => {
    const s = buildBookSeries([obs(0, -3, -110), obs(24, -4, -110)], { gapMinutes: 12 * 60 });
    expect(s.changes[0]).toMatchObject({ acrossGap: true, type: "point" });
    expect(s.points[1]!.kinds).toEqual(["gap-end", "change", "last"]);
  });

  it("returns every observation in 'all' resolution", () => {
    const s = buildBookSeries([obs(0, -3, -110), obs(6, -3, -110), obs(12, -3, -110)], {
      resolution: "all",
    });
    expect(s.points.map((p) => p.kinds)).toEqual([["first"], ["observation"], ["last"]]);
  });

  it("handles moneylines (null points) and a single observation", () => {
    const s = buildBookSeries([obs(0, null, -185)]);
    expect(s.points).toEqual([
      { observedAt: at(0), point: null, americanPrice: -185, kinds: ["first"] },
    ]);
    const ml = buildBookSeries([obs(0, null, -185), obs(6, null, -200)]);
    expect(ml.changes[0]).toMatchObject({ type: "price", pointDelta: null });
  });

  it("handles an empty series", () => {
    expect(buildBookSeries([])).toMatchObject({
      observations: 0,
      points: [],
      firstObservedAt: null,
    });
  });

  it("rejects mixed books and unsorted input", () => {
    expect(() => buildBookSeries([obs(0, -3, -110), obs(6, -3, -110, "fanduel")])).toThrow(
      RangeError,
    );
    expect(() => buildBookSeries([obs(6, -3, -110), obs(0, -3, -110)])).toThrow(RangeError);
  });
});

describe("buildSeriesByBook", () => {
  it("groups and sorts mixed observations per book", () => {
    const series = buildSeriesByBook([
      obs(6, -3, -115, "fanduel"),
      obs(0, -3, -110, "fanduel"),
      obs(0, -3.5, -110),
    ]);
    expect(series.map((s) => s.bookmakerKey)).toEqual(["draftkings", "fanduel"]);
    expect(series[1]!.changes).toHaveLength(1);
  });
});
