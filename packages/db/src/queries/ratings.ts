// MarketScope Ratings (MS-033): the KenPom contract snapshots, team history, schedules with model
// estimates, coaching staff, and the live forward test. All values are model estimates written by
// apps/football (ADR-035/039); this module only reads them.

import { sql } from "drizzle-orm";
import type { Database } from "../client";

const iso = (col: string) =>
  sql.raw(`to_char(${col} AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`);

/** The frozen production model; other versions (e.g. a synthetic demo seed) are shown only if it is absent. */
export const DEFAULT_MODEL_VERSION = "ratings-v1";

export interface RatingWeek {
  season: number;
  week: number;
}

export type RatingRow = {
  team: string;
  fullName: string;
  conference: string;
  division: string;
  adjEm: number;
  adjEmSe: number;
  adjEmRank: number;
  adjO: number;
  adjOSe: number;
  adjORank: number;
  adjD: number;
  adjDSe: number;
  adjDRank: number;
  adjSt: number;
  adjStRank: number;
  adjPace: number;
  adjPaceRank: number;
  priorWeight: number;
  games: number;
  wins: number;
  losses: number;
  ties: number;
  pointsFor: number;
  pointsAgainst: number;
  expectedWins: number;
  pythagWins: number;
  luck: number;
  luckRank: number;
  oneScoreLuck: number;
  fumbleLuck: number;
  intLuck: number;
  fgLuck: number;
  returnTdDiff: number;
  sos: number | null;
  sosRank: number | null;
  oppAdjO: number | null;
  oppAdjD: number | null;
  nondivSos: number | null;
  remainingSos: number | null;
  remainingGames: number;
  passOff: number;
  passDef: number;
  rushOff: number;
  rushDef: number;
  offSuccessRate: number | null;
  defSuccessRate: number | null;
  offExplosiveness: number | null;
  defExplosiveness: number | null;
  offStartYardline: number | null;
  defStartYardline: number | null;
  offPointsPerOpp: number | null;
  defPointsPerOpp: number | null;
  offTurnovers: number | null;
  defTurnovers: number | null;
};

const RATING_COLUMNS = sql.raw(`
  r.team, t.full_name AS "fullName", t.conference, t.division,
  r.adj_em AS "adjEm", r.adj_em_se AS "adjEmSe", r.adj_em_rank AS "adjEmRank",
  r.adj_o AS "adjO", r.adj_o_se AS "adjOSe", r.adj_o_rank AS "adjORank",
  r.adj_d AS "adjD", r.adj_d_se AS "adjDSe", r.adj_d_rank AS "adjDRank",
  r.adj_st AS "adjSt", r.adj_st_rank AS "adjStRank", r.adj_pace AS "adjPace", r.adj_pace_rank AS "adjPaceRank",
  r.prior_weight AS "priorWeight", r.games, r.wins, r.losses, r.ties,
  r.points_for AS "pointsFor", r.points_against AS "pointsAgainst",
  r.expected_wins AS "expectedWins", r.pythag_wins AS "pythagWins", r.luck, r.luck_rank AS "luckRank",
  r.one_score_luck AS "oneScoreLuck", r.fumble_luck AS "fumbleLuck", r.int_luck AS "intLuck",
  r.fg_luck AS "fgLuck", r.return_td_diff AS "returnTdDiff",
  r.sos, r.sos_rank AS "sosRank", r.opp_adj_o AS "oppAdjO", r.opp_adj_d AS "oppAdjD",
  r.nondiv_sos AS "nondivSos", r.remaining_sos AS "remainingSos", r.remaining_games AS "remainingGames",
  r.pass_off AS "passOff", r.pass_def AS "passDef", r.rush_off AS "rushOff", r.rush_def AS "rushDef",
  r.off_success_rate AS "offSuccessRate", r.def_success_rate AS "defSuccessRate",
  r.off_explosiveness AS "offExplosiveness", r.def_explosiveness AS "defExplosiveness",
  r.off_start_yardline AS "offStartYardline", r.def_start_yardline AS "defStartYardline",
  r.off_points_per_opp AS "offPointsPerOpp", r.def_points_per_opp AS "defPointsPerOpp",
  r.off_turnovers AS "offTurnovers", r.def_turnovers AS "defTurnovers"
`);

/** The version to show: the frozen model when present, else the newest other version (e.g. synthetic). */
export async function ratingVersion(db: Database): Promise<string | null> {
  const rows = await db.execute<{ model_version: string }>(sql`
    SELECT model_version FROM rating_snapshots GROUP BY model_version
    ORDER BY (model_version = ${DEFAULT_MODEL_VERSION}) DESC, max(computed_at) DESC LIMIT 1
  `);
  return rows[0]?.model_version ?? null;
}

/** Every (season, week) snapshot of a version, oldest first (week 0 = preseason). */
export async function ratingWeeks(db: Database, version: string): Promise<RatingWeek[]> {
  const rows = await db.execute<{ season: number; week: number }>(sql`
    SELECT DISTINCT season, week FROM rating_snapshots WHERE model_version = ${version}
    ORDER BY season, week
  `);
  return rows.map((r) => ({ season: r.season, week: r.week }));
}

