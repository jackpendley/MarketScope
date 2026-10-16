// Application-domain types. Provider-specific shapes never leak past the normalizer;
// everything downstream (database, API, UI) speaks in these types.

export const MARKETS = ["h2h", "spreads", "totals"] as const;
export type Market = (typeof MARKETS)[number];

export const SELECTIONS = ["HOME", "AWAY", "OVER", "UNDER"] as const;
export type Selection = (typeof SELECTIONS)[number];

export const SELECTIONS_BY_MARKET: Readonly<Record<Market, readonly Selection[]>> = {
  h2h: ["HOME", "AWAY"],
  spreads: ["HOME", "AWAY"],
  totals: ["OVER", "UNDER"],
};

export const MARKET_LABELS: Readonly<Record<Market, string>> = {
  h2h: "Moneyline",
  spreads: "Spread",
  totals: "Total",
};

export function isMarket(value: string): value is Market {
  return (MARKETS as readonly string[]).includes(value);
}

export interface NormalizedEvent {
  providerEventId: string;
  sportKey: string;
  homeTeam: string;
  awayTeam: string;
  /** ISO 8601 UTC kickoff time as reported by the provider. */
  commenceTime: string;
}

/**
 * One bookmaker's price for one selection, as observed at a point in time.
 *
 * Timestamp semantics (do not conflate):
 * - bookmakerUpdatedAt: when the provider says this book's market last changed (may be null).
 * - observedAt: when our collector received the response (or the historical snapshot time).
 */
export interface NormalizedQuote {
  providerEventId: string;
  bookmakerKey: string;
  market: Market;
  selection: Selection;
  /** Spread or total line. Always null for moneylines. Spread sign is the book's own sign. */
  point: number | null;
  americanPrice: number;
  bookmakerUpdatedAt: string | null;
  observedAt: string;
  /** True when the event had already started at observedAt (in-play pricing). */
  isLive: boolean;
}

export const NORMALIZATION_ISSUE_CODES = [
  "BOOKMAKER_MISSING",
  "UNEXPECTED_BOOKMAKER",
  "MARKET_MISSING",
  "UNEXPECTED_MARKET",
  "INCOMPLETE_MARKET",
  "UNKNOWN_OUTCOME",
  "DUPLICATE_SELECTION",
  "INVALID_PRICE",
  "INVALID_POINT",
  "UNEXPECTED_POINT",
  "INCONSISTENT_SPREAD",
  "INVALID_TIMESTAMP",
] as const;
export type NormalizationIssueCode = (typeof NORMALIZATION_ISSUE_CODES)[number];

/** A data-quality finding. Issues are reported, never silently swallowed or "fixed" with invented data. */
export interface NormalizationIssue {
  code: NormalizationIssueCode;
  providerEventId: string;
  bookmakerKey?: string;
  market?: string;
  detail: string;
}
