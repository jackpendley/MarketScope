// OddsPapi change logs → minute-level main-line moves (MS-042, ADR-052). Pure, no I/O.
//
// transform.ts samples the same logs at snapshot times; here we keep every change instead.
// For each book and market we walk the merged entry times, pick the main line at each one
// (pickMain: both sides active, closest to even) and emit a row whenever the line, either
// price or either limit differs from the last row. Three rules keep the rows meaningful:
//   - settle: entries less than `settleMs` apart are one change (a book writing its two sides
//     or its alternate lines a few milliseconds apart), recorded when the burst ends;
//   - suspensions: a main line off the board for at least `minSuspensionMs` gets a row with
//     no prices, so "still showing the old number" is never confused with "off the board";
//     shorter blips are ignored;
//   - window: rows from `windowDays` before kickoff, plus the line in effect at the start.

import { decimalToAmerican, type Market } from "@marketscope/shared";
import {
  bookCandidates,
  pickMain,
  withoutGhosts,
  type Candidate,
  type OddsPapiHistory,
  type OddsPapiMarketMeta,
} from "./transform";

export interface LineMove {
  bookmakerKey: string;
  market: Market;
  /** Provider time of the change (for a suspension, when the line went off). */
  changedAt: string;
  /** Home team's spread or the total; null for moneylines and suspensions. */
  point: number | null;
  /** HOME (spreads, h2h) or OVER (totals); null while suspended. */
  price1: number | null;
  /** AWAY or UNDER; null while suspended. */
  price2: number | null;
  limit1: number | null;
  limit2: number | null;
}

export interface LineMoveOptions {
  /** Kickoff (ISO). Only entries strictly before kickoff are used. */
  kickoff: string;
  /** OddsPapi bookmaker slug → MarketScope bookmaker key. Unmapped books are ignored. */
  bookMap: Readonly<Record<string, string>>;
  windowDays?: number;
  settleMs?: number;
  minSuspensionMs?: number;
  /**
   * MarketScope keys whose limits are kept; other books' limits are dropped, so a limit change
   * alone never makes a row. Omitted = keep every book's limits.
   */
  limitBooks?: ReadonlySet<string>;
  /** MarketScope keys whose limits are stored on each row but never create a row by themselves
   * (exchanges: the size at the top of book changes constantly). */
  recordLimitBooks?: ReadonlySet<string>;
  /** Markets to derive (default: all three). */
  markets?: readonly Market[];
  /** Remove ghost spread and total markets before picking the main line (MS-058, ADR-065). */
  ghostRule?: boolean;
}

export const LINE_MOVE_DEFAULTS = {
  windowDays: 14,
  settleMs: 1_000,
  minSuspensionMs: 60_000,
} as const;

const DAY = 86_400_000;

export function deriveLineMoves(
  history: OddsPapiHistory,
  markets: ReadonlyMap<number, OddsPapiMarketMeta>,
  options: LineMoveOptions,
): LineMove[] {
  const { limitBooks, recordLimitBooks, markets: only, ghostRule = false, ...rest } = options;
  const opts = { ...LINE_MOVE_DEFAULTS, ...rest };
  const kick = Date.parse(opts.kickoff);
  const out: LineMove[] = [];
  for (const [slug, book] of Object.entries(history.bookmakers ?? {})) {
    const bookmakerKey = opts.bookMap[slug];
    if (!bookmakerKey) continue;
    const { spreads, totals, moneyline } = bookCandidates(book, markets, kick);
    const byMarket: [Market, Candidate[]][] = [
      ["spreads", spreads],
      ["totals", totals],
      ["h2h", moneyline ? [moneyline] : []],
    ];
    for (const [market, candidates] of byMarket) {
      if (only && !only.includes(market)) continue;
      const triggers = !limitBooks || limitBooks.has(bookmakerKey);
      out.push(
        ...timeline(bookmakerKey, market, candidates, kick, {
          ...opts,
          keepLimits: triggers || Boolean(recordLimitBooks?.has(bookmakerKey)),
          limitsInKey: triggers,
          ghostRule,
        }),
      );
    }
  }
  return out;
}

