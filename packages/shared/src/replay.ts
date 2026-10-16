// Market replay: what was observable at a chosen moment, and how lines moved. Pure.

import type { Market } from "./domain";
import type { HistoryObservation, LineChange } from "./history";
import { detectKeyNumberCrossings, NFL_KEY_NUMBERS, type KeyNumberEvent } from "./key-numbers";

export type ReplayStatus = "fresh" | "stale" | "none";

export interface BookStateAt {
  bookmakerKey: string;
  status: ReplayStatus;
  /** Latest observation at or before T (present for fresh and stale). */
  observation: HistoryObservation | null;
  /** Minutes between that observation and T. */
  ageMinutes: number | null;
}

/**
 * Each book's latest observation at or before `at`. Observations older than
 * `freshnessMinutes` are reported as stale (shown as "last seen", never used as current),
 * and books with nothing yet as "none". Prices are never carried forward silently.
 */
export function stateAt(
  observations: readonly HistoryObservation[],
  at: string,
  {
    freshnessMinutes,
    bookmakerKeys,
  }: { freshnessMinutes: number; bookmakerKeys?: readonly string[] },
): BookStateAt[] {
  const atMs = Date.parse(at);
  if (Number.isNaN(atMs)) throw new RangeError(`invalid timestamp: ${at}`);
  const latest = new Map<string, HistoryObservation>();
  for (const obs of observations) {
    if (Date.parse(obs.observedAt) > atMs) continue;
    const prev = latest.get(obs.bookmakerKey);
    if (!prev || obs.observedAt > prev.observedAt) latest.set(obs.bookmakerKey, obs);
  }
  const keys = bookmakerKeys ?? [...new Set(observations.map((o) => o.bookmakerKey))].sort();
  return keys.map((bookmakerKey) => {
    const observation = latest.get(bookmakerKey) ?? null;
    if (!observation) return { bookmakerKey, status: "none", observation: null, ageMinutes: null };
    const ageMinutes = (atMs - Date.parse(observation.observedAt)) / 60_000;
    return {
      bookmakerKey,
      status: ageMinutes <= freshnessMinutes ? "fresh" : "stale",
      observation,
      ageMinutes,
    };
  });
}

export interface Dispersion {
  books: number;
  /** Highest minus lowest line. */
  range: number;
  /** Population standard deviation of the lines. */
  stdDev: number;
  /** Mean absolute deviation from `center` (the consensus). */
  meanAbsDeviation: number;
  /** Books at least `threshold` points from `center`. */
  booksOffCenter: number;
}

/**
 * Cross-book disagreement for contemporaneous lines (one per book; callers pass only
 * fresh observations). Returns null with fewer than two books.
 */
export function calculateBookDispersion(
  points: readonly number[],
  center: number,
  threshold = 0.5,
): Dispersion | null {
  if (points.length < 2) return null;
  const mean = points.reduce((s, p) => s + p, 0) / points.length;
  const variance = points.reduce((s, p) => s + (p - mean) ** 2, 0) / points.length;
  return {
    books: points.length,
    range: round2(Math.max(...points) - Math.min(...points)),
    stdDev: round2(Math.sqrt(variance)),
    meanAbsDeviation: round2(points.reduce((s, p) => s + Math.abs(p - center), 0) / points.length),
    booksOffCenter: points.filter((p) => Math.abs(p - center) >= threshold - 1e-9).length,
  };
}

export type MovementDirection =
  | "toward-home" // home spread fell (−2.5 → −3.5): the market moved toward the home team
  | "toward-away" // home spread rose (−3.5 → −2.5): the market moved toward the away team
  | "total-up"
  | "total-down"
  | "price-only";

export interface Movement extends LineChange {
  direction: MovementDirection;
  keyNumbers: KeyNumberEvent[];
}

/**
 * Describe a change. For spreads the point is the chosen selection's line as posted;
 * direction is reported in HOME orientation: a home spread rising (−3.5 → −2.5) moves
 * toward the away side, falling (−2.5 → −3.5) toward the home side. For AWAY series the
 * sign is flipped so the label means the same thing.
 */
export function describeMovement(
  change: LineChange,
  market: Market,
  selection: "HOME" | "AWAY" | "OVER" | "UNDER",
  keyNumbers: readonly number[] = NFL_KEY_NUMBERS,
): Movement {
  if (change.type === "price" || change.pointDelta === null || change.pointDelta === 0) {
    return { ...change, direction: "price-only", keyNumbers: [] };
  }
  if (market === "totals") {
    return {
      ...change,
      direction: change.pointDelta > 0 ? "total-up" : "total-down",
      keyNumbers: [],
    };
  }
  const homeDelta = selection === "AWAY" ? -change.pointDelta : change.pointDelta;
  return {
    ...change,
    direction: homeDelta > 0 ? "toward-away" : "toward-home",
    keyNumbers:
      market === "spreads" && change.fromPoint !== null && change.toPoint !== null
        ? detectKeyNumberCrossings(change.fromPoint, change.toPoint, keyNumbers)
        : [],
  };
}

const round2 = (n: number) => Math.round(n * 100) / 100;
