// View model for the odds comparison table. Pure functions: no React, no I/O.

import {
  compareIdenticalMarketPrices,
  type BookmakerInfo,
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
      /** Best price among books offering this exact line (never set for in-play events). */
      isBest: boolean;
    }
  /** The book isn't in this event's feed at all. */
  | { kind: "book-missing" }
  /** The book is in the feed but doesn't list this market. */
  | { kind: "market-missing" }
  /** The market is listed, but this selection was absent or rejected by validation. */
  | { kind: "selection-missing" };

export interface BoardRow {
  market: Market;
  selection: Selection;
  label: string;
  cells: Record<string, BoardCell>;
}

export interface BoardColumn {
  book: BookmakerInfo;
  inFeed: boolean;
  /** Latest market-level update reported by the book for this event. */
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
  books: readonly BookmakerInfo[],
): EventBoard {
  const { event, quotes, issues } = odds;
  const isLive = quotes.some((q) => q.isLive);

  const missingMarkets = new Set(
    issues.filter((i) => i.code === "MARKET_MISSING").map((i) => `${i.bookmakerKey}|${i.market}`),
  );
  const booksInFeed = new Set(
    books
      .map((b) => b.key)
      .filter(
        (key) => !issues.some((i) => i.code === "BOOKMAKER_MISSING" && i.bookmakerKey === key),
      ),
  );

  const best = new Set<string>();
  if (!isLive) {
    for (const group of compareIdenticalMarketPrices(quotes)) {
      if (!group.comparable) continue;
      for (const key of group.bestBookmakerKeys)
        best.add(`${key}|${group.market}|${group.selection}`);
    }
  }

  const rows: BoardRow[] = ROW_ORDER.map(({ market, selection }) => {
    const cells: Record<string, BoardCell> = {};
    for (const book of books) {
      const quote = quotes.find(
        (q) => q.bookmakerKey === book.key && q.market === market && q.selection === selection,
      );
      if (quote) {
        cells[book.key] = {
          kind: "quote",
          point: quote.point,
          americanPrice: quote.americanPrice,
          isBest: best.has(`${book.key}|${market}|${selection}`),
        };
      } else if (!booksInFeed.has(book.key)) {
        cells[book.key] = { kind: "book-missing" };
      } else if (missingMarkets.has(`${book.key}|${market}`)) {
        cells[book.key] = { kind: "market-missing" };
      } else {
        cells[book.key] = { kind: "selection-missing" };
      }
    }
    return { market, selection, label: rowLabel(selection, event.homeTeam, event.awayTeam), cells };
  });

  const columns: BoardColumn[] = books.map((book) => {
    const updates = quotes
      .filter((q) => q.bookmakerKey === book.key && q.bookmakerUpdatedAt !== null)
      .map((q) => q.bookmakerUpdatedAt!)
      .sort();
    return { book, inFeed: booksInFeed.has(book.key), latestUpdate: updates.at(-1) ?? null };
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
