// Market state at a chosen time T, as a board-style view model. Pure, no React.

import {
  calculateBookDispersion,
  getBookmakerInfo,
  stateAt,
  type BoardBook,
  type BookStateAt,
  type Dispersion,
  type HistoryObservation,
  type Market,
  type Selection,
} from "@marketscope/shared";

export interface ReplaySelectionInput {
  selection: Selection;
  label: string;
  observations: HistoryObservation[];
}

export interface ReplayCell {
  status: BookStateAt["status"];
  point: number | null;
  americanPrice: number | null;
  observedAt: string | null;
  ageMinutes: number | null;
}

export interface ReplayColumn {
  book: BoardBook;
  feedKey: string | null;
  fallbackLabel: string | null;
}

export interface ReplayView {
  at: string;
  columns: ReplayColumn[];
  rows: { selection: Selection; label: string; cells: Record<string, ReplayCell> }[];
  /** Median line across fresh displayed books (spreads: first row's side; totals: the total). */
  consensus: { point: number; books: number } | null;
  dispersion: Dispersion | null;
  freshBooks: number;
}

const MIN_CONSENSUS_BOOKS = 3;

export function buildReplayView(
  selections: readonly ReplaySelectionInput[],
  {
    at,
    books,
    market,
    freshnessMinutes,
  }: { at: string; books: readonly BoardBook[]; market: Market; freshnessMinutes: number },
): ReplayView {
  const feeds = [...new Set(books.flatMap((b) => b.feeds))];
  const states = selections.map((s) => ({
    ...s,
    byFeed: new Map(
      stateAt(s.observations, at, { freshnessMinutes, bookmakerKeys: feeds }).map((st) => [
        st.bookmakerKey,
        st,
      ]),
    ),
  }));

  // One feed per board book: prefer a feed that is fresh at T, else one with any data.
  const statusOf = (feed: string) =>
    states.reduce<BookStateAt["status"]>((best, s) => {
      const st = s.byFeed.get(feed)?.status ?? "none";
      return best === "fresh" || st === "fresh"
        ? "fresh"
        : best === "stale" || st === "stale"
          ? "stale"
          : "none";
    }, "none");
  const columns: ReplayColumn[] = books.map((book) => {
    const feedKey =
      book.feeds.find((f) => statusOf(f) === "fresh") ??
      book.feeds.find((f) => statusOf(f) !== "none") ??
      null;
    const fallback = feedKey !== null && feedKey !== book.feeds[0];
    const name = feedKey ? (getBookmakerInfo(feedKey)?.displayName ?? feedKey) : "";
    return {
      book,
      feedKey,
      fallbackLabel: fallback ? (name.match(/\(([^)]+)\)$/)?.[1] ?? feedKey) : null,
    };
  });

  const rows = states.map((s) => ({
    selection: s.selection,
    label: s.label,
    cells: Object.fromEntries(
      columns.map((col): [string, ReplayCell] => {
        const st = col.feedKey ? s.byFeed.get(col.feedKey) : undefined;
        return [
          col.book.id,
          {
            status: st?.status ?? "none",
            point: st?.observation?.point ?? null,
            americanPrice: st?.observation?.americanPrice ?? null,
            observedAt: st?.observation?.observedAt ?? null,
            ageMinutes: st?.ageMinutes ?? null,
          },
        ];
      }),
    ),
  }));

  // Consensus and dispersion use the first row (home side for spreads, Over for totals),
  // fresh cells only. Moneylines have no line to summarize.
  const freshPoints =
    market === "h2h" || rows.length === 0
      ? []
      : Object.values(rows[0]!.cells)
          .filter((c) => c.status === "fresh" && c.point !== null)
          .map((c) => c.point!);
  const consensusPoint = freshPoints.length >= MIN_CONSENSUS_BOOKS ? median(freshPoints) : null;

  return {
    at,
    columns,
    rows,
    consensus:
      consensusPoint === null ? null : { point: consensusPoint, books: freshPoints.length },
    dispersion:
      consensusPoint === null ? null : calculateBookDispersion(freshPoints, consensusPoint),
    freshBooks:
      rows.length === 0
        ? 0
        : Object.values(rows[0]!.cells).filter((c) => c.status === "fresh").length,
  };
}

/** Distinct observation times across all selections, ascending: the replay cursor stops. */
export function snapshotTimes(selections: readonly ReplaySelectionInput[]): string[] {
  return [...new Set(selections.flatMap((s) => s.observations.map((o) => o.observedAt)))].sort();
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
}
