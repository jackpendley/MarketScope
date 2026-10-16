import type { Market, NormalizedQuote, Selection } from "./domain";
import { americanToDecimal } from "./odds";

export interface PriceComparisonGroup {
  market: Market;
  selection: Selection;
  /** The exact line shared by every quote in the group (null for moneylines). */
  point: number | null;
  quotes: NormalizedQuote[];
  /** Highest payout in the group, as an American price. */
  bestPrice: number;
  /** Every book offering bestPrice (ties are all best). */
  bestBookmakerKeys: string[];
  /** A "best price" is only meaningful when at least two books offer this exact line. */
  comparable: boolean;
}

/**
 * Groups quotes by (market, selection, point) and finds the best price within
 * each group. Prices are ONLY compared when the line is identical: home −3.5 −110
 * and home −3 −115 are different bets and land in different groups.
 *
 * Expects quotes for a single event. Comparison uses decimal odds, so −105 beats −110
 * and +100 beats −105.
 */
export function compareIdenticalMarketPrices(
  quotes: readonly NormalizedQuote[],
): PriceComparisonGroup[] {
  const groups = new Map<string, NormalizedQuote[]>();
  for (const q of quotes) {
    const key = `${q.market}|${q.selection}|${q.point ?? "none"}`;
    const list = groups.get(key) ?? [];
    list.push(q);
    groups.set(key, list);
  }

  return [...groups.values()].map((group) => {
    const first = group[0]!;
    const bestDecimal = Math.max(...group.map((q) => americanToDecimal(q.americanPrice)));
    const best = group.filter((q) => americanToDecimal(q.americanPrice) === bestDecimal);
    return {
      market: first.market,
      selection: first.selection,
      point: first.point,
      quotes: group,
      bestPrice: best[0]!.americanPrice,
      bestBookmakerKeys: best.map((q) => q.bookmakerKey),
      comparable: new Set(group.map((q) => q.bookmakerKey)).size >= 2,
    };
  });
}
