// Market Signal Lab: versioned, reproducible signal definitions over stored observations.
// Pure functions, no I/O. Every detection carries the observation ids that produced it.
// Signals DESCRIBE observable market behavior. They do not claim professional betting
// activity and are not betting recommendations. See docs/SIGNAL_DEFINITIONS.md.

import { BOARD_BOOKS, type BoardBook } from "./bookmakers";
import type { Market, Selection } from "./domain";
import { buildBookSeries, type HistoryObservation } from "./history";
import { describeMovement } from "./replay";

export interface SignalObservation extends HistoryObservation {
  id: number;
  market: Market;
  selection: Selection;
}

export const SIGNAL_TYPES = [
  "line_move",
  "price_move",
  "key_number",
  "book_divergence",
  "rapid_consensus_move",
  "same_line_price_disagreement",
] as const;
export type SignalType = (typeof SIGNAL_TYPES)[number];

export interface SignalDefinition {
  type: SignalType;
  version: number;
  title: string;
  definition: string;
  limitations: string;
}

/** Thresholds for algorithm version 1. Changing any of these requires a version bump. */
export const SIGNAL_THRESHOLDS = {
  divergencePoints: 0.5,
  divergenceMinBooks: 3,
  rapidConsensusPoints: 1.0,
  rapidWindowMinutes: 6 * 60,
  consensusMinBooks: 3,
  priceDisagreementCents: 10,
  gapMinutes: 12 * 60,
} as const;

export const SIGNAL_DEFINITIONS: Readonly<Record<SignalType, SignalDefinition>> = {
  line_move: {
    type: "line_move",
    version: 1,
    title: "Line move",
    definition:
      "A book's home spread or total line differs from its previous observation. Reported as an interval between the two snapshots; value = point change (home orientation for spreads).",
    limitations:
      "Only as precise as the polling cadence: the move happened somewhere in the interval. A move across a data gap is flagged.",
  },
  price_move: {
    type: "price_move",
    version: 1,
    title: "Price move",
    definition:
      "Same book, same line, different American price (oriented side: home spread, home moneyline, Over). Value = change in cents on a continuous scale (−110 → −120 is −10).",
    limitations: "Small price moves are routine; frequency alone says little.",
  },
  key_number: {
    type: "key_number",
    version: 1,
    title: "Key-number crossing",
    definition:
      "A book's home spread moves across or onto ±3 or ±7, the most common NFL margins. Value = the signed key number.",
    limitations: "Descriptive only: crossing a key number does not by itself imply betting value.",
  },
  book_divergence: {
    type: "book_divergence",
    version: 1,
    title: "Book divergence",
    definition:
      "In a single snapshot, a book's home spread is at least 0.5 points from the consensus: the median home spread of all target books in that snapshot (at least 3). Emitted when a divergence begins. Value = book minus consensus.",
    limitations:
      "Only target books are compared; a book can diverge because it moved first, last, or for its own risk reasons. Persistence is not tracked in v1.",
  },
  rapid_consensus_move: {
    type: "rapid_consensus_move",
    version: 1,
    title: "Rapid consensus move",
    definition:
      "The consensus home spread (median of at least 3 books in one snapshot) differs by at least 1.0 point from the earliest consensus within the previous 6 hours. Value = consensus change.",
    limitations:
      "With 4 snapshots a day, only consecutive snapshots fall inside the window. Moves spanning longer collection gaps are never called rapid.",
  },
  same_line_price_disagreement: {
    type: "same_line_price_disagreement",
    version: 1,
    title: "Same-line price disagreement",
    definition:
      "In a single snapshot, at least two books offer the identical market, side, and line but their prices differ by at least 10 cents. Emitted when the disagreement begins. Value = price spread in cents.",
    limitations:
      "Displayed prices only; limits, promos, and account restrictions are unknown. Not an arbitrage claim.",
  },
};

export interface SignalDetection {
  type: SignalType;
  version: number;
  market: Market;
  selection: Selection | null;
  bookmakerKey: string | null;
  /** When the signal became observable (end of its evidence window). */
  detectedAt: string;
  windowStart: string;
  windowEnd: string;
  value: number;
  details: Record<string, unknown>;
  /** odds_observations.id values that constitute the evidence. */
  evidence: number[];
}

/** −110 → −10, +110 → +10: price differences in "cents" without the jump at even money. */
const cents = (american: number) => (american < 0 ? american + 100 : american - 100);
const median = (values: number[]) => {
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};

/** Compute every v1 signal for one game's pregame observations (any order, all markets). */
export function computeSignals(
  observations: readonly SignalObservation[],
  { books = BOARD_BOOKS }: { books?: readonly BoardBook[] } = {},
): SignalDetection[] {
  const pregame = observations.filter((o) => !o.isLive);
  return [
    ...perFeedSignals(pregame),
    ...divergenceSignals(pregame, books),
    ...rapidConsensusSignals(pregame, books),
    ...priceDisagreementSignals(pregame, books),
  ].sort(compareDetections);
}

