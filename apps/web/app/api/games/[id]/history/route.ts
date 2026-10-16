import type { NextRequest } from "next/server";
import { gameIdSchema, historyQuerySchema } from "@/lib/params";
import {
  apiError,
  handleUnexpected,
  invalidParams,
  ok,
  searchParamsObject,
} from "@/lib/server/api";
import { getDb } from "@/lib/server/db";
import { loadGameHistory } from "@/lib/server/history";

/**
 * GET /api/games/:id/history?market&selection&books&from&to&resolution&gapMinutes&includeLive
 *
 * Per-book series for one selection. Changes are detected by value and reported as
 * intervals between observations; gaps longer than gapMinutes are listed explicitly.
 * "changes" resolution (default) keeps first/last/changes/gap edges, so nothing
 * meaningful is dropped.
 */
export async function GET(request: NextRequest, ctx: RouteContext<"/api/games/[id]/history">) {
  const { id } = await ctx.params;
  if (!gameIdSchema.safeParse(id).success) {
    return apiError(400, "INVALID_PARAMETERS", "`id` must be a UUID.");
  }
  const parsed = historyQuerySchema.safeParse(searchParamsObject(request.url));
  if (!parsed.success) return invalidParams(parsed.error);

  try {
    const history = await loadGameHistory(getDb(), id, parsed.data);
    if (!history) return apiError(404, "NOT_FOUND", "No game with that id.");
    const { game, series, sources, observations, truncated, params } = history;
    return ok(
      {
        game: {
          id: game.id,
          homeTeam: game.homeTeam,
          awayTeam: game.awayTeam,
          commenceTime: game.commenceTime,
        },
        market: params.market,
        selection: params.selection,
        series,
      },
      {
        resolution: params.resolution,
        gapMinutes: params.gapMinutes,
        includeLive: params.includeLive,
        observations,
        truncated,
        sources,
        orientation:
          params.market === "spreads"
            ? `Points are the ${params.selection === "HOME" ? "home" : "away"} team's spread as posted.`
            : undefined,
      },
    );
  } catch (err) {
    return handleUnexpected(err, "GET /api/games/:id/history");
  }
}
