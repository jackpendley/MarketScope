// View logic for the Matchups page, the game-page model panel and the /model scorecard (MS-033b).
// Pure: no Next.js or database imports.
import type { RatingWeek, ScoredEstimate } from "@marketscope/db";

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
const int = (v: string | undefined) => (v !== undefined && /^\d{1,4}$/.test(v) ? Number(v) : null);

export function parseWeekQuery(sp: Record<string, string | string[] | undefined>): {
  season: number | null;
  week: number | null;
} {
  return { season: int(one(sp.season)), week: int(one(sp.week)) };
}

/** The requested week if offered; else the current (next unplayed) week; else the latest. */
export function resolveMatchupWeek(
  weeks: RatingWeek[],
  q: { season: number | null; week: number | null },
  current: RatingWeek | null,
): RatingWeek | null {
  const find = (w: { season: number | null; week: number | null } | null) =>
    w ? weeks.find((x) => x.season === w.season && x.week === w.week) : undefined;
  return find(q) ?? find(current) ?? weeks.at(-1) ?? null;
}

/** "KC by 3.5" from an expected home margin; "Even" inside a twentieth of a point. */
export function favoriteText(home: string, away: string, margin: number, digits = 1): string {
  if (Math.abs(margin) < 0.05) return "Even";
  return `${margin > 0 ? home : away} by ${Math.abs(margin).toFixed(digits)}`;
}

/** A home-oriented spread as posted, e.g. "KC −3.5" for −3.5 or "LV −2" for +2. */
export function spreadText(home: string, away: string, homeSpread: number): string {
  if (homeSpread === 0) return "Pick'em";
  const side = homeSpread < 0 ? home : away;
  return `${side} −${Math.abs(homeSpread).toString()}`;
}

export const percent = (p: number | null, digits = 0) =>
  p === null || !Number.isFinite(p) ? "–" : `${(100 * p).toFixed(digits)}%`;

/**
 * Game quality, 0-100: the average league percentile of the two teams' AdjEM ranks going in
 * (100 = both best in the league). Descriptive only, like KenPom's FanMatch.
 */
export function gameQuality(
  homeRank: number | null,
  awayRank: number | null,
  teams: number | null,
): number | null {
  if (homeRank === null || awayRank === null || teams === null || teams < 2) return null;
  const pct = (rank: number) => (teams - rank) / (teams - 1);
  return Math.round((100 * (pct(homeRank) + pct(awayRank))) / 2);
}

/** Excitement, 0-100: quality scaled by expected closeness (1 at a coin flip, 0 at a certainty). */
export function excitement(quality: number | null, pHome: number | null): number | null {
  if (quality === null || pHome === null) return null;
  return Math.round(quality * (1 - Math.abs(2 * pHome - 1)));
}

const CONTRIBUTION_LABELS: Record<string, string> = {
  ratings: "Team ratings",
  home: "Home field",
  qb: "Quarterbacks",
  absences: "Other absences",
};

export interface ContributionRow {
  key: string;
  label: string;
  /** Points toward the home team (negative = toward the away team). */
  value: number;
}

/** Margin contributions in a fixed order (known keys first), for the waterfall. */
export function contributionRows(contributions: Record<string, number>): ContributionRow[] {
  const known = Object.keys(CONTRIBUTION_LABELS);
  const keys = [
    ...known.filter((k) => k in contributions),
    ...Object.keys(contributions)
      .filter((k) => !known.includes(k))
      .sort(),
  ];
  return keys
    .filter((k) => Number.isFinite(contributions[k]))
    .map((k) => ({ key: k, label: CONTRIBUTION_LABELS[k] ?? k, value: contributions[k]! }));
}

/** No-vig home win probability from American moneylines (proportional normalization). */
export function noVigHomeProb(homeMl: number | null, awayMl: number | null): number | null {
  if (homeMl === null || awayMl === null || homeMl === 0 || awayMl === 0) return null;
  const implied = (ml: number) => (ml < 0 ? -ml / (-ml + 100) : 100 / (ml + 100));
  const h = implied(homeMl);
  const a = implied(awayMl);
  return h / (h + a);
}

