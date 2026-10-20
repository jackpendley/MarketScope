// SYNTHETIC paper positions for demo/e2e databases (mode = "synthetic"), so /portfolio can be built
// and tested without real data. Built on the synthetic nfl_games from synthetic-ratings.ts: played
// games are graded, upcoming ones stay open. Not real odds and not real results.

import { bookmakers, nflGames, paperPositions, type Database } from "@marketscope/db";
import { asc, eq } from "drizzle-orm";

const STRATEGIES = ["wong-V0", "wong-V1", "F1", "F2", "F7", "F8", "F10"] as const;

export async function seedSyntheticPaper(db: Database): Promise<number> {
  await db
    .insert(bookmakers)
    .values({ key: "williamhill_us", displayName: "Caesars" })
    .onConflictDoNothing();
  await db.delete(paperPositions).where(eq(paperPositions.mode, "synthetic"));
  const games = await db.select().from(nflGames).orderBy(asc(nflGames.kickoffUtc));
  const rows: (typeof paperPositions.$inferInsert)[] = [];
  games.forEach((g, i) => {
    const played = g.homeScore !== null && g.awayScore !== null;
    const margin = played ? g.homeScore! - g.awayScore! : 0;
    const homeLine = g.nflverseCloseHomeSpread ?? -3;
    const kickoff = new Date(g.kickoffUtc);
    const quoteAt = new Date(kickoff.getTime() - 5 * 3_600_000).toISOString();
    STRATEGIES.forEach((strategy, s) => {
      if ((i + s) % 3 === 2) return; // not every strategy fires on every game
      const total = strategy === "F7" || strategy === "F8";
      const home = (i + s) % 2 === 0;
      const line = total ? 44.5 : home ? homeLine : -homeLine;
      const teaser = strategy.startsWith("wong");
      const teased = teaser ? line + 6 : null;
      const teamMargin = home ? margin : -margin;
      const v = total ? line - (g.homeScore! + g.awayScore!) : teamMargin + (teased ?? line);
      rows.push({
        strategy,
        mode: "synthetic",
        gameId: g.gameId,
        season: g.season,
        week: g.week,
        kickoffUtc: g.kickoffUtc,
        market: teaser ? "teaser_leg" : total ? "total" : "spread",
        side: total ? "under" : home ? g.homeTeam : g.awayTeam,
        line,
        teasedLine: teased,
        price: teaser ? null : -110,
        bookmakerKey: "williamhill_us",
        quoteObservedAt: quoteAt,
        placedAt: quoteAt,
        result: played ? (v > 0 ? "win" : v === 0 ? "push" : "loss") : null,
        closeLine: played ? line - (((i + s) % 3) - 1) * 0.5 : null,
        closeSource: played ? "synthetic" : null,
        clv: played ? (((i + s) % 3) - 1) * 0.5 : null,
        gradedAt: played ? new Date(kickoff.getTime() + 4 * 3_600_000).toISOString() : null,
      });
    });
  });
  if (rows.length) await db.insert(paperPositions).values(rows);
  return rows.length;
}
