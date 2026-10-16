import type { NormalizedQuote } from "./domain";

export const DEFAULT_MIN_CONSENSUS_BOOKS = 3;

export type ConsensusResult =
  | { homePoint: number; bookmakerKeys: string[] }
  | { homePoint: null; bookmakerKeys: string[]; reason: string };

/**
 * Consensus home spread: the MEDIAN of the home-team spread across books (one quote
 * per book). With an even count it averages the two middle values, so it can land
 * on a quarter point (e.g. −3.25) that no book actually offers. It is a summary
 * statistic, not a bettable line.
 *
 * Callers must pass only quotes that are comparable in time (same snapshot, not
 * stale, not in-play). Returns no consensus when fewer than `minBooks` books qualify,
 * rather than overstating agreement.
 */
export function calculateConsensusSpread(
  quotes: readonly NormalizedQuote[],
  { minBooks = DEFAULT_MIN_CONSENSUS_BOOKS }: { minBooks?: number } = {},
): ConsensusResult {
  const homeSpreads = quotes.filter(
    (q) => q.market === "spreads" && q.selection === "HOME" && q.point !== null,
  );
  const byBook = new Map<string, number>();
  for (const q of homeSpreads) {
    if (byBook.has(q.bookmakerKey)) {
      throw new RangeError(`multiple home spreads for ${q.bookmakerKey}; pass one quote per book`);
    }
    byBook.set(q.bookmakerKey, q.point!);
  }
  const bookmakerKeys = [...byBook.keys()].sort();
  if (byBook.size < minBooks) {
    return {
      homePoint: null,
      bookmakerKeys,
      reason: `${byBook.size} of the required ${minBooks} books reported a home spread`,
    };
  }
  const points = [...byBook.values()].sort((a, b) => a - b);
  const mid = Math.floor(points.length / 2);
  const homePoint = points.length % 2 === 1 ? points[mid]! : (points[mid - 1]! + points[mid]!) / 2;
  return { homePoint, bookmakerKeys };
}
