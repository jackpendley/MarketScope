// View model for /portfolio (MS-045b, ADR-056). Pure: no I/O, so it is unit-tested.
//
// Positions are hypothetical: placed by the paper job from pre-registered systems at a real book's
// line, graded after the game. Straight positions pay their recorded price. Wong teaser legs are
// paired the same way as the backtest (research/backtest.py pair_chronological): within each
// season-week, by kickoff then team, 1-2, 3-4, …; a push loses the teaser; priced at TEASER_PRICE.

import type { PaperPositionRow } from "@marketscope/db";
import catalogue from "./generated/systems-catalogue.json";
import wong from "./generated/wong-teasers.json";

export const TEASER_PRICE = -125;

export type Group = "Wong teasers" | "System catalogue";
export interface StrategyInfo {
  id: string;
  label: string;
  group: Group;
  /** The backtest verdict this strategy carries into the forward test. */
  backtest: string;
}

export const STRATEGIES: readonly StrategyInfo[] = [
  ...(["V0", "V1", "V2"] as const).map((v) => ({
    id: `wong-${v}`,
    label: `Wong ${v}: ${wong.variants[v].label}`,
    group: "Wong teasers" as const,
    backtest: v === "V0" ? "no claim (primary)" : "secondary",
  })),
  ...catalogue.systems.map((s) => ({
    id: s.id,
    label: `${s.id} ${s.label}`,
    group: "System catalogue" as const,
    backtest: s.supported ? "supported" : "no claim",
  })),
];
const INFO = new Map(STRATEGIES.map((s) => [s.id, s]));
export const strategyInfo = (id: string): StrategyInfo =>
  INFO.get(id) ?? { id, label: id, group: "System catalogue", backtest: "–" };

export function profit(price: number): number {
  return price < 0 ? 100 / -price : price / 100;
}

/** Units for one graded straight position (null while open). */
export function straightUnits(p: Pick<PaperPositionRow, "result" | "price">): number | null {
  if (p.result === null || p.price === null) return null;
  return p.result === "win" ? profit(p.price) : p.result === "push" ? 0 : -1;
}

export interface Teaser {
  season: number;
  week: number;
  /** Kickoff of the later leg: when the teaser is settled. */
  settledAt: string;
  legs: [PaperPositionRow, PaperPositionRow];
  units: number | null;
}

export function pairTeasers(legs: readonly PaperPositionRow[]): Teaser[] {
  const byWeek = new Map<string, PaperPositionRow[]>();
  for (const l of legs) {
    const k = `${l.season}-${l.week}`;
    byWeek.set(k, [...(byWeek.get(k) ?? []), l]);
  }
  const out: Teaser[] = [];
  for (const group of byWeek.values()) {
    const sorted = [...group].sort(
      (a, b) => a.kickoffUtc.localeCompare(b.kickoffUtc) || a.side.localeCompare(b.side),
    );
    for (let i = 0; i + 1 < sorted.length; i += 2) {
      const pair: [PaperPositionRow, PaperPositionRow] = [sorted[i]!, sorted[i + 1]!];
      const results = pair.map((l) => l.result);
      const units = results.includes(null)
        ? null
        : results.includes("loss") || results.includes("push")
          ? -1
          : profit(TEASER_PRICE);
      out.push({
        season: pair[0].season,
        week: pair[0].week,
        settledAt: pair[1].kickoffUtc,
        legs: pair,
        units,
      });
    }
  }
  return out.sort((a, b) => a.settledAt.localeCompare(b.settledAt));
}

/** One settled unit result in time order, for summaries and the equity curve. */
interface Settlement {
  at: string;
  units: number;
}

function settlements(strategy: string, rows: readonly PaperPositionRow[]): Settlement[] {
  if (strategy.startsWith("wong-"))
    return pairTeasers(rows)
      .filter((t) => t.units !== null)
      .map((t) => ({ at: t.settledAt, units: t.units! }));
  return rows
    .map((r) => ({ at: r.kickoffUtc, units: straightUnits(r) }))
    .filter((s): s is Settlement => s.units !== null);
}

export interface StrategySummary {
  info: StrategyInfo;
  positions: number;
  open: number;
  wins: number;
  losses: number;
  pushes: number;
  /** Stakes settled: teasers for Wong strategies, positions otherwise. */
  settled: number;
  units: number;
  /** Units per unit staked; null before anything settles. */
  roi: number | null;
  /** Mean CLV in points over graded positions with a close; null if none. */
  meanClv: number | null;
  clvCount: number;
}

export function summarise(rows: readonly PaperPositionRow[]): StrategySummary[] {
  const byStrategy = new Map<string, PaperPositionRow[]>();
  for (const r of rows) byStrategy.set(r.strategy, [...(byStrategy.get(r.strategy) ?? []), r]);
  const order = new Map(STRATEGIES.map((s, i) => [s.id, i]));
  return [...byStrategy.entries()]
    .sort(([a], [b]) => (order.get(a) ?? 99) - (order.get(b) ?? 99) || a.localeCompare(b))
    .map(([strategy, list]) => {
      const s = settlements(strategy, list);
      const units = s.reduce((n, x) => n + x.units, 0);
      const clvs = list.map((r) => r.clv).filter((v): v is number => v !== null);
      return {
        info: strategyInfo(strategy),
        positions: list.length,
        open: list.filter((r) => r.result === null).length,
        wins: list.filter((r) => r.result === "win").length,
        losses: list.filter((r) => r.result === "loss").length,
        pushes: list.filter((r) => r.result === "push").length,
        settled: s.length,
        units,
        roi: s.length ? units / s.length : null,
        meanClv: clvs.length ? clvs.reduce((a, b) => a + b, 0) / clvs.length : null,
        clvCount: clvs.length,
      };
    });
}

export interface EquityPoint {
  /** Day (ISO date, UTC) */
  day: string;
  [strategy: string]: number | string | null;
}

/** Cumulative units per strategy at the end of each day with a settlement. */
export function equityByDay(rows: readonly PaperPositionRow[]): {
  points: EquityPoint[];
  strategies: string[];
} {
  const byStrategy = new Map<string, PaperPositionRow[]>();
  for (const r of rows) byStrategy.set(r.strategy, [...(byStrategy.get(r.strategy) ?? []), r]);
  const daily = new Map<string, Map<string, number>>();
  for (const [strategy, list] of byStrategy)
    for (const s of settlements(strategy, list)) {
      const day = s.at.slice(0, 10);
      const m = daily.get(day) ?? new Map<string, number>();
      m.set(strategy, (m.get(strategy) ?? 0) + s.units);
      daily.set(day, m);
    }
  const strategies = summarise(rows)
    .filter((s) => s.settled > 0)
    .map((s) => s.info.id);
  const running = new Map<string, number>();
  const points = [...daily.keys()].sort().map((day) => {
    const point: EquityPoint = { day };
    for (const id of strategies) {
      const add = daily.get(day)?.get(id);
      if (add !== undefined) running.set(id, (running.get(id) ?? 0) + add);
      point[id] = running.has(id) ? Math.round(running.get(id)! * 100) / 100 : null;
    }
    return point;
  });
  return { points, strategies };
}

export const MODES = {
  all: { label: "All", modes: ["live", "reconstructed", "synthetic"] },
  live: { label: "Live", modes: ["live"] },
  reconstructed: { label: "Reconstructed", modes: ["reconstructed"] },
} as const;
export type ModeKey = keyof typeof MODES;
export const isModeKey = (v: unknown): v is ModeKey => typeof v === "string" && v in MODES;

export const signed = (x: number, digits = 2) =>
  `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(digits)}`;
