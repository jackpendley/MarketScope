// Minute-level line moves (MS-042, ADR-052): one game's main-line changes per book.

import { and, asc, eq } from "drizzle-orm";
import type { Database } from "../client";
import { lineMoveFixes, lineMoves, type marketType } from "../schema";

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

/**
 * Every stored move for one game and market, by book and oldest first, with ghost-market
 * corrections applied (ADR-065): a book with rows in line_move_fixes shows those instead.
 */
export async function lineMoveHistory(
  db: Database,
  eventId: string,
  market: (typeof marketType.enumValues)[number],
): Promise<LineMoveRow[]> {
  const read = (t: typeof lineMoves | typeof lineMoveFixes) =>
    db
      .select({
        bookmakerKey: t.bookmakerKey,
        changedAt: t.changedAt,
        point: t.point,
        price1: t.price1,
        price2: t.price2,
        limit1: t.limit1,
        limit2: t.limit2,
      })
      .from(t)
      .where(and(eq(t.eventId, eventId), eq(t.marketType, market)))
      .orderBy(asc(t.bookmakerKey), asc(t.changedAt));
  const [moves, fixes] = await Promise.all([read(lineMoves), read(lineMoveFixes)]);
  const fixed = new Set(fixes.map((r) => r.bookmakerKey));
  return [...moves.filter((r) => !fixed.has(r.bookmakerKey)), ...fixes].sort(
    (a, b) =>
      a.bookmakerKey.localeCompare(b.bookmakerKey) ||
      Date.parse(a.changedAt) - Date.parse(b.changedAt),
  );
}
