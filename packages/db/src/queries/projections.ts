// Season projections (MS-034): simulated playoff, division, #1-seed, conference and Super Bowl odds
// written by apps/football (`ingest projections`, ADR-042). Model estimates; this module only reads.

import { sql } from "drizzle-orm";
import type { Database } from "../client";
import type { RatingWeek } from "./ratings";

export type ProjectionRow = {
  team: string;
  fullName: string;
  conference: string;
  division: string;
  sims: number;
  gamesPlayed: number;
  strength: number;
  meanWins: number;
  winDist: number[];
  playoffP: number;
  divisionP: number;
  seed1P: number;
  confP: number;
  sbP: number;
  /** Record and rating from the rating snapshot of the same week (null if missing). */
  wins: number | null;
  losses: number | null;
  ties: number | null;
  adjEm: number | null;
  adjEmRank: number | null;
};

/** Every (season, week) with projections for a version, oldest first. */
export async function projectionWeeks(db: Database, version: string): Promise<RatingWeek[]> {
  const rows = await db.execute<{ season: number; week: number }>(sql`
    SELECT DISTINCT season, week FROM season_projections WHERE model_version = ${version}
    ORDER BY season, week
  `);
  return rows.map((r) => ({ season: r.season, week: r.week }));
}

/** All teams' projections after one week, best playoff odds first. */
export async function projectionsForWeek(
  db: Database,
  { version, season, week }: { version: string } & RatingWeek,
): Promise<ProjectionRow[]> {
  return db.execute<ProjectionRow>(sql`
    SELECT p.team, t.full_name AS "fullName", t.conference, t.division, p.sims,
           p.games_played AS "gamesPlayed", p.strength, p.mean_wins AS "meanWins", p.win_dist AS "winDist",
           p.playoff_p AS "playoffP", p.division_p AS "divisionP", p.seed1_p AS "seed1P",
           p.conf_p AS "confP", p.sb_p AS "sbP",
           r.wins, r.losses, r.ties, r.adj_em AS "adjEm", r.adj_em_rank AS "adjEmRank"
    FROM season_projections p
    JOIN nfl_teams t ON t.abbr = p.team
    LEFT JOIN rating_snapshots r ON r.model_version = p.model_version AND r.season = p.season
      AND r.week = p.week AND r.team = p.team
    WHERE p.model_version = ${version} AND p.season = ${season} AND p.week = ${week}
    ORDER BY p.playoff_p DESC, p.mean_wins DESC, p.team
  `);
}

export type ProjectionHistoryRow = {
  week: number;
  meanWins: number;
  winDist: number[];
  playoffP: number;
  divisionP: number;
  seed1P: number;
  confP: number;
  sbP: number;
};

/** One team's projections through a season (odds trend), oldest first. */
export async function teamProjectionHistory(
  db: Database,
  { version, team, season }: { version: string; team: string; season: number },
): Promise<ProjectionHistoryRow[]> {
  return db.execute<ProjectionHistoryRow>(sql`
    SELECT week, mean_wins AS "meanWins", win_dist AS "winDist", playoff_p AS "playoffP",
           division_p AS "divisionP", seed1_p AS "seed1P", conf_p AS "confP", sb_p AS "sbP"
    FROM season_projections
    WHERE model_version = ${version} AND team = ${team} AND season = ${season}
    ORDER BY week
  `);
}
