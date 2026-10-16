import type { Market } from "./domain";

/** −110 → "-110", 150 → "+150". */
export function formatAmericanOdds(american: number): string {
  return american > 0 ? `+${american}` : `${american}`;
}

/**
 * Spreads keep the book's sign ("+3.5", "-3", "PK" for 0); totals are unsigned ("47.5").
 * Moneylines have no point and render as an empty string.
 */
export function formatPoint(point: number | null, market: Market): string {
  if (point === null || market === "h2h") return "";
  if (market === "totals") return `${point}`;
  if (point === 0) return "PK";
  return point > 0 ? `+${point}` : `${point}`;
}
