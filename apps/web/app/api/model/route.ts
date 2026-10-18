import { forwardTest, modelRunRecords, ratingVersion } from "@marketscope/db";
import { scorecard } from "@/lib/model-view";
import { apiError, handleUnexpected, ok } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";

/**
 * GET /api/model
 *
 * The live forward-test scorecard (each game's last pre-kickoff estimate vs the result and the
 * nflverse close) and the committed evaluation records (the one-time 2025 test).
 */
export async function GET() {
  try {
    const db = getDb();
    const version = await ratingVersion(db);
    if (!version) return apiError(404, "NOT_FOUND", "No model output has been written yet.");
    const [ft, runs] = await Promise.all([forwardTest(db, version), modelRunRecords(db, version)]);
    return ok(
      { scorecard: scorecard(ft.scored), pending: ft.pending, games: ft.scored, runs },
      {
        modelVersion: version,
        firstPredictedAt: ft.firstPredictedAt,
        disclaimer: "Model estimates made before kickoff. Not betting advice.",
      },
    );
  } catch (err) {
    return handleUnexpected(err, "GET /api/model");
  }
}