/** Total order so output is deterministic regardless of input order. */
function compareDetections(a: SignalDetection, b: SignalDetection): number {
  return (
    a.detectedAt.localeCompare(b.detectedAt) ||
    a.type.localeCompare(b.type) ||
    (a.bookmakerKey ?? "").localeCompare(b.bookmakerKey ?? "") ||
    a.market.localeCompare(b.market) ||
    (a.selection ?? "").localeCompare(b.selection ?? "") ||
    a.windowStart.localeCompare(b.windowStart) ||
    a.value - b.value
  );
}

// ---- A, B, C: per-feed changes -------------------------------------------------------

const ORIENTED: ReadonlyArray<[Market, Selection]> = [
  ["spreads", "HOME"],
  ["totals", "OVER"],
  ["h2h", "HOME"],
];

function perFeedSignals(observations: readonly SignalObservation[]): SignalDetection[] {
  const out: SignalDetection[] = [];
  for (const [market, selection] of ORIENTED) {
    const byFeed = groupBy(
      observations.filter((o) => o.market === market && o.selection === selection),
      (o) => o.bookmakerKey,
    );
    for (const [feed, list] of byFeed) {
      const sorted = [...list].sort((a, b) => a.observedAt.localeCompare(b.observedAt));
      const idAt = new Map(sorted.map((o) => [o.observedAt, o.id]));
      const series = buildBookSeries(sorted, {
        gapMinutes: SIGNAL_THRESHOLDS.gapMinutes,
        resolution: "changes",
      });
      for (const change of series.changes) {
        const movement = describeMovement(change, market, selection);
        const evidence = [idAt.get(change.intervalStart)!, idAt.get(change.intervalEnd)!];
        const base = {
          market,
          selection,
          bookmakerKey: feed,
          detectedAt: change.intervalEnd,
          windowStart: change.intervalStart,
          windowEnd: change.intervalEnd,
          evidence,
        };
        const details = {
          fromPoint: change.fromPoint,
          toPoint: change.toPoint,
          fromPrice: change.fromPrice,
          toPrice: change.toPrice,
          direction: movement.direction,
          acrossGap: change.acrossGap,
        };
        if (market !== "h2h" && change.type !== "price" && change.pointDelta !== null) {
          out.push({ ...base, type: "line_move", version: 1, value: change.pointDelta, details });
        }
        if (change.type === "price") {
          out.push({
            ...base,
            type: "price_move",
            version: 1,
            value: cents(change.toPrice) - cents(change.fromPrice),
            details,
          });
        }
        for (const k of movement.keyNumbers) {
          if (k.kind === "left") continue;
          out.push({
            ...base,
            type: "key_number",
            version: 1,
            value: k.signedKey,
            details: { ...details, key: k.key, kind: k.kind },
          });
        }
      }
    }
  }
  return out;
}

// ---- Snapshot helpers for contemporaneous signals --------------------------------------

/** One observation per board book in a snapshot (preferred feed first), for one selection. */
function boardQuotesAt(
  snapshot: readonly SignalObservation[],
  books: readonly BoardBook[],
  market: Market,
  selection: Selection,
): { book: BoardBook; obs: SignalObservation }[] {
  const rows: { book: BoardBook; obs: SignalObservation }[] = [];
  for (const book of books) {
    for (const feed of book.feeds) {
      const obs = snapshot.find(
        (o) => o.bookmakerKey === feed && o.market === market && o.selection === selection,
      );
      if (obs) {
        rows.push({ book, obs });
        break;
      }
    }
  }
  return rows;
}

function snapshots(observations: readonly SignalObservation[]): [string, SignalObservation[]][] {
  return [...groupBy(observations, (o) => o.observedAt)].sort(([a], [b]) => a.localeCompare(b));
}

// ---- D: book divergence ----------------------------------------------------------------

function divergenceSignals(
  observations: readonly SignalObservation[],
  books: readonly BoardBook[],
): SignalDetection[] {
  const out: SignalDetection[] = [];
  const divergentBefore = new Set<string>();
  for (const [at, snap] of snapshots(observations)) {
    const quotes = boardQuotesAt(snap, books, "spreads", "HOME").filter(
      (q) => q.obs.point !== null,
    );
    const divergentNow = new Set<string>();
    if (quotes.length >= SIGNAL_THRESHOLDS.divergenceMinBooks) {
      // Consensus of ALL target books in the snapshot (spec 14.1 D). A leave-one-out median
      // is unstable with 3 books: the two "others" average, so the non-outliers get flagged.
      const consensus = median(quotes.map((q) => q.obs.point!));
      for (const q of quotes) {
        const diff = Math.round((q.obs.point! - consensus) * 100) / 100;
        if (Math.abs(diff) + 1e-9 < SIGNAL_THRESHOLDS.divergencePoints) continue;
        divergentNow.add(q.book.id);
        if (divergentBefore.has(q.book.id)) continue; // still diverging: only the onset is a signal
        out.push({
          type: "book_divergence",
          version: 1,
          market: "spreads",
          selection: "HOME",
          bookmakerKey: q.obs.bookmakerKey,
          detectedAt: at,
          windowStart: at,
          windowEnd: at,
          value: diff,
          details: { point: q.obs.point, consensus, books: quotes.map((x) => x.obs.bookmakerKey) },
          evidence: quotes.map((x) => x.obs.id),
        });
      }
    }
    divergentBefore.clear();
    divergentNow.forEach((b) => divergentBefore.add(b));
  }
  return out;
}

