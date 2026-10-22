// OddsPapi historical line-move logs → MarketScope snapshot observations. Pure, no I/O.
//
// OddsPapi records each book's price history per market/outcome as a change log
// ({createdAt, price (decimal), active}). A quote stays valid until a newer entry or a
// deactivation replaces it; there are no periodic "still the same" heartbeats. To make
// imported history comparable with live collection (and usable by replay and the
// same-snapshot signals), we DERIVE snapshots on the live cadence:
//   - every 6 hours at 00/06/12/18 UTC within the last `windowDays` before kickoff, plus
//   - a near-close snapshot `closeMinutes` before kickoff.
// At each snapshot time, each book's main line is the market whose two sides are both
// active and priced closest to even (validated 30/32 against our own observations).
// Encoding (verified 2026-10-17): period "result" = full game incl. overtime; spread
// markets carry the HOME team's line in `handicap`; participant1 = home; moneyline = 141.

import { decimalToAmerican, type Market, type Selection } from "@marketscope/shared";

export interface OddsPapiOutcomeMeta {
  outcomeId: number;
  outcomeName: string;
}

export interface OddsPapiMarketMeta {
  marketId: number;
  sportId?: number;
  marketType: string;
  handicap: number;
  period: string;
  playerProp: boolean;
  outcomes: OddsPapiOutcomeMeta[];
}

export interface OddsPapiEntry {
  createdAt: string;
  price: number;
  active: boolean;
  /** Maximum stake, for books that report one (e.g. Pinnacle). */
  limit?: number | null;
}

export interface OddsPapiHistory {
  bookmakers: Record<
    string,
    {
      markets: Record<
        string,
        { outcomes: Record<string, { players: Record<string, OddsPapiEntry[]> }> }
      >;
    }
  >;
}

export interface DerivedObservation {
  bookmakerKey: string;
  market: Market;
  selection: Selection;
  point: number | null;
  americanPrice: number;
  /** When the provider recorded the price change this quote comes from. */
  bookmakerUpdatedAt: string;
  /** The derived snapshot time. */
  observedAt: string;
}

export interface DeriveOptions {
  /** Kickoff (ISO). Only entries strictly before kickoff are used: pregame only. */
  kickoff: string;
  /** OddsPapi bookmaker slug → MarketScope bookmaker key. Unmapped books are ignored. */
  bookMap: Readonly<Record<string, string>>;
  windowDays?: number;
  slotHours?: number;
  closeMinutes?: number;
}

const HOUR = 3_600_000;

/** Snapshot times from max(first entry, kickoff − window) to the near-close time. */
export function snapshotTimes(
  firstEntryAt: string,
  kickoff: string,
  {
    windowDays = 30,
    slotHours = 6,
    closeMinutes = 5,
  }: Pick<DeriveOptions, "windowDays" | "slotHours" | "closeMinutes"> = {},
): string[] {
  const kick = instantMs(kickoff);
  const close = kick - closeMinutes * 60_000;
  const start = Math.max(Date.parse(firstEntryAt), kick - windowDays * 24 * HOUR);
  const slot = slotHours * HOUR;
  const times: string[] = [];
  for (let t = Math.ceil(start / slot) * slot; t < close; t += slot)
    times.push(new Date(t).toISOString());
  if (close >= start) times.push(new Date(close).toISOString());
  return times;
}

export interface Series {
  times: number[];
  entries: OddsPapiEntry[];
}

/** Latest entry at or before t (binary search over a time-sorted series). */
export function latestAt(series: Series | undefined, t: number): OddsPapiEntry | null {
  if (!series) return null;
  let lo = 0;
  let hi = series.times.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (series.times[mid]! <= t) {
      found = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return found >= 0 ? series.entries[found]! : null;
}

/**
 * Milliseconds since the epoch for an ISO 8601 timestamp with a zone (Z or an offset). Date.parse
 * reads a timestamp without a zone in the machine's local time, so that is an error, as is anything
 * unparseable. Offsets are compared as instants: 17:30+01:00 is before 17:00Z.
 */
export function instantMs(iso: string): number {
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(iso)) throw new Error(`timestamp without a time zone: ${iso}`);
  const t = Date.parse(iso);
  if (Number.isNaN(t)) throw new Error(`unparseable timestamp: ${iso}`);
  return t;
}

