import type { NextRequest } from "next/server";
import { ratingsForWeek, ratingVersion, ratingWeeks } from "@marketscope/db";
import { parseRatingsQuery, resolveWeek } from "@/lib/ratings-view";
import { apiError, handleUnexpected, ok, searchParamsObject } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";

/**
 * GET /api/ratings?season&week
 *
 * MarketScope Ratings for one weekly snapshot (default: the latest), best AdjEM first. Values are
 * point-in-time model estimates (docs/RATINGS.md), not betting advice.
 */
export async function GET(request: NextRequest) {
  const q = parseRatingsQuery(searchParamsObject(request.url));
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) return apiError(404, "NOT_FOUND", "No ratings have been computed yet.");
    const weeks = await ratingWeeks(db, version);
    const at = resolveWeek(weeks, q);
    if (!at) return apiError(404, "NOT_FOUND", "No ratings have been computed yet.");
    const rows = await ratingsForWeek(db, { version, ...at });
    return ok(rows, {
      count: rows.length,
      modelVersion: version,
      season: at.season,
      week: at.week,
      disclaimer: "Model estimates (point-in-time). Not betting advice.",
    });
  } catch (err) {
    return handleUnexpected(err, "GET /api/ratings");
  }
}
