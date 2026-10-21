// Turns per-book series into one Recharts dataset. Pure, no React.
//
// Rows exist at every observation time of any book. A book's value at a row is the value
// it last showed, held only WITHIN a continuous segment:
// - null before its first observation and after its last (never extrapolated),
// - null from just after a gap starts until the gap ends (the line breaks).
// Charts draw these as step-after lines with connectNulls=false.

import type { BookSeries } from "@marketscope/shared";

export type ChartField = "point" | "price";

export interface ChartRow {
  t: number;
  [bookmakerKey: string]: number | null;
}

/**
 * American odds on a continuous scale: −110 → −10, +110 → +10, ±100 → 0. Raw American
 * odds jump 200 between −101 and +101, which would exaggerate small moves through even money.
 */
export function americanToScale(price: number): number {
  return price < 0 ? price + 100 : price - 100;
}

export function scaleToAmerican(value: number): number {
  return value < 0 ? value - 100 : value + 100;
}

export function formatScaledAmerican(value: number): string {
  if (Math.abs(value) < 0.5) return "EVEN";
  const american = Math.round(scaleToAmerican(value));
  return american > 0 ? `+${american}` : `${american}`;
}

export function buildChartRows(
  series: readonly BookSeries[],
  field: ChartField,
): { rows: ChartRow[]; keys: string[] } {
  const breakTimes = new Map<string, { start: number; end: number }[]>();
  const times = new Set<number>();
  for (const s of series) {
    for (const p of s.points) times.add(Date.parse(p.observedAt));
    const breaks = s.gaps.map((g) => ({ start: Date.parse(g.from) + 1, end: Date.parse(g.to) }));
    breaks.forEach((b) => times.add(b.start));
    breakTimes.set(s.bookmakerKey, breaks);
  }
  const sorted = [...times].sort((a, b) => a - b);

  const rows: ChartRow[] = sorted.map((t) => ({ t }));
  for (const s of series) {
    const values = new Map(
      s.points.map((p) => [
        Date.parse(p.observedAt),
        field === "point" ? p.point : americanToScale(p.americanPrice),
      ]),
    );
    const first = s.firstObservedAt ? Date.parse(s.firstObservedAt) : Infinity;
    const last = s.lastObservedAt ? Date.parse(s.lastObservedAt) : -Infinity;
    const breaks = breakTimes.get(s.bookmakerKey) ?? [];
    let held: number | null = null;

    for (const row of rows) {
      const { t } = row;
      if (values.has(t)) held = values.get(t)!;
      const inBreak = breaks.some((b) => t >= b.start && t < b.end);
      row[s.bookmakerKey] = t < first || t > last || inBreak ? null : held;
    }
  }
  return { rows, keys: series.map((s) => s.bookmakerKey) };
}

/** Fixed color per feed (entity, never rank), validated for the dark surface. */
export const FEED_COLORS: Readonly<Record<string, string>> = {
  draftkings: "#3987e5",
  fanduel: "#d95926",
  betmgm: "#199e70",
  williamhill_us: "#c98500",
  hardrockbet_az: "#d55181",
  hardrockbet: "#008300",
  // Reference book (not on the board): categorical slot 7, validated adjacent to slot 6.
  pinnacle: "#9085e9",
  // Market makers in the minute-level panel only (drawn dashed, like Pinnacle there).
  circa: "#2fb3a6",
  bookmaker_eu: "#c7ced8",
  // Exchanges (MS-051), hidden by default in the minute-level panel.
  novig: "#e0a35b",
  prophetx: "#b07cd8",
  kalshi: "#7bc96f",
};

/**
 * Axis ticks on a fixed step (0.5 for spreads/totals, 5 or 10 on the price scale) with
 * one step of padding, so ticks land on values books actually post.
 */
export function axisTicks(
  rows: readonly ChartRow[],
  keys: readonly string[],
  step: number,
  maxTicks = 9,
): { domain: [number, number]; ticks: number[] } | null {
  const values = rows
    .flatMap((r) => keys.map((k) => r[k]))
    .filter((v): v is number => typeof v === "number");
  if (values.length === 0) return null;
  let s = step;
  const lo = () => Math.floor(Math.min(...values) / s) * s - s;
  const hi = () => Math.ceil(Math.max(...values) / s) * s + s;
  while ((hi() - lo()) / s + 1 > maxTicks) s *= 2;
  const ticks: number[] = [];
  for (let v = lo(); v <= hi() + 1e-9; v += s) ticks.push(Math.round(v * 100) / 100);
  return { domain: [lo(), hi()], ticks };
}

/**
 * A text alternative for a history chart (screen readers): each book's first and last value and
 * how many times it changed, e.g. "DraftKings −3 to −3.5 (1 change); FanDuel −3 throughout".
 */
export function seriesSummary(
  series: readonly (BookSeries & { displayName: string })[],
  field: ChartField,
  format: (v: number) => string,
): string {
  const parts = series.flatMap((s) => {
    const values = s.points
      .map((p) => (field === "point" ? p.point : americanToScale(p.americanPrice)))
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (values.length === 0) return [];
    const changes = values.slice(1).filter((v, i) => v !== values[i]).length;
    const first = format(values[0]!);
    const last = format(values[values.length - 1]!);
    if (changes === 0) return [`${s.displayName} ${first} throughout`];
    return [`${s.displayName} ${first} to ${last} (${changes} change${changes === 1 ? "" : "s"})`];
  });
  return parts.length ? parts.join("; ") + "." : "No observations.";
}