/** Continuous "cents" scale so −105 vs +105 counts as 10 apart, not 210. */
const cents = (american: number) => (american < 0 ? american + 100 : american - 100);

/** One full-game market of one book: a line (handicap) and its two sides' histories. */
export interface Candidate {
  handicap: number;
  side1: Series;
  side2: Series;
}

export interface BookCandidates {
  spreads: Candidate[];
  totals: Candidate[];
  moneyline: Candidate | null;
  /** Earliest pregame entry (ms), or Infinity if the book has none. */
  firstEntry: number;
}

/** A book's full-game spread, total and moneyline markets, using pregame entries only. */
export function bookCandidates(
  book: OddsPapiHistory["bookmakers"][string],
  markets: ReadonlyMap<number, OddsPapiMarketMeta>,
  kickoffMs: number,
): BookCandidates {
  const out: BookCandidates = { spreads: [], totals: [], moneyline: null, firstEntry: Infinity };
  for (const [marketId, market] of Object.entries(book.markets ?? {})) {
    const meta = markets.get(Number(marketId));
    if (!meta || meta.period !== "result" || meta.playerProp) continue;
    const isSpread = meta.marketType === "spreads";
    const isTotal = meta.marketType === "totals";
    const isMoneyline = meta.marketType === "moneyline";
    if (!isSpread && !isTotal && !isMoneyline) continue;

    const name = new Map(meta.outcomes.map((o) => [String(o.outcomeId), o.outcomeName]));
    const seriesFor = (wanted: string): Series | undefined => {
      const id = [...name.entries()].find(([, n]) => n === wanted)?.[0];
      // Sorted by instant (a stable sort, so equal times keep the provider's order), not as text.
      const timed = id
        ? (market.outcomes[id]?.players?.["0"] ?? [])
            .map((e) => ({ e, t: instantMs(e.createdAt) }))
            .filter(({ e, t }) => t < kickoffMs && e.price > 1)
            .sort((a, b) => a.t - b.t)
        : [];
      return timed.length
        ? { times: timed.map(({ t }) => t), entries: timed.map(({ e }) => e) }
        : undefined;
    };
    const side1 = seriesFor(isTotal ? "Over" : "1");
    const side2 = seriesFor(isTotal ? "Under" : "2");
    if (!side1 || !side2) continue;
    out.firstEntry = Math.min(out.firstEntry, side1.times[0]!, side2.times[0]!);
    const candidate = { handicap: Number(meta.handicap), side1, side2 };
    if (isSpread) out.spreads.push(candidate);
    else if (isTotal) out.totals.push(candidate);
    else out.moneyline = candidate;
  }
  return out;
}

export interface MainLine {
  handicap: number;
  side1: OddsPapiEntry;
  side2: OddsPapiEntry;
}

/**
 * The main line at time t: the candidate whose two sides are both active and priced closest
 * to even (ties go to the smaller |handicap|). Null when nothing is on the board.
 */
export function pickMain(candidates: readonly Candidate[], t: number): MainLine | null {
  let best: (MainLine & { gap: number }) | null = null;
  for (const c of candidates) {
    const a = latestAt(c.side1, t);
    const b = latestAt(c.side2, t);
    if (!a?.active || !b?.active) continue;
    const gap = Math.abs(cents(decimalToAmerican(a.price)) - cents(decimalToAmerican(b.price)));
    if (
      !best ||
      gap < best.gap ||
      (gap === best.gap && Math.abs(c.handicap) < Math.abs(best.handicap))
    ) {
      best = { handicap: c.handicap, side1: a, side2: b, gap };
    }
  }
  return best && { handicap: best.handicap, side1: best.side1, side2: best.side2 };
}

