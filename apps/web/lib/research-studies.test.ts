import { describe, expect, it } from "vitest";
import { MARKET_STUDIES, STUDIES } from "./research-studies";

const num = (s: string) => Number(s.replace("−", "-"));

describe("research studies", () => {
  it("lists every study once, in order", () => {
    expect(STUDIES.map((s) => s.id)).toEqual([
      "R1",
      "R2",
      "R2h",
      "R2w",
      "R3",
      "R4",
      "R5",
      "R6",
      "R7",
    ]);
  });

  it("lists the sharp-market studies in order", () => {
    expect(MARKET_STUDIES.map((s) => s.id)).toEqual(["S1", "S2", "S3", "M1", "M2", "I1", "I2"]);
  });

  it("gives every completed study a primary estimate inside its interval and a report", () => {
    for (const s of [...STUDIES, ...MARKET_STUDIES].filter(
      (x) => x.status !== "waiting for data",
    )) {
      expect(s.primary, s.id).not.toBeNull();
      expect(s.report, s.id).toMatch(/^https:\/\/github\.com\/.+\/research\/reports\/.+\.md$/);
      const [lo = NaN, hi = NaN] = s.primary!.interval.split(" to ").map(num);
      const est = num(s.primary!.estimate);
      expect(lo, s.id).toBeLessThanOrEqual(est);
      expect(hi, s.id).toBeGreaterThanOrEqual(est);
      // A claim needs an interval that excludes its threshold (zero unless stated).
      const t = s.primary!.threshold ?? 0;
      if (s.status === "claim" || s.status === "discovery claim")
        expect(lo > t || hi < t, s.id).toBe(true);
    }
  });

  it("never uses wagering language", () => {
    const text = JSON.stringify([...STUDIES, ...MARKET_STUDIES]).toLowerCase();
    for (const word of [/\bbet(s|ting|tor)?\b/, /\bpicks?\b/, /\bedge\b/, /\blocks?\b/])
      expect(text).not.toMatch(word);
  });
});
