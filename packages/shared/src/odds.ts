// American odds math.
//
// ┌──────────────────────────────────────────────────────────────────────────┐
// │ EXERCISE (yours): implement the three functions marked TODO(you).         │
// │ Run `pnpm --filter @marketscope/shared test` until odds.test.ts is green. │
// │ Rules:                                                                    │
// │  • Invalid American odds (see isValidAmericanOdds) → throw RangeError.    │
// │  • Negative odds −A: implied = A / (A + 100); positive +A: 100 / (A+100). │
// │  • Decimal odds = total return per 1 unit staked (stake included).       │
// │  • decimalToAmerican rounds to the nearest integer; 2.0 maps to +100.    │
// └──────────────────────────────────────────────────────────────────────────┘
//
// Raw implied probability includes the bookmaker's margin. It is NOT a
// calibrated real-world win probability.

/**
 * A valid American price is an integer with |price| >= 100.
 * (−100 and +100 are the same price: even money.)
 */
export function isValidAmericanOdds(american: number): boolean {
  return Number.isInteger(american) && Math.abs(american) >= 100;
}

/** TODO(you): −110 → 0.5238…, +150 → 0.4. Throws RangeError on invalid input. */
export function americanToImpliedProbability(american: number): number {
  throw new Error(`not implemented: americanToImpliedProbability(${american})`);
}

/** TODO(you): −110 → 1.9090…, +150 → 2.5. Throws RangeError on invalid input. */
export function americanToDecimal(american: number): number {
  throw new Error(`not implemented: americanToDecimal(${american})`);
}

/** TODO(you): 2.5 → 150, 1.5 → −200, 2.0 → 100. Throws RangeError unless decimal > 1. */
export function decimalToAmerican(decimal: number): number {
  throw new Error(`not implemented: decimalToAmerican(${decimal})`);
}

export interface Payout {
  /** Winnings excluding the returned stake. */
  profit: number;
  /** Stake plus profit. */
  totalReturn: number;
}

export function potentialPayout(stake: number, american: number): Payout {
  if (!Number.isFinite(stake) || stake <= 0) {
    throw new RangeError(`stake must be a positive finite number, got ${stake}`);
  }
  const totalReturn = stake * americanToDecimal(american);
  return { profit: totalReturn - stake, totalReturn };
}

/**
 * Bookmaker margin for a complete set of mutually exclusive outcomes
 * (e.g. both sides of a spread at the SAME point): sum of raw implied
 * probabilities minus 1. −110/−110 → ≈ 0.0476 (4.76%).
 *
 * Only meaningful when the prices form a valid pair (same book, market, and line).
 */
export function overround(prices: readonly number[]): number {
  if (prices.length < 2) {
    throw new RangeError("overround needs at least two outcome prices");
  }
  return prices.reduce((sum, p) => sum + americanToImpliedProbability(p), 0) - 1;
}
