// Paper portfolio (MS-045b, ADR-056): hypothetical positions from pre-registered systems.

import { and, asc, eq, inArray, sql } from "drizzle-orm";
import type { Database } from "../client";
import { nflGames, paperPositions } from "../schema";

export interface PaperPositionRow {
  id: number;
  strategy: string;
  mode: string;
  gameId: string;
  season: number;
  week: number;
  kickoffUtc: string;
  homeTeam: string;
  awayTeam: string;
  market: string;
  side: string;
  line: number;
  teasedLine: number | null;
  price: number | null;
  bookmakerKey: string;
  quoteObservedAt: string;
  placedAt: string;
  result: string | null;
  closeLine: number | null;
  closeSource: string | null;
  clv: number | null;
}

/** A season's positions in the given modes, in kickoff order. */
export async function listPaperPositions(
  db: Database,
  { season, modes }: { season: number; modes: readonly string[] },
): Promise<PaperPositionRow[]> {
  return db
    .select({
      id: paperPositions.id,
      strategy: paperPositions.strategy,
      mode: paperPositions.mode,
      gameId: paperPositions.gameId,
      season: paperPositions.season,
      week: paperPositions.week,
      kickoffUtc: paperPositions.kickoffUtc,
      homeTeam: nflGames.homeTeam,
      awayTeam: nflGames.awayTeam,
      market: paperPositions.market,
      side: paperPositions.side,
      line: paperPositions.line,
      teasedLine: paperPositions.teasedLine,
      price: paperPositions.price,
      bookmakerKey: paperPositions.bookmakerKey,
      quoteObservedAt: paperPositions.quoteObservedAt,
      placedAt: paperPositions.placedAt,
      result: paperPositions.result,
      closeLine: paperPositions.closeLine,
      closeSource: paperPositions.closeSource,
      clv: paperPositions.clv,
    })
    .from(paperPositions)
    .innerJoin(nflGames, eq(nflGames.gameId, paperPositions.gameId))
    .where(and(eq(paperPositions.season, season), inArray(paperPositions.mode, [...modes])))
    .orderBy(asc(paperPositions.kickoffUtc), asc(paperPositions.strategy), asc(paperPositions.id));
}

/** Seasons that have any paper positions, newest first. */
export async function paperSeasons(db: Database): Promise<number[]> {
  const rows = await db.execute<{ season: number }>(
    sql`SELECT DISTINCT season FROM paper_positions ORDER BY season DESC`,
  );
  return rows.map((r) => r.season);
}