/** The full table for one snapshot, best AdjEM first. */
export async function ratingsForWeek(
  db: Database,
  { version, season, week }: { version: string } & RatingWeek,
): Promise<RatingRow[]> {
  return db.execute<RatingRow>(sql`
    SELECT ${RATING_COLUMNS}
    FROM rating_snapshots r JOIN nfl_teams t ON t.abbr = r.team
    WHERE r.model_version = ${version} AND r.season = ${season} AND r.week = ${week}
    ORDER BY r.adj_em_rank, r.team
  `);
}

/** One team's snapshots through a season (rating trend), oldest first. */
export async function teamRatingHistory(
  db: Database,
  { version, team, season }: { version: string; team: string; season: number },
): Promise<(RatingRow & { week: number })[]> {
  return db.execute(sql`
    SELECT r.week, ${RATING_COLUMNS}
    FROM rating_snapshots r JOIN nfl_teams t ON t.abbr = r.team
    WHERE r.model_version = ${version} AND r.team = ${team} AND r.season = ${season}
    ORDER BY r.week
  `) as unknown as Promise<(RatingRow & { week: number })[]>;
}

export type TeamGame = {
  gameId: string;
  week: number;
  gameType: string;
  kickoffUtc: string;
  isHome: boolean;
  neutralSite: boolean;
  opponent: string;
  teamScore: number | null;
  opponentScore: number | null;
  /** Opponent's AdjEM rank in the last snapshot before the game, and in the latest snapshot of the season. */
  opponentRankThen: number | null;
  opponentRankNow: number | null;
  /** The team's last model estimate before kickoff (team perspective), when one exists. */
  modelMargin: number | null;
  modelWinProb: number | null;
  modelTeamScore: number | null;
  modelOpponentScore: number | null;
};

/**
 * A franchise's games in a season (historical abbreviations such as OAK resolve to the franchise),
 * with opponent ranks then/now and the last pre-kickoff model estimate from the live forward test.
 */
export async function teamGames(
  db: Database,
  { version, team, season }: { version: string; team: string; season: number },
): Promise<TeamGame[]> {
  return db.execute<TeamGame>(sql`
    WITH abbrs AS (SELECT abbr FROM nfl_teams WHERE franchise = ${team}),
    g AS (
      SELECT game_id, week, game_type, kickoff_utc, neutral_site,
             (home_team IN (SELECT abbr FROM abbrs)) AS is_home,
             CASE WHEN home_team IN (SELECT abbr FROM abbrs) THEN away_team ELSE home_team END AS opp_abbr,
             CASE WHEN home_team IN (SELECT abbr FROM abbrs) THEN home_score ELSE away_score END AS team_score,
             CASE WHEN home_team IN (SELECT abbr FROM abbrs) THEN away_score ELSE home_score END AS opp_score
      FROM nfl_games
      WHERE season = ${season} AND (home_team IN (SELECT abbr FROM abbrs) OR away_team IN (SELECT abbr FROM abbrs))
    )
    SELECT g.game_id AS "gameId", g.week, g.game_type AS "gameType", ${iso("g.kickoff_utc")} AS "kickoffUtc",
           g.is_home AS "isHome", g.neutral_site AS "neutralSite", ot.franchise AS opponent,
           g.team_score AS "teamScore", g.opp_score AS "opponentScore",
           (SELECT r.adj_em_rank FROM rating_snapshots r
             WHERE r.model_version = ${version} AND r.team = ot.franchise AND r.season = ${season} AND r.week < g.week
             ORDER BY r.week DESC LIMIT 1) AS "opponentRankThen",
           (SELECT r.adj_em_rank FROM rating_snapshots r
             WHERE r.model_version = ${version} AND r.team = ot.franchise AND r.season = ${season}
             ORDER BY r.week DESC LIMIT 1) AS "opponentRankNow",
           CASE WHEN g.is_home THEN p.expected_margin ELSE -p.expected_margin END AS "modelMargin",
           CASE WHEN g.is_home THEN p.p_home ELSE 1 - p.p_home END AS "modelWinProb",
           CASE WHEN g.is_home THEN p.home_score ELSE p.away_score END AS "modelTeamScore",
           CASE WHEN g.is_home THEN p.away_score ELSE p.home_score END AS "modelOpponentScore"
    FROM g
    JOIN nfl_teams ot ON ot.abbr = g.opp_abbr
    LEFT JOIN LATERAL (
      SELECT expected_margin, p_home, home_score, away_score FROM model_predictions mp
      WHERE mp.model_version = ${version} AND mp.game_id = g.game_id AND mp.predicted_at < mp.kickoff_utc
      ORDER BY mp.predicted_at DESC LIMIT 1
    ) p ON true
    ORDER BY g.kickoff_utc
  `);
}

export type StaffMember = {
  role: string;
  coachName: string;
  fromWeek: number;
  toWeek: number;
  offensePlaycaller: boolean;
  defensePlaycaller: boolean;
};

/** Coaching staff spans for a franchise-season (HC, coordinators, play-callers). */
export async function teamStaff(
  db: Database,
  { team, season }: { team: string; season: number },
): Promise<StaffMember[]> {
  return db.execute<StaffMember>(sql`
    SELECT role, coach_name AS "coachName", from_week AS "fromWeek", to_week AS "toWeek",
           offense_playcaller AS "offensePlaycaller", defense_playcaller AS "defensePlaycaller"
    FROM nfl_coaching_staff
    WHERE season = ${season} AND team IN (SELECT abbr FROM nfl_teams WHERE franchise = ${team})
    ORDER BY array_position(ARRAY['HC', 'OC', 'DC', 'STC', 'PC'], role), from_week
  `);
}