// ---- E: rapid consensus move ------------------------------------------------------------

function rapidConsensusSignals(
  observations: readonly SignalObservation[],
  books: readonly BoardBook[],
): SignalDetection[] {
  const consensus = snapshots(observations)
    .map(([at, snap]) => {
      const quotes = boardQuotesAt(snap, books, "spreads", "HOME").filter(
        (q) => q.obs.point !== null,
      );
      return quotes.length >= SIGNAL_THRESHOLDS.consensusMinBooks
        ? {
            at,
            value: median(quotes.map((q) => q.obs.point!)),
            ids: quotes.map((q) => q.obs.id),
            books: quotes.length,
          }
        : null;
    })
    .filter((c) => c !== null);

  const out: SignalDetection[] = [];
  const usedAnchors = new Set<string>();
  for (const current of consensus) {
    const t = Date.parse(current.at);
    const anchor = consensus.find(
      (c) =>
        Date.parse(c.at) < t &&
        t - Date.parse(c.at) <= SIGNAL_THRESHOLDS.rapidWindowMinutes * 60_000,
    );
    if (!anchor || usedAnchors.has(anchor.at)) continue;
    const change = Math.round((current.value - anchor.value) * 100) / 100;
    if (Math.abs(change) + 1e-9 < SIGNAL_THRESHOLDS.rapidConsensusPoints) continue;
    usedAnchors.add(anchor.at);
    out.push({
      type: "rapid_consensus_move",
      version: 1,
      market: "spreads",
      selection: "HOME",
      bookmakerKey: null,
      detectedAt: current.at,
      windowStart: anchor.at,
      windowEnd: current.at,
      value: change,
      details: {
        fromConsensus: anchor.value,
        toConsensus: current.value,
        fromBooks: anchor.books,
        toBooks: current.books,
        minutes: Math.round((t - Date.parse(anchor.at)) / 60_000),
      },
      evidence: [...anchor.ids, ...current.ids],
    });
  }
  return out;
}

// ---- F: same-line price disagreement ------------------------------------------------------

const ALL_SIDES: ReadonlyArray<[Market, Selection]> = [
  ["spreads", "HOME"],
  ["spreads", "AWAY"],
  ["totals", "OVER"],
  ["totals", "UNDER"],
  ["h2h", "HOME"],
  ["h2h", "AWAY"],
];

function priceDisagreementSignals(
  observations: readonly SignalObservation[],
  books: readonly BoardBook[],
): SignalDetection[] {
  const out: SignalDetection[] = [];
  const activeBefore = new Set<string>();
  for (const [at, snap] of snapshots(observations)) {
    const activeNow = new Set<string>();
    for (const [market, selection] of ALL_SIDES) {
      const quotes = boardQuotesAt(snap, books, market, selection);
      for (const [pointKey, group] of groupBy(quotes, (q) => String(q.obs.point))) {
        if (group.length < 2) continue;
        const prices = group.map((q) => cents(q.obs.americanPrice));
        const spread = Math.max(...prices) - Math.min(...prices);
        if (spread < SIGNAL_THRESHOLDS.priceDisagreementCents) continue;
        const key = `${market}|${selection}|${pointKey}`;
        activeNow.add(key);
        if (activeBefore.has(key)) continue;
        const best = group.reduce((a, b) =>
          cents(b.obs.americanPrice) > cents(a.obs.americanPrice) ? b : a,
        );
        const worst = group.reduce((a, b) =>
          cents(b.obs.americanPrice) < cents(a.obs.americanPrice) ? b : a,
        );
        out.push({
          type: "same_line_price_disagreement",
          version: 1,
          market,
          selection,
          bookmakerKey: null,
          detectedAt: at,
          windowStart: at,
          windowEnd: at,
          value: spread,
          details: {
            point: group[0]!.obs.point,
            best: { bookmakerKey: best.obs.bookmakerKey, price: best.obs.americanPrice },
            worst: { bookmakerKey: worst.obs.bookmakerKey, price: worst.obs.americanPrice },
            books: group.length,
          },
          evidence: group.map((q) => q.obs.id),
        });
      }
    }
    activeBefore.clear();
    activeNow.forEach((k) => activeBefore.add(k));
  }
  return out;
}

function groupBy<T>(items: readonly T[], key: (t: T) => string): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const k = key(item);
    const list = map.get(k) ?? [];
    list.push(item);
    map.set(k, list);
  }
  return map;
}
