// View model for the minute-level line-move panel (MS-042). Pure: no I/O, no React.
//
// line_moves rows are EVENTS: a book's main line is in effect from its row until its next
// row. That differs from snapshots (lib/history-chart.ts), where a value is known only at
// observation times. So here a value is held between a book's rows, is null while the book
// is suspended (a row without prices), and is null before the book's first row.

import type { LineMoveRow } from "@marketscope/db";
import type { Market, Selection } from "@marketscope/shared";
import { americanToScale, type ChartField, type ChartRow } from "./history-chart";

export const LINE_MOVE_RANGES = {
  "6h": { hours: 6, label: "Final 6 hours" },
  "48h": { hours: 48, label: "Final 48 hours" },
  "14d": { hours: 14 * 24, label: "Final 14 days" },
} as const;
export type LineMoveRange = keyof typeof LINE_MOVE_RANGES;

/** A move oriented to the charted side; null while the book is suspended. */
export interface SideQuote {
  point: number | null;
  price: number;
}

/** Away spreads are the negated home line; side 2 carries the AWAY/UNDER price. */
export function orient(row: LineMoveRow, market: Market, selection: Selection): SideQuote | null {
  if (row.price1 === null || row.price2 === null) return null;
  const second = selection === "AWAY" || selection === "UNDER";
  const point =
    row.point === null
      ? null
      : market === "spreads" && second
        ? row.point === 0
          ? 0
          : -row.point
        : row.point;
  return { point, price: second ? row.price2 : row.price1 };
}

interface Move {
  t: number;
  quote: SideQuote | null;
  limit: number | null;
}

/** Each book's moves in time order, oriented to the charted side. */
export function movesByBook(
  rows: readonly LineMoveRow[],
  market: Market,
  selection: Selection,
): Map<string, Move[]> {
  const second = selection === "AWAY" || selection === "UNDER";
  const out = new Map<string, Move[]>();
  for (const r of rows) {
    const list = out.get(r.bookmakerKey) ?? [];
    list.push({
      t: Date.parse(r.changedAt),
      quote: orient(r, market, selection),
      limit: second ? r.limit2 : r.limit1,
    });
    out.set(r.bookmakerKey, list);
  }
  for (const list of out.values()) list.sort((a, b) => a.t - b.t);
  return out;
}

function valueOf(q: SideQuote | null, field: ChartField): number | null {
  if (!q) return null;
  return field === "point" ? q.point : americanToScale(q.price);
}

/**
 * Chart rows over [from, until]: one row at `from`, at every move inside the range, and at
 * `until`, so step-after lines run to the end. Each book holds its value between its moves.
 */
export function lineMoveChartRows(
  byBook: ReadonlyMap<string, Move[]>,
  field: ChartField,
  from: number,
  until: number,
): ChartRow[] {
  const times = new Set<number>([from, until]);
  for (const moves of byBook.values())
    for (const m of moves) if (m.t > from && m.t < until) times.add(m.t);
  const rows: ChartRow[] = [...times].sort((a, b) => a - b).map((t) => ({ t }));
  for (const [key, moves] of byBook) {
    let i = -1;
    for (const row of rows) {
      while (i + 1 < moves.length && moves[i + 1]!.t <= row.t) i++;
      row[key] = i >= 0 ? valueOf(moves[i]!.quote, field) : null;
    }
  }
  return rows;
}

export interface PointMove {
  t: number;
  bookmakerKey: string;
  from: number;
  to: number;
  /** Limit the book reported with the new line, where it reports one. */
  limit: number | null;
  /** The first book to post `to` in the same direction within the lookback (may be itself). */
  leaderKey: string;
  /** Time since the leader posted it; 0 for the leader itself. */
  lagMs: number;
}

/**
 * Every line (point) change, oldest first, with which book posted the new number first.
 * A change compares with the book's last available line, so a suspension in between does not
 * count as a move. The leader is the earliest change by any book to the same number in the
 * same direction within `lookbackHours`: descriptive timing, not a claim about who bet.
 */
export function pointMoveLog(
  byBook: ReadonlyMap<string, Move[]>,
  { lookbackHours = 24 }: { lookbackHours?: number } = {},
): PointMove[] {
  const changes: Omit<PointMove, "leaderKey" | "lagMs">[] = [];
  for (const [bookmakerKey, moves] of byBook) {
    let last: number | null = null;
    for (const m of moves) {
      const p = m.quote?.point;
      if (p === null || p === undefined) continue;
      if (last !== null && p !== last)
        changes.push({ t: m.t, bookmakerKey, from: last, to: p, limit: m.limit });
      last = p;
    }
  }
  changes.sort((a, b) => a.t - b.t || a.bookmakerKey.localeCompare(b.bookmakerKey));
  const lookback = lookbackHours * 3_600_000;
  return changes.map((c) => {
    const up = c.to > c.from;
    const leader =
      changes.find(
        (d) => d.to === c.to && d.to > d.from === up && d.t >= c.t - lookback && d.t <= c.t,
      ) ?? c;
    return { ...c, leaderKey: leader.bookmakerKey, lagMs: c.t - leader.t };
  });
}

/** Screen-reader text: each book's line at the start and end of the range and its changes. */
export function lineMoveSummary(
  byBook: ReadonlyMap<string, Move[]>,
  names: Readonly<Record<string, string>>,
  field: ChartField,
  from: number,
  until: number,
  format: (v: number) => string,
): string {
  const parts: string[] = [];
  for (const [key, moves] of byBook) {
    const at = (t: number) => {
      const m = moves.filter((x) => x.t <= t).at(-1);
      return m ? valueOf(m.quote, field) : null;
    };
    const start = at(from);
    const end = at(until);
    const inRange = moves.filter((m) => m.t > from && m.t <= until);
    const changes = inRange.filter((m, i) => {
      const prev = i === 0 ? start : valueOf(inRange[i - 1]!.quote, field);
      const v = valueOf(m.quote, field);
      return v !== null && prev !== null && v !== prev;
    }).length;
    const name = names[key] ?? key;
    if (start === null && end === null) continue;
    const s = start === null ? "off the board" : format(start);
    const e = end === null ? "off the board" : format(end);
    parts.push(
      changes === 0 && s === e
        ? `${name} ${s} throughout`
        : `${name} ${s} to ${e} (${changes} change${changes === 1 ? "" : "s"})`,
    );
  }
  return parts.length ? parts.join("; ") + "." : "No line moves in this range.";
}
