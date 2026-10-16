// View model for the odds comparison table. Pure functions: no React, no I/O.

import {
  calculateConsensusSpread,
  compareIdenticalMarketPrices,
  getBookmakerInfo,
  type BoardBook,
  type ConsensusResult,
  type Market,
  type NormalizationIssue,
  type NormalizedEvent,
  type NormalizedQuote,
  type Selection,
} from "@marketscope/shared";

export type BoardCell =
  | {
      kind: "quote";
      point: number | null;
      americanPrice: number;
      /** Best price among current columns offering this exact line (never for in-play or stale). */
      isBest: boolean;
      /** The book was absent from the event's newest snapshot; this is its last-seen price. */
      stale: boolean;
      observedAt: string;
    }
  /** None of the column's feeds have data for this event. */
  | { kind: "book-missing" }
  /** The displayed feed has data for this event but not for this market. */
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
  /** The feed displayed for this event, or null if no feed has data. */
  feedKey: string | null;
  /** Label when the displayed feed isn't the column's preferred one (e.g. "IN feed"). */
  fallbackLabel: string | null;
  /** True when the displayed feed has no quotes in the event's newest snapshot. */
  stale: boolean;
  /** Latest market-level update reported by the displayed feed. */
  latestUpdate: string | null;
}

export interface EventBoard {
  /** Internal event id when the board comes from the database. */
  gameId: string | null;
  providerEventId: string;
  homeTeam: string;
  awayTeam: string;
  commenceTime: string;
  isLive: boolean;
  /** Newest observation time across all quotes for this event. */
  latestObservedAt: string | null;
  columns: BoardColumn[];
  rows: BoardRow[];
  /** Median home spread across current, pregame, displayed feeds (null below 3 books). */
  consensus: ConsensusResult;
  issues: NormalizationIssue[];
}

export interface BoardInput {
  gameId?: string | null;
  event: NormalizedEvent;
  quotes: NormalizedQuote[];
  issues?: NormalizationIssue[];
}

const ROW_ORDER: { market: Market; selection: Selection }[] = [
  { market: "spreads", selection: "AWAY" },
  { market: "spreads", selection: "HOME" },
  { market: "h2h", selection: "AWAY" },
  { market: "h2h", selection: "HOME" },
  { market: "totals", selection: "OVER" },
  { market: "totals", selection: "UNDER" },
];

export function buildEventBoard(input: BoardInput, books: readonly BoardBook[]): EventBoard {
  const { event, quotes } = input;
  const issues = input.issues ?? [];
  const isLive = quotes.some((q) => q.isLive);
  const latestObservedAt = quotes.reduce<string | null>(
    (max, q) => (max === null || q.observedAt > max ? q.observedAt : max),
    null,
  );
  const isCurrent = (q: NormalizedQuote) => q.observedAt === latestObservedAt;

  const feedsWithData = new Set([
    ...quotes.map((q) => q.bookmakerKey),
    ...issues.filter((i) => i.code !== "BOOKMAKER_MISSING").map((i) => i.bookmakerKey),
  ]);
  const feedsCurrent = new Set(quotes.filter(isCurrent).map((q) => q.bookmakerKey));

  const columns: BoardColumn[] = books.map((book) => {
    // Prefer a feed present in the newest snapshot; otherwise the first with any data.
    const feedKey =
      book.feeds.find((f) => feedsCurrent.has(f)) ??
      book.feeds.find((f) => feedsWithData.has(f)) ??
      null;
    const updates = quotes
      .filter((q) => q.bookmakerKey === feedKey && q.bookmakerUpdatedAt !== null)
      .map((q) => q.bookmakerUpdatedAt!)
      .sort();
    const isFallback = feedKey !== null && feedKey !== book.feeds[0];
    return {
      book,
      feedKey,
      fallbackLabel: isFallback ? fallbackLabel(feedKey) : null,
      stale:
        feedKey !== null &&
        quotes.some((q) => q.bookmakerKey === feedKey) &&
        !feedsCurrent.has(feedKey),
      latestUpdate: updates.at(-1) ?? null,
    };
  });

  // Only each column's displayed feed participates, so a book with two feeds can't be
  // counted twice; only current (newest-snapshot) quotes are compared.
  const displayedFeeds = new Set(columns.map((c) => c.feedKey).filter((k) => k !== null));
  const displayedQuotes = quotes.filter((q) => displayedFeeds.has(q.bookmakerKey));
  const comparableQuotes = displayedQuotes.filter(isCurrent);

  const best = new Set<string>();
  if (!isLive) {
    for (const group of compareIdenticalMarketPrices(comparableQuotes)) {
      if (!group.comparable) continue;
      for (const key of group.bestBookmakerKeys) {
        best.add(`${key}|${group.market}|${group.selection}`);
      }
    }
  }

  const consensus: ConsensusResult = isLive
    ? { homePoint: null, bookmakerKeys: [], reason: "game has started" }
    : calculateConsensusSpread(comparableQuotes);

  const rows: BoardRow[] = ROW_ORDER.map(({ market, selection }) => {
    const cells: Record<string, BoardCell> = {};
    for (const { book, feedKey } of columns) {
      const feedQuotes = displayedQuotes.filter((q) => q.bookmakerKey === feedKey);
      const quote = feedQuotes.find((q) => q.market === market && q.selection === selection);
      if (quote) {
        const stale = !isCurrent(quote);
        cells[book.id] = {
          kind: "quote",
          point: quote.point,
          americanPrice: quote.americanPrice,
          isBest: !stale && best.has(`${feedKey}|${market}|${selection}`),
          stale,
          observedAt: quote.observedAt,
        };
      } else if (feedKey === null) {
        cells[book.id] = { kind: "book-missing" };
      } else if (!feedQuotes.some((q) => q.market === market)) {
        cells[book.id] = { kind: "market-missing" };
      } else {
        cells[book.id] = { kind: "selection-missing" };
      }
    }
    return { market, selection, label: rowLabel(selection, event.homeTeam, event.awayTeam), cells };
  });

  return {
    gameId: input.gameId ?? null,
    providerEventId: event.providerEventId,
    homeTeam: event.homeTeam,
    awayTeam: event.awayTeam,
    commenceTime: event.commenceTime,
    isLive,
    latestObservedAt,
    columns,
    rows,
    consensus,
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
