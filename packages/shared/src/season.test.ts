import { describe, expect, it } from "vitest";
import { nflSeasonForKickoff } from "./season";

describe("nflSeasonForKickoff", () => {
  it.each([
    ["2026-09-10T00:20:00Z", 2026],
    ["2026-12-25T21:30:00Z", 2026],
    ["2027-01-10T18:00:00Z", 2026],
    ["2027-02-07T23:30:00Z", 2026],
    ["2027-08-15T00:00:00Z", 2027],
  ])("%s → %d season", (iso, season) => {
    expect(nflSeasonForKickoff(iso)).toBe(season);
  });

  it("rejects invalid timestamps", () => {
    expect(() => nflSeasonForKickoff("soon")).toThrow(RangeError);
  });
});
