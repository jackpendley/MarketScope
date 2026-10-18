// Model estimates for the Matchups page, the game-page panel and the live scorecard (MS-033b). The
// estimates are written once, before kickoff, by apps/football (ADR-039); this module only reads
// them. "Last estimate" always means the newest row created before kickoff.

import { sql, type SQL } from "drizzle-orm";
import type { Database } from "../client";
import type { RatingWeek } from "./ratings";

const iso = (col: string) =>
  sql.raw(`to_char(${col} AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`);

export type ModelEstimate = {
  predictedAt: string;
  /** Expected home margin (points); positive = home team favored. */
  expectedMargin: number;
  expectedTotal: number | null;
  homeScore: number | null;
  awayScore: number | null;
  pHome: number;
  /** Expected starting QBs by name (null when unknown) and the probability each plays. */
  homeQb: string | null;
  awayQb: string | null;
  homeQbP: number | null;
  awayQbP: number | null;
  /** Additive margin contributions, home perspective: ratings, home, qb, absences. */
  contributions: Record<string, number>;
};

export type Matchup = {
  gameId: string;
  season: number;
  week: number;
  gameType: string;
  kickoffUtc: string;
  neutralSite: boolean;
  divisionGame: boolean;
  /** Franchise abbreviations (historical codes such as OAK resolve to LV) and full names. */
  homeTeam: string;
  awayTeam: string;
  homeName: string;
  awayName: string;
  /** Final score, null until the game is final. */
  homeFinal: number | null;
  awayFinal: number | null;
  /** The linked odds event (null when unlinked). */
  eventId: string | null;
  /** nflverse closing line, home orientation (negative = home favored). A labeled benchmark. */
  closeHomeSpread: number | null;
  closeTotal: number | null;
  /** Each team's AdjEM and rank in the last snapshot before the game, of `teams` ranked. */
  homeAdjEm: number | null;
  homeRank: number | null;
  awayAdjEm: number | null;
  awayRank: number | null;
  teams: number | null;
  estimate: ModelEstimate | null;
};

type MatchupSqlRow = Omit<Matchup, "estimate"> & {
  predictedAt: string | null;
  expectedMargin: number | null;
  expectedTotal: number | null;
  homeScore: number | null;
  awayScore: number | null;
  pHome: number | null;
  homeQb: string | null;
  awayQb: string | null;
  homeQbP: number | null;
  awayQbP: number | null;
  contributions: Record<string, number> | null;
};

/** A QB's display name: latest snap-count row, else any injury-report row. */
const qbName = (col: string) =>
  sql.raw(`COALESCE(
    (SELECT s.player FROM nfl_player_game_snaps s WHERE s.gsis_id = ${col} ORDER BY s.season DESC, s.week DESC LIMIT 1),
    (SELECT i.full_name FROM nfl_injury_reports i WHERE i.gsis_id = ${col} ORDER BY i.season DESC LIMIT 1))`);

