import type { NextRequest } from "next/server";
import { z } from "zod";
import { gameIdSchema } from "@/lib/params";
import {
  apiError,
  handleUnexpected,
  invalidParams,
  ok,
  searchParamsObject,
} from "@/lib/server/api";
import { getDb } from "@/lib/server/db";
import { loadMarketReplay, REPLAY_GAP_MINUTES } from "@/lib/server/replay";

const querySchema = z
  .object({
    market: z.enum(["spreads", "totals", "h2h"]).default("spreads"),
    selection: z.enum(["HOME", "AWAY", "OVER", "UNDER"]).optional(),
    pointsOnly: z
      .enum(["true", "false"])
      .default("false")
      .transform((v) => v === "true"),
  })
  .strict()
  .transform((q) => ({ ...q, selection: q.selection ?? (q.market === "totals" ? "OVER" : "HOME") }))
  .refine(
    (q) => (q.market === "totals" ? ["OVER", "UNDER"] : ["HOME", "AWAY"]).includes(q.selection),
    {
      message: "selection is not valid for this market",
      path: ["selection"],
    },
  );

/**
 * GET /api/games/:id/movements?market&selection&pointsOnly
 *
 * Detected line/price movements per book, oldest first. Each movement is an interval
 * between two observations with its direction (home orientation for spreads) and any
 * NFL key-number (3, 7) events. pointsOnly=true drops price-only changes.
 */
export async function GET(request: NextRequest, ctx: RouteContext<"/api/games/[id]/movements">) {
  const { id } = await ctx.params;
  if (!gameIdSchema.safeParse(id).success) {
    return apiError(400, "INVALID_PARAMETERS", "`id` must be a UUID.");
  }
  const parsed = querySchema.safeParse(searchParamsObject(request.url));
  if (!parsed.success) return invalidParams(parsed.error);
  const { market, selection, pointsOnly } = parsed.data;

  try {
    const data = await loadMarketReplay(getDb(), id, { market, chartSelection: selection });
    if (!data) return apiError(404, "NOT_FOUND", "No game with that id.");
    const movements = pointsOnly
      ? data.movements.filter((m) => m.direction !== "price-only")
      : data.movements;
    return ok(
      {
        game: { id: data.game.id, homeTeam: data.game.homeTeam, awayTeam: data.game.awayTeam },
        market,
        selection: data.chartSelection,
        movements,
      },
      {
        count: movements.length,
        gapMinutes: REPLAY_GAP_MINUTES,
        sources: data.sources,
        truncated: data.truncated,
      },
    );
  } catch (err) {
    return handleUnexpected(err, "GET /api/games/:id/movements");
  }
}
