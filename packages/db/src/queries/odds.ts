// Read-side queries used by the web app and API. All timestamps are returned as
// ISO 8601 UTC strings ("…Z"), formatted by Postgres so no client-side parsing of
// Postgres' text format is needed.

import {
  and,
  asc,
  count,
  countDistinct,
  desc,
  eq,
  gte,
  inArray,
  lt,
  min,
  sql,
  type SQL,
} from "drizzle-orm";
import type { AnyPgColumn } from "drizzle-orm/pg-core";
import type { Database } from "../client";
import { events, ingestionRuns, oddsObservations } from "../schema";

const isoUtc = (value: AnyPgColumn | SQL) =>
  sql<string>`to_char(${value} at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`;
const isoUtcNullable = (value: AnyPgColumn | SQL) =>
  sql<string | null>`to_char(${value} at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`;

export interface GameRow {
  id: string;
  providerEventId: string;
  sportKey: string;
  season: number;
  week: number | null;
  homeTeam: string;
  awayTeam: string;
  commenceTime: string;
}

const gameColumns = {
  id: events.id,
  providerEventId: events.providerEventId,
  sportKey: events.sportKey,
  season: events.season,
  week: events.week,
  homeTeam: events.homeTeam,
  awayTeam: events.awayTeam,
  commenceTime: isoUtc(events.commenceTimeUtc),
};

/** Games kicking off in [from, to), soonest first. Always bounded by `limit`. */
export async function listGames(
  db: Database,
  { from, to, limit }: { from: string; to: string; limit: number },
): Promise<GameRow[]> {
  return db
    .select(gameColumns)
    .from(events)
    .where(and(gte(events.commenceTimeUtc, from), lt(events.commenceTimeUtc, to)))
    .orderBy(asc(events.commenceTimeUtc), asc(events.id))
    .limit(limit);
}

export async function getGame(db: Database, id: string): Promise<GameRow | null> {
  const [row] = await db.select(gameColumns).from(events).where(eq(events.id, id));
  return row ?? null;
}

export interface LatestQuoteRow {
  eventId: string;
  bookmakerKey: string;
  market: "h2h" | "spreads" | "totals";
  selection: "HOME" | "AWAY" | "OVER" | "UNDER";
  point: number | null;
  americanPrice: number;
  bookmakerUpdatedAt: string | null;
  observedAt: string;
  isLive: boolean;
  /** "the-odds-api" for real data; "synthetic" for generated demo/e2e data. */
  source: string;
}

/**
 * The most recent observation of every (event, market, selection, book).
 *
 * DISTINCT ON keeps the first row of each group under the ORDER BY, i.e. the newest
 * observation. The column order matches odds_observations_history_idx
 * (event_id, market_type, selection, bookmaker_key, observed_at DESC), so Postgres can
 * read the groups straight off the index instead of sorting.
 *
 * A book that disappeared from later snapshots still returns its last row; callers must
 * compare observedAt against the event's newest observation to flag it as stale.
 */
export async function latestQuotesForEvents(
  db: Database,
  eventIds: readonly string[],
): Promise<LatestQuoteRow[]> {
  if (eventIds.length === 0) return [];
  const o = oddsObservations;
  return db
    .selectDistinctOn([o.eventId, o.marketType, o.selection, o.bookmakerKey], {
      eventId: o.eventId,
      bookmakerKey: o.bookmakerKey,
      market: o.marketType,
      selection: o.selection,
      point: o.point,
      americanPrice: o.americanPrice,
      bookmakerUpdatedAt: isoUtcNullable(o.bookmakerUpdatedAt),
      observedAt: isoUtc(o.observedAt),
      isLive: o.isLive,
      source: o.source,
    })
    .from(o)
    .where(inArray(o.eventId, [...eventIds]))
    .orderBy(o.eventId, o.marketType, o.selection, o.bookmakerKey, desc(o.observedAt));
}

export interface GameObservationStats {
  observations: number;
  snapshots: number;
  firstObservedAt: string | null;
  lastObservedAt: string | null;
}

/** How much history exists for a game (drives the replay teaser and data-quality panel). */
export async function gameObservationStats(
  db: Database,
  eventId: string,
): Promise<GameObservationStats> {
  const o = oddsObservations;
  const [row] = await db
    .select({
      observations: count(),
      snapshots: countDistinct(o.observedAt),
      firstObservedAt: isoUtcNullable(min(o.observedAt)),
      lastObservedAt: isoUtcNullable(sql`max(${o.observedAt})`),
    })
    .from(o)
    .where(eq(o.eventId, eventId));
  return row!;
}

export interface RunSummary {
  id: string;
  jobKey: string;
  status: "started" | "completed" | "failed" | "skipped";
  startedAt: string;
  finishedAt: string | null;
  eventsSeen: number;
  quotesSeen: number;
  creditsUsed: number | null;
  creditsRemaining: number | null;
  errorCode: string | null;
  issueCounts: Record<string, number> | null;
}

