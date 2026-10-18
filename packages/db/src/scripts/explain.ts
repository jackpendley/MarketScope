// EXPLAIN ANALYZE the app's hot read queries exactly as the app sends them (MS-023).
//
//   DATABASE_URL=… pnpm --filter @marketscope/db explain [--json]
//
// Each query function runs once through a Drizzle client whose logger captures the SQL
// and parameters; every captured statement is then re-run as
// EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) inside a READ ONLY transaction that is rolled
// back. Safe against production: nothing is written.

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import { requiresTls, usesTransactionPooler, type Database } from "../client";
import {
  databaseHasSyntheticData,
  eventSignalObservations,
  gameCoverage,
  gameObservationStats,
  latestCompletedRun,
  latestQuotesForEvents,
  listGames,
  listSignals,
  observationSummaries,
  ratingsForWeek,
  ratingVersion,
  ratingWeeks,
  recentRuns,
  selectionHistory,
  teamGames,
  teamRatingHistory,
} from "../queries";
import * as schema from "../schema";

interface Captured {
  name: string;
  query: string;
  params: unknown[];
}

interface PlanNode {
  "Node Type": string;
  "Relation Name"?: string;
  "Index Name"?: string;
  "Actual Rows"?: number;
  "Actual Loops"?: number;
  Plans?: PlanNode[];
}

function walk(node: PlanNode, visit: (n: PlanNode) => void) {
  visit(node);
  for (const child of node.Plans ?? []) walk(child, visit);
}

async function main() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("Set DATABASE_URL.");
  const sql = postgres(url, {
    max: 1,
    ssl: requiresTls(url) ? "require" : false,
    prepare: !usesTransactionPooler(url),
    onnotice: () => {},
  });

  const captured: Captured[] = [];
  let current = "";
  const db = drizzle({
    client: sql,
    schema,
    casing: "snake_case",
    logger: { logQuery: (query, params) => captured.push({ name: current, query, params }) },
  }) as unknown as Database;
  const step = async <T>(name: string, fn: () => Promise<T>): Promise<T> => {
    current = name;
    return fn();
  };

  try {
    const now = Date.now();
    const DAY = 86_400_000;
    // Representative inputs: the board's window, the replay index's window, and the game
    // with the most observations (the worst case for per-game queries).
    const board = await step("listGames (board, 7 days)", () =>
      listGames(db, {
        from: new Date(now - 4 * 3_600_000).toISOString(),
        to: new Date(now + 7 * DAY).toISOString(),
        limit: 100,
      }),
    );
    await step("latestQuotesForEvents (board)", () =>
      latestQuotesForEvents(
        db,
        board.map((g) => g.id),
      ),
    );
    await step("latestCompletedRun (board, health)", () => latestCompletedRun(db));
    await step("recentRuns (health)", () => recentRuns(db, 10));
    await step("databaseHasSyntheticData (every page)", () => databaseHasSyntheticData(db));

    const replay = await step("listGames (replay index, ±14 days)", () =>
      listGames(db, {
        from: new Date(now - 14 * DAY).toISOString(),
        to: new Date(now + 14 * DAY).toISOString(),
        limit: 100,
      }),
    );
    await step("observationSummaries (replay index)", () =>
      observationSummaries(
        db,
        replay.map((g) => g.id),
      ),
    );

    const [biggest] = await sql<{ event_id: string }[]>`
      SELECT event_id FROM odds_observations GROUP BY 1 ORDER BY count(*) DESC LIMIT 1`;
    if (biggest) {
      const eventId = biggest.event_id;
      await step("gameObservationStats (game page)", () => gameObservationStats(db, eventId));
      await step("selectionHistory (history page, spreads HOME)", () =>
        selectionHistory(db, { eventId, market: "spreads", selection: "HOME" }),
      );
      await step("eventSignalObservations (signals job)", () =>
        eventSignalObservations(db, eventId),
      );
      await step("listSignals (game)", () => listSignals(db, { eventId, limit: 300 }));
    }
    await step("gameCoverage (Data page, 150 days)", () =>
      gameCoverage(db, {
        from: new Date(now - 150 * DAY).toISOString(),
        to: new Date(now + 14 * DAY).toISOString(),
        // Mirrors FEED_COLUMNS in apps/web/lib/coverage-view.ts.
        feedColumns: {
          hardrockbet_az: "hardrock",
          hardrockbet: "hardrock",
          williamhill_us: "caesars",
        },
        limit: 400,
      }),
    );
    await step("listSignals (Signal Lab, 7 days)", () =>
      listSignals(db, { from: new Date(now - 7 * DAY).toISOString(), limit: 300 }),
    );
    await step("listSignals (Signal Lab, 30 days)", () =>
      listSignals(db, { from: new Date(now - 30 * DAY).toISOString(), limit: 300 }),
    );

    // Ratings pages (MS-033): the latest snapshot, a team's season and schedule.
    const version = await step("ratingVersion (ratings pages)", () => ratingVersion(db));
    if (version) {
      const weeks = await step("ratingWeeks (ratings pages)", () => ratingWeeks(db, version));
      const at = weeks.at(-1);
      if (at) {
        const table = await step("ratingsForWeek (ratings table)", () =>
          ratingsForWeek(db, { version, ...at }),
        );
        const team = table[0]?.team;
        if (team) {
          await step("teamRatingHistory (team page)", () =>
            teamRatingHistory(db, { version, team, season: at.season }),
          );
          await step("teamGames (team page schedule)", () =>
            teamGames(db, { version, team, season: at.season }),
          );
        }
      }
    }

    const results: {
      name: string;
      planningMs: number;
      executionMs: number;
      rows: number;
      sharedHit: number;
      sharedRead: number;
      scans: string[];
      plan: unknown;
    }[] = [];
    for (const c of captured) {
      const plan = await sql
        .begin("READ ONLY", async (tx) => {
          const [row] = await tx.unsafe(
            `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ${c.query}`,
            c.params as never[],
          );
          throw Object.assign(new Error("rollback"), {
            plan: (row as Record<string, unknown>)["QUERY PLAN"],
          });
        })
        .catch((e: { plan?: unknown }) => {
          if (!e.plan) throw e;
          return e.plan as [
            {
              Plan: PlanNode & Record<string, number>;
              "Planning Time": number;
              "Execution Time": number;
            },
          ];
        });
      const top = plan[0];
      const scans: string[] = [];
      walk(top.Plan, (n) => {
        if (n["Relation Name"] || n["Index Name"]) {
          scans.push(
            `${n["Node Type"]} ${n["Index Name"] ?? n["Relation Name"]} (${(n["Actual Rows"] ?? 0) * (n["Actual Loops"] ?? 1)} rows)`,
          );
        }
      });
      results.push({
        name: c.name,
        planningMs: top["Planning Time"],
        executionMs: top["Execution Time"],
        rows: top.Plan["Actual Rows"] ?? 0,
        sharedHit: top.Plan["Shared Hit Blocks"] ?? 0,
        sharedRead: top.Plan["Shared Read Blocks"] ?? 0,
        scans,
        plan: top,
      });
    }

    if (process.argv.includes("--json")) {
      console.log(JSON.stringify(results, null, 2));
      return;
    }
    for (const r of results) {
      console.log(
        `${r.name}\n  ${r.executionMs.toFixed(2)} ms exec · ${r.planningMs.toFixed(2)} ms plan · ${r.rows} rows · buffers hit ${r.sharedHit} read ${r.sharedRead}`,
      );
      for (const s of r.scans) console.log(`    ${s}`);
    }
  } finally {
    await sql.end({ timeout: 5 });
  }
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
});
