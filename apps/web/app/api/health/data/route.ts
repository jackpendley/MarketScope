import { datasetFreshness, latestCompletedRun, recentRuns } from "@marketscope/db";
import { collectionStatus } from "@/lib/coverage-view";
import { handleUnexpected, ok } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";

/** GET /api/health/data — safe ingestion health summary (no credentials or infrastructure details). */
export async function GET() {
  try {
    const db = getDb();
    const now = new Date();
    const [latest, recent, datasets] = await Promise.all([
      latestCompletedRun(db),
      recentRuns(db, 10),
      datasetFreshness(db, now),
    ]);
    // Live collection only: historical imports are excluded by the queries.
    const { status, ageMinutes } = collectionStatus(latest, now);
    return ok({
      status,
      latestCompletedRun: latest && {
        startedAt: latest.startedAt,
        ageMinutes,
        eventsSeen: latest.eventsSeen,
        quotesSeen: latest.quotesSeen,
        creditsRemaining: latest.creditsRemaining,
        issueCounts: latest.issueCounts,
      },
      // Gaps by dataset (ADR-071): final games without line moves, partial imports, unscored games.
      datasets,
      recentRuns: recent.map((r) => ({
        status: r.status,
        startedAt: r.startedAt,
        eventsSeen: r.eventsSeen,
        errorCode: r.errorCode,
      })),
    });
  } catch (err) {
    return handleUnexpected(err, "GET /api/health/data");
  }
}
