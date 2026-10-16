import "server-only";
import { getGame, selectionHistory, type Database, type GameRow } from "@marketscope/db";
import { buildSeriesByBook, getBookmakerInfo, type BookSeries } from "@marketscope/shared";
import type { HistoryParams } from "@/lib/params";

export interface NamedSeries extends BookSeries {
  displayName: string;
}

export interface GameHistory {
  game: GameRow;
  params: HistoryParams;
  series: NamedSeries[];
  /** Distinct data sources present ("synthetic" means demo data). */
  sources: string[];
  observations: number;
  truncated: boolean;
}

export async function loadGameHistory(
  db: Database,
  gameId: string,
  params: HistoryParams,
): Promise<GameHistory | null> {
  const game = await getGame(db, gameId);
  if (!game) return null;
  const { rows, truncated } = await selectionHistory(db, {
    eventId: game.id,
    market: params.market,
    selection: params.selection,
    bookmakerKeys: params.books,
    from: params.from,
    to: params.to,
    includeLive: params.includeLive,
  });
  const series = buildSeriesByBook(rows, {
    gapMinutes: params.gapMinutes,
    resolution: params.resolution,
  }).map((s) => ({
    ...s,
    displayName: getBookmakerInfo(s.bookmakerKey)?.displayName ?? s.bookmakerKey,
  }));
  return {
    game,
    params,
    series,
    sources: [...new Set(rows.map((r) => r.source))].sort(),
    observations: rows.length,
    truncated,
  };
}
