// View logic for season projections (MS-034). Pure: no Next.js or database imports.
import type { ProjectionRow } from "@marketscope/db";

/**
 * Probability text for simulated odds. Exact 0 and 1 mean "never" / "every" simulated season, which
 * is not the same as eliminated or clinched, so the extremes keep their precision.
 */
export function oddsText(p: number): string {
  if (!Number.isFinite(p)) return "–";
  if (p <= 0) return "0%";
  if (p >= 1) return "100%";
  if (p < 0.001) return "<0.1%";
  if (p > 0.999) return ">99.9%";
  if (p < 0.01 || p > 0.99) return `${(100 * p).toFixed(1)}%`;
  return `${Math.round(100 * p)}%`;
}

/** Subtle shading by probability (always next to the number, never the only signal). */
export function oddsTone(p: number): string {
  if (p >= 0.9) return "bg-accent/30";
  if (p >= 0.6) return "bg-accent/15";
  return "";
}

export interface DivisionGroup {
  division: string;
  rows: ProjectionRow[];
}

/** Divisions in the usual order (AFC then NFC, East-North-South-West), teams by playoff odds. */
export function groupByDivision(rows: ProjectionRow[], conference: string | null): DivisionGroup[] {
  const order = ["East", "North", "South", "West"];
  const divisions = [...new Set(rows.map((r) => r.division))]
    .filter((d) => !conference || d.startsWith(conference))
    .sort((a, b) => {
      const [ca, da] = a.split(" ");
      const [cb, db] = b.split(" ");
      return ca!.localeCompare(cb!) || order.indexOf(da!) - order.indexOf(db!);
    });
  return divisions.map((division) => ({
    division,
    rows: rows
      .filter((r) => r.division === division)
      .sort((a, b) => b.playoffP - a.playoffP || b.meanWins - a.meanWins),
  }));
}

/** The most likely win total and the middle 80% range of the simulated win distribution. */
export function winRange(dist: number[]): { mode: number; low: number; high: number } {
  let mode = 0;
  dist.forEach((p, k) => {
    if (p > dist[mode]!) mode = k;
  });
  let cum = 0;
  let low = 0;
  let high = dist.length - 1;
  let lowSet = false;
  for (let k = 0; k < dist.length; k++) {
    cum += dist[k]!;
    if (!lowSet && cum >= 0.1 - 1e-9) {
      low = k;
      lowSet = true;
    }
    if (cum >= 0.9 - 1e-9) {
      high = k;
      break;
    }
  }
  return { mode, low, high };
}
