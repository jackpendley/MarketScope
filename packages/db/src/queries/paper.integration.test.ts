import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { bookmakers, nflGames, nflTeams, paperPositions } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import { listPaperPositions, paperSeasons } from "./paper";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());

const KICKOFF = "2026-10-25T17:00:00.000Z";
const position = (over: Partial<typeof paperPositions.$inferInsert> = {}) => ({
  strategy: "F1",
  mode: "live",
  gameId: "2026_08_KC_BUF",
  season: 2026,
  week: 8,
  kickoffUtc: KICKOFF,
  market: "spread",
  side: "BUF",
  line: 2.5,
  price: -110,
  bookmakerKey: "williamhill_us",
  quoteObservedAt: "2026-10-25T12:07:00.000Z",
  placedAt: "2026-10-25T12:20:00.000Z",
  ...over,
});

beforeEach(async () => {
  await resetDatabase(sql);
  await db
    .insert(bookmakers)
    .values({ key: "williamhill_us", displayName: "Caesars" })
    .onConflictDoNothing();
  await db.insert(nflTeams).values(
    ["KC", "BUF"].map((abbr) => ({
      abbr,
      franchise: abbr,
      fullName: abbr,
      nickname: abbr,
      conference: "AFC",
      division: "AFC East",
    })),
  );
  await db.insert(nflGames).values({
    gameId: "2026_08_KC_BUF",
    season: 2026,
    gameType: "REG",
    week: 8,
    kickoffUtc: KICKOFF,
    homeTeam: "BUF",
    awayTeam: "KC",
    neutralSite: false,
    divisionGame: false,
  });
});

describe("paper positions", () => {
  it("lists a season's positions with the game's teams", async () => {
    await db
      .insert(paperPositions)
      .values([position(), position({ strategy: "F2", mode: "reconstructed" })]);
    const rows = await listPaperPositions(db, { season: 2026, modes: ["live"] });
    expect(rows.map((r) => [r.strategy, r.homeTeam, r.awayTeam, r.line])).toEqual([
      ["F1", "BUF", "KC", 2.5],
    ]);
    expect(await paperSeasons(db)).toEqual([2026]);
  });

  it("allows grading but never a change to the placement", async () => {
    const [p] = await db
      .insert(paperPositions)
      .values(position())
      .returning({ id: paperPositions.id });
    await sql`UPDATE paper_positions SET result = 'win', clv = 0.5, graded_at = now() WHERE id = ${p!.id}`;
    await expect(sql`UPDATE paper_positions SET line = 3.5 WHERE id = ${p!.id}`).rejects.toThrow(
      /immutable/,
    );
    await expect(sql`UPDATE paper_positions SET price = -105 WHERE id = ${p!.id}`).rejects.toThrow(
      /immutable/,
    );
  });

  it("never deletes a live position; reconstructed ones can be replaced", async () => {
    await db
      .insert(paperPositions)
      .values([position(), position({ strategy: "F2", mode: "reconstructed" })]);
    await expect(sql`DELETE FROM paper_positions WHERE mode = 'live'`).rejects.toThrow(
      /cannot be deleted/,
    );
    await sql`DELETE FROM paper_positions WHERE mode = 'reconstructed'`;
    expect(await db.$count(paperPositions)).toBe(1);
  });

  it("rejects live positions placed after kickoff and quotes from after kickoff", async () => {
    await expect(
      db.insert(paperPositions).values(position({ placedAt: "2026-10-25T17:01:00Z" })),
    ).rejects.toThrow();
    await expect(
      db
        .insert(paperPositions)
        .values(position({ mode: "reconstructed", quoteObservedAt: "2026-10-25T17:00:00Z" })),
    ).rejects.toThrow();
    // A reconstructed position may be created after kickoff, from a quote observed before it.
    await db
      .insert(paperPositions)
      .values(position({ mode: "reconstructed", placedAt: "2026-10-26T11:00:00Z" }));
  });

  it("requires teaser legs to carry a teased line and other positions a price", async () => {
    await expect(
      db.insert(paperPositions).values(position({ market: "teaser_leg", price: null })),
    ).rejects.toThrow();
    await expect(db.insert(paperPositions).values(position({ price: null }))).rejects.toThrow();
    await db
      .insert(paperPositions)
      .values(position({ market: "teaser_leg", price: null, teasedLine: 8.5 }));
  });
});
