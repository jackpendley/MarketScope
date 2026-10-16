import { buildBookSeries, type HistoryObservation } from "@marketscope/shared";
import { describe, expect, it } from "vitest";
import {
  americanToScale,
  axisTicks,
  buildChartRows,
  formatScaledAmerican,
  scaleToAmerican,
} from "./history-chart";

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

describe("American odds scale", () => {
  it("is continuous through even money", () => {
    expect(americanToScale(-110)).toBe(-10);
    expect(americanToScale(110)).toBe(10);
    expect(americanToScale(-100)).toBe(0);
    expect(americanToScale(100)).toBe(0);
    expect(scaleToAmerican(-10)).toBe(-110);
    expect(scaleToAmerican(10)).toBe(110);
  });

  it("formats ticks as American odds", () => {
    expect(formatScaledAmerican(-10)).toBe("-110");
    expect(formatScaledAmerican(25)).toBe("+125");
    expect(formatScaledAmerican(0)).toBe("EVEN");
  });
});

describe("buildChartRows", () => {
  it("holds a book's value between its kept points (compressed series)", () => {
    const dk = buildBookSeries([
      obs("dk", 0, -3),
      obs("dk", 6, -3),
      obs("dk", 12, -3.5),
      obs("dk", 18, -3.5),
    ]);
    const fd = buildBookSeries([
      obs("fd", 0, -3),
      obs("fd", 6, -2.5),
      obs("fd", 12, -2.5),
      obs("fd", 18, -2.5),
    ]);
    const { rows } = buildChartRows([dk, fd], "point");
    // DK's 6h observation was compressed away; its value at the 6h row is still -3.
    expect(rows.map((r) => [r.t, r.dk, r.fd])).toEqual([
      [t0, -3, -3],
      [t0 + 6 * H, -3, -2.5],
      [t0 + 12 * H, -3.5, -2.5],
      [t0 + 18 * H, -3.5, -2.5],
    ]);
  });

  it("breaks the line across a gap instead of holding the value", () => {
    const dk = buildBookSeries([obs("dk", 0, -3), obs("dk", 6, -3), obs("dk", 30, -3)], {
      gapMinutes: 12 * 60,
    });
    const fd = buildBookSeries(
      [0, 6, 12, 18, 24, 30].map((h) => obs("fd", h, -3)),
      { resolution: "all" },
    );
    const { rows } = buildChartRows([dk, fd], "point");
    const dkAt = (h: number) => rows.find((r) => r.t === t0 + h * H)!.dk;
    expect(dkAt(6)).toBe(-3);
    expect(rows.find((r) => r.t === t0 + 6 * H + 1)!.dk).toBeNull(); // break marker
    expect(dkAt(12)).toBeNull();
    expect(dkAt(24)).toBeNull();
    expect(dkAt(30)).toBe(-3);
    // FanDuel is unaffected by DraftKings' gap.
    expect(rows.find((r) => r.t === t0 + 12 * H)!.fd).toBe(-3);
  });

  it("never extrapolates before a book's first or after its last observation", () => {
    const dk = buildBookSeries([obs("dk", 6, -3), obs("dk", 12, -3)]);
    const fd = buildBookSeries([obs("fd", 0, -3), obs("fd", 18, -3)]);
    const { rows } = buildChartRows([dk, fd], "point");
    expect(rows.find((r) => r.t === t0)!.dk).toBeNull();
    expect(rows.find((r) => r.t === t0 + 18 * H)!.dk).toBeNull();
  });

  it("plots prices on the continuous scale", () => {
    const dk = buildBookSeries([obs("dk", 0, -3, -105), obs("dk", 6, -3, 105)]);
    const { rows } = buildChartRows([dk], "price");
    expect(rows.map((r) => r.dk)).toEqual([-5, 5]);
  });
});

describe("axisTicks", () => {
  const rows = [
    { t: 1, dk: -3.5, fd: -4 },
    { t: 2, dk: -5, fd: null },
  ];
  it("uses half-point ticks with one step of padding", () => {
    expect(axisTicks(rows, ["dk", "fd"], 0.5)).toEqual({
      domain: [-5.5, -3],
      ticks: [-5.5, -5, -4.5, -4, -3.5, -3],
    });
  });
  it("widens the step when there would be too many ticks", () => {
    const wide = axisTicks(
      [
        { t: 1, dk: -14 },
        { t: 2, dk: 3 },
      ],
      ["dk"],
      0.5,
    )!;
    expect(wide.ticks.length).toBeLessThanOrEqual(9);
    expect(wide.ticks.every((t) => Number.isInteger(t / 0.5))).toBe(true);
  });
  it("returns null with no values", () => {
    expect(axisTicks([{ t: 1, dk: null }], ["dk"], 0.5)).toBeNull();
  });
});