function matchupSql(version: string, where: SQL): SQL {
  return sql`
    SELECT g.game_id AS "gameId", g.season, g.week, g.game_type AS "gameType",
           ${iso("g.kickoff_utc")} AS "kickoffUtc", g.neutral_site AS "neutralSite",
           g.division_game AS "divisionGame",
           ht.franchise AS "homeTeam", aw.franchise AS "awayTeam",
           ht.full_name AS "homeName", aw.full_name AS "awayName",
           g.home_score AS "homeFinal", g.away_score AS "awayFinal", g.event_id AS "eventId",
           g.nflverse_close_home_spread::float8 AS "closeHomeSpread",
           g.nflverse_close_total::float8 AS "closeTotal",
           hr.adj_em AS "homeAdjEm", hr.adj_em_rank AS "homeRank",
           ar.adj_em AS "awayAdjEm", ar.adj_em_rank AS "awayRank", rw.teams,
           ${iso("p.predicted_at")} AS "predictedAt", p.expected_margin AS "expectedMargin",
           p.expected_total AS "expectedTotal", p.home_score AS "homeScore", p.away_score AS "awayScore",
           p.p_home AS "pHome", ${qbName("p.home_qb")} AS "homeQb", ${qbName("p.away_qb")} AS "awayQb",
           p.home_qb_p AS "homeQbP", p.away_qb_p AS "awayQbP", p.contributions
    FROM nfl_games g
    JOIN nfl_teams ht ON ht.abbr = g.home_team
    JOIN nfl_teams aw ON aw.abbr = g.away_team
    LEFT JOIN LATERAL (
      SELECT r.week, count(*)::int AS teams FROM rating_snapshots r
      WHERE r.model_version = ${version} AND r.season = g.season AND r.week < g.week
      GROUP BY r.week ORDER BY r.week DESC LIMIT 1
    ) rw ON true
    LEFT JOIN rating_snapshots hr ON hr.model_version = ${version} AND hr.season = g.season
      AND hr.week = rw.week AND hr.team = ht.franchise
    LEFT JOIN rating_snapshots ar ON ar.model_version = ${version} AND ar.season = g.season
      AND ar.week = rw.week AND ar.team = aw.franchise
    LEFT JOIN LATERAL (
      SELECT * FROM model_predictions mp
      WHERE mp.model_version = ${version} AND mp.game_id = g.game_id AND mp.predicted_at < mp.kickoff_utc
      ORDER BY mp.predicted_at DESC LIMIT 1
    ) p ON true
    WHERE ${where}
    ORDER BY g.kickoff_utc, g.game_id
  `;
}

function toMatchup(r: MatchupSqlRow): Matchup {
  const {
    predictedAt,
    expectedMargin,
    expectedTotal,
    homeScore,
    awayScore,
    pHome,
    homeQb,
    awayQb,
    homeQbP,
    awayQbP,
    contributions,
    ...game
  } = r;
  return {
    ...game,
    estimate:
      predictedAt !== null && expectedMargin !== null && pHome !== null
        ? {
            predictedAt,
            expectedMargin,
            expectedTotal,
            homeScore,
            awayScore,
            pHome,
            homeQb,
            awayQb,
            homeQbP,
            awayQbP,
            contributions: contributions ?? {},
          }
        : null,
  };
}

/**
 * Weeks the Matchups page offers: every week of every season from the first season with a stored
 * estimate (the forward test), or the latest season when there are none yet.
 */
export async function matchupWeeks(db: Database, version: string): Promise<RatingWeek[]> {
  const rows = await db.execute<{ season: number; week: number }>(sql`
    SELECT DISTINCT season, week FROM nfl_games
    WHERE season >= COALESCE(
      (SELECT min(g.season) FROM model_predictions mp JOIN nfl_games g USING (game_id)
        WHERE mp.model_version = ${version}),
      (SELECT max(season) FROM nfl_games))
    ORDER BY season, week
  `);
  return rows.map((r) => ({ season: r.season, week: r.week }));
}

/** The week of the next game that isn't final (kicking off after `now` minus 18 h), if any. */
export async function currentWeek(db: Database, now: string): Promise<RatingWeek | null> {
  const [row] = await db.execute<{ season: number; week: number }>(sql`
    SELECT season, week FROM nfl_games
    WHERE home_score IS NULL AND kickoff_utc > ${now}::timestamptz - interval '18 hours'
    ORDER BY kickoff_utc LIMIT 1
  `);
  return row ? { season: row.season, week: row.week } : null;
}

/** One week's games with pre-game ratings and the last model estimate before kickoff. */
export async function matchupsForWeek(
  db: Database,
  { version, season, week }: { version: string } & RatingWeek,
): Promise<Matchup[]> {
  const rows = await db.execute<MatchupSqlRow>(
    matchupSql(version, sql`g.season = ${season} AND g.week = ${week}`),
  );
  return rows.map(toMatchup);
}