/** Small deterministic PRNG (mulberry32) so the published CIs are reproducible. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;

/** 95% percentile CI for the mean of per-game values, resampling games with replacement. */
export function bootstrapMeanCi(values: number[], resamples = 2000, seed = 2026): [number, number] {
  const draw = rng(seed);
  const means: number[] = [];
  for (let b = 0; b < resamples; b++) {
    let s = 0;
    for (let i = 0; i < values.length; i++) s += values[Math.floor(draw() * values.length)]!;
    means.push(s / values.length);
  }
  means.sort((x, y) => x - y);
  return [means[Math.floor(0.025 * resamples)]!, means[Math.ceil(0.975 * resamples) - 1]!];
}

/** Games needed before the scorecard shows a confidence interval or a calibration table. */
export const MIN_CI_GAMES = 30;
export const MIN_CALIBRATION_GAMES = 50;

export interface PairedMetric {
  /** Games where both the model and the benchmark are available. */
  games: number;
  model: number;
  close: number;
  /** model − close (lower is better for both metrics, so negative favors the model). */
  diff: number;
  ci: [number, number] | null;
}

export interface WeekRow extends RatingWeek {
  games: number;
  modelMae: number;
  closeMae: number | null;
  cumulativeModelMae: number;
  cumulativeCloseMae: number | null;
}

export interface CalibrationBin {
  label: string;
  games: number;
  meanP: number;
  homeWinRate: number;
}

export interface Scorecard {
  games: number;
  modelMarginMae: number | null;
  /** The model favorite won (ties excluded). */
  favoriteWon: { won: number; decided: number };
  margin: PairedMetric | null;
  brier: PairedMetric | null;
  total: PairedMetric | null;
  weeks: WeekRow[];
  calibration: CalibrationBin[] | null;
}

function paired(model: number[], close: number[]): PairedMetric | null {
  if (model.length === 0) return null;
  const diffs = model.map((m, i) => m - close[i]!);
  return {
    games: model.length,
    model: mean(model),
    close: mean(close),
    diff: mean(diffs),
    ci: model.length >= MIN_CI_GAMES ? bootstrapMeanCi(diffs) : null,
  };
}

/** Live forward-test metrics: the model's last pre-kickoff estimate vs results and the close. */
export function scorecard(rows: ScoredEstimate[]): Scorecard {
  const margin = (r: ScoredEstimate) => r.homeFinal - r.awayFinal;
  const homeWin = (r: ScoredEstimate) => (margin(r) > 0 ? 1 : margin(r) < 0 ? 0 : 0.5);

  const withClose = rows.filter((r) => r.closeHomeSpread !== null);
  const marginMetric = paired(
    withClose.map((r) => Math.abs(r.expectedMargin - margin(r))),
    withClose.map((r) => Math.abs(-r.closeHomeSpread! - margin(r))),
  );
  const withProb = rows
    .map((r) => ({ r, p: noVigHomeProb(r.closeHomeMoneyline, r.closeAwayMoneyline) }))
    .filter((x): x is { r: ScoredEstimate; p: number } => x.p !== null);
  const brierMetric = paired(
    withProb.map(({ r }) => (r.pHome - homeWin(r)) ** 2),
    withProb.map(({ r, p }) => (p - homeWin(r)) ** 2),
  );
  const withTotal = rows.filter((r) => r.expectedTotal !== null && r.closeTotal !== null);
  const totalMetric = paired(
    withTotal.map((r) => Math.abs(r.expectedTotal! - (r.homeFinal + r.awayFinal))),
    withTotal.map((r) => Math.abs(r.closeTotal! - (r.homeFinal + r.awayFinal))),
  );

  const decided = rows.filter((r) => margin(r) !== 0 && r.expectedMargin !== 0);
  const won = decided.filter((r) => Math.sign(r.expectedMargin) === Math.sign(margin(r))).length;

  const weeks: WeekRow[] = [];
  const cumModel: number[] = [];
  const cumClose: number[] = [];
  for (const r of rows) {
    const modelErr = Math.abs(r.expectedMargin - margin(r));
    const closeErr = r.closeHomeSpread === null ? null : Math.abs(-r.closeHomeSpread - margin(r));
    cumModel.push(modelErr);
    if (closeErr !== null) cumClose.push(closeErr);
    let w = weeks.at(-1);
    if (!w || w.season !== r.season || w.week !== r.week) {
      w = {
        season: r.season,
        week: r.week,
        games: 0,
        modelMae: 0,
        closeMae: null,
        cumulativeModelMae: 0,
        cumulativeCloseMae: null,
      };
      weeks.push(w);
    }
    const closeN = w.closeMae === null ? 0 : w.games;
    w.modelMae = (w.modelMae * w.games + modelErr) / (w.games + 1);
    if (closeErr !== null) w.closeMae = ((w.closeMae ?? 0) * closeN + closeErr) / (closeN + 1);
    w.games += 1;
    w.cumulativeModelMae = mean(cumModel);
    w.cumulativeCloseMae = cumClose.length ? mean(cumClose) : null;
  }

  let calibration: CalibrationBin[] | null = null;
  if (rows.length >= MIN_CALIBRATION_GAMES) {
    const binOf = (p: number) => Math.min(4, Math.floor(p * 5));
    calibration = [0, 1, 2, 3, 4]
      .map((b) => {
        const bin = rows.filter((r) => binOf(r.pHome) === b);
        return {
          label: `${b * 20}–${b * 20 + 20}%`,
          games: bin.length,
          meanP: bin.length ? mean(bin.map((r) => r.pHome)) : 0,
          homeWinRate: bin.length ? mean(bin.map(homeWin)) : 0,
        };
      })
      .filter((b) => b.games > 0);
  }

  return {
    games: rows.length,
    modelMarginMae: rows.length
      ? mean(rows.map((r) => Math.abs(r.expectedMargin - margin(r))))
      : null,
    favoriteWon: { won, decided: decided.length },
    margin: marginMetric,
    brier: brierMetric,
    total: totalMetric,
    weeks,
    calibration,
  };
}

