import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import {
  events,
  modelPredictions,
  modelRuns,
  nflGames,
  nflInjuryReports,
  nflPlayerGameSnaps,
  nflTeams,
  ratingSnapshots,
} from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import {
  currentWeek,
  forwardTest,
  matchupForEvent,
  matchupsForWeek,
  matchupWeeks,
  modelRunRecords,
} from "./model";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

const team = (abbr: string, franchise = abbr) => ({
  abbr,
  franchise,
  fullName: `Team ${abbr}`,
  nickname: abbr,
  conference: "AFC",
  division: "AFC West",
});

const game = (gameId: string, week: number, kickoff: string, home: string, away: string) => ({
  gameId,
  season: 2026,
  gameType: "REG",
  week,
  kickoffUtc: kickoff,
  homeTeam: home,
  awayTeam: away,
  neutralSite: false,
  divisionGame: true,
});

const snapshot = (week: number, teamAbbr: string, adjEm: number, rank: number) => ({
  modelVersion: "ratings-v1",
  season: 2026,
  week,
  team: teamAbbr,
  adjEm,
  adjEmSe: 2,
  adjEmRank: rank,
  adjO: 2,
  adjOSe: 0.1,
  adjORank: rank,
  adjD: 2,
  adjDSe: 0.1,
  adjDRank: rank,
  adjSt: 0,
  adjStSe: 0.3,
  adjStRank: rank,
  adjPace: 11,
  adjPaceSe: 0.2,
  adjPaceRank: rank,
  priorWeight: 0.8,
  passOff: 0,
  passDef: 0,
  rushOff: 0,
  rushDef: 0,
  succOff: 0,
  succDef: 0,
  ppdOff: 0,
  ppdDef: 0,
  games: week,
  wins: 0,
  losses: 0,
  ties: 0,
  pointsFor: 0,
  pointsAgainst: 0,
  expectedWins: 0,
  pythagWins: 0,
  luck: 0,
  luckRank: rank,
  oneScoreLuck: 0,
  fumbleLuck: 0,
  intLuck: 0,
  fgLuck: 0,
  returnTdDiff: 0,
  remainingGames: 17 - week,
});

const estimate = (gameId: string, predictedAt: string, kickoff: string, margin: number) => ({
  modelVersion: "ratings-v1",
  gameId,
  predictedAt,
  kickoffUtc: kickoff,
  homeTeam: "KC",
  awayTeam: "LV",
  expectedMargin: margin,
  expectedTotal: 46,
  homeScore: (46 + margin) / 2,
  awayScore: (46 - margin) / 2,
  pHome: 0.5 + margin / 30,
  homeQb: "00-0033873",
  awayQb: "00-0099999",
  homeQbP: 1,
  awayQbP: 0.64,
  contributions: { ratings: margin - 0.3, home: 0.3, qb: 0, absences: 0 },
});

async function seed() {
  await db.insert(nflTeams).values([team("KC"), team("LV"), team("OAK", "LV")]);
  const [event] = await db
    .insert(events)
    .values({
      providerEventId: "evt-2",
      sportKey: "americanfootball_nfl",
      season: 2026,
      homeTeam: "Team KC",
      awayTeam: "Team LV",
      commenceTimeUtc: "2026-09-20T17:00:00Z",
    })
    .returning({ id: events.id });
  await db.insert(nflGames).values([
    {
      ...game("2026_01_KC_OAK", 1, "2026-09-13T20:25:00Z", "OAK", "KC"),
      homeScore: 10,
      awayScore: 24,
      nflverseCloseHomeSpread: 3.5,
      nflverseCloseTotal: 47.5,
      nflverseCloseHomeMoneyline: 150,
      nflverseCloseAwayMoneyline: -175,
    },
    { ...game("2026_02_LV_KC", 2, "2026-09-20T17:00:00Z", "KC", "LV"), eventId: event!.id },
  ]);
  await db
    .insert(ratingSnapshots)
    .values([snapshot(0, "KC", 4, 1), snapshot(0, "LV", -4, 2), snapshot(1, "KC", 5, 1)]);
  await db
    .insert(modelPredictions)
    .values([
      estimate("2026_01_KC_OAK", "2026-09-12T13:00:00Z", "2026-09-13T20:25:00Z", -3),
      estimate("2026_01_KC_OAK", "2026-09-13T13:00:00Z", "2026-09-13T20:25:00Z", -4),
      estimate("2026_02_LV_KC", "2026-09-19T13:00:00Z", "2026-09-20T17:00:00Z", 5),
    ]);
  await db.insert(nflPlayerGameSnaps).values([
    {
      gameId: "2026_01_KC_OAK",
      season: 2026,
      week: 1,
      pfrPlayerId: "MahoPa00",
      gsisId: "00-0033873",
      player: "Patrick Mahomes",
      position: "QB",
      team: "KC",
      offenseSnaps: 60,
      defenseSnaps: 0,
      stSnaps: 0,
    },
  ]);
  await db.insert(nflInjuryReports).values({
    season: 2026,
    week: 2,
    gameType: "REG",
    team: "LV",
    gsisId: "00-0099999",
    fullName: "Rookie Quarterback",
    position: "QB",
    reportStatus: "Questionable",
    contentHash: "x",
  });
}

