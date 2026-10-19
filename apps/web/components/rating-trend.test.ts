import { describe, expect, it } from "vitest";
import { trendLabel } from "./rating-trend";

describe("trendLabel", () => {
  it("names the starting and current rating with its range", () => {
    expect(
      trendLabel(2026, [
        { week: 0, adjEm: 1.2, adjEmSe: 3.0 },
        { week: 6, adjEm: 4.9, adjEmSe: 2.3 },
      ]),
    ).toMatch(/^AdjEM by week, 2026: \+1\.2 at .+, now \+4\.9 ± 2\.3 at .+$/);
    expect(trendLabel(2026, [])).toBe("AdjEM by week, 2026: no ratings yet");
  });
});
