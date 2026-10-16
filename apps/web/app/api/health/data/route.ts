import { latestCompletedRun, recentRuns } from "@marketscope/db";
import { calculateFreshness } from "@marketscope/shared";
import { handleUnexpected, ok } from "@/lib/server/api";
import { getDb } from "@/lib/server/db";

/** Collection is expected every 6 hours; twice that without a success means it's behind. */
const STALE_AFTER_MINUTES = 12 * 60;

/** GET /api/health/data — safe ingestion health summary (no credentials or infrastructure details). */
export async function GET() {
  try {
    const db = getDb();
    const [latest, recent] = await Promise.all([latestCompletedRun(db), recentRuns(db, 10)]);
    const now = new Date();
    const ageMinutes = latest
      ? Math.round(calculateFreshness(latest.startedAt, now, STALE_AFTER_MINUTES).ageMinutes)
      : null;
    const status = !latest ? "no-data" : ageMinutes! > STALE_AFTER_MINUTES ? "behind" : "ok";
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
