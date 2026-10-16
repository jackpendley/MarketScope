import { describe, expect, it } from "vitest";
import { matchesTeamSearch, parseBoardFilters } from "./board-filters";

describe("parseBoardFilters", () => {
  it("defaults to all markets, all books, 7 days", () => {
    const f = parseBoardFilters({});
    expect(f).toMatchObject({ q: "", market: null, days: 7 });
    expect([...f.books]).toEqual(["draftkings", "fanduel", "betmgm", "caesars", "hardrock"]);
  });

  it("accepts valid values and ignores invalid ones", () => {
    const f = parseBoardFilters({
      q: "  Bills ",
      market: "spreads",
      books: ["fanduel", "bovada"],
      days: "3",
    });
    expect(f).toMatchObject({ q: "Bills", market: "spreads", days: 3 });
    expect([...f.books]).toEqual(["fanduel"]);
  });

  it("falls back on unknown market and day values", () => {
    expect(parseBoardFilters({ market: "props", days: "999" })).toMatchObject({
      market: null,
      days: 7,
    });
  });

  it("treats a single book param as a one-item list", () => {
    expect([...parseBoardFilters({ books: "betmgm" }).books]).toEqual(["betmgm"]);
  });
});

describe("matchesTeamSearch", () => {
  const board = { homeTeam: "Buffalo Bills", awayTeam: "Miami Dolphins" };
  it("matches either team case-insensitively", () => {
    expect(matchesTeamSearch(board, "bills")).toBe(true);
    expect(matchesTeamSearch(board, "MIAMI")).toBe(true);
    expect(matchesTeamSearch(board, "Jets")).toBe(false);
    expect(matchesTeamSearch(board, "")).toBe(true);
  });
});
