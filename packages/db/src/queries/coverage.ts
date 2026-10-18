// Data-coverage queries (MS-023): how much pregame history each game has, per book and
// source. Counts only, never prices, so this is safe to show anywhere.

import { sql } from "drizzle-orm";
import type { Database } from "../client";

export interface GameCoverageRow {
  eventId: string;
  homeTeam: string;
  awayTeam: string;
  commenceTime: string;
  /** Distinct sources for this game (the importer guarantees at most one real source). */
  sources: string[];
  /** Distinct pregame snapshot times with any home-spread quote. */
  snapshots: number;
  firstObservedAt: string;
  lastObservedAt: string;
  /** Column key → number of those snapshots in which that column had a spread quote. */
  snapshotsByColumn: Record<string, number>;
  signals: number;
}

/**
 * Per-game pregame coverage for games kicking off in [from, to), newest kickoff first.
 *
 * Coverage is measured on the home spread (every book that posts a game posts it), which
 * keeps the scan to one sixth of the rows. `feedColumns` maps feed keys to display
 * columns (e.g. both Hard Rock feeds → "hardrock"); unmapped feeds keep their own key.
 * A snapshot counts once per column even when two of its feeds both reported.
 */
export async function gameCoverage(
  db: Database,
  {
    from,
    to,
    feedColumns,
    limit,
  }: { from: string; to: string; feedColumns: Readonly<Record<string, string>>; limit: number },
): Promise<GameCoverageRow[]> {
  const mapping = Object.entries(feedColumns);
  const feedTable =
    mapping.length > 0
      ? sql`(VALUES ${sql.join(
          mapping.map(([feed, column]) => sql`(${feed}::text, ${column}::text)`),
          sql`, `,
        )}) AS feed(feed_key, column_key)`
      : sql`(SELECT NULL::text AS feed_key, NULL::text AS column_key WHERE false) AS feed`;

  // Every aggregate is computed once and joined; correlated per-game subqueries made
  // Postgres re-aggregate the inlined CTE once per game (MS-023: 575 ms → see PERFORMANCE.md).
  const rows = await db.execute<{
    event_id: string;
    home_team: string;
    away_team: string;
    commence_time: string;
    sources: string[];
    snapshots: number;
    first_observed_at: string;
    last_observed_at: string;
    by_column: Record<string, number>;
    signals: number;
  }>(sql`
    WITH games AS (
      SELECT id, home_team, away_team, commence_time_utc
      FROM events
      WHERE commence_time_utc >= ${from} AND commence_time_utc < ${to}
    ),
    obs AS (
      SELECT o.event_id, coalesce(feed.column_key, o.bookmaker_key) AS column_key,
             o.observed_at, o.source
      FROM odds_observations o
      JOIN games g ON g.id = o.event_id
      LEFT JOIN ${feedTable} ON feed.feed_key = o.bookmaker_key
      WHERE o.market_type = 'spreads' AND o.selection = 'HOME'
        AND o.observed_at < g.commence_time_utc
    ),
    per_column AS (
      SELECT event_id, jsonb_object_agg(column_key, n) AS by_column
      FROM (
        SELECT event_id, column_key, count(DISTINCT observed_at)::int AS n
        FROM obs GROUP BY event_id, column_key
      ) c
      GROUP BY event_id
    ),
    signal_counts AS (
      SELECT s.event_id, count(*)::int AS n
      FROM market_signals s JOIN games g ON g.id = s.event_id
      GROUP BY s.event_id
    ),
    per_game AS (
      SELECT event_id,
             array_agg(DISTINCT source ORDER BY source) AS sources,
             count(DISTINCT observed_at)::int AS snapshots,
             min(observed_at) AS first_observed_at,
             max(observed_at) AS last_observed_at
      FROM obs GROUP BY event_id
    )
    SELECT g.id AS event_id, g.home_team, g.away_team,
           to_char(g.commence_time_utc AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS commence_time,
           p.sources, p.snapshots,
           to_char(p.first_observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS first_observed_at,
           to_char(p.last_observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS last_observed_at,
           c.by_column, coalesce(sc.n, 0) AS signals
    FROM games g
    JOIN per_game p ON p.event_id = g.id
    JOIN per_column c ON c.event_id = g.id
    LEFT JOIN signal_counts sc ON sc.event_id = g.id
    ORDER BY g.commence_time_utc DESC, g.id
    LIMIT ${limit}
  `);

  return rows.map((r) => ({
    eventId: r.event_id,
    homeTeam: r.home_team,
    awayTeam: r.away_team,
    commenceTime: r.commence_time,
    sources: r.sources,
    snapshots: r.snapshots,
    firstObservedAt: r.first_observed_at,
    lastObservedAt: r.last_observed_at,
    snapshotsByColumn: r.by_column ?? {},
    signals: r.signals,
  }));
}
