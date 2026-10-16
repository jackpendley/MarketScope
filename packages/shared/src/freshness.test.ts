import { describe, expect, it } from "vitest";
import { calculateFreshness, formatAge } from "./freshness";

const now = new Date("2026-10-16T12:00:00Z");

describe("calculateFreshness", () => {
  it("labels observations within the window as recent", () => {
    expect(calculateFreshness("2026-10-16T11:50:00Z", now, 15)).toEqual({
      ageMinutes: 10,
      label: "recent",
    });
  });

  it("labels older observations as snapshots", () => {
    expect(calculateFreshness("2026-10-16T06:00:00Z", now, 15)).toEqual({
      ageMinutes: 360,
      label: "snapshot",
    });
  });

  it("clamps clock skew (future timestamps) to zero age", () => {
    expect(calculateFreshness("2026-10-16T12:01:00Z", now, 15).ageMinutes).toBe(0);
  });

  it("rejects invalid timestamps", () => {
    expect(() => calculateFreshness("later", now, 15)).toThrow(RangeError);
  });
});

describe("formatAge", () => {
  it.each([
    [0.4, "just now"],
    [12, "12m"],
    [60, "1h"],
    [185, "3h 5m"],
    [2880, "2d"],
    [3000, "2d 2h"],
  ])("%d → %s", (minutes, text) => {
    expect(formatAge(minutes)).toBe(text);
  });
});
