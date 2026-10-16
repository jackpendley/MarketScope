// Converts one provider event into application-domain quotes.
//
// The normalizer is the boundary between The Odds API's nested JSON and the rest
// of MarketScope. Rules (see docs/DATA_DICTIONARY.md):
// - HOME/AWAY come from exact equality with the event's home_team/away_team.
//   Never alphabetical, never fuzzy: an unrecognized name is reported and dropped.
// - Spread signs are preserved exactly as the book posted them.
// - Moneyline points are always null.
// - Invalid values are reported as issues, never repaired or invented.

import { isValidAmericanOdds } from "../../odds";
import {
  MARKETS,
  SELECTIONS_BY_MARKET,
  isMarket,
  type Market,
  type NormalizationIssue,
  type NormalizedEvent,
  type NormalizedQuote,
  type Selection,
} from "../../domain";
import type { ProviderEventOdds } from "./schema";

export interface NormalizeOptions {
  /** When our collector received the response (or the historical snapshot time). ISO 8601. */
  observedAt: string;
  /** Books we asked for. Anything else is reported as unexpected; absent ones as missing. */
  targetBookmakers: readonly string[];
  /** Markets we asked for. Defaults to all featured markets. */
  markets?: readonly Market[];
}

export interface NormalizedEventOdds {
  event: NormalizedEvent;
  quotes: NormalizedQuote[];
  issues: NormalizationIssue[];
}

type ProviderOutcome =
  ProviderEventOdds["bookmakers"][number]["markets"][number]["outcomes"][number];

export function normalizeEventOdds(
  raw: ProviderEventOdds,
  options: NormalizeOptions,
): NormalizedEventOdds {
  const requestedMarkets = options.markets ?? MARKETS;
  const observedAtMs = Date.parse(options.observedAt);
  if (Number.isNaN(observedAtMs)) {
    throw new RangeError(`observedAt is not a valid timestamp: ${options.observedAt}`);
  }

  const event: NormalizedEvent = {
    providerEventId: raw.id,
    sportKey: raw.sport_key,
    homeTeam: raw.home_team,
    awayTeam: raw.away_team,
    commenceTime: new Date(raw.commence_time).toISOString(),
  };
  const isLive = Date.parse(raw.commence_time) <= observedAtMs;

  const quotes: NormalizedQuote[] = [];
  const issues: NormalizationIssue[] = [];
  const report = (issue: Omit<NormalizationIssue, "providerEventId">) =>
    issues.push({ providerEventId: raw.id, ...issue });

  const seenBooks = new Set<string>();

  for (const book of raw.bookmakers) {
    if (!options.targetBookmakers.includes(book.key)) {
      report({
        code: "UNEXPECTED_BOOKMAKER",
        bookmakerKey: book.key,
        detail: `Bookmaker "${book.key}" was not requested`,
      });
      continue;
    }
    seenBooks.add(book.key);
    const seenMarkets = new Set<Market>();

    for (const market of book.markets) {
      if (!isMarket(market.key) || !requestedMarkets.includes(market.key)) {
        report({
          code: "UNEXPECTED_MARKET",
          bookmakerKey: book.key,
          market: market.key,
          detail: `Market "${market.key}" was not requested`,
        });
        continue;
      }
      const marketKey = market.key;
      seenMarkets.add(marketKey);

      const bookmakerUpdatedAt = parseOptionalTimestamp(market.last_update);
      if (market.last_update !== undefined && bookmakerUpdatedAt === null) {
        report({
          code: "INVALID_TIMESTAMP",
          bookmakerKey: book.key,
          market: marketKey,
          detail: `Unparseable last_update "${market.last_update}"; stored as null`,
        });
      }

      // Map each outcome to a selection, then drop selections that appear more than once
      // (we can't know which one is the main line).
      const bySelection = new Map<Selection, NormalizedQuote[]>();
      for (const outcome of market.outcomes) {
        const quote = normalizeOutcome(outcome, marketKey, raw, book.key, report);
        if (!quote) continue;
        const list = bySelection.get(quote.selection) ?? [];
        list.push({ ...quote, bookmakerUpdatedAt, observedAt: options.observedAt, isLive });
        bySelection.set(quote.selection, list);
      }

      const accepted: NormalizedQuote[] = [];
      for (const [selection, list] of bySelection) {
        if (list.length > 1) {
          report({
            code: "DUPLICATE_SELECTION",
            bookmakerKey: book.key,
            market: marketKey,
            detail: `${list.length} outcomes mapped to ${selection}; all dropped`,
          });
        } else {
          accepted.push(list[0]!);
        }
      }

      const expected = SELECTIONS_BY_MARKET[marketKey];
      const missing = expected.filter((s) => !accepted.some((q) => q.selection === s));
      if (missing.length > 0 && accepted.length > 0) {
        report({
          code: "INCOMPLETE_MARKET",
          bookmakerKey: book.key,
          market: marketKey,
          detail: `Missing ${missing.join(", ")}`,
        });
      }

      if (marketKey === "spreads") {
        const home = accepted.find((q) => q.selection === "HOME");
        const away = accepted.find((q) => q.selection === "AWAY");
        if (
          home &&
          away &&
          home.point !== null &&
          away.point !== null &&
          home.point !== -away.point
        ) {
          report({
            code: "INCONSISTENT_SPREAD",
            bookmakerKey: book.key,
            market: marketKey,
            detail: `Home ${home.point} and away ${away.point} are not opposite; kept as reported`,
          });
        }
      }

      quotes.push(...accepted);
    }

    for (const m of requestedMarkets) {
      if (!seenMarkets.has(m)) {
        report({
          code: "MARKET_MISSING",
          bookmakerKey: book.key,
          market: m,
          detail: `No ${m} market in feed for this book`,
        });
      }
    }
  }

  for (const key of options.targetBookmakers) {
    if (!seenBooks.has(key)) {
      report({
        code: "BOOKMAKER_MISSING",
        bookmakerKey: key,
        detail: `No data for "${key}" in feed`,
      });
    }
  }

  return { event, quotes, issues };
}