/** Near-even band for a main line: no-vig probability of side 1 within [0.3, 0.7]. */
export const GHOST_NEAR_EVEN = 0.3;
/** A main line carries a normal margin: implied probabilities summing to at most 1.12. */
export const GHOST_MAX_OVERROUND = 1.12;
/** Two near-even lines at least this far apart must differ in probability... */
export const GHOST_MIN_GAP = 2;
/** ...by at least this much per point. */
export const GHOST_MIN_SLOPE = 0.005;

/**
 * Sportsbook spread and total markets with ghosts removed (MS-058, ADR-065). The feed sometimes
 * keeps a market "active" after the book stopped updating it, and pickMain can take it:
 *   - near even, normal margin: a main line is priced near even with a normal margin, so a market
 *     outside that never is (a book that suspends its board can leave two far-tail markets active,
 *     e.g. a 64.5 total at 13/1; junk markets can carry a 70% margin);
 *   - flat pair: two near-even lines at least 2 points apart whose probabilities barely differ
 *     cannot both be live (Caesars' −10 at 50.0% beside its real −7 at 50.2%); the one updated
 *     less recently is the ghost. Only flatness counts, not direction: a feed can label a whole
 *     ladder the other way round.
 * Staleness alone is not a rule: FanDuel's real main line can sit unchanged for days while its
 * alternates are repriced (checked against The Odds API's main lines). Not for exchanges, whose
 * resting orders are real.
 */
export function withoutGhosts(candidates: readonly Candidate[], t: number): Candidate[] {
  const live: { c: Candidate; p: number; last: number }[] = [];
  for (const c of candidates) {
    const a = latestAt(c.side1, t);
    const b = latestAt(c.side2, t);
    if (!a?.active || !b?.active) continue;
    const overround = 1 / a.price + 1 / b.price;
    const p = 1 / a.price / overround;
    if (overround > GHOST_MAX_OVERROUND) continue;
    if (p < GHOST_NEAR_EVEN || p > 1 - GHOST_NEAR_EVEN) continue;
    live.push({ c, p, last: Math.max(Date.parse(a.createdAt), Date.parse(b.createdAt)) });
  }
  return live
    .filter(
      (x) =>
        !live.some((y) => {
          const gap = Math.abs(y.c.handicap - x.c.handicap);
          return (
            gap >= GHOST_MIN_GAP && Math.abs(y.p - x.p) / gap < GHOST_MIN_SLOPE && x.last < y.last
          );
        }),
    )
    .map((x) => x.c);
}

export function deriveObservations(
  history: OddsPapiHistory,
  markets: ReadonlyMap<number, OddsPapiMarketMeta>,
  options: DeriveOptions,
): DerivedObservation[] {
  const kick = instantMs(options.kickoff);
  const out: DerivedObservation[] = [];

  for (const [slug, book] of Object.entries(history.bookmakers ?? {})) {
    const bookmakerKey = options.bookMap[slug];
    if (!bookmakerKey) continue;
    const { spreads, totals, moneyline, firstEntry } = bookCandidates(book, markets, kick);
    if (firstEntry === Infinity) continue;

    for (const at of snapshotTimes(new Date(firstEntry).toISOString(), options.kickoff, options)) {
      const t = Date.parse(at);
      const push = (market: Market, selection: Selection, point: number | null, e: OddsPapiEntry) =>
        out.push({
          bookmakerKey,
          market,
          selection,
          point,
          americanPrice: decimalToAmerican(e.price),
          bookmakerUpdatedAt: new Date(e.createdAt).toISOString(),
          observedAt: at,
        });

      const spread = pickMain(spreads, t);
      if (spread) {
        // Spread markets store the home line; the away line is its negation.
        push("spreads", "HOME", spread.handicap, spread.side1);
        push("spreads", "AWAY", spread.handicap === 0 ? 0 : -spread.handicap, spread.side2);
      }
      const total = pickMain(totals, t);
      if (total) {
        push("totals", "OVER", total.handicap, total.side1);
        push("totals", "UNDER", total.handicap, total.side2);
      }
      const ml = moneyline && pickMain([moneyline], t);
      if (ml) {
        push("h2h", "HOME", null, ml.side1);
        push("h2h", "AWAY", null, ml.side2);
      }
    }
  }
  return out;
}
