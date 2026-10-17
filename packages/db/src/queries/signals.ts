import { and, asc, desc, eq, gte, inArray, lt, or, sql, type SQL } from "drizzle-orm";
import type { AnyPgColumn } from "drizzle-orm/pg-core";
import type { Database } from "../client";
import { events, marketSignals, oddsObservations } from "../schema";

const isoUtc = (value: AnyPgColumn | SQL) =>
  sql<string>`to_char(${value} at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`;
const isoUtcNullable = (value: AnyPgColumn | SQL) =>
  sql<string | null>`to_char(${value} at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`;

type MarketType = "h2h" | "spreads" | "totals";
type SelectionType = "HOME" | "AWAY" | "OVER" | "UNDER";

export interface SignalInputRow {
  id: number;
  bookmakerKey: string;
  market: MarketType;
  selection: SelectionType;
  point: number | null;
  americanPrice: number;
  bookmakerUpdatedAt: string | null;
  observedAt: string;
  isLive: boolean;
}

/** Every pregame observation of one game (all markets), with ids, for signal computation. */
export async function eventSignalObservations(
  db: Database,
  eventId: string,
): Promise<SignalInputRow[]> {
  const o = oddsObservations;
  return db
    .select({
      id: o.id,
      bookmakerKey: o.bookmakerKey,
      market: o.marketType,
      selection: o.selection,
      point: o.point,
      americanPrice: o.americanPrice,
      bookmakerUpdatedAt: isoUtcNullable(o.bookmakerUpdatedAt),
      observedAt: isoUtc(o.observedAt),
      isLive: o.isLive,
    })
    .from(o)
    .where(and(eq(o.eventId, eventId), eq(o.isLive, false)))
    .orderBy(asc(o.observedAt), asc(o.id));
}

export interface SignalWrite {
  type: string;
  version: number;
  market: MarketType;
  selection: SelectionType | null;
  bookmakerKey: string | null;
  detectedAt: string;
  windowStart: string;
  windowEnd: string;
  value: number;
  details: Record<string, unknown>;
  evidence: number[];
}

/**
 * Replace a game's signals for the given (type, version) pairs in one transaction, so a
 * recompute is idempotent and readers never see a half-written set.
 */
export async function replaceEventSignals(
  db: Database,
  eventId: string,
  definitions: readonly { type: string; version: number }[],
  detections: readonly SignalWrite[],
): Promise<number> {
  return db.transaction(async (tx) => {
    if (definitions.length > 0) {
      await tx
        .delete(marketSignals)
        .where(
          and(
            eq(marketSignals.eventId, eventId),
            or(
              ...definitions.map((d) =>
                and(
                  eq(marketSignals.signalType, d.type),
                  eq(marketSignals.algorithmVersion, d.version),
                ),
              ),
            ),
          ),
        );
    }
    for (let i = 0; i < detections.length; i += 500) {
      await tx.insert(marketSignals).values(
        detections.slice(i, i + 500).map((d) => ({
          eventId,
          signalType: d.type,
          algorithmVersion: d.version,
          marketType: d.market,
          selection: d.selection,
          bookmakerKey: d.bookmakerKey,
          detectedAt: d.detectedAt,
          windowStart: d.windowStart,
          windowEnd: d.windowEnd,
          value: d.value,
          details: d.details,
          evidenceObservationIds: d.evidence,
        })),
      );
    }
    return detections.length;
  });
}

export interface SignalRow {
  id: number;
  eventId: string;
  homeTeam: string;
  awayTeam: string;
  commenceTime: string;
  type: string;
  version: number;
  market: MarketType;
  selection: SelectionType | null;
  bookmakerKey: string | null;
  detectedAt: string;
  windowStart: string;
  windowEnd: string;
  value: number;
  details: Record<string, unknown>;
  evidence: number[];
}

export const MAX_SIGNALS = 500;

/** Signals detected in [from, to), newest first, bounded. */
export async function listSignals(
  db: Database,
  q: { from?: string; to?: string; types?: readonly string[]; eventId?: string; limit?: number },
): Promise<SignalRow[]> {
  const s = marketSignals;
  const conditions: SQL[] = [];
  if (q.from) conditions.push(gte(s.detectedAt, q.from));
  if (q.to) conditions.push(lt(s.detectedAt, q.to));
  if (q.types && q.types.length > 0) conditions.push(inArray(s.signalType, [...q.types]));
  if (q.eventId) conditions.push(eq(s.eventId, q.eventId));
  return db
    .select({
      id: s.id,
      eventId: s.eventId,
      homeTeam: events.homeTeam,
      awayTeam: events.awayTeam,
      commenceTime: isoUtc(events.commenceTimeUtc),
      type: s.signalType,
      version: s.algorithmVersion,
      market: s.marketType,
      selection: s.selection,
      bookmakerKey: s.bookmakerKey,
      detectedAt: isoUtc(s.detectedAt),
      windowStart: isoUtc(s.windowStart),
      windowEnd: isoUtc(s.windowEnd),
      value: s.value,
      details: s.details,
      evidence: s.evidenceObservationIds,
    })
    .from(s)
    .innerJoin(events, eq(events.id, s.eventId))
    .where(conditions.length > 0 ? and(...conditions) : undefined)
    .orderBy(desc(s.detectedAt), asc(s.id))
    .limit(Math.min(q.limit ?? 200, MAX_SIGNALS));
}

/** Games whose kickoff falls in [from, to): the scope of a scheduled recompute. */
export async function eventIdsKickingOff(
  db: Database,
  from: string,
  to: string,
): Promise<string[]> {
  const rows = await db
    .select({ id: events.id })
    .from(events)
    .where(and(gte(events.commenceTimeUtc, from), lt(events.commenceTimeUtc, to)))
    .orderBy(asc(events.commenceTimeUtc));
  return rows.map((r) => r.id);
}

/** True if any synthetic (demo/e2e) data has been ingested into this database. */
export async function databaseHasSyntheticData(db: Database): Promise<boolean> {
  const [row] = await db
    .select({
      exists: sql<boolean>`exists (select 1 from ingestion_runs where provider = 'synthetic')`,
    })
    .from(sql`(select 1) as one`);
  return row?.exists ?? false;
}
