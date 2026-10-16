// Maps database rows to domain types and API response shapes. Pure: no I/O, no Next.js.

import type { GameRow, LatestQuoteRow } from "@marketscope/db";
import {
  calculateFreshness,
  COLLECTED_BOOKMAKERS,
  COLLECTED_BOOKMAKER_KEYS,
  MARKETS,
  type FreshnessLabel,
  type NormalizedEvent,
  type NormalizedQuote,
} from "@marketscope/shared";

export function toNormalizedEvent(game: GameRow): NormalizedEvent {
  return {
    providerEventId: game.providerEventId,
    sportKey: game.sportKey,
    homeTeam: game.homeTeam,
    awayTeam: game.awayTeam,
    commenceTime: game.commenceTime,
  };
}

export function toNormalizedQuote(game: GameRow, row: LatestQuoteRow): NormalizedQuote {
  return {
    providerEventId: game.providerEventId,
    bookmakerKey: row.bookmakerKey,
    market: row.market,
    selection: row.selection,
    point: row.point,
    americanPrice: row.americanPrice,
    bookmakerUpdatedAt: row.bookmakerUpdatedAt,
    observedAt: row.observedAt,
    isLive: row.isLive,
  };
}

export function groupByEvent(rows: readonly LatestQuoteRow[]): Map<string, LatestQuoteRow[]> {
  const map = new Map<string, LatestQuoteRow[]>();
  for (const row of rows) {
    const list = map.get(row.eventId) ?? [];
    list.push(row);
    map.set(row.eventId, list);
  }
  return map;
}

export interface Coverage {
  /** Newest observation time for this game (the latest snapshot that included it). */
  latestObservedAt: string | null;
  /** Feeds with at least one quote in that latest snapshot. */
  feedsInLatestSnapshot: string[];
  /** Collected feeds with no quote in the latest snapshot (absent ≠ "not offered by the book"). */
  feedsMissing: string[];
}

export function computeCoverage(rows: readonly LatestQuoteRow[]): Coverage {
  const latestObservedAt = rows.reduce<string | null>(
    (max, r) => (max === null || r.observedAt > max ? r.observedAt : max),
    null,
  );
  const current = new Set(
    rows.filter((r) => r.observedAt === latestObservedAt).map((r) => r.bookmakerKey),
  );
  return {
    latestObservedAt,
    feedsInLatestSnapshot: COLLECTED_BOOKMAKER_KEYS.filter((k) => current.has(k)),
    feedsMissing: COLLECTED_BOOKMAKER_KEYS.filter((k) => !current.has(k)),
  };
}

export interface ApiGame {
  id: string;
  homeTeam: string;
  awayTeam: string;
  commenceTime: string;
  season: number;
  week: number | null;
  started: boolean;
  coverage: Coverage;
}

export function toApiGame(game: GameRow, rows: readonly LatestQuoteRow[], now: Date): ApiGame {
  return {
    id: game.id,
    homeTeam: game.homeTeam,
    awayTeam: game.awayTeam,
    commenceTime: game.commenceTime,
    season: game.season,
    week: game.week,
    started: Date.parse(game.commenceTime) <= now.getTime(),
    coverage: computeCoverage(rows),
  };
}

export interface ApiQuote {
  bookmakerKey: string;
  market: LatestQuoteRow["market"];
  selection: LatestQuoteRow["selection"];
  point: number | null;
  americanPrice: number;
  isLive: boolean;
  /** When our collector observed this quote. */
  observedAt: string;
  /** Provider-reported market update time (may be null). */
  bookmakerUpdatedAt: string | null;
  freshness: {
    /** Minutes since we observed it: the age of the collection. */
    collectionAgeMinutes: number;
    /** Minutes since the book's reported update: the age of the sportsbook's data. */
    bookUpdateAgeMinutes: number | null;
    label: FreshnessLabel;
    /** The book was absent from the game's newest snapshot; this is its last-seen quote. */
    stale: boolean;
  };
}

export function toApiQuotes(
  rows: readonly LatestQuoteRow[],
  now: Date,
  recentMinutes: number,
): ApiQuote[] {
  const { latestObservedAt } = computeCoverage(rows);
  return rows.map((r) => {
    const collection = calculateFreshness(r.observedAt, now, recentMinutes);
    return {
      bookmakerKey: r.bookmakerKey,
      market: r.market,
      selection: r.selection,
      point: r.point,
      americanPrice: r.americanPrice,
      isLive: r.isLive,
      observedAt: r.observedAt,
      bookmakerUpdatedAt: r.bookmakerUpdatedAt,
      freshness: {
        collectionAgeMinutes: round1(collection.ageMinutes),
        bookUpdateAgeMinutes: r.bookmakerUpdatedAt
          ? round1(calculateFreshness(r.bookmakerUpdatedAt, now, recentMinutes).ageMinutes)
          : null,
        label: collection.label,
        stale: r.observedAt !== latestObservedAt,
      },
    };
  });
}

const round1 = (n: number) => Math.round(n * 10) / 10;

export interface FeedCoverage {
  bookmakerKey: string;
  displayName: string;
  status: "current" | "stale" | "absent";
  /** Markets with at least one quote in this feed's newest observation. */
  markets: LatestQuoteRow["market"][];
  lastObservedAt: string | null;
  lastBookUpdateAt: string | null;
}

/** Per-feed coverage for one game: is each collected feed in the latest snapshot? */
export function feedCoverage(rows: readonly LatestQuoteRow[]): FeedCoverage[] {
  const { latestObservedAt } = computeCoverage(rows);
  return COLLECTED_BOOKMAKERS.map((b) => {
    const feedRows = rows.filter((r) => r.bookmakerKey === b.key);
    const lastObservedAt = maxOf(feedRows.map((r) => r.observedAt));
    const newest = feedRows.filter((r) => r.observedAt === lastObservedAt);
    return {
      bookmakerKey: b.key,
      displayName: b.displayName,
      status:
        feedRows.length === 0
          ? "absent"
          : lastObservedAt === latestObservedAt
            ? "current"
            : "stale",
      markets: MARKETS.filter((m) => newest.some((r) => r.market === m)),
      lastObservedAt,
      lastBookUpdateAt: maxOf(feedRows.map((r) => r.bookmakerUpdatedAt).filter((t) => t !== null)),
    };
  });
}

function maxOf(values: string[]): string | null {
  return values.reduce<string | null>((max, v) => (max === null || v > max ? v : max), null);
}
