// Deterministic SYNTHETIC odds history for demos and end-to-end tests.
//
// This is NOT real market data. It produces provider-shaped payloads (so they go through
// the real normalizer and collector) with clearly fake event ids, and the collector
// stores them with source = "synthetic". The UI shows a banner whenever synthetic rows
// are present. The seed script refuses to write to any database whose name doesn't
// contain "e2e" or "demo".

import { SYNTHETIC_NFL_ODDS } from "@marketscope/shared/fixtures";

const HOUR = 3_600_000;

export interface SyntheticSnapshot {
  receivedAt: string;
  payload: unknown;
}

export interface SyntheticHistoryOptions {
  /** The newest snapshot's time. */
  now: Date;
  snapshots?: number;
  intervalHours?: number;
  /** Snapshot indexes to skip entirely (a collector outage, so a data gap). */
  outage?: readonly number[];
  seed?: number;
}

type Outcome = { name: string; price: number; point?: number };
type Market = { key: string; last_update?: string; outcomes: Outcome[] };
type Book = { key: string; title: string; markets: Market[] };
type Event = {
  id: string;
  commence_time: string;
  home_team: string;
  away_team: string;
  bookmakers: Book[];
};

/** Small deterministic PRNG (mulberry32), so every run produces identical history. */
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

const clampJuice = (p: number) => Math.max(-130, Math.min(-100, Math.round(p)));
/** Rough favorite/underdog moneylines for a home spread. Synthetic, not a pricing model. */
function moneylines(homePoint: number): [number, number] {
  const fav = Math.round(-110 - 22 * Math.abs(homePoint));
  const dog = Math.round(100 + 18 * Math.abs(homePoint));
  const safeDog = dog < 100 ? 100 : dog;
  return homePoint <= 0 ? [fav, safeDog] : [safeDog, fav];
}

export function generateSyntheticHistory(options: SyntheticHistoryOptions): SyntheticSnapshot[] {
  const { now, snapshots = 20, intervalHours = 6, outage = [7, 8], seed = 2026 } = options;
  const random = rng(seed);
  const base = structuredClone(SYNTHETIC_NFL_ODDS) as Event[];

  // Kickoffs a few days after the newest snapshot so every game is pregame throughout.
  const kickoffOffsets = [2 * 24, 2 * 24 + 3, 4 * 24];
  const events = base.map((e, i) => ({
    ...e,
    id: `synthetic-history-${i + 1}`,
    commence_time: new Date(
      now.getTime() + kickoffOffsets[i % kickoffOffsets.length]! * HOUR,
    ).toISOString(),
  }));

  // State per (event, book): the home spread, spread juice, total, and total juice.
  const state = new Map<
    string,
    { home: number; juice: number; total: number; overJuice: number }
  >();
  for (const e of events) {
    for (const b of e.bookmakers) {
      const spreads = b.markets.find((m) => m.key === "spreads");
      const totals = b.markets.find((m) => m.key === "totals");
      const home = spreads?.outcomes.find((o) => o.name === e.home_team)?.point ?? -3;
      state.set(`${e.id}|${b.key}`, {
        home,
        juice: -110,
        total: totals?.outcomes[0]?.point ?? 44.5,
        overJuice: -110,
      });
    }
  }

  const out: SyntheticSnapshot[] = [];
  for (let i = 0; i < snapshots; i++) {
    const at = new Date(now.getTime() - (snapshots - 1 - i) * intervalHours * HOUR);
    // Market-wide drift each step: occasionally the whole market moves half a point.
    const marketMove = random() < 0.25 ? (random() < 0.5 ? -0.5 : 0.5) : 0;
    if (outage.includes(i)) continue;

    const payload = events.map((e) => ({
      ...e,
      bookmakers: e.bookmakers
        // BetMGM drops out of two snapshots (a book-level gap, not an outage).
        .filter((b) => !(b.key === "betmgm" && (i === 12 || i === 13)))
        .map((b) => {
          const s = state.get(`${e.id}|${b.key}`)!;
          // DraftKings tends to move first; others follow with some probability.
          const follows = b.key === "draftkings" || random() < 0.6;
          if (marketMove !== 0 && follows) s.home += marketMove;
          if (random() < 0.3) s.juice = clampJuice(s.juice + (random() < 0.5 ? -5 : 5));
          if (random() < 0.15) s.total += random() < 0.5 ? -0.5 : 0.5;
          if (random() < 0.3) s.overJuice = clampJuice(s.overJuice + (random() < 0.5 ? -4 : 4));
          const otherJuice = clampJuice(-220 - s.juice);
          const [homeMl, awayMl] = moneylines(s.home);
          const lastUpdate = new Date(
            at.getTime() - Math.floor(random() * 20) * 60_000,
          ).toISOString();

          return {
            ...b,
            markets: b.markets.map((m): Market => {
              if (m.key === "spreads") {
                return {
                  key: "spreads",
                  last_update: lastUpdate,
                  outcomes: [
                    { name: e.home_team, price: s.juice, point: s.home },
                    { name: e.away_team, price: otherJuice, point: -s.home },
                  ],
                };
              }
              if (m.key === "totals") {
                return {
                  key: "totals",
                  last_update: lastUpdate,
                  outcomes: [
                    { name: "Over", price: s.overJuice, point: s.total },
                    { name: "Under", price: clampJuice(-220 - s.overJuice), point: s.total },
                  ],
                };
              }
              return {
                key: "h2h",
                last_update: lastUpdate,
                outcomes: [
                  { name: e.home_team, price: homeMl },
                  { name: e.away_team, price: awayMl },
                ],
              };
            }),
          };
        }),
    }));
    out.push({ receivedAt: at.toISOString(), payload });
  }
  return out;
}

/** Refuse to write synthetic data anywhere but clearly-named demo/e2e databases. */
export function assertSyntheticTarget(databaseUrl: string): void {
  const name = new URL(databaseUrl).pathname.slice(1);
  if (!/(e2e|demo)/.test(name)) {
    throw new Error(
      `Refusing to seed synthetic data into "${name}". Use a database whose name contains "e2e" or "demo".`,
    );
  }
}
