import type { LineMoveRow } from "@marketscope/db";
import { describe, expect, it } from "vitest";
import {
  lineMoveChartRows,
  lineMoveSummary,
  movesByBook,
  orient,
  pointMoveLog,
} from "./line-moves-view";

const row = (
  bookmakerKey: string,
  changedAt: string,
  point: number | null,
  price1: number | null,
  price2: number | null = price1 === null ? null : -110,
  limit1: number | null = null,
): LineMoveRow => ({
  bookmakerKey,
  changedAt,
  point,
  price1,
  price2,
  limit1,
  limit2: limit1,
});

const T = (iso: string) => Date.parse(iso);

// Pinnacle moves to -3.5 first; DraftKings follows 9 minutes later, then is suspended.
const ROWS: LineMoveRow[] = [
  row("pinnacle", "2026-10-18T10:00:00Z", -3, -110, -110, 5000),
  row("pinnacle", "2026-10-18T12:00:00Z", -3.5, -105, -115, 7500),
  row("draftkings", "2026-10-18T09:00:00Z", -3, -110),
  row("draftkings", "2026-10-18T12:09:00Z", -3.5, -110),
  row("draftkings", "2026-10-18T14:00:00Z", null, null),
  row("draftkings", "2026-10-18T14:30:00Z", -3.5, -112),
];

describe("orient", () => {
  it("negates the home spread for the away side and takes side 2's price", () => {
    expect(orient(ROWS[1]!, "spreads", "AWAY")).toEqual({ point: 3.5, price: -115 });
    expect(orient(ROWS[1]!, "spreads", "HOME")).toEqual({ point: -3.5, price: -105 });
    expect(orient(row("x", "2026-10-18T00:00:00Z", 0, -110), "spreads", "AWAY")?.point).toBe(0);
  });

  it("is null while suspended", () => {
    expect(orient(ROWS[4]!, "spreads", "HOME")).toBeNull();
  });
});

describe("lineMoveChartRows", () => {
  const byBook = movesByBook(ROWS, "spreads", "HOME");
  const rows = lineMoveChartRows(
    byBook,
    "point",
    T("2026-10-18T11:00:00Z"),
    T("2026-10-18T17:00:00Z"),
  );

  it("adds rows at the range edges and every move inside it", () => {
    expect(rows.map((r) => new Date(r.t).toISOString().slice(11, 16))).toEqual([
      "11:00",
      "12:00",
      "12:09",
      "14:00",
      "14:30",
      "17:00",
    ]);
  });

  it("holds each book's line between its moves, and breaks it while suspended", () => {
    expect(rows.map((r) => r.pinnacle)).toEqual([-3, -3.5, -3.5, -3.5, -3.5, -3.5]);
    expect(rows.map((r) => r.draftkings)).toEqual([-3, -3, -3.5, null, -3.5, -3.5]);
  });

  it("is null before a book's first move", () => {
    const early = lineMoveChartRows(
      byBook,
      "point",
      T("2026-10-18T09:30:00Z"),
      T("2026-10-18T09:45:00Z"),
    );
    expect(early.map((r) => r.pinnacle)).toEqual([null, null]);
    expect(early.map((r) => r.draftkings)).toEqual([-3, -3]);
  });

  it("charts prices on the continuous scale", () => {
    const prices = lineMoveChartRows(
      byBook,
      "price",
      T("2026-10-18T12:30:00Z"),
      T("2026-10-18T13:00:00Z"),
    );
    expect(prices[0]!.pinnacle).toBe(-5); // -105
  });
});

describe("pointMoveLog", () => {
  it("lists line changes with the first book to post the new number", () => {
    const log = pointMoveLog(movesByBook(ROWS, "spreads", "HOME"));
    expect(
      log.map((m) => [m.bookmakerKey, m.from, m.to, m.leaderKey, m.lagMs / 60_000, m.limit]),
    ).toEqual([
      ["pinnacle", -3, -3.5, "pinnacle", 0, 7500],
      ["draftkings", -3, -3.5, "pinnacle", 9, null],
    ]);
  });

  it("ignores suspensions and price-only changes", () => {
    const log = pointMoveLog(movesByBook(ROWS, "spreads", "HOME"));
    expect(log.some((m) => m.t === T("2026-10-18T14:30:00Z"))).toBe(false);
  });

  it("does not credit a move in the opposite direction or outside the lookback", () => {
    const rows = [
      row("pinnacle", "2026-10-15T10:00:00Z", -3, -110),
      row("pinnacle", "2026-10-15T11:00:00Z", -3.5, -110), // posted -3.5 three days earlier
      row("pinnacle", "2026-10-18T09:00:00Z", -4, -110),
      row("draftkings", "2026-10-18T08:00:00Z", -3, -110),
      row("draftkings", "2026-10-18T12:00:00Z", -3.5, -110),
      row("circa", "2026-10-18T08:00:00Z", -4, -110),
      row("circa", "2026-10-18T11:00:00Z", -3.5, -110), // moving down to -3.5, not up
    ];
    const log = pointMoveLog(movesByBook(rows, "spreads", "HOME"));
    const dk = log.find((m) => m.bookmakerKey === "draftkings")!;
    expect(dk.leaderKey).toBe("draftkings");
    const circa = log.find((m) => m.bookmakerKey === "circa")!;
    expect(circa.leaderKey).toBe("circa");
  });
});

describe("lineMoveSummary", () => {
  it("describes each book's line over the range", () => {
    const text = lineMoveSummary(
      movesByBook(ROWS, "spreads", "HOME"),
      { pinnacle: "Pinnacle", draftkings: "DraftKings" },
      "point",
      T("2026-10-18T11:00:00Z"),
      T("2026-10-18T17:00:00Z"),
      String,
    );
    expect(text).toBe("Pinnacle -3 to -3.5 (1 change); DraftKings -3 to -3.5 (1 change).");
  });
});
