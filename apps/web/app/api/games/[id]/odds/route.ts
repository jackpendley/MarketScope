import type { NextRequest } from "next/server";
import { computeCoverage, toApiGame, toApiQuotes } from "@/lib/game-data";
import { gameIdSchema } from "@/lib/params";
import { apiError, handleUnexpected, ok } from "@/lib/server/api";
import { getDb, quoteFreshnessMinutes } from "@/lib/server/db";
import { loadGameDetail } from "@/lib/server/games";

/**
 * GET /api/games/:id/odds — latest observed quote per book/market/selection.
 * Each quote carries both ages: how long ago we collected it, and how long ago the
 * book reported updating it. Quotes are snapshots, never implied to be live.
 */
export async function GET(_request: NextRequest, ctx: RouteContext<"/api/games/[id]/odds">) {
  const { id } = await ctx.params;
  const parsedId = gameIdSchema.safeParse(id);
  if (!parsedId.success) return apiError(400, "INVALID_PARAMETERS", "`id` must be a UUID.");

  try {
    const detail = await loadGameDetail(getDb(), parsedId.data);
    if (!detail) return apiError(404, "NOT_FOUND", "No game with that id.");
    const now = new Date();
    const recentMinutes = quoteFreshnessMinutes();
    return ok(
      {
        game: toApiGame(detail.game, detail.quotes, now),
        quotes: toApiQuotes(detail.quotes, now, recentMinutes),
        consensus: detail.board.consensus,
      },
      {
        coverage: computeCoverage(detail.quotes),
        recentThresholdMinutes: recentMinutes,
        source: "The Odds API (periodic snapshots)",
      },
    );
  } catch (err) {
    return handleUnexpected(err, "GET /api/games/:id/odds");
  }
}
