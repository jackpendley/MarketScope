// View model for the odds comparison table. Pure functions: no React, no I/O.

import {
  compareIdenticalMarketPrices,
  getBookmakerInfo,
  type BoardBook,
  type Market,
  type NormalizationIssue,
  type NormalizedEventOdds,
  type Selection,
} from "@marketscope/shared";

export type BoardCell =
  | {
      kind: "quote";
      point: number | null;
      americanPrice: number;
      /** Best price among columns offering this exact line (never set for in-play events). */
      isBest: boolean;
    }
  /** None of the column's feeds are in this event's data. */
  | { kind: "book-missing" }
  /** The displayed feed is present but doesn't list this market. */
  | { kind: "market-missing" }
  /** The market is listed, but this selection was absent or rejected by validation. */
  | { kind: "selection-missing" };

export interface BoardRow {
  market: Market;
  selection: Selection;
  label: string;
  /** Keyed by BoardBook.id. */
  cells: Record<string, BoardCell>;
}

export interface BoardColumn {
  book: BoardBook;
  /** The feed displayed for this event: the first preferred feed with data, or null. */
  feedKey: string | null;
  /** Label for the displayed feed when it isn't the column's primary feed (e.g. "IN feed"). */
  fallbackLabel: string | null;
  /** Latest market-level update reported by the displayed feed for this event. */
  latestUpdate: string | null;
}

export interface EventBoard {
  providerEventId: string;
  homeTeam: string;
  awayTeam: string;
  commenceTime: string;
  isLive: boolean;
  columns: BoardColumn[];
  rows: BoardRow[];
  issues: NormalizationIssue[];
}

const ROW_ORDER: { market: Market; selection: Selection }[] = [
  { market: "spreads", selection: "AWAY" },
  { market: "spreads", selection: "HOME" },
  { market: "h2h", selection: "AWAY" },
  { market: "h2h", selection: "HOME" },
  { market: "totals", selection: "OVER" },
  { market: "totals", selection: "UNDER" },
];

export function buildEventBoard(
  odds: NormalizedEventOdds,
  books: readonly BoardBook[],
): EventBoard {
  const { event, quotes, issues } = odds;
  const isLive = quotes.some((q) => q.isLive);

  // A feed "has data" if it produced any quote or was present with a missing market.
  const feedsWithData = new Set([
    ...quotes.map((q) => q.bookmakerKey),
    ...issues.filter((i) => i.code !== "BOOKMAKER_MISSING").map((i) => i.bookmakerKey),
  ]);

  const columns: BoardColumn[] = books.map((book) => {
    const feedKey = book.feeds.find((f) => feedsWithData.has(f)) ?? null;
    const updates = quotes
      .filter((q) => q.bookmakerKey === feedKey && q.bookmakerUpdatedAt !== null)
      .map((q) => q.bookmakerUpdatedAt!)
      .sort();
    const isFallback = feedKey !== null && feedKey !== book.feeds[0];
    return {
      book,
      feedKey,
      fallbackLabel: isFallback ? fallbackLabel(feedKey) : null,
      latestUpdate: updates.at(-1) ?? null,
    };
  });

  // Only the displayed feed of each column takes part in the comparison, so a
  // book with two feeds can't be counted twice.
  const displayedFeeds = new Set(columns.map((c) => c.feedKey).filter((k) => k !== null));
  const displayedQuotes = quotes.filter((q) => displayedFeeds.has(q.bookmakerKey));

  const best = new Set<string>();
  if (!isLive) {
    for (const group of compareIdenticalMarketPrices(displayedQuotes)) {
      if (!group.comparable) continue;
      for (const key of group.bestBookmakerKeys) {
        best.add(`${key}|${group.market}|${group.selection}`);
      }
    }
  }

  const missingMarkets = new Set(
    issues.filter((i) => i.code === "MARKET_MISSING").map((i) => `${i.bookmakerKey}|${i.market}`),
  );

  const rows: BoardRow[] = ROW_ORDER.map(({ market, selection }) => {
    const cells: Record<string, BoardCell> = {};
    for (const { book, feedKey } of columns) {
      const quote = displayedQuotes.find(
        (q) => q.bookmakerKey === feedKey && q.market === market && q.selection === selection,
      );
      if (quote) {
        cells[book.id] = {
          kind: "quote",
          point: quote.point,
          americanPrice: quote.americanPrice,
          isBest: best.has(`${feedKey}|${market}|${selection}`),
        };
      } else if (feedKey === null) {
        cells[book.id] = { kind: "book-missing" };
      } else if (missingMarkets.has(`${feedKey}|${market}`)) {
        cells[book.id] = { kind: "market-missing" };
      } else {
        cells[book.id] = { kind: "selection-missing" };
      }
    }
    return { market, selection, label: rowLabel(selection, event.homeTeam, event.awayTeam), cells };
  });

  return {
    providerEventId: event.providerEventId,
    homeTeam: event.homeTeam,
    awayTeam: event.awayTeam,
    commenceTime: event.commenceTime,
    isLive,
    columns,
    rows,
    issues,
  };
}

function fallbackLabel(feedKey: string): string {
  const name = getBookmakerInfo(feedKey)?.displayName ?? feedKey;
  // "Hard Rock Bet (IN feed)" → "IN feed"
  return name.match(/\(([^)]+)\)$/)?.[1] ?? feedKey;
}

function rowLabel(selection: Selection, home: string, away: string): string {
  switch (selection) {
    case "HOME":
      return home;
    case "AWAY":
      return away;
    case "OVER":
      return "Over";
    case "UNDER":
      return "Under";
  }
}
