import { describe, expect, it } from "vitest";
import { DRIVERS, EXPERIMENTS } from "./ml-lab";

const num = (s: string) => Number(s.replace("−", "-"));
const range = (s: string) => s.split(" to ").map(num) as [number, number];

describe("ML Lab experiments", () => {
  it("keeps every estimate inside its interval", () => {
    for (const e of EXPERIMENTS)
      for (const m of [e.dBrier, e.dLogLoss, e.auc]) {
        if (!m) continue;
        const [lo, hi] = range(m.interval);
        expect(lo, e.id).toBeLessThanOrEqual(num(m.estimate));
        expect(hi, e.id).toBeGreaterThanOrEqual(num(m.estimate));
      }
  });

  it("applies the claim rule: better needs both intervals below 0, worse both above 0", () => {
    for (const e of EXPERIMENTS) {
      const [bLo, bHi] = range(e.dBrier!.interval);
      const [lLo, lHi] = range(e.dLogLoss!.interval);
      const expected =
        bHi < 0 && lHi < 0 ? "better" : bLo > 0 && lLo > 0 ? "worse" : "not distinguishable";
      expect(e.verdict, e.id).toBe(expected);
    }
  });

  it("lists drivers with signed coefficients and no wagering language", () => {
    expect(DRIVERS.every((d) => /^[+−]\d/.test(d.coefficient))).toBe(true);
    const text = JSON.stringify({ EXPERIMENTS, DRIVERS }).toLowerCase();
    for (const word of [/\bbet(s|ting|tor)?\b/, /\bpicks?\b/, /\bedge\b/, /\blocks?\b/])
      expect(text).not.toMatch(word);
  });
});
