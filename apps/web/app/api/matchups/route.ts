import type { NextRequest } from "next/server";
import { currentWeek, matchupsForWeek, matchupWeeks, ratingVersion } from "@marketscope/db";
import { parseWeekQuery, resolveMatchupWeek } from "@/lib/model-view";
import { apiError, handleUnexpected, ok, searchParamsObject } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";

/**
 * GET /api/matchups?season&week
 *
 * One week's games (default: the next week with an unplayed game) with pre-game MarketScope ratings
 * and the last model estimate stored before kickoff. Model estimates, not betting advice.
 */
export async function GET(request: NextRequest) {
  const q = parseWeekQuery(searchParamsObject(request.url));
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) return apiError(404, "NOT_FOUND", "No model output has been written yet.");
    const [weeks, current] = await Promise.all([
      matchupWeeks(db, version),
      currentWeek(db, new Date().toISOString()),
    ]);
    const at = resolveMatchupWeek(weeks, q, current);
    if (!at) return apiError(404, "NOT_FOUND", "No games have been loaded yet.");
    const rows = await matchupsForWeek(db, { version, ...at });
    return ok(rows, {
      count: rows.length,
      modelVersion: version,
      season: at.season,
      week: at.week,
      disclaimer: "Model estimates made before kickoff. Not betting advice.",
    });
  } catch (err) {
    return handleUnexpected(err, "GET /api/matchups");
  }
}
