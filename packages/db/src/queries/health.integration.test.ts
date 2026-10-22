import { eq } from "drizzle-orm";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { bookmakers, events, ingestionRuns, lineMoves, nflGames, nflTeams } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import { datasetFreshness } from "./health";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

const NOW = new Date("2026-10-22T12:00:00Z");

async function seed() {
  await db.insert(nflTeams).values(
    ["BUF", "MIA", "NYJ", "NE"].map((abbr) => ({
      abbr,
      franchise: abbr,
      fullName: abbr,
      nickname: abbr,
      conference: "AFC",
      division: "AFC East",
    })),
  );
  await db
    .insert(bookmakers)
    .values({ key: "pinnacle", displayName: "Pinnacle" })
    .onConflictDoNothing();
  const [a, b] = await db
    .insert(events)
    .values(
      ["e1", "e2"].map((id, i) => ({
        providerEventId: id,
        sportKey: "americanfootball_nfl",
        season: 2026,
        homeTeam: `H${i}`,
        awayTeam: `A${i}`,
        commenceTimeUtc: "2026-10-18T17:00:00Z",
      })),
    )
    .returning({ id: events.id });
  const game = (gameId: string, home: string, away: string, kickoffUtc: string) => ({
    gameId,
    season: 2026,
    gameType: "REG",
    week: 7,
    kickoffUtc,
    homeTeam: home,
    awayTeam: away,
    neutralSite: false,
    divisionGame: true,
  });
  await db.insert(nflGames).values([
    {
      ...game("2026_07_MIA_BUF", "BUF", "MIA", "2026-10-18T17:00:00Z"),
      homeScore: 24,
      awayScore: 20,
      eventId: a!.id,
    },
    {
      ...game("2026_07_NE_NYJ", "NYJ", "NE", "2026-10-18T17:00:00Z"),
      homeScore: 10,
      awayScore: 13,
      eventId: b!.id,
    },
  ]);
  return { a: a!.id, b: b!.id };
}

describe("datasetFreshness", () => {
  it("reports an empty database as ok", async () => {
    const f = await datasetFreshness(db, NOW);
    expect(f.lineMoves).toMatchObject({ status: "ok", partialImports: 0, finalsWithoutMoves: 0 });
    expect(f.results).toMatchObject({ status: "ok", pastKickoffWithoutScore: 0 });
  });

  it("finds final games without moves even when every job succeeded", async () => {
    const { a } = await seed();
    await db.insert(lineMoves).values({
      eventId: a,
      bookmakerKey: "pinnacle",
      marketType: "spreads",
      changedAt: "2026-10-17T12:00:00Z",
      point: -3,
      price1: -110,
      price2: -110,
      source: "oddspapi",
    });
    await db.insert(ingestionRuns).values({
      jobKey: "oddspapi-moves:x:v2",
      provider: "oddspapi",
      requestType: "historical",
      startedAt: "2026-10-19T08:00:00Z",
      finishedAt: "2026-10-19T08:05:00Z",
      status: "completed",
    });
    const f = await datasetFreshness(db, NOW);
    expect(f.lineMoves).toMatchObject({
      status: "gaps",
      finalsWithoutMoves: 1,
      oldestMissingKickoff: "2026-10-18T17:00:00.000Z",
      latestImportAt: "2026-10-19T08:05:00.000Z",
    });
    // inside the grace window the same game is not yet a gap
    expect(
      (await datasetFreshness(db, new Date("2026-10-19T12:00:00Z"))).lineMoves.finalsWithoutMoves,
    ).toBe(0);
  });

  it("counts partial imports, including pre-ADR-071 completed runs with a too_large issue", async () => {
    await db.insert(ingestionRuns).values([
      {
        jobKey: "oddspapi-moves-ex:a:v1",
        provider: "oddspapi",
        requestType: "historical",
        startedAt: "2026-10-19T08:00:00Z",
        status: "partial",
        issueCounts: { too_large_kalshi: 1 },
      },
      {
        jobKey: "oddspapi-moves-ex:b:v1",
        provider: "oddspapi",
        requestType: "historical",
        startedAt: "2026-10-19T08:00:00Z",
        status: "completed",
        issueCounts: { too_large_kalshi: 1, moves_novig: 4 },
      },
      {
        jobKey: "oddspapi-moves-ex:c:v1",
        provider: "oddspapi",
        requestType: "historical",
        startedAt: "2026-10-19T08:00:00Z",
        status: "completed",
        issueCounts: { moves_novig: 4 },
      },
    ]);
    const f = await datasetFreshness(db, NOW);
    expect(f.lineMoves).toMatchObject({ status: "gaps", partialImports: 2 });
  });

  it("finds games past kickoff without a score", async () => {
    await seed();
    await db
      .update(nflGames)
      .set({ homeScore: null, awayScore: null })
      .where(eq(nflGames.gameId, "2026_07_NE_NYJ"));
    const f = await datasetFreshness(db, NOW);
    expect(f.results).toMatchObject({ status: "gaps", pastKickoffWithoutScore: 1 });
  });
});
