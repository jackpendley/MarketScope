import { describe, expect, it } from "vitest";
import {
  CATALOGUE,
  equityRows,
  PRICES,
  seasonStarts,
  versusBreakEven,
  WONG,
  y2026,
} from "./systems-view";

describe("systems view", () => {
  it("lists prices from best to worst and break-evens rising with price", () => {
    expect(PRICES[0]).toBe(-110);
    const be = PRICES.map((p) => WONG.breakEven[String(p) as keyof typeof WONG.breakEven]);
    expect([...be].sort((a, b) => a - b)).toEqual(be);
  });

  it("classifies an interval against a break-even", () => {
    expect(versusBreakEven(0.75, 0.8, 0.745)).toBe("above");
    expect(versusBreakEven(0.7, 0.74, 0.745)).toBe("below");
    expect(versusBreakEven(0.72, 0.79, 0.745)).toBe("includes");
  });

  it("keeps the primary estimate inside its interval", () => {
    const p = WONG.primary;
    expect(p.low).toBeLessThanOrEqual(p.rate);
    expect(p.high).toBeGreaterThanOrEqual(p.rate);
  });

  it("builds the equity curve in order with season starts", () => {
    const rows = equityRows("V0");
    expect(rows.map((r) => r.n)).toEqual(rows.map((_, i) => i + 1));
    const starts = seasonStarts("V0");
    expect(starts[0]!.season).toBe(2016);
    expect(starts.map((s) => s.season)).toEqual([...new Set(rows.map((r) => r.season))]);
  });

  it("has a 2026 row for every source and variant", () => {
    for (const src of ["nflverse close", "Caesars' closing line"] as const)
      for (const v of ["V0", "V1", "V2"] as const) expect(y2026(src, v).legs).toBeGreaterThan(0);
  });

  it("lists F1–F10 with estimates inside their intervals", () => {
    expect(CATALOGUE.systems.map((s) => s.id)).toEqual(
      Array.from({ length: 10 }, (_, i) => `F${i + 1}`),
    );
    for (const s of CATALOGUE.systems) {
      expect(s.low).toBeLessThanOrEqual(s.rate);
      expect(s.high).toBeGreaterThanOrEqual(s.rate);
      if (s.supported) expect(s.holm).toBe(true);
    }
  });

  it("never uses pick or lock language", () => {
    const text = JSON.stringify(WONG).toLowerCase();
    expect(text).not.toMatch(/\b(picks?|locks?)\b/);
  });
});
