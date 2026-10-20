// Minute-level line moves (MS-042, ADR-052): one game's main-line changes per book.

import { and, asc, eq } from "drizzle-orm";
import type { Database } from "../client";
import { lineMoves, type marketType } from "../schema";

export interface LineMoveRow {
  bookmakerKey: string;
  changedAt: string;
  /** Home spread or total; null for moneylines and suspensions. */
  point: number | null;
  /** HOME/OVER price; null while suspended. */
  price1: number | null;
  /** AWAY/UNDER price; null while suspended. */
  price2: number | null;
  limit1: number | null;
  limit2: number | null;
}

/** Every stored move for one game and market, oldest first (primary-key order). */
export async function lineMoveHistory(
  db: Database,
  eventId: string,
  market: (typeof marketType.enumValues)[number],
): Promise<LineMoveRow[]> {
  return db
    .select({
      bookmakerKey: lineMoves.bookmakerKey,
      changedAt: lineMoves.changedAt,
      point: lineMoves.point,
      price1: lineMoves.price1,
      price2: lineMoves.price2,
      limit1: lineMoves.limit1,
      limit2: lineMoves.limit2,
    })
    .from(lineMoves)
    .where(and(eq(lineMoves.eventId, eventId), eq(lineMoves.marketType, market)))
    .orderBy(asc(lineMoves.bookmakerKey), asc(lineMoves.changedAt));
}
