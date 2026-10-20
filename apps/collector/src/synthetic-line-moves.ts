// SYNTHETIC minute-level line moves for demo/e2e databases (source = "synthetic"), so the
// replay page's line-move panel can be developed and tested without real provider data.
// Built from the synthetic snapshots: DraftKings and FanDuel keep their own times, and
// "reference" Pinnacle and Circa copies of DraftKings move 25 and 15 minutes earlier.

import { bookmakers, lineMoves, type Database } from "@marketscope/db";
import { LINE_MOVE_ONLY_BOOKMAKERS, REFERENCE_BOOKMAKERS } from "@marketscope/shared";
import { eq, sql } from "drizzle-orm";

type Snapshot = {
  event_id: string;
  bookmaker_key: string;
  market_type: "h2h" | "spreads" | "totals";
  observed_at: string;
  selection: "HOME" | "AWAY" | "OVER" | "UNDER";
  point: string | null;
  american_price: number;
};

const COPIES: { key: string; from: string; leadMinutes: number }[] = [
  { key: "draftkings", from: "draftkings", leadMinutes: 0 },
  { key: "fanduel", from: "fanduel", leadMinutes: 0 },
  { key: "pinnacle", from: "draftkings", leadMinutes: 25 },
  { key: "circa", from: "draftkings", leadMinutes: 15 },
];

export async function seedSyntheticLineMoves(db: Database): Promise<number> {
  await db
    .insert(bookmakers)
    .values(
      [...REFERENCE_BOOKMAKERS, ...LINE_MOVE_ONLY_BOOKMAKERS].map((b) => ({
        key: b.key,
        displayName: b.displayName,
        regionHint: b.regionHint,
      })),
    )
    .onConflictDoNothing({ target: bookmakers.key });
  await db.delete(lineMoves).where(eq(lineMoves.source, "synthetic"));

  const snaps = await db.execute<Snapshot>(sql`
    SELECT event_id, bookmaker_key, market_type, observed_at, selection, point, american_price
    FROM odds_observations
    WHERE source = 'synthetic' AND NOT is_live AND bookmaker_key IN ('draftkings', 'fanduel')
    ORDER BY event_id, bookmaker_key, market_type, observed_at`);

  // Pair the two sides of each snapshot.
  const pairs = new Map<string, { point: number | null; p1?: number; p2?: number }>();
  for (const s of snaps) {
    const key = `${s.event_id}|${s.bookmaker_key}|${s.market_type}|${new Date(s.observed_at).toISOString()}`;
    const pair = pairs.get(key) ?? { point: null };
    const first = s.selection === "HOME" || s.selection === "OVER";
    if (first) {
      pair.p1 = s.american_price;
      if (s.point !== null) pair.point = Number(s.point);
    } else pair.p2 = s.american_price;
    pairs.set(key, pair);
  }

  const rows: (typeof lineMoves.$inferInsert)[] = [];
  for (const copy of COPIES) {
    let lastKey: string | null = null;
    let lastSeries: string | null = null;
    for (const [key, pair] of [...pairs].sort(([a], [b]) => a.localeCompare(b))) {
      const [eventId, book, market, at] = key.split("|") as [
        string,
        string,
        Snapshot["market_type"],
        string,
      ];
      if (book !== copy.from || pair.p1 === undefined || pair.p2 === undefined) continue;
      const series = `${eventId}|${market}`;
      if (series !== lastSeries) lastKey = null;
      lastSeries = series;
      const value = JSON.stringify([pair.point, pair.p1, pair.p2]);
      if (value === lastKey) continue;
      lastKey = value;
      rows.push({
        eventId,
        bookmakerKey: copy.key,
        marketType: market,
        changedAt: new Date(Date.parse(at) - copy.leadMinutes * 60_000).toISOString(),
        point: market === "h2h" ? null : pair.point,
        price1: pair.p1,
        price2: pair.p2,
        limit1: copy.key === "pinnacle" ? 5000 : null,
        limit2: copy.key === "pinnacle" ? 5000 : null,
        source: "synthetic",
      });
    }
  }
  for (let i = 0; i < rows.length; i += 1_000)
    await db.insert(lineMoves).values(rows.slice(i, i + 1_000));
  return rows.length;
}
