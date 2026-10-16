// American odds math.
//
// Conventions:
// - Negative odds −A: risk A to win 100. Positive odds +A: risk 100 to win A.
// - Decimal odds = total return per 1 unit staked (stake included).
// - Invalid American odds (see isValidAmericanOdds) throw RangeError.
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

function assertValidAmerican(american: number): void {
  if (!isValidAmericanOdds(american)) {
    throw new RangeError(`invalid American odds: ${american}`);
  }
}

/** Raw implied probability: −A → A/(A+100), +A → 100/(A+100). −110 → 0.5238…, +150 → 0.4. */
export function americanToImpliedProbability(american: number): number {
  assertValidAmerican(american);
  return american < 0 ? -american / (-american + 100) : 100 / (american + 100);
}

/** −110 → 1.9090…, +150 → 2.5, ±100 → 2.0. */
export function americanToDecimal(american: number): number {
  assertValidAmerican(american);
  return american < 0 ? 1 + 100 / -american : 1 + american / 100;
}

/**
 * 2.5 → 150, 1.5 → −200, 2.0 → 100 (even money is written as +100).
 * Rounds to the nearest integer. Throws RangeError unless decimal > 1.
 */
export function decimalToAmerican(decimal: number): number {
  if (!Number.isFinite(decimal) || decimal <= 1) {
    throw new RangeError(`decimal odds must be a finite number > 1, got ${decimal}`);
  }
  return decimal >= 2 ? Math.round((decimal - 1) * 100) : Math.round(-100 / (decimal - 1));
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
