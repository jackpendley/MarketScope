import type { NextRequest } from "next/server";
import { gamesQuerySchema } from "@/lib/params";
import { toApiGame } from "@/lib/game-data";
import { handleUnexpected, invalidParams, ok, searchParamsObject } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";
import { loadGamesWithQuotes } from "@/lib/server/games";

/** GET /api/games?from&to&limit — NFL games in a window with per-game feed coverage. */
export async function GET(request: NextRequest) {
  const now = new Date();
  const parsed = gamesQuerySchema(now).safeParse(searchParamsObject(request.url));
  if (!parsed.success) return invalidParams(parsed.error);

  try {
    const games = await loadGamesWithQuotes(getDb(), parsed.data);
    return ok(
      games.map(({ game, quotes }) => toApiGame(game, quotes, now)),
      { ...parsed.data, count: games.length, source: "The Odds API (periodic snapshots)" },
    );
  } catch (err) {
    return handleUnexpected(err, "GET /api/games");
  }
}
