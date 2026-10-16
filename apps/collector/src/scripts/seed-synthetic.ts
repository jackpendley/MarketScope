// Seed a demo/e2e database with deterministic SYNTHETIC odds history, run through the
// real collector (normalizer, transactions, constraints) with source = "synthetic".
//
//   DATABASE_URL=postgres://localhost:5432/marketscope_demo pnpm --filter @marketscope/collector seed:synthetic --reset
//
// Deliberately does NOT read .env.local, and refuses database names without "e2e"/"demo".

import { createDb } from "@marketscope/db";
import { runMigrations } from "@marketscope/db/migrate";
import { parseArgs } from "node:util";
import { collectNflOdds } from "../collect";
import { jsonLogger } from "../log";
import { assertSyntheticTarget, generateSyntheticHistory } from "../synthetic";

const { values } = parseArgs({
  options: {
    reset: { type: "boolean", default: false },
    snapshots: { type: "string", default: "20" },
  },
});

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("Set DATABASE_URL to a demo/e2e database.");
  process.exit(1);
}
assertSyntheticTarget(url);
await runMigrations(url);

const { db, sql, close } = createDb(url, { max: 2 });
try {
  if (values.reset) {
    await sql`TRUNCATE odds_observations, ingestion_payloads, ingestion_runs, events RESTART IDENTITY CASCADE`;
  }
  const snapshots = generateSyntheticHistory({
    now: new Date(),
    snapshots: Number(values.snapshots),
  });
  let quotes = 0;
  for (const snap of snapshots) {
    const client = {
      fetchOdds: async () => ({
        data: snap.payload,
        usage: { requestsRemaining: null, requestsUsed: null, requestsLast: null },
        httpStatus: 200,
        durationMs: 0,
        receivedAt: snap.receivedAt,
        attempts: 1,
      }),
    };
    const outcome = await collectNflOdds(
      {
        db,
        client,
        config: { MONTHLY_CREDIT_BUDGET: 0, MAX_CREDITS_PER_RUN: 0, MIN_CREDITS_REMAINING: 0 },
        source: "synthetic",
      },
      { jobKey: `synthetic:${snap.receivedAt}` },
    );
    if (outcome.status === "completed") quotes += outcome.quotesInserted;
    else if (outcome.status === "failed") throw new Error(`seed failed: ${outcome.errorMessage}`);
  }
  jsonLogger.info("seed.completed", { snapshots: snapshots.length, quotes });
} finally {
  await close();
}