export interface Estimate {
  value: number;
  lo: number | null;
  hi: number | null;
}

export interface TestRecordRow {
  model: string;
  marginMae: Estimate | null;
  /** This model minus the nflverse close (negative = more accurate than the close). */
  vsClose: Estimate | null;
  /** ratings-v1 minus this model, paired on the same games (null for ratings-v1 itself). */
  versionVs: Estimate | null;
  brier: Estimate | null;
  logLoss: Estimate | null;
  totalMae: Estimate | null;
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

function estimateOf(m: Record<string, unknown> | undefined, key: string): Estimate | null {
  const num = (k: string) => (typeof m?.[k] === "number" ? (m[k] as number) : null);
  const value = num(key);
  return value === null ? null : { value, lo: num(`${key}_lo`), hi: num(`${key}_hi`) };
}

/**
 * Rows of a committed evaluation record (model_runs.metrics): one per model, the version first and
 * the close last. Unknown or non-model keys (e.g. paired comparisons, scalars) are skipped.
 */
export function testRecordRows(metrics: Record<string, unknown>, version: string): TestRecordRow[] {
  const pairedAll = isRecord(metrics.paired_vs_benchmarks) ? metrics.paired_vs_benchmarks : {};
  const models = Object.keys(metrics).filter(
    (k) =>
      k !== "paired_vs_benchmarks" &&
      isRecord(metrics[k]) &&
      "margin_mae" in (metrics[k] as object),
  );
  const rank = (k: string) => (k === version ? 0 : k === "nflverse close" ? 2 : 1);
  return models
    .sort((a, b) => rank(a) - rank(b))
    .map((model) => {
      const m = metrics[model] as Record<string, unknown>;
      const p = isRecord(pairedAll[model])
        ? (pairedAll[model] as Record<string, unknown>)
        : undefined;
      return {
        model,
        marginMae: estimateOf(m, "margin_mae"),
        vsClose: model === "nflverse close" ? null : estimateOf(m, "d_margin_mae"),
        versionVs: model === version ? null : estimateOf(p, "d_margin_mae"),
        brier: estimateOf(m, "brier"),
        logLoss: estimateOf(m, "log_loss"),
        totalMae: estimateOf(m, "total_mae"),
      };
    });
}
