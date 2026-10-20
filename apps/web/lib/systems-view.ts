// View model for /systems (MS-044). The numbers come from research/src/marketscope_research/run_systems.py,
// which writes lib/generated/wong-teasers.json; this page never computes results itself.
// Everything here is a hypothetical backtest on closing lines, labelled as such on the page.

import catalogue from "./generated/systems-catalogue.json";
import data from "./generated/wong-teasers.json";

export const REPORT =
  "https://github.com/jackpendley/MarketScope/blob/main/research/reports/systems-wong-teasers.md";
export const PREREGISTRATION =
  "https://github.com/jackpendley/MarketScope/blob/main/research/PREREGISTRATION.md";

export type VariantKey = "V0" | "V1" | "V2";
export const VARIANT_KEYS: readonly VariantKey[] = ["V0", "V1", "V2"];
export const PRICES = Object.keys(data.breakEven)
  .map(Number)
  .sort((a, b) => b - a);

export const WONG = data;

export const pct = (x: number, digits = 1) => `${(100 * x).toFixed(digits)}%`;
export const signedPct = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(100 * x).toFixed(1)}%`;
export const signedUnits = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}`;

/** Which side of the break-even an interval falls on. */
export function versusBreakEven(low: number, high: number, breakEven: number) {
  if (low > breakEven) return "above";
  if (high < breakEven) return "below";
  return "includes";
}

/** Cumulative units per teaser in order, with the season each teaser belongs to. */
export function equityRows(variant: VariantKey): { n: number; units: number; season: number }[] {
  const v = data.variants[variant];
  return v.equity.map((units, i) => ({ n: i + 1, units, season: v.equitySeason[i]! }));
}

/** Indices where a new season starts (for axis ticks / labels). */
export function seasonStarts(variant: VariantKey): { n: number; season: number }[] {
  const rows = equityRows(variant);
  return rows.filter((r, i) => i === 0 || rows[i - 1]!.season !== r.season);
}

export const Y2026_SOURCES = ["nflverse close", "Caesars' closing line"] as const;
export function y2026(source: (typeof Y2026_SOURCES)[number], variant: VariantKey) {
  return data.y2026[`${source}|${variant}` as keyof typeof data.y2026];
}

/** The F1–F10 catalogue (Addendum F), from run_catalogue.py. */
export const CATALOGUE = catalogue;
export const CATALOGUE_REPORT =
  "https://github.com/jackpendley/MarketScope/blob/main/research/reports/systems-catalogue.md";
