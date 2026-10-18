// Football-data status (MS-026): what the nflverse pipeline has loaded and how well odds
// events link to football games. Counts and names only.

import { sql } from "drizzle-orm";
import type { Database } from "../client";

export interface FootballIngestRun {
  jobKey: string;
  dataset: string;
  status: string;
  startedAt: string;
  finishedAt: string | null;
  rowsUpserted: number;
  sourceVersion: string | null;
}

export interface UnlinkedEvent {
  eventId: string;
  homeTeam: string;
  awayTeam: string;
  commenceTime: string;
}

export interface FootballDataStatus {
  games: number;
  finalGames: number;
  /** Final games that have team-game stats (both teams' rows) from play-by-play. */
  statsGames: number;
  /** Injury-report rows, and how many were first seen live (before kickoff) by our job. */
  injuryRows: number;
  liveInjuryRows: number;
  snapRows: number;
  firstSeason: number | null;
  lastSeason: number | null;
  latestRun: FootballIngestRun | null;
  /** Odds events kicking off in [from, to) and how many are linked to an nflverse game. */
  events: number;
  linkedEvents: number;
  unlinked: UnlinkedEvent[];
}

const iso = (col: string) =>
  sql.raw(`to_char(${col} AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`);

export async function footballDataStatus(
  db: Database,
  { from, to, limit }: { from: string; to: string; limit: number },
): Promise<FootballDataStatus> {
  const [totals] = await db.execute<{
    games: number;
    final_games: number;
    stats_games: number;
    injury_rows: number;
    live_injury_rows: number;
    snap_rows: number;
    first_season: number | null;
    last_season: number | null;
  }>(sql`
    SELECT count(*)::int AS games, count(home_score)::int AS final_games,
           (SELECT count(DISTINCT game_id)::int FROM nfl_team_game_stats) AS stats_games,
           (SELECT count(*)::int FROM nfl_injury_reports) AS injury_rows,
           (SELECT count(first_seen_at)::int FROM nfl_injury_reports) AS live_injury_rows,
           (SELECT count(*)::int FROM nfl_player_game_snaps) AS snap_rows,
           min(season) AS first_season, max(season) AS last_season
    FROM nfl_games
  `);
  const runs = await db.execute<{
    job_key: string;
    dataset: string;
    status: string;
    started_at: string;
    finished_at: string | null;
    rows_upserted: number;
    source_version: string | null;
  }>(sql`
    SELECT job_key, dataset, status::text, ${iso("started_at")} AS started_at,
           ${iso("finished_at")} AS finished_at, rows_upserted, source_version
    FROM nfl_ingest_runs ORDER BY started_at DESC LIMIT 1
  `);
  const [links] = await db.execute<{ events: number; linked: number }>(sql`
    SELECT count(*)::int AS events, count(g.game_id)::int AS linked
    FROM events e LEFT JOIN nfl_games g ON g.event_id = e.id
    WHERE e.commence_time_utc >= ${from} AND e.commence_time_utc < ${to}
  `);
  const unlinked = await db.execute<{
    event_id: string;
    home_team: string;
    away_team: string;
    commence_time: string;
  }>(sql`
    SELECT e.id AS event_id, e.home_team, e.away_team, ${iso("e.commence_time_utc")} AS commence_time
    FROM events e LEFT JOIN nfl_games g ON g.event_id = e.id
    WHERE g.game_id IS NULL AND e.commence_time_utc >= ${from} AND e.commence_time_utc < ${to}
    ORDER BY e.commence_time_utc DESC
    LIMIT ${limit}
  `);
  const run = runs[0];
  return {
    games: totals?.games ?? 0,
    finalGames: totals?.final_games ?? 0,
    statsGames: totals?.stats_games ?? 0,
    injuryRows: totals?.injury_rows ?? 0,
    liveInjuryRows: totals?.live_injury_rows ?? 0,
    snapRows: totals?.snap_rows ?? 0,
    firstSeason: totals?.first_season ?? null,
    lastSeason: totals?.last_season ?? null,
    latestRun: run
      ? {
          jobKey: run.job_key,
          dataset: run.dataset,
          status: run.status,
          startedAt: run.started_at,
          finishedAt: run.finished_at,
          rowsUpserted: run.rows_upserted,
          sourceVersion: run.source_version,
        }
      : null,
    events: links?.events ?? 0,
    linkedEvents: links?.linked ?? 0,
    unlinked: unlinked.map((r) => ({
      eventId: r.event_id,
      homeTeam: r.home_team,
      awayTeam: r.away_team,
      commenceTime: r.commence_time,
    })),
  };
}
