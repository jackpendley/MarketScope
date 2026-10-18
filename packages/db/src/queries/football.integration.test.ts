import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { events, nflGames, nflIngestRuns, nflTeams } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import { footballDataStatus } from "./football";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

const window = { from: "2026-10-01T00:00:00Z", to: "2026-11-01T00:00:00Z", limit: 10 };

describe("footballDataStatus", () => {
  it("reports an empty pipeline without failing", async () => {
    const s = await footballDataStatus(db, window);
    expect(s).toMatchObject({ games: 0, latestRun: null, events: 0, linkedEvents: 0 });
  });

  it("counts games, links, unlinked events, and the latest run", async () => {
    await db.insert(nflTeams).values(
      ["BUF", "MIA"].map((abbr) => ({
        abbr,
        franchise: abbr,
        fullName: abbr,
        nickname: abbr,
        conference: "AFC",
        division: "AFC East",
      })),
    );
    const [linked, unlinked] = await db
      .insert(events)
      .values([
        {
          providerEventId: "e1",
          sportKey: "americanfootball_nfl",
          season: 2026,
          homeTeam: "Buffalo Bills",
          awayTeam: "Miami Dolphins",
          commenceTimeUtc: "2026-10-18T17:00:00Z",
        },
        {
          providerEventId: "e2",
          sportKey: "americanfootball_nfl",
          season: 2026,
          homeTeam: "Springfield",
          awayTeam: "Shelbyville",
          commenceTimeUtc: "2026-10-19T00:20:00Z",
        },
      ])
      .returning({ id: events.id });
    await db.insert(nflGames).values({
      gameId: "2026_07_MIA_BUF",
      season: 2026,
      gameType: "REG",
      week: 7,
      kickoffUtc: "2026-10-18T17:00:00Z",
      homeTeam: "BUF",
      awayTeam: "MIA",
      neutralSite: false,
      divisionGame: true,
      homeScore: 24,
      awayScore: 20,
      eventId: linked!.id,
    });
    await db.insert(nflIngestRuns).values([
      { jobKey: "a", dataset: "schedules", startedAt: "2026-10-17T00:00:00Z", status: "completed" },
      { jobKey: "b", dataset: "schedules", startedAt: "2026-10-18T00:00:00Z", status: "failed" },
    ]);

    const s = await footballDataStatus(db, window);
    expect(s).toMatchObject({
      games: 1,
      finalGames: 1,
      statsGames: 0,
      firstSeason: 2026,
      lastSeason: 2026,
      events: 2,
      linkedEvents: 1,
    });
    expect(s.latestRun).toMatchObject({
      jobKey: "b",
      status: "failed",
      startedAt: "2026-10-18T00:00:00.000Z",
    });
    expect(s.unlinked).toEqual([
      {
        eventId: unlinked!.id,
        homeTeam: "Springfield",
        awayTeam: "Shelbyville",
        commenceTime: "2026-10-19T00:20:00.000Z",
      },
    ]);
  });
});
