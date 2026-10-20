import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { bookmakers, events, lineMoves } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import { lineMoveHistory } from "./line-moves";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());

let eventId: string;
beforeEach(async () => {
  await resetDatabase(sql);
  await db
    .insert(bookmakers)
    .values([
      { key: "pinnacle", displayName: "Pinnacle (reference)" },
      { key: "draftkings", displayName: "DraftKings" },
    ])
    .onConflictDoNothing();
  const [evt] = await db
    .insert(events)
    .values({
      providerEventId: "g1",
      sportKey: "americanfootball_nfl",
      season: 2026,
      homeTeam: "Buffalo Bills",
      awayTeam: "Miami Dolphins",
      commenceTimeUtc: "2026-10-18T17:00:00Z",
    })
    .returning({ id: events.id });
  eventId = evt!.id;
  const move = (
    bookmakerKey: string,
    changedAt: string,
    point: number | null,
    price1: number | null,
  ) => ({
    eventId,
    bookmakerKey,
    marketType: "spreads" as const,
    changedAt,
    point,
    price1,
    price2: price1 === null ? null : -110,
    source: "oddspapi",
  });
  await db
    .insert(lineMoves)
    .values([
      move("pinnacle", "2026-10-17T10:00:00Z", -3, -110),
      move("draftkings", "2026-10-17T09:00:00Z", -3, -110),
      move("pinnacle", "2026-10-17T12:00:00Z", -3.5, -105),
      move("pinnacle", "2026-10-17T11:00:00Z", null, null),
    ]);
});

describe("lineMoveHistory", () => {
  it("returns one market's moves by book, oldest first, suspensions included", async () => {
    const rows = await lineMoveHistory(db, eventId, "spreads");
    expect(rows.map((r) => [r.bookmakerKey, r.point, r.price1])).toEqual([
      ["draftkings", -3, -110],
      ["pinnacle", -3, -110],
      ["pinnacle", null, null],
      ["pinnacle", -3.5, -105],
    ]);
    expect(await lineMoveHistory(db, eventId, "totals")).toEqual([]);
  });

  it("enforces paired prices and a point only on available spread/total rows", async () => {
    const bad = (values: Partial<typeof lineMoves.$inferInsert>) =>
      db.insert(lineMoves).values({
        eventId,
        bookmakerKey: "pinnacle",
        marketType: "spreads",
        changedAt: "2026-10-17T13:00:00Z",
        source: "oddspapi",
        ...values,
      });
    await expect(bad({ point: -3, price1: -110 })).rejects.toThrow();
    await expect(bad({ point: -3 })).rejects.toThrow();
    await expect(bad({ price1: -110, price2: -110 })).rejects.toThrow();
    await expect(
      bad({ marketType: "h2h", point: 1, price1: -110, price2: -110 }),
    ).rejects.toThrow();
    await expect(bad({ point: -3, price1: -50, price2: -110 })).rejects.toThrow();
  });
});
