// Line history: turns one book's ordered observations into a series with explicit
// changes and gaps. Pure functions, no I/O.
//
// Semantics (see docs/DATA_DICTIONARY.md):
// - A CHANGE is a difference in point or price from the book's previous observation.
//   It is detected by value, never from bookmaker_updated_at (which advances even when
//   nothing changes).
// - A change happened somewhere in (previous.observedAt, current.observedAt]. We
//   never claim an exact moment.
// - A GAP is two consecutive observations further apart than `gapMinutes`. Charts must
//   break the line there instead of implying the price held through the gap.

export interface HistoryObservation {
  bookmakerKey: string;
  observedAt: string;
  point: number | null;
  americanPrice: number;
  bookmakerUpdatedAt: string | null;
  isLive: boolean;
}

export type ChangeType = "point" | "price" | "both";

export interface LineChange {
  bookmakerKey: string;
  type: ChangeType;
  /** The change occurred after this observation… */
  intervalStart: string;
  /** …and at or before this one. */
  intervalEnd: string;
  fromPoint: number | null;
  toPoint: number | null;
  fromPrice: number;
  toPrice: number;
  /** toPoint − fromPoint (null for moneylines). */
  pointDelta: number | null;
  /** True when the interval spans a data gap, so the timing is especially uncertain. */
  acrossGap: boolean;
}

export interface DataGap {
  from: string;
  to: string;
  minutes: number;
}

export type SeriesPointKind = "first" | "change" | "gap-start" | "gap-end" | "last" | "observation";

export interface SeriesPoint {
  observedAt: string;
  point: number | null;
  americanPrice: number;
  kinds: SeriesPointKind[];
}

export interface BookSeries {
  bookmakerKey: string;
  observations: number;
  firstObservedAt: string | null;
  lastObservedAt: string | null;
  /** All observations ("all") or only first/last/changes/gap edges ("changes"). */
  points: SeriesPoint[];
  changes: LineChange[];
  gaps: DataGap[];
}

export type HistoryResolution = "changes" | "all";

export const DEFAULT_GAP_MINUTES = 12 * 60;

/**
 * Build one book's series. `observations` must belong to a single book, market, and
 * selection, sorted by observedAt ascending.
 */
export function buildBookSeries(
  observations: readonly HistoryObservation[],
  {
    gapMinutes = DEFAULT_GAP_MINUTES,
    resolution = "changes",
  }: { gapMinutes?: number; resolution?: HistoryResolution } = {},
): BookSeries {
  const bookmakerKey = observations[0]?.bookmakerKey ?? "";
  const changes: LineChange[] = [];
  const gaps: DataGap[] = [];
  const kindsByIndex = observations.map<SeriesPointKind[]>(() => []);

  observations.forEach((obs, i) => {
    if (obs.bookmakerKey !== bookmakerKey) {
      throw new RangeError("buildBookSeries expects observations from a single book");
    }
    if (i === 0) {
      kindsByIndex[0]!.push("first");
      return;
    }
    const prev = observations[i - 1]!;
    const minutes = (Date.parse(obs.observedAt) - Date.parse(prev.observedAt)) / 60_000;
    if (minutes < 0) throw new RangeError("observations must be sorted by observedAt");

    const acrossGap = minutes > gapMinutes;
    if (acrossGap) {
      gaps.push({ from: prev.observedAt, to: obs.observedAt, minutes: Math.round(minutes) });
      kindsByIndex[i - 1]!.push("gap-start");
      kindsByIndex[i]!.push("gap-end");
    }

    const pointChanged = obs.point !== prev.point;
    const priceChanged = obs.americanPrice !== prev.americanPrice;
    if (pointChanged || priceChanged) {
      kindsByIndex[i]!.push("change");
      changes.push({
        bookmakerKey,
        type: pointChanged && priceChanged ? "both" : pointChanged ? "point" : "price",
        intervalStart: prev.observedAt,
        intervalEnd: obs.observedAt,
        fromPoint: prev.point,
        toPoint: obs.point,
        fromPrice: prev.americanPrice,
        toPrice: obs.americanPrice,
        pointDelta:
          obs.point !== null && prev.point !== null ? round1(obs.point - prev.point) : null,
        acrossGap,
      });
    }
  });
  if (observations.length > 1) kindsByIndex[observations.length - 1]!.push("last");

  const points: SeriesPoint[] = [];
  observations.forEach((obs, i) => {
    const kinds = kindsByIndex[i]!;
    if (resolution === "changes" && kinds.length === 0) return;
    points.push({
      observedAt: obs.observedAt,
      point: obs.point,
      americanPrice: obs.americanPrice,
      kinds: kinds.length > 0 ? kinds : ["observation"],
    });
  });

  return {
    bookmakerKey,
    observations: observations.length,
    firstObservedAt: observations[0]?.observedAt ?? null,
    lastObservedAt: observations.at(-1)?.observedAt ?? null,
    points,
    changes,
    gaps,
  };
}

/** Group mixed-book observations (any order) into per-book series, keyed by book. */
export function buildSeriesByBook(
  observations: readonly HistoryObservation[],
  options?: { gapMinutes?: number; resolution?: HistoryResolution },
): BookSeries[] {
  const byBook = new Map<string, HistoryObservation[]>();
  for (const obs of observations) {
    const list = byBook.get(obs.bookmakerKey) ?? [];
    list.push(obs);
    byBook.set(obs.bookmakerKey, list);
  }
  return [...byBook.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, list]) =>
      buildBookSeries(
        [...list].sort((a, b) => a.observedAt.localeCompare(b.observedAt)),
        options,
      ),
    );
}

const round1 = (n: number) => Math.round(n * 10) / 10;
