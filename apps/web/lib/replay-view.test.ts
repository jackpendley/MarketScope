import { BOARD_BOOKS, type HistoryObservation } from "@marketscope/shared";
import { describe, expect, it } from "vitest";
import { buildReplayView, snapshotTimes, type ReplaySelectionInput } from "./replay-view";

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

const home: ReplaySelectionInput = {
  selection: "HOME",
  label: "Buffalo Bills",
  observations: [
    obs("draftkings", 0, -3),
    obs("draftkings", 6, -3.5),
    obs("fanduel", 0, -3),
    obs("fanduel", 6, -3),
    obs("betmgm", 0, -2.5), // not observed again
    obs("hardrockbet_az", 6, -3.5),
    obs("hardrockbet", 6, -3.5),
  ],
};
const away: ReplaySelectionInput = {
  selection: "AWAY",
  label: "Miami Dolphins",
  observations: home.observations.map((o) => ({ ...o, point: -o.point! })),
};
const opts = { books: BOARD_BOOKS, market: "spreads" as const, freshnessMinutes: 4 * 60 };

describe("buildReplayView", () => {
  it("shows each book's state at T, flagging books not seen within the window as stale", () => {
    const view = buildReplayView([home, away], { ...opts, at: at(6) });
    const cell = (book: string) => view.rows[0]!.cells[book]!;
    expect(cell("draftkings")).toMatchObject({ status: "fresh", point: -3.5 });
    expect(cell("betmgm")).toMatchObject({ status: "stale", point: -2.5, ageMinutes: 360 });
    expect(cell("caesars")).toMatchObject({ status: "none", point: null });
    expect(view.rows[1]!.cells.draftkings!.point).toBe(3.5);
  });

  it("uses one Hard Rock feed (AZ preferred), so consensus never double-counts a book", () => {
    const view = buildReplayView([home, away], { ...opts, at: at(6) });
    expect(view.columns.find((c) => c.book.id === "hardrock")).toMatchObject({
      feedKey: "hardrockbet_az",
      fallbackLabel: null,
    });
    // Fresh home spreads: DK -3.5, FD -3, HR(AZ) -3.5 → median -3.5 over 3 books (MGM is stale).
    expect(view.consensus).toEqual({ point: -3.5, books: 3 });
    expect(view.dispersion).toMatchObject({ books: 3, range: 0.5, booksOffCenter: 1 });
  });

  it("reflects the earlier market when the cursor moves back", () => {
    const view = buildReplayView([home, away], { ...opts, at: at(0) });
    expect(view.rows[0]!.cells.draftkings!.point).toBe(-3);
    expect(view.rows[0]!.cells.hardrock!.status).toBe("none");
    // DK -3, FD -3, MGM -2.5 → median -3.
    expect(view.consensus).toEqual({ point: -3, books: 3 });
  });

  it("withholds consensus with fewer than three fresh books", () => {
    const view = buildReplayView([home, away], { ...opts, at: at(20) });
    expect(view.consensus).toBeNull();
    expect(view.freshBooks).toBe(0);
  });

  it("has no line consensus for moneylines", () => {
    const ml: ReplaySelectionInput = {
      ...home,
      observations: home.observations.map((o) => ({ ...o, point: null })),
    };
    expect(buildReplayView([ml], { ...opts, market: "h2h", at: at(6) }).consensus).toBeNull();
  });
});

describe("snapshotTimes", () => {
  it("lists distinct observation times in order", () => {
    expect(snapshotTimes([home, away])).toEqual([at(0), at(6)]);
  });
});
