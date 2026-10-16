import { describe, expect, it } from "vitest";
import {
  americanToDecimal,
  americanToImpliedProbability,
  decimalToAmerican,
  isValidAmericanOdds,
  overround,
  potentialPayout,
} from "./odds";

const INVALID_AMERICAN = [0, 50, -99, 99, -50, 110.5, -110.5, Number.NaN, Infinity, -Infinity];

describe("isValidAmericanOdds", () => {
  it.each([-10000, -110, -100, 100, 150, 2500])("accepts %d", (price) => {
    expect(isValidAmericanOdds(price)).toBe(true);
  });

  it.each(INVALID_AMERICAN)("rejects %d", (price) => {
    expect(isValidAmericanOdds(price)).toBe(false);
  });
});

describe("americanToImpliedProbability", () => {
  it.each([
    [-110, 110 / 210],
    [+150, 0.4],
    [-200, 2 / 3],
    [+300, 0.25],
    [+100, 0.5],
    [-100, 0.5],
  ])("%d → %f", (american, expected) => {
    expect(americanToImpliedProbability(american)).toBeCloseTo(expected, 10);
  });

  it("matches the spec's worked example: −110 ≈ 52.38%", () => {
    expect(americanToImpliedProbability(-110) * 100).toBeCloseTo(52.38, 2);
  });

  it("favorites imply more than 50%, underdogs less", () => {
    expect(americanToImpliedProbability(-150)).toBeGreaterThan(0.5);
    expect(americanToImpliedProbability(+130)).toBeLessThan(0.5);
  });

  it.each(INVALID_AMERICAN)("throws RangeError for %d", (price) => {
    expect(() => americanToImpliedProbability(price)).toThrow(RangeError);
  });
});

describe("americanToDecimal", () => {
  it.each([
    [-110, 1 + 100 / 110],
    [+150, 2.5],
    [-200, 1.5],
    [+100, 2],
    [-100, 2],
    [+250, 3.5],
  ])("%d → %f", (american, expected) => {
    expect(americanToDecimal(american)).toBeCloseTo(expected, 10);
  });

  it("is monotonic: a better price for the bettor always has higher decimal odds", () => {
    const ordered = [-500, -200, -115, -110, -105, 100, 105, 150, 400];
    const decimals = ordered.map(americanToDecimal);
    for (let i = 1; i < decimals.length; i++) {
      expect(decimals[i]).toBeGreaterThan(decimals[i - 1]!);
    }
  });

  it.each(INVALID_AMERICAN)("throws RangeError for %d", (price) => {
    expect(() => americanToDecimal(price)).toThrow(RangeError);
  });
});

describe("decimalToAmerican", () => {
  it.each([
    [2.5, 150],
    [1.5, -200],
    [2.0, 100],
    [3.5, 250],
    [1.91, -110],
    [1.952, -105],
  ])("%f → %d", (decimal, expected) => {
    expect(decimalToAmerican(decimal)).toBe(expected);
  });

  it.each([-500, -200, -115, -110, -105, 100, 105, 150, 250, 1000])(
    "round-trips American %d",
    (price) => {
      expect(decimalToAmerican(americanToDecimal(price))).toBe(price);
    },
  );

  it("maps −100 to +100 (same even-money price)", () => {
    expect(decimalToAmerican(americanToDecimal(-100))).toBe(100);
  });

  it.each([1, 0.5, 0, -2, Number.NaN, Infinity])("throws RangeError for %f", (decimal) => {
    expect(() => decimalToAmerican(decimal)).toThrow(RangeError);
  });
});

describe("potentialPayout", () => {
  it("−110 risking 110 wins 100", () => {
    const { profit, totalReturn } = potentialPayout(110, -110);
    expect(profit).toBeCloseTo(100, 10);
    expect(totalReturn).toBeCloseTo(210, 10);
  });

  it("+150 risking 100 wins 150", () => {
    const { profit, totalReturn } = potentialPayout(100, 150);
    expect(profit).toBeCloseTo(150, 10);
    expect(totalReturn).toBeCloseTo(250, 10);
  });

  it.each([0, -10, Number.NaN])("rejects stake %d", (stake) => {
    expect(() => potentialPayout(stake, -110)).toThrow(RangeError);
  });
});

describe("overround", () => {
  it("−110/−110 has ≈4.76% margin", () => {
    expect(overround([-110, -110])).toBeCloseTo(0.047619, 5);
  });

  it("+100/+100 has zero margin", () => {
    expect(overround([100, 100])).toBeCloseTo(0, 10);
  });

  it("requires at least two prices", () => {
    expect(() => overround([-110])).toThrow(RangeError);
  });
});
