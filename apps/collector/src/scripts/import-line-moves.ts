// Minute-level line moves for completed NFL games, from OddsPapi history (MS-042, ADR-052).
//
//   pnpm --filter @marketscope/collector import:line-moves [--from 2026-09-01] [--to <now>]
//        [--limit N] [--dry-run] [--check] [--profile books|exchanges|fixes|all]
//
// Billable requests: 1 for fixtures (+1 for the market catalog when the local cache is
// missing). History calls are free but rate-limited (5 s each, 3 per game). Games already
// imported are skipped without any call, so the nightly run only fetches new finals.
// --check prints how well the stored moves reproduce the stored OddsPapi snapshots.
// fixes: ghost-market corrections (ADR-065), written to line_move_fixes; line_moves is untouched.

import { createDb } from "@marketscope/db";
import { parseArgs } from "node:util";
import { ConfigError, loadConfig, requireDatabaseUrl, requireOddsPapiKey } from "../config";
import {
  BOOKS_PROFILE,
  crossCheckSnapshots,
  EXCHANGES_PROFILE,
  FIXES_PROFILE,
  importLineMoves,
  type LineMoveProfile,
} from "../line-moves-import";
import { jsonLogger } from "../log";
import { loadNflMarkets } from "../oddspapi-markets";
import { createOddsPapiClient, ODDSPAPI_NFL_TOURNAMENT_ID } from "../providers/oddspapi/client";
import { deriveLineMoves } from "../providers/oddspapi/line-moves";

async function main() {
  const { values } = parseArgs({
    options: {
      from: { type: "string", default: "2026-09-01T00:00:00Z" },
      to: { type: "string", default: new Date().toISOString() },
      limit: { type: "string" },
      "dry-run": { type: "boolean", default: false },
      check: { type: "boolean", default: false },
      profile: { type: "string", default: "all" },
    },
  });
  const config = loadConfig();

  if (values.check) {
    const { db, close } = createDb(requireDatabaseUrl(config));
    try {
      for (const r of await crossCheckSnapshots(db))
        jsonLogger.info("line_moves.cross_check", {
          ...r,
          share: r.snapshots ? Number((r.matched / r.snapshots).toFixed(4)) : null,
        });
    } finally {
      await close();
    }
    return;
  }

  const all = [BOOKS_PROFILE, EXCHANGES_PROFILE, FIXES_PROFILE];
  const profiles: LineMoveProfile[] =
    values.profile === "all" ? all : all.filter((p) => p.name === values.profile);
  if (!profiles.length) throw new ConfigError(`Unknown --profile ${values.profile}`);
  const client = createOddsPapiClient({ apiKey: requireOddsPapiKey(config) });
  const before = await client.account();
  jsonLogger.info("oddspapi.quota", { ...before, when: "start" });
  const markets = await loadNflMarkets(client);

  const fixtures = (
    await client.fixtures({
      tournamentId: ODDSPAPI_NFL_TOURNAMENT_ID,
      statusId: 2, // finished
      from: values.from!,
      to: values.to!,
    })
  )
    .sort((a, b) => a.startTime.localeCompare(b.startTime))
    .slice(0, values.limit ? Number(values.limit) : undefined);
  jsonLogger.info("line_moves.fixtures", {
    count: fixtures.length,
    from: values.from,
    to: values.to,
  });

  if (values["dry-run"]) {
    const f = fixtures[0];
    if (!f) return;
    const profile = profiles[0]!;
    const merged = { bookmakers: {} as Record<string, never> };
    for (const g of profile.requestGroups)
      Object.assign(merged.bookmakers, (await client.historicalOdds(f.fixtureId, g)).bookmakers);
    const rows = deriveLineMoves(merged, markets, {
      kickoff: f.startTime,
      bookMap: profile.bookMap,
      limitBooks: profile.limitBooks,
      recordLimitBooks: profile.recordLimitBooks,
      markets: profile.markets,
    });
    const perBook: Record<string, number> = {};
    for (const r of rows) perBook[r.bookmakerKey] = (perBook[r.bookmakerKey] ?? 0) + 1;
    jsonLogger.info("line_moves.dry_run", {
      fixture: `${f.participant2Name} @ ${f.participant1Name}`,
      moves: rows.length,
      ...perBook,
    });
    return;
  }

  const { db, close } = createDb(requireDatabaseUrl(config));
  try {
    const counts: Record<string, number> = {};
    let moves = 0;
    for (const [i, fixture] of fixtures.entries()) {
      for (const profile of profiles) {
        const outcome = await importLineMoves(
          { db, client, markets, log: jsonLogger },
          fixture,
          profile,
        );
        const key = `${profile.name}_${outcome.status}`;
        counts[key] = (counts[key] ?? 0) + 1;
        if (outcome.status === "imported") moves += outcome.moves;
        if (outcome.status === "failed") counts.failed = (counts.failed ?? 0) + 1;
      }
      if ((i + 1) % 10 === 0)
        jsonLogger.info("line_moves.progress", { done: i + 1, of: fixtures.length, ...counts });
    }
    jsonLogger.info("line_moves.summary", { fixtures: fixtures.length, moves, ...counts });
    if (counts.failed) process.exitCode = 1;
  } finally {
    await close();
  }
  const after = await client.account();
  jsonLogger.info("oddspapi.quota", { ...after, when: "end" });
}

main().catch((err: unknown) => {
  if (err instanceof ConfigError) console.error(err.message);
  else
    jsonLogger.error("line_moves.crashed", {
      message: err instanceof Error ? err.message : String(err),
    });
  process.exitCode = 1;
});