describe("model queries", () => {
  it("returns a week's games with pre-game ratings and the last estimate before kickoff", async () => {
    await seed();
    const [m] = await matchupsForWeek(db, { version: "ratings-v1", season: 2026, week: 1 });
    expect(m).toMatchObject({
      homeTeam: "LV", // OAK resolves to the franchise
      awayTeam: "KC",
      homeFinal: 10,
      awayFinal: 24,
      closeHomeSpread: 3.5,
      homeRank: 2,
      awayRank: 1,
      awayAdjEm: 4,
      teams: 2,
    });
    expect(m!.estimate).toMatchObject({
      expectedMargin: -4, // the later of the two estimates
      homeQb: "Patrick Mahomes", // name from snap counts
      awayQb: "Rookie Quarterback", // falls back to the injury report
      contributions: { ratings: -4.3, home: 0.3, qb: 0, absences: 0 },
    });
  });

  it("finds the matchup for a linked odds event, using the latest earlier snapshot", async () => {
    await seed();
    const [{ id }] = (await sql`SELECT id FROM events`) as unknown as [{ id: string }];
    const m = await matchupForEvent(db, { version: "ratings-v1", eventId: id });
    expect(m).toMatchObject({ gameId: "2026_02_LV_KC", homeAdjEm: 5, teams: 1, awayRank: null });
    expect(m!.estimate!.expectedMargin).toBe(5);
    expect(
      await matchupForEvent(db, {
        version: "ratings-v1",
        eventId: "00000000-0000-0000-0000-000000000000",
      }),
    ).toBeNull();
  });

  it("lists forward-test weeks and the current week", async () => {
    await seed();
    expect(await matchupWeeks(db, "ratings-v1")).toEqual([
      { season: 2026, week: 1 },
      { season: 2026, week: 2 },
    ]);
    expect(await currentWeek(db, "2026-09-18T00:00:00Z")).toEqual({ season: 2026, week: 2 });
    expect(await currentWeek(db, "2026-12-01T00:00:00Z")).toBeNull();
  });

  it("scores final games and counts pending ones", async () => {
    await seed();
    const ft = await forwardTest(db, "ratings-v1");
    expect(ft.pending).toBe(1);
    expect(ft.firstPredictedAt).toBe("2026-09-12T13:00:00.000Z");
    expect(ft.scored).toHaveLength(1);
    expect(ft.scored[0]).toMatchObject({
      gameId: "2026_01_KC_OAK",
      expectedMargin: -4,
      homeFinal: 10,
      closeHomeSpread: 3.5,
      closeHomeMoneyline: 150,
    });
  });

  it("returns evaluation records, the test run first", async () => {
    await seed();
    await db.insert(modelRuns).values([
      {
        modelVersion: "ratings-v1",
        runKind: "validation",
        seasons: "2023-2024",
        games: 570,
        metrics: { "ratings-v1": { margin_mae: 10.27 } },
        paramsSha256: "abc",
        codeSha: "def",
        ranAt: "2026-10-17T00:00:00Z",
      },
      {
        modelVersion: "ratings-v1",
        runKind: "test",
        seasons: "2025",
        games: 285,
        metrics: { "ratings-v1": { margin_mae: 10.06 } },
        paramsSha256: "abc",
        codeSha: "def",
        ranAt: "2026-10-16T00:00:00Z",
      },
    ]);
    const runs = await modelRunRecords(db, "ratings-v1");
    expect(runs.map((r) => r.runKind)).toEqual(["test", "validation"]);
    expect(runs[0]!.metrics["ratings-v1"]).toEqual({ margin_mae: 10.06 });
  });
});