function timeline(
  bookmakerKey: string,
  market: Market,
  candidates: readonly Candidate[],
  kick: number,
  opts: Required<
    Omit<
      LineMoveOptions,
      "kickoff" | "bookMap" | "limitBooks" | "recordLimitBooks" | "markets" | "ghostRule"
    >
  > & {
    keepLimits: boolean;
    limitsInKey: boolean;
    ghostRule: boolean;
  },
): LineMove[] {
  const times = [...new Set(candidates.flatMap((c) => [...c.side1.times, ...c.side2.times]))].sort(
    (a, b) => a - b,
  );
  const rows: LineMove[] = [];
  let lastKey: string | null = null;
  let offSince: number | null = null;

  const suspend = (at: number) => {
    // Only after the line has been on the board, and only once per suspension.
    if (lastKey === null || lastKey === "off") return;
    rows.push({
      bookmakerKey,
      market,
      changedAt: new Date(at).toISOString(),
      point: null,
      price1: null,
      price2: null,
      limit1: null,
      limit2: null,
    });
    lastKey = "off";
  };
  const limit = (v: number | null | undefined) =>
    v == null || !opts.keepLimits ? null : Math.round(v);

  for (const [i, t] of times.entries()) {
    const next = times[i + 1];
    if (next !== undefined && next - t < opts.settleMs) continue;
    const main = pickMain(
      opts.ghostRule && market !== "h2h" ? withoutGhosts(candidates, t) : candidates,
      t,
    );
    if (!main) {
      offSince ??= t;
      continue;
    }
    if (offSince !== null && t - offSince >= opts.minSuspensionMs) suspend(offSince);
    offSince = null;
    const row: LineMove = {
      bookmakerKey,
      market,
      changedAt: new Date(t).toISOString(),
      point: market === "h2h" ? null : main.handicap,
      price1: decimalToAmerican(main.side1.price),
      price2: decimalToAmerican(main.side2.price),
      limit1: limit(main.side1.limit),
      limit2: limit(main.side2.limit),
    };
    const key = JSON.stringify(
      opts.limitsInKey
        ? [row.point, row.price1, row.price2, row.limit1, row.limit2]
        : [row.point, row.price1, row.price2],
    );
    if (key !== lastKey) {
      rows.push(row);
      lastKey = key;
    }
  }
  if (offSince !== null && kick - offSince >= opts.minSuspensionMs) suspend(offSince);

  const start = kick - opts.windowDays * DAY;
  const first = rows.findIndex((r) => Date.parse(r.changedAt) >= start);
  return first === -1 ? rows.slice(-1) : rows.slice(Math.max(0, first - 1));
}

/**
 * Corrections for `line_move_fixes` (MS-058, ADR-065): for each book and market whose ghost-free
 * timeline differs from the registered one, the whole ghost-free timeline. `line_moves` itself is
 * never rewritten (pre-registered studies read it as it is). A timeline that is entirely ghosts
 * becomes one suspension row at its first change, so readers never fall back to the ghosts.
 */
export function ghostFixRows(registered: readonly LineMove[], ghostFree: readonly LineMove[]) {
  const group = (rows: readonly LineMove[]) => {
    const out = new Map<string, LineMove[]>();
    for (const r of rows) {
      const key = `${r.bookmakerKey}|${r.market}`;
      out.set(key, [...(out.get(key) ?? []), r]);
    }
    return out;
  };
  const before = group(registered);
  const after = group(ghostFree);
  const fixes: LineMove[] = [];
  for (const [key, rows] of before) {
    const fixed = after.get(key) ?? [];
    if (JSON.stringify(rows) === JSON.stringify(fixed)) continue;
    fixes.push(
      ...(fixed.length
        ? fixed
        : [{ ...rows[0]!, point: null, price1: null, price2: null, limit1: null, limit2: null }]),
    );
  }
  // A ghost-free timeline where the registered one had nothing cannot happen (the rule only
  // removes markets), but keep it if it ever does.
  for (const [key, rows] of after) if (!before.has(key)) fixes.push(...rows);
  return fixes;
}

/** The row in effect at time t (latest changedAt ≤ t) for one book and market, if any. */
export function lineAt(
  moves: readonly LineMove[],
  bookmakerKey: string,
  market: Market,
  t: string,
): LineMove | null {
  const at = Date.parse(t);
  let found: LineMove | null = null;
  for (const m of moves) {
    if (m.bookmakerKey !== bookmakerKey || m.market !== market) continue;
    const c = Date.parse(m.changedAt);
    if (c <= at && (!found || c > Date.parse(found.changedAt))) found = m;
  }
  return found;
}
