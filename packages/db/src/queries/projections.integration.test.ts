import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { nflTeams, seasonProjections } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import { projectionsForWeek, projectionWeeks, teamProjectionHistory } from "./projections";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

const projection = (team: string, week: number, playoffP: number) => ({
  modelVersion: "ratings-v1",
  season: 2026,
  week,
  team,
  sims: 10000,
  gamesPlayed: week * 16,
  strength: playoffP * 10 - 5,
  meanWins: 8 + playoffP * 4,
  winDist: Array.from({ length: 18 }, (_, k) => (k === 9 ? 1 : 0)),
  playoffP,
  divisionP: playoffP / 2,
  seed1P: playoffP / 5,
  confP: playoffP / 8,
  sbP: playoffP / 16,
});

describe("projection queries", () => {
  it("lists weeks, ranks a week by playoff odds and returns a team's trend", async () => {
    await db.insert(nflTeams).values(
      ["KC", "LV"].map((abbr) => ({
        abbr,
        franchise: abbr,
        fullName: `Team ${abbr}`,
        nickname: abbr,
        conference: "AFC",
        division: "AFC West",
      })),
    );
    await db
      .insert(seasonProjections)
      .values([
        projection("KC", 0, 0.6),
        projection("LV", 0, 0.3),
        projection("KC", 1, 0.7),
        projection("LV", 1, 0.2),
      ]);
    expect(await projectionWeeks(db, "ratings-v1")).toEqual([
      { season: 2026, week: 0 },
      { season: 2026, week: 1 },
    ]);
    const rows = await projectionsForWeek(db, { version: "ratings-v1", season: 2026, week: 1 });
    expect(rows.map((r) => [r.team, r.playoffP, r.fullName])).toEqual([
      ["KC", 0.7, "Team KC"],
      ["LV", 0.2, "Team LV"],
    ]);
    expect(rows[0]!.winDist[9]).toBe(1);
    expect(rows[0]!.wins).toBeNull(); // no rating snapshot in this test
    const history = await teamProjectionHistory(db, {
      version: "ratings-v1",
      team: "LV",
      season: 2026,
    });
    expect(history.map((h) => [h.week, h.playoffP])).toEqual([
      [0, 0.3],
      [1, 0.2],
    ]);
  });
});
