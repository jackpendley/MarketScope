import type { NextRequest } from "next/server";
import { projectionsForWeek, projectionWeeks, ratingVersion } from "@marketscope/db";
import { parseRatingsQuery, resolveWeek } from "@/lib/ratings-view";
import { apiError, handleUnexpected, ok, searchParamsObject } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";

/**
 * GET /api/projections?season&week
 *
 * Simulated season odds for every team after one week (default: the latest), best playoff odds
 * first. Model estimates from simulated seasons (docs/RATINGS.md), not betting advice.
 */
export async function GET(request: NextRequest) {
  const q = parseRatingsQuery(searchParamsObject(request.url));
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) return apiError(404, "NOT_FOUND", "No projections have been computed yet.");
    const at = resolveWeek(await projectionWeeks(db, version), q);
    if (!at) return apiError(404, "NOT_FOUND", "No projections have been computed yet.");
    const rows = await projectionsForWeek(db, { version, ...at });
    return ok(rows, {
      count: rows.length,
      modelVersion: version,
      season: at.season,
      week: at.week,
      sims: rows[0]?.sims ?? 0,
      disclaimer: "Model estimates from simulated seasons. Not betting advice.",
    });
  } catch (err) {
    return handleUnexpected(err, "GET /api/projections");
  }
}
