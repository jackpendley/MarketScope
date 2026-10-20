// Backfill completed NFL games from OddsPapi line-move history (ADR-026).
//
//   pnpm --filter @marketscope/collector import:oddspapi [--from 2026-09-01] [--to 2026-10-16T00:00:00Z]
//        [--limit N] [--dry-run]
//
// Billable requests: 1 for fixtures (+1 for the market catalog only if the local cache is
// missing). History calls are free but rate-limited (5 s each, 2 per game).
// The default --to is when live Odds API collection began, so no game mixes sources.

import { createDb } from "@marketscope/db";
import { parseArgs } from "node:util";
import { ConfigError, loadConfig, requireDatabaseUrl, requireOddsPapiKey } from "../config";
import { jsonLogger } from "../log";
import { importFixture, ODDSPAPI_BOOK_MAP, ODDSPAPI_REQUEST_GROUPS } from "../oddspapi-import";
import { loadNflMarkets } from "../oddspapi-markets";
import { createOddsPapiClient, ODDSPAPI_NFL_TOURNAMENT_ID } from "../providers/oddspapi/client";
import { deriveObservations } from "../providers/oddspapi/transform";
import { recomputeSignals } from "../signals-job";

const LIVE_COLLECTION_START = "2026-10-16T00:00:00Z";

async function main() {
  const { values } = parseArgs({
    options: {
      from: { type: "string", default: "2026-09-01T00:00:00Z" },
      to: { type: "string", default: LIVE_COLLECTION_START },
      limit: { type: "string" },
      "dry-run": { type: "boolean", default: false },
    },
  });
  const config = loadConfig();
  const client = createOddsPapiClient({ apiKey: requireOddsPapiKey(config) });

  const before = await client.account();
  jsonLogger.info("oddspapi.quota", { ...before, when: "start" });

  const markets = await loadNflMarkets(client); // billable once, then cached

  const fixtures = (
    await client.fixtures({
      tournamentId: ODDSPAPI_NFL_TOURNAMENT_ID,
      statusId: 2,
      from: values.from!,
      to: values.to!,
    })
  )
    .filter((f) => f.startTime < values.to!)
    .sort((a, b) => a.startTime.localeCompare(b.startTime))
    .slice(0, values.limit ? Number(values.limit) : undefined);
  jsonLogger.info("oddspapi.fixtures", {
    count: fixtures.length,
    from: values.from,
    to: values.to,
  });

  if (values["dry-run"]) {
    for (const f of fixtures.slice(0, 2)) {
      const merged = { bookmakers: {} as Record<string, never> };
      for (const g of ODDSPAPI_REQUEST_GROUPS)
        Object.assign(merged.bookmakers, (await client.historicalOdds(f.fixtureId, g)).bookmakers);
      const rows = deriveObservations(merged, markets, {
        kickoff: f.startTime,
        bookMap: ODDSPAPI_BOOK_MAP,
      });
      jsonLogger.info("oddspapi.dry_run", {
        fixture: `${f.participant2Name} @ ${f.participant1Name}`,
        observations: rows.length,
        snapshots: new Set(rows.map((r) => r.observedAt)).size,
      });
    }
    return;
  }

  const { db, close } = createDb(requireDatabaseUrl(config));
  try {
    const counts: Record<string, number> = {};
    const imported: string[] = [];
    for (const [i, fixture] of fixtures.entries()) {
      const outcome = await importFixture({ db, client, markets, log: jsonLogger }, fixture);
      counts[outcome.status] = (counts[outcome.status] ?? 0) + 1;
      if (outcome.status === "imported") imported.push(outcome.eventId);
      if ((i + 1) % 10 === 0)
        jsonLogger.info("oddspapi.progress", { done: i + 1, of: fixtures.length, ...counts });
    }
    await recomputeSignals(db, imported, jsonLogger);
    jsonLogger.info("oddspapi.summary", { fixtures: fixtures.length, ...counts });
  } finally {
    await close();
  }
  const after = await client.account();
  jsonLogger.info("oddspapi.quota", { ...after, when: "end" });
}

main().catch((err: unknown) => {
  if (err instanceof ConfigError) console.error(err.message);
  else
    jsonLogger.error("oddspapi.crashed", {
      message: err instanceof Error ? err.message : String(err),
    });
  process.exitCode = 1;
});
