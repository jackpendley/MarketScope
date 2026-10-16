import "server-only";
import {
  gameObservationStats,
  getGame,
  latestQuotesForEvents,
  listGames,
  type Database,
  type GameObservationStats,
  type GameRow,
  type LatestQuoteRow,
} from "@marketscope/db";
import { BOARD_BOOKS } from "@marketscope/shared";
import { groupByEvent, toNormalizedEvent, toNormalizedQuote } from "@/lib/game-data";
import { buildEventBoard, type EventBoard } from "@/lib/odds-board";

export interface GameWindow {
  from: string;
  to: string;
  limit: number;
}

export interface GameWithQuotes {
  game: GameRow;
  quotes: LatestQuoteRow[];
}

/** Games in a window plus each one's latest quote per book/market/selection (2 queries). */
export async function loadGamesWithQuotes(
  db: Database,
  window: GameWindow,
): Promise<GameWithQuotes[]> {
  const games = await listGames(db, window);
  const quotes = groupByEvent(
    await latestQuotesForEvents(
      db,
      games.map((g) => g.id),
    ),
  );
  return games.map((game) => ({ game, quotes: quotes.get(game.id) ?? [] }));
}

/** True when any quote comes from generated demo data rather than the provider. */
export function hasSyntheticData(items: readonly GameWithQuotes[]): boolean {
  return items.some(({ quotes }) => quotes.some((q) => q.source === "synthetic"));
}

export function toBoard({ game, quotes }: GameWithQuotes): EventBoard {
  return buildEventBoard(
    {
      gameId: game.id,
      event: toNormalizedEvent(game),
      quotes: quotes.map((q) => toNormalizedQuote(game, q)),
    },
    BOARD_BOOKS,
  );
}

export interface GameDetail extends GameWithQuotes {
  board: EventBoard;
  stats: GameObservationStats;
}

export async function loadGameDetail(db: Database, id: string): Promise<GameDetail | null> {
  const game = await getGame(db, id);
  if (!game) return null;
  const [quotes, stats] = await Promise.all([
    latestQuotesForEvents(db, [game.id]),
    gameObservationStats(db, game.id),
  ]);
  const withQuotes = { game, quotes };
  return { ...withQuotes, board: toBoard(withQuotes), stats };
}
