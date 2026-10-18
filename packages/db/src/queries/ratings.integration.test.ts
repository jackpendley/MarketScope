import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { modelPredictions, nflCoachingStaff, nflGames, nflTeams, ratingSnapshots } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import {
  ratingsForWeek,
  ratingVersion,
  ratingWeeks,
  teamGames,
  teamRatingHistory,
  teamStaff,
} from "./ratings";

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

function snapshot(version: string, season: number, week: number, teamAbbr: string, rank: number) {
  return {
    modelVersion: version,
    season,
    week,
    team: teamAbbr,
    adjEm: 5 - rank,
    adjEmSe: 2,
    adjEmRank: rank,
    adjO: 2.2,
    adjOSe: 0.1,
    adjORank: rank,
    adjD: 2.0,
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
    wins: week,
    losses: 0,
    ties: 0,
    pointsFor: 20 * week,
    pointsAgainst: 10 * week,
    expectedWins: week * 0.8,
    pythagWins: week * 0.9,
    luck: week * 0.2,
    luckRank: rank,
    oneScoreLuck: 0,
    fumbleLuck: 0,
    intLuck: 0,
    fgLuck: 0,
    returnTdDiff: 0,
    remainingGames: 17 - week,
  };
}

async function seed() {
  await db.insert(nflTeams).values([team("KC"), team("LV"), team("OAK", "LV")]);
  await db.insert(nflGames).values([
    {
      gameId: "2019_01_KC_OAK",
      season: 2019,
      gameType: "REG",
      week: 1,
      kickoffUtc: "2019-09-08T20:25:00Z",
      homeTeam: "OAK",
      awayTeam: "KC",
      neutralSite: false,
      divisionGame: true,
      homeScore: 10,
      awayScore: 28,
    },
    {
      gameId: "2019_02_OAK_KC",
      season: 2019,
      gameType: "REG",
      week: 2,
      kickoffUtc: "2019-09-15T17:00:00Z",
      homeTeam: "KC",
      awayTeam: "OAK",
      neutralSite: false,
      divisionGame: true,
    },
  ]);
  await db
    .insert(ratingSnapshots)
    .values([
      snapshot("ratings-v1", 2019, 0, "KC", 1),
      snapshot("ratings-v1", 2019, 0, "LV", 2),
      snapshot("ratings-v1", 2019, 1, "KC", 1),
      snapshot("ratings-v1", 2019, 1, "LV", 2),
      snapshot("synthetic-demo", 2019, 1, "KC", 2),
    ]);
  await db.insert(modelPredictions).values([
    {
      modelVersion: "ratings-v1",
      gameId: "2019_02_OAK_KC",
      predictedAt: "2019-09-14T13:00:00Z",
      kickoffUtc: "2019-09-15T17:00:00Z",
      homeTeam: "KC",
      awayTeam: "LV",
      expectedMargin: 4,
      expectedTotal: 48,
      homeScore: 26,
      awayScore: 22,
      pHome: 0.62,
      contributions: { ratings: 3.7, home: 0.3 },
    },
    {
      modelVersion: "ratings-v1",
      gameId: "2019_02_OAK_KC",
      predictedAt: "2019-09-15T13:00:00Z",
      kickoffUtc: "2019-09-15T17:00:00Z",
      homeTeam: "KC",
      awayTeam: "LV",
      expectedMargin: 6,
      expectedTotal: 50,
      homeScore: 28,
      awayScore: 22,
      pHome: 0.68,
      contributions: { ratings: 5.7, home: 0.3 },
    },
  ]);
  await db.insert(nflCoachingStaff).values([
    {
      season: 2019,
      team: "OAK",
      role: "OC",
      coachId: "Greg_Olson",
      coachName: "Greg Olson",
      fromWeek: 1,
      toWeek: 17,
      offensePlaycaller: false,
      defensePlaycaller: false,
    },
    {
      season: 2019,
      team: "OAK",
      role: "HC",
      coachId: "Jon_Gruden",
      coachName: "Jon Gruden",
      fromWeek: 1,
      toWeek: 17,
      offensePlaycaller: true,
      defensePlaycaller: false,
    },
  ]);
}

describe("ratings queries", () => {
  it("returns nothing on an empty database", async () => {
    expect(await ratingVersion(db)).toBeNull();
  });

  it("prefers the frozen model version and lists its weeks", async () => {
    await seed();
    expect(await ratingVersion(db)).toBe("ratings-v1");
    expect(await ratingWeeks(db, "ratings-v1")).toEqual([
      { season: 2019, week: 0 },
      { season: 2019, week: 1 },
    ]);
  });

  it("returns a week's table ranked, with team names", async () => {
    await seed();
    const rows = await ratingsForWeek(db, { version: "ratings-v1", season: 2019, week: 1 });
    expect(rows.map((r) => [r.team, r.adjEmRank, r.fullName])).toEqual([
      ["KC", 1, "Team KC"],
      ["LV", 2, "Team LV"],
    ]);
    expect(rows[0]).toMatchObject({ wins: 1, sos: null, remainingGames: 16 });
    const history = await teamRatingHistory(db, {
      version: "ratings-v1",
      team: "LV",
      season: 2019,
    });
    expect(history.map((h) => h.week)).toEqual([0, 1]);
  });

  it("resolves historical abbreviations and uses the last estimate before kickoff", async () => {
    await seed();
    const games = await teamGames(db, { version: "ratings-v1", team: "LV", season: 2019 });
    expect(games).toHaveLength(2);
    expect(games[0]).toMatchObject({
      week: 1,
      isHome: true,
      opponent: "KC",
      teamScore: 10,
      opponentScore: 28,
      opponentRankThen: 1, // KC in the preseason snapshot (week 0 < week 1)
      opponentRankNow: 1,
      modelMargin: null,
    });
    expect(games[1]).toMatchObject({
      week: 2,
      isHome: false,
      teamScore: null,
      modelMargin: -6, // the later of the two estimates, from LV's side
      modelTeamScore: 22,
      modelOpponentScore: 28,
    });
    expect(games[1]!.modelWinProb).toBeCloseTo(0.32);
  });

  it("lists the staff for the franchise, head coach first", async () => {
    await seed();
    const staff = await teamStaff(db, { team: "LV", season: 2019 });
    expect(staff.map((s) => [s.role, s.coachName, s.offensePlaycaller])).toEqual([
      ["HC", "Jon Gruden", true],
      ["OC", "Greg Olson", false],
    ]);
  });
});
