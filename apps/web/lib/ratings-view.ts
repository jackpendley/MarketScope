// View logic for the MarketScope Ratings pages (MS-033). Pure: no Next.js or database imports.
import type { RatingRow, RatingWeek } from "@marketscope/db";

export const SORT_KEYS = [
  "adjEm",
  "adjO",
  "adjD",
  "adjSt",
  "adjPace",
  "luck",
  "sos",
  "team",
] as const;
export type SortKey = (typeof SORT_KEYS)[number];

/** Each sortable column sorts by its rank (1 = best, so AdjD's 1 is the lowest points allowed). */
const RANK_OF: Record<Exclude<SortKey, "team">, keyof RatingRow> = {
  adjEm: "adjEmRank",
  adjO: "adjORank",
  adjD: "adjDRank",
  adjSt: "adjStRank",
  adjPace: "adjPaceRank",
  luck: "luckRank",
  sos: "sosRank",
};

export interface RatingsQuery {
  season: number | null;
  week: number | null;
  sort: SortKey;
  conference: string | null;
}

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export function parseRatingsQuery(sp: Record<string, string | string[] | undefined>): RatingsQuery {
  const int = (v: string | undefined) =>
    v !== undefined && /^\d{1,4}$/.test(v) ? Number(v) : null;
  const sort = one(sp.sort);
  const conf = one(sp.conf);
  return {
    season: int(one(sp.season)),
    week: int(one(sp.week)),
    sort: (SORT_KEYS as readonly string[]).includes(sort ?? "") ? (sort as SortKey) : "adjEm",
    conference: conf === "AFC" || conf === "NFC" ? conf : null,
  };
}

/**
 * The snapshot to show: the requested one if it exists; otherwise the latest week of the requested
 * season, or the latest snapshot overall.
 */
export function resolveWeek(
  weeks: RatingWeek[],
  q: Pick<RatingsQuery, "season" | "week">,
): RatingWeek | null {
  if (weeks.length === 0) return null;
  const exact = weeks.find((w) => w.season === q.season && w.week === q.week);
  if (exact) return exact;
  const inSeason = weeks.filter((w) => w.season === q.season);
  return (inSeason.length ? inSeason : weeks).at(-1) ?? null;
}

export function sortRatings(rows: RatingRow[], sort: SortKey): RatingRow[] {
  const out = [...rows];
  if (sort === "team") return out.sort((a, b) => a.fullName.localeCompare(b.fullName));
  const key = RANK_OF[sort];
  return out.sort((a, b) => {
    const ra = (a[key] as number | null) ?? Number.POSITIVE_INFINITY;
    const rb = (b[key] as number | null) ?? Number.POSITIVE_INFINITY;
    return ra - rb || a.adjEmRank - b.adjEmRank;
  });
}

/** NFL week names: preseason prior, regular season, then the playoff rounds (18 weeks from 2021). */
export function weekLabel(season: number, week: number): string {
  if (week === 0) return "Preseason";
  const regular = season >= 2021 ? 18 : 17;
  if (week <= regular) return `Week ${week}`;
  return (
    ["Wild Card", "Divisional", "Conference", "Super Bowl"][week - regular - 1] ?? `Week ${week}`
  );
}

/**
 * Rank shading on a diverging scale (accent for the top, danger for the bottom, neutral middle).
 * Always rendered next to the rank number, so color is never the only signal.
 */
export function rankTone(rank: number | null, n: number): string {
  if (rank === null || n < 4) return "";
  const q = (rank - 0.5) / n;
  if (q < 0.125) return "bg-accent/30";
  if (q < 0.25) return "bg-accent/15";
  if (q > 0.875) return "bg-danger/30";
  if (q > 0.75) return "bg-danger/15";
  return "";
}

/** Secondary text on a rank cell: muted grey fails contrast on the tinted tones, so tinted cells
 * use the foreground at 85% (WCAG AA, checked by e2e/a11y.spec.ts). */
export function rankText(rank: number | null, n: number): string {
  return rankTone(rank, n) ? "text-fg/85" : "text-muted";
}

export const signed = (v: number | null, digits = 1) =>
  v === null || !Number.isFinite(v)
    ? "–"
    : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}`;

export const fixed = (v: number | null, digits = 2) =>
  v === null || !Number.isFinite(v) ? "–" : v.toFixed(digits);

export function record(r: Pick<RatingRow, "wins" | "losses" | "ties">): string {
  return `${r.wins}-${r.losses}${r.ties ? `-${r.ties}` : ""}`;
}

/** Ranks of a value across the league (1 = best), for Five Factors computed on the page. */
export function rankBy<T>(
  rows: T[],
  value: (r: T) => number | null,
  higherIsBetter: boolean,
): Map<T, number | null> {
  const vals = rows.map((r) => [r, value(r)] as const);
  const ranked = vals
    .filter(([, v]) => v !== null && Number.isFinite(v))
    .sort((a, b) =>
      higherIsBetter ? (b[1] as number) - (a[1] as number) : (a[1] as number) - (b[1] as number),
    );
  const out = new Map<T, number | null>(vals.map(([r]) => [r, null]));
  ranked.forEach(([r, v], i) => {
    const firstIdx = ranked.findIndex(([, w]) => w === v);
    out.set(r, (firstIdx >= 0 ? firstIdx : i) + 1);
  });
  return out;
}

export function isSyntheticVersion(version: string): boolean {
  return version.toLowerCase().includes("synthetic");
}

export type PlaycallerTag = { label: string; note: string | null };

/**
 * The badge for a play-calling flag. `basis` is the row's playcaller_basis; a row calling both
 * sides holds "offense | defense". "rule" means no source names the play-caller (the coordinator is
 * assumed); "shared" means sources say two coaches split the calls.
 */
export function playcallerTag(basis: string | null, side: "offense" | "defense"): PlaycallerTag {
  const parts = (basis ?? "").split(" | ");
  const b = (side === "offense" ? parts[0] : parts[parts.length - 1]) ?? "";
  const label = `calls ${side}`;
  if (b === "rule")
    return {
      label: `${label} (assumed)`,
      note: `No source names the ${side} play-caller; the ${side === "offense" ? "offensive" : "defensive"} coordinator is assumed.`,
    };
  if (b === "shared")
    return {
      label: `${label} (shared)`,
      note: "Sources say two coaches split the calls; this is the one reported as primary.",
    };
  return { label, note: null };
}
