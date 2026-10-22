import { sql } from "drizzle-orm";
import type { Database } from "../client";

/**
 * Freshness by dataset, judged by gaps rather than by whether a job ran (ADR-071). A job can succeed
 * and still leave data missing: an import that skipped a book, or a nightly window that a long outage
 * outran. So each dataset is checked against what should exist by now:
 *   - line moves: final games of the current season with no moves at all, and `partial` imports;
 *   - results: games that kicked off long enough ago to be final but have no score.
 * `graceHours` allows for the nightly schedules before a missing row counts as a gap.
 */
export interface DatasetFreshness {
  lineMoves: {
    status: "ok" | "gaps";
    latestImportAt: string | null;
    partialImports: number;
    finalsWithoutMoves: number;
    oldestMissingKickoff: string | null;
  };
  results: {
    status: "ok" | "gaps";
    latestFinalAt: string | null;
    pastKickoffWithoutScore: number;
  };
}

const iso = (col: string) =>
  sql.raw(`to_char(${col} AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')`);

export async function datasetFreshness(
  db: Database,
  now: Date,
  graceHours = 36,
): Promise<DatasetFreshness> {
  const cutoff = new Date(now.getTime() - graceHours * 3_600_000).toISOString();
  const [moves] = await db.execute<{
    latest: string | null;
    partial: number;
    missing: number;
    oldest: string | null;
  }>(sql`
    WITH season AS (SELECT max(season) AS s FROM nfl_games),
    missing AS (
      SELECT g.kickoff_utc FROM nfl_games g, season
      WHERE g.season = season.s AND g.home_score IS NOT NULL AND g.event_id IS NOT NULL
        AND g.kickoff_utc < ${cutoff}
        AND NOT EXISTS (SELECT 1 FROM line_moves m WHERE m.event_id = g.event_id)
    )
    SELECT
      (SELECT ${iso("max(finished_at)")} FROM ingestion_runs
        WHERE job_key LIKE 'oddspapi-moves%' AND status IN ('completed', 'partial')) AS latest,
      (SELECT count(*)::int FROM ingestion_runs
        WHERE job_key LIKE 'oddspapi-moves%'
          AND (status = 'partial'
               -- runs before ADR-071 recorded a skipped book as completed with a too_large_* issue
               OR (status = 'completed' AND EXISTS (
                     SELECT 1 FROM jsonb_object_keys(coalesce(issue_counts, '{}'::jsonb)) k
                     WHERE k LIKE 'too_large_%')))) AS partial,
      (SELECT count(*)::int FROM missing) AS missing,
      (SELECT ${iso("min(kickoff_utc)")} FROM missing) AS oldest
  `);
  const [results] = await db.execute<{ latest: string | null; unscored: number }>(sql`
    WITH season AS (SELECT max(season) AS s FROM nfl_games)
    SELECT
      (SELECT ${iso("max(final_observed_at)")} FROM nfl_games) AS latest,
      (SELECT count(*)::int FROM nfl_games g, season
        WHERE g.season = season.s AND g.home_score IS NULL AND g.kickoff_utc < ${cutoff}) AS unscored
  `);
  return {
    lineMoves: {
      status: moves!.partial || moves!.missing ? "gaps" : "ok",
      latestImportAt: moves!.latest,
      partialImports: moves!.partial,
      finalsWithoutMoves: moves!.missing,
      oldestMissingKickoff: moves!.oldest,
    },
    results: {
      status: results!.unscored ? "gaps" : "ok",
      latestFinalAt: results!.latest,
      pastKickoffWithoutScore: results!.unscored,
    },
  };
}