const runColumns = {
  id: ingestionRuns.id,
  jobKey: ingestionRuns.jobKey,
  status: ingestionRuns.status,
  startedAt: isoUtc(ingestionRuns.startedAt),
  finishedAt: isoUtcNullable(ingestionRuns.finishedAt),
  eventsSeen: ingestionRuns.eventsSeen,
  quotesSeen: ingestionRuns.quotesSeen,
  creditsUsed: ingestionRuns.creditsUsed,
  creditsRemaining: ingestionRuns.creditsRemaining,
  errorCode: ingestionRuns.errorCode,
  issueCounts: ingestionRuns.issueCounts,
};

/**
 * The newest completed LIVE collection run. Historical imports (request_type
 * 'historical') are excluded: they're completed runs too, but they say nothing about
 * whether scheduled collection is healthy or how fresh the board is.
 */
export async function latestCompletedRun(db: Database): Promise<RunSummary | null> {
  const [row] = await db
    .select(runColumns)
    .from(ingestionRuns)
    .where(and(eq(ingestionRuns.status, "completed"), eq(ingestionRuns.requestType, "live")))
    .orderBy(desc(ingestionRuns.startedAt))
    .limit(1);
  return row ?? null;
}

/** The newest live collection runs, any status (historical imports excluded). */
export async function recentRuns(db: Database, limit: number): Promise<RunSummary[]> {
  return db
    .select(runColumns)
    .from(ingestionRuns)
    .where(eq(ingestionRuns.requestType, "live"))
    .orderBy(desc(ingestionRuns.startedAt))
    .limit(limit);
}

export const MAX_HISTORY_ROWS = 20_000;

export interface HistoryQuery {
  eventId: string;
  market: LatestQuoteRow["market"];
  selection: LatestQuoteRow["selection"];
  /** Restrict to these feeds (default: all). */
  bookmakerKeys?: readonly string[];
  from?: string;
  to?: string;
  /** Include in-play observations (default false: MarketScope is pregame-only). */
  includeLive?: boolean;
  limit?: number;
}

export interface HistoryRow {
  bookmakerKey: string;
  observedAt: string;
  point: number | null;
  americanPrice: number;
  bookmakerUpdatedAt: string | null;
  isLive: boolean;
  source: string;
}

/**
 * Every observation of one selection for one game, ordered by book then time. Served
 * by odds_observations_history_idx (event, market, selection, book, observed_at).
 * Bounded: returns at most `limit` rows and reports whether it truncated.
 */
export async function selectionHistory(
  db: Database,
  q: HistoryQuery,
): Promise<{ rows: HistoryRow[]; truncated: boolean }> {
  const o = oddsObservations;
  const limit = Math.min(q.limit ?? MAX_HISTORY_ROWS, MAX_HISTORY_ROWS);
  const conditions = [
    eq(o.eventId, q.eventId),
    eq(o.marketType, q.market),
    eq(o.selection, q.selection),
  ];
  if (q.bookmakerKeys && q.bookmakerKeys.length > 0) {
    conditions.push(inArray(o.bookmakerKey, [...q.bookmakerKeys]));
  }
  if (q.from) conditions.push(gte(o.observedAt, q.from));
  if (q.to) conditions.push(lt(o.observedAt, q.to));
  if (!q.includeLive) conditions.push(eq(o.isLive, false));

  const rows = await db
    .select({
      bookmakerKey: o.bookmakerKey,
      observedAt: isoUtc(o.observedAt),
      point: o.point,
      americanPrice: o.americanPrice,
      bookmakerUpdatedAt: isoUtcNullable(o.bookmakerUpdatedAt),
      isLive: o.isLive,
      source: o.source,
    })
    .from(o)
    .where(and(...conditions))
    .orderBy(asc(o.bookmakerKey), asc(o.observedAt))
    .limit(limit + 1);
  return { rows: rows.slice(0, limit), truncated: rows.length > limit };
}

/** History summary per game (one grouped query), for the replay index. */
export async function observationSummaries(
  db: Database,
  eventIds: readonly string[],
): Promise<Map<string, GameObservationStats>> {
  if (eventIds.length === 0) return new Map();
  const o = oddsObservations;
  const rows = await db
    .select({
      eventId: o.eventId,
      observations: count(),
      snapshots: countDistinct(o.observedAt),
      firstObservedAt: isoUtcNullable(min(o.observedAt)),
      lastObservedAt: isoUtcNullable(sql`max(${o.observedAt})`),
    })
    .from(o)
    .where(and(inArray(o.eventId, [...eventIds]), eq(o.isLive, false)))
    .groupBy(o.eventId);
  return new Map(rows.map(({ eventId, ...stats }) => [eventId, stats]));
}
