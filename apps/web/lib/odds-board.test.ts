import {
  TARGET_BOOKMAKERS,
  TARGET_BOOKMAKER_KEYS,
  normalizeEventOdds,
  parseOddsResponse,
} from "@marketscope/shared";
import { SYNTHETIC_NFL_ODDS, SYNTHETIC_OBSERVED_AT } from "@marketscope/shared/fixtures";
import { describe, expect, it } from "vitest";
import { buildEventBoard, type BoardCell } from "./odds-board";

const { events } = parseOddsResponse(SYNTHETIC_NFL_ODDS);
function board(id: string) {
  const raw = events.find((e) => e.id === id)!;
  const odds = normalizeEventOdds(raw, {
    observedAt: SYNTHETIC_OBSERVED_AT,
    targetBookmakers: TARGET_BOOKMAKER_KEYS,
  });
  return buildEventBoard(odds, TARGET_BOOKMAKERS);
}
function cell(
  b: ReturnType<typeof board>,
  market: string,
  selection: string,
  book: string,
): BoardCell {
  return b.rows.find((r) => r.market === market && r.selection === selection)!.cells[book]!;
}

describe("buildEventBoard", () => {
  const bufMia = board("synthetic-evt-001");

  it("orders rows away-then-home with team names as labels", () => {
    expect(bufMia.rows.map((r) => r.label)).toEqual([
      "Miami Dolphins",
      "Buffalo Bills",
      "Miami Dolphins",
      "Buffalo Bills",
      "Over",
      "Under",
    ]);
  });

  it("highlights the best price only among identical lines", () => {
    // Home −3.5: DK −110, MGM −105, HR −108 → MGM best. FD is alone at −3, so never "best".
    expect(cell(bufMia, "spreads", "HOME", "betmgm")).toMatchObject({
      kind: "quote",
      isBest: true,
    });
    expect(cell(bufMia, "spreads", "HOME", "draftkings")).toMatchObject({ isBest: false });
    expect(cell(bufMia, "spreads", "HOME", "fanduel")).toMatchObject({ point: -3, isBest: false });
  });

  it("distinguishes a missing book from a missing market", () => {
    expect(cell(bufMia, "spreads", "HOME", "williamhill_us")).toEqual({ kind: "book-missing" });
    expect(cell(bufMia, "totals", "OVER", "betmgm")).toEqual({ kind: "market-missing" });
    expect(bufMia.columns.find((c) => c.book.key === "williamhill_us")?.inFeed).toBe(false);
  });

  it("marks a selection rejected by validation as missing, not invented", () => {
    const gbChi = board("synthetic-evt-002");
    expect(cell(gbChi, "h2h", "AWAY", "draftkings")).toEqual({ kind: "selection-missing" });
  });

  it("never marks best prices on an event that has started", () => {
    const dalPhi = board("synthetic-evt-003");
    expect(dalPhi.isLive).toBe(true);
    const anyBest = dalPhi.rows.some((r) =>
      Object.values(r.cells).some((c) => c.kind === "quote" && c.isBest),
    );
    expect(anyBest).toBe(false);
  });

  it("reports each book's latest market update", () => {
    expect(bufMia.columns.find((c) => c.book.key === "fanduel")?.latestUpdate).toBe(
      "2026-10-15T17:40:31.000Z",
    );
  });
});
