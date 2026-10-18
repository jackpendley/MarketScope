// View model for the Data Coverage page. Pure: no I/O, so it is unit-tested.

import type { GameCoverageRow, RunSummary } from "@marketscope/db";
import { BOARD_BOOKS, calculateFreshness, REFERENCE_BOOKMAKERS } from "@marketscope/shared";

export interface CoverageColumn {
  key: string;
  label: string;
  reference: boolean;
}

/** Board books in display order, then reference books (outside consensus). */
export const COVERAGE_COLUMNS: readonly CoverageColumn[] = [
  ...BOARD_BOOKS.map((b) => ({ key: b.id, label: b.displayName, reference: false })),
  ...REFERENCE_BOOKMAKERS.map((b) => ({
    key: b.key,
    label: b.displayName.replace(/ \(reference\)$/, ""),
    reference: true,
  })),
];

/** Feed key → column key, e.g. both Hard Rock feeds → "hardrock". */
export const FEED_COLUMNS: Readonly<Record<string, string>> = Object.fromEntries(
  BOARD_BOOKS.flatMap((b) => b.feeds.map((feed) => [feed, b.id])),
);

export const SOURCE_LABELS: Readonly<Record<string, string>> = {
  "the-odds-api": "Live (The Odds API)",
  oddspapi: "Imported (OddsPapi)",
  synthetic: "Synthetic",
};

export type CoverageLevel = "none" | "low" | "partial" | "full";

/** Share of a game's snapshots in which a column had a quote, bucketed for display. */
export function coverageCell(
  snapshots: number,
  covered: number | undefined,
): { share: number; level: CoverageLevel } {
  const share = snapshots > 0 ? (covered ?? 0) / snapshots : 0;
  const level: CoverageLevel =
    share === 0 ? "none" : share < 0.5 ? "low" : share < 0.9 ? "partial" : "full";
  return { share, level };
}

export interface CoverageSummary {
  games: number;
  gamesBySource: [string, number][];
  snapshots: number;
  signals: number;
  /** Games where at least 3 board books (not reference books) posted a spread at some point. */
  consensusEligibleGames: number;
  /** Mean share of snapshots covered, per column, over games where the column appears at all. */
  columnAverages: Record<string, number | null>;
}

export function summarizeCoverage(rows: readonly GameCoverageRow[]): CoverageSummary {
  const bySource = new Map<string, number>();
  let snapshots = 0;
  let signals = 0;
  for (const r of rows) {
    for (const s of r.sources) bySource.set(s, (bySource.get(s) ?? 0) + 1);
    snapshots += r.snapshots;
    signals += r.signals;
  }
  const columnAverages: Record<string, number | null> = {};
  for (const c of COVERAGE_COLUMNS) {
    const shares = rows
      .filter((r) => (r.snapshotsByColumn[c.key] ?? 0) > 0)
      .map((r) => coverageCell(r.snapshots, r.snapshotsByColumn[c.key]).share);
    columnAverages[c.key] = shares.length
      ? shares.reduce((a, b) => a + b, 0) / shares.length
      : null;
  }
  const boardColumns = COVERAGE_COLUMNS.filter((c) => !c.reference);
  const consensusEligibleGames = rows.filter(
    (r) => boardColumns.filter((c) => (r.snapshotsByColumn[c.key] ?? 0) > 0).length >= 3,
  ).length;
  return {
    games: rows.length,
    consensusEligibleGames,
    gamesBySource: [...bySource].sort((a, b) => b[1] - a[1]),
    snapshots,
    signals,
    columnAverages,
  };
}

/** Scheduled collection runs every 6 hours; twice that without a success means it's behind. */
export const COLLECTION_STALE_AFTER_MINUTES = 12 * 60;

export type CollectionStatus = "ok" | "behind" | "no-data";

export function collectionStatus(
  latest: RunSummary | null,
  now: Date,
): { status: CollectionStatus; ageMinutes: number | null } {
  if (!latest) return { status: "no-data", ageMinutes: null };
  const { ageMinutes } = calculateFreshness(latest.startedAt, now, COLLECTION_STALE_AFTER_MINUTES);
  return {
    status: ageMinutes > COLLECTION_STALE_AFTER_MINUTES ? "behind" : "ok",
    ageMinutes: Math.round(ageMinutes),
  };
}