/** The matchup for the football game linked to an odds event (game page panel). */
export async function matchupForEvent(
  db: Database,
  { version, eventId }: { version: string; eventId: string },
): Promise<Matchup | null> {
  const [row] = await db.execute<MatchupSqlRow>(matchupSql(version, sql`g.event_id = ${eventId}`));
  return row ? toMatchup(row) : null;
}

export type ScoredEstimate = {
  gameId: string;
  season: number;
  week: number;
  kickoffUtc: string;
  homeTeam: string;
  awayTeam: string;
  homeFinal: number;
  awayFinal: number;
  predictedAt: string;
  expectedMargin: number;
  expectedTotal: number | null;
  pHome: number;
  closeHomeSpread: number | null;
  closeTotal: number | null;
  closeHomeMoneyline: number | null;
  closeAwayMoneyline: number | null;
};

export type ForwardTest = {
  /** Final games with a stored estimate, oldest first. */
  scored: ScoredEstimate[];
  /** Games with an estimate that aren't final yet. */
  pending: number;
  firstPredictedAt: string | null;
};

/** The live forward test: each game's last estimate before kickoff, joined to its result. */
export async function forwardTest(db: Database, version: string): Promise<ForwardTest> {
  const scored = await db.execute<ScoredEstimate>(sql`
    WITH last AS (
      SELECT DISTINCT ON (game_id) * FROM model_predictions
      WHERE model_version = ${version} AND predicted_at < kickoff_utc
      ORDER BY game_id, predicted_at DESC
    )
    SELECT g.game_id AS "gameId", g.season, g.week, ${iso("g.kickoff_utc")} AS "kickoffUtc",
           ht.franchise AS "homeTeam", aw.franchise AS "awayTeam",
           g.home_score AS "homeFinal", g.away_score AS "awayFinal",
           ${iso("p.predicted_at")} AS "predictedAt", p.expected_margin AS "expectedMargin",
           p.expected_total AS "expectedTotal", p.p_home AS "pHome",
           g.nflverse_close_home_spread::float8 AS "closeHomeSpread",
           g.nflverse_close_total::float8 AS "closeTotal",
           g.nflverse_close_home_moneyline AS "closeHomeMoneyline",
           g.nflverse_close_away_moneyline AS "closeAwayMoneyline"
    FROM last p
    JOIN nfl_games g ON g.game_id = p.game_id
    JOIN nfl_teams ht ON ht.abbr = g.home_team
    JOIN nfl_teams aw ON aw.abbr = g.away_team
    WHERE g.home_score IS NOT NULL
    ORDER BY g.kickoff_utc, g.game_id
  `);
  const [meta] = await db.execute<{ pending: number; first: string | null }>(sql`
    SELECT count(DISTINCT mp.game_id) FILTER (WHERE g.home_score IS NULL)::int AS pending,
           ${iso("min(mp.predicted_at)")} AS first
    FROM model_predictions mp JOIN nfl_games g ON g.game_id = mp.game_id
    WHERE mp.model_version = ${version}
  `);
  return { scored, pending: meta?.pending ?? 0, firstPredictedAt: meta?.first ?? null };
}

export type ModelRunRecord = {
  runKind: string;
  seasons: string;
  games: number;
  /** Per-model metrics with CIs, keyed by model name, plus extras (as written by apps/football). */
  metrics: Record<string, unknown>;
  paramsSha256: string;
  codeSha: string;
  notes: string | null;
  ranAt: string;
};

/** Committed evaluation records for a version (the one-time 2025 test first). */
export async function modelRunRecords(db: Database, version: string): Promise<ModelRunRecord[]> {
  return db.execute<ModelRunRecord>(sql`
    SELECT run_kind AS "runKind", seasons, games, metrics, params_sha256 AS "paramsSha256",
           code_sha AS "codeSha", notes, ${iso("ran_at")} AS "ranAt"
    FROM model_runs WHERE model_version = ${version}
    ORDER BY array_position(ARRAY['test', 'validation', 'forward'], run_kind), ran_at DESC
  `);
}