function normalizeOutcome(
  outcome: ProviderOutcome,
  market: Market,
  raw: ProviderEventOdds,
  bookmakerKey: string,
  report: (issue: Omit<NormalizationIssue, "providerEventId">) => void,
): Pick<
  NormalizedQuote,
  "providerEventId" | "bookmakerKey" | "market" | "selection" | "point" | "americanPrice"
> | null {
  const selection = mapSelection(market, outcome.name, raw);
  if (!selection) {
    report({
      code: "UNKNOWN_OUTCOME",
      bookmakerKey,
      market,
      detail: `Outcome "${outcome.name}" matches neither "${raw.home_team}" nor "${raw.away_team}"`,
    });
    return null;
  }

  if (!isValidAmericanOdds(outcome.price)) {
    report({
      code: "INVALID_PRICE",
      bookmakerKey,
      market,
      detail: `${selection} price ${outcome.price} is not a valid American price`,
    });
    return null;
  }

  let point: number | null = null;
  if (market === "h2h") {
    if (outcome.point !== undefined) {
      report({
        code: "UNEXPECTED_POINT",
        bookmakerKey,
        market,
        detail: `Moneyline ${selection} carried point ${outcome.point}; ignored`,
      });
    }
  } else {
    const valid =
      outcome.point !== undefined &&
      Number.isFinite(outcome.point) &&
      (market !== "totals" || outcome.point > 0);
    if (!valid) {
      report({
        code: "INVALID_POINT",
        bookmakerKey,
        market,
        detail: `${selection} has missing or invalid point ${String(outcome.point)}`,
      });
      return null;
    }
    point = outcome.point!;
  }

  return {
    providerEventId: raw.id,
    bookmakerKey,
    market,
    selection,
    point,
    americanPrice: outcome.price,
  };
}

function mapSelection(market: Market, name: string, raw: ProviderEventOdds): Selection | null {
  if (market === "totals") {
    const normalized = name.trim().toLowerCase();
    if (normalized === "over") return "OVER";
    if (normalized === "under") return "UNDER";
    return null;
  }
  if (name === raw.home_team) return "HOME";
  if (name === raw.away_team) return "AWAY";
  return null;
}

function parseOptionalTimestamp(value: string | undefined): string | null {
  if (value === undefined) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : new Date(ms).toISOString();
}
