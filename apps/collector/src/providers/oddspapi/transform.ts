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
  const kick = Date.parse(kickoff);
  const close = kick - closeMinutes * 60_000;
  const start = Math.max(Date.parse(firstEntryAt), kick - windowDays * 24 * HOUR);
  const slot = slotHours * HOUR;
  const times: string[] = [];
  for (let t = Math.ceil(start / slot) * slot; t < close; t += slot)
    times.push(new Date(t).toISOString());
  if (close >= start) times.push(new Date(close).toISOString());
  return times;
}

interface Series {
  times: number[];
  entries: OddsPapiEntry[];
}

/** Latest entry at or before t (binary search over a time-sorted series). */
function latestAt(series: Series | undefined, t: number): OddsPapiEntry | null {
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

/** Continuous "cents" scale so −105 vs +105 counts as 10 apart, not 210. */
const cents = (american: number) => (american < 0 ? american + 100 : american - 100);

interface Candidate {
  handicap: number;
  side1: Series;
  side2: Series;
}

export function deriveObservations(
  history: OddsPapiHistory,
  markets: ReadonlyMap<number, OddsPapiMarketMeta>,
  options: DeriveOptions,
): DerivedObservation[] {
  const kick = Date.parse(options.kickoff);
  const out: DerivedObservation[] = [];

  for (const [slug, book] of Object.entries(history.bookmakers ?? {})) {
    const bookmakerKey = options.bookMap[slug];
    if (!bookmakerKey) continue;

    const spreads: Candidate[] = [];
    const totals: Candidate[] = [];
    let moneyline: Candidate | null = null;
    let firstEntry = Infinity;

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
        const entries = id
          ? (market.outcomes[id]?.players?.["0"] ?? [])
              .filter((e) => Date.parse(e.createdAt) < kick && e.price > 1)
              .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
          : [];
        return entries.length
          ? { times: entries.map((e) => Date.parse(e.createdAt)), entries }
          : undefined;
      };
      const side1 = seriesFor(isTotal ? "Over" : "1");
      const side2 = seriesFor(isTotal ? "Under" : "2");
      if (!side1 || !side2) continue;
      firstEntry = Math.min(firstEntry, side1.times[0]!, side2.times[0]!);
      const candidate = { handicap: Number(meta.handicap), side1, side2 };
      if (isSpread) spreads.push(candidate);
      else if (isTotal) totals.push(candidate);
      else moneyline = candidate;
    }
    if (firstEntry === Infinity) continue;

    for (const at of snapshotTimes(new Date(firstEntry).toISOString(), options.kickoff, options)) {
      const t = Date.parse(at);
      const pick = (candidates: Candidate[]) => {
        let best: { c: Candidate; a: OddsPapiEntry; b: OddsPapiEntry; gap: number } | null = null;
        for (const c of candidates) {
          const a = latestAt(c.side1, t);
          const b = latestAt(c.side2, t);
          if (!a?.active || !b?.active) continue;
          const gap = Math.abs(
            cents(decimalToAmerican(a.price)) - cents(decimalToAmerican(b.price)),
          );
          if (
            !best ||
            gap < best.gap ||
            (gap === best.gap && Math.abs(c.handicap) < Math.abs(best.c.handicap))
          ) {
            best = { c, a, b, gap };
          }
        }
        return best;
      };
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

      const spread = pick(spreads);
      if (spread) {
        // Spread markets store the home line; the away line is its negation.
        push("spreads", "HOME", spread.c.handicap, spread.a);
        push("spreads", "AWAY", spread.c.handicap === 0 ? 0 : -spread.c.handicap, spread.b);
      }
      const total = pick(totals);
      if (total) {
        push("totals", "OVER", total.c.handicap, total.a);
        push("totals", "UNDER", total.c.handicap, total.b);
      }
      if (moneyline) {
        const a = latestAt(moneyline.side1, t);
        const b = latestAt(moneyline.side2, t);
        if (a?.active && b?.active) {
          push("h2h", "HOME", null, a);
          push("h2h", "AWAY", null, b);
        }
      }
    }
  }
  return out;
}
