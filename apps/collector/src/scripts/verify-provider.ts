// MS-002: verify that The Odds API returns usable NFL data for our target books.
//
//   pnpm verify:provider            free checks only (/sports, /events): 0 credits
//   pnpm verify:provider --spend    also calls /odds once (3 credits on h2h,spreads,totals)
//
// Writes the raw /odds response to fixtures/the-odds-api/local/ (gitignored) and
// appends a price-free coverage summary to docs/PROVIDER_COVERAGE.md.

import { appendFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";
import {
  MARKETS,
  TARGET_BOOKMAKERS,
  TARGET_BOOKMAKER_KEYS,
  normalizeEventOdds,
  parseOddsResponse,
} from "@marketscope/shared";
import { ConfigError, loadConfig, requireOddsApiKey } from "../config";
import { buildCoverageReport, renderCoverageMarkdown } from "../coverage";
import {
  createTheOddsApiClient,
  estimateOddsCost,
  ProviderError,
} from "../providers/the-odds-api/client";

const SPORT_KEY = "americanfootball_nfl";
const REPO_ROOT = path.resolve(import.meta.dirname, "../../../..");
const CAPTURE_DIR = path.join(REPO_ROOT, "fixtures/the-odds-api/local");
const COVERAGE_DOC = path.join(REPO_ROOT, "docs/PROVIDER_COVERAGE.md");

async function main() {
  const { values } = parseArgs({ options: { spend: { type: "boolean", default: false } } });
  const config = loadConfig();
  const client = createTheOddsApiClient({
    apiKey: requireOddsApiKey(config),
    baseUrl: config.ODDS_API_BASE_URL,
    timeoutMs: config.HTTP_TIMEOUT_MS,
  });

  console.log("1) GET /v4/sports (free)");
  const sports = await client.fetchSports();
  const nfl = sports.data.find((s) => s.key === SPORT_KEY);
  if (!nfl) throw new Error(`Sport "${SPORT_KEY}" not found in /sports`);
  console.log(
    `   ${SPORT_KEY}: "${nfl.title}" active=${nfl.active}  (credits remaining: ${sports.usage.requestsRemaining ?? "?"})`,
  );

  console.log("2) GET /v4/sports/americanfootball_nfl/events (free)");
  const events = await client.fetchEvents(SPORT_KEY);
  console.log(`   ${events.data.length} upcoming/in-progress events, ${events.durationMs} ms`);
  for (const e of events.data.slice(0, 5)) {
    console.log(`   - ${e.away_team} @ ${e.home_team}  ${e.commence_time}`);
  }

  const cost = estimateOddsCost(MARKETS, TARGET_BOOKMAKER_KEYS);
  if (!values.spend) {
    console.log(
      `\n3) Skipped GET /odds: estimated cost ${cost} credits. Re-run with --spend to make the paid call.`,
    );
    return;
  }
  if (cost > config.MAX_CREDITS_PER_RUN) {
    throw new Error(
      `Estimated cost ${cost} exceeds MAX_CREDITS_PER_RUN=${config.MAX_CREDITS_PER_RUN}`,
    );
  }
  const remaining = events.usage.requestsRemaining;
  if (remaining !== null && remaining - cost < config.MIN_CREDITS_REMAINING) {
    throw new Error(
      `Only ${remaining} credits remain; refusing to go below MIN_CREDITS_REMAINING=${config.MIN_CREDITS_REMAINING}`,
    );
  }

  console.log(`3) GET /v4/sports/americanfootball_nfl/odds (estimated ${cost} credits)`);
  const odds = await client.fetchOdds({
    sportKey: SPORT_KEY,
    bookmakers: TARGET_BOOKMAKER_KEYS,
    markets: MARKETS,
  });

  await mkdir(CAPTURE_DIR, { recursive: true });
  const capturePath = path.join(
    CAPTURE_DIR,
    `real-nfl-odds-${odds.receivedAt.replace(/[:.]/g, "-")}.json`,
  );
  await writeFile(capturePath, JSON.stringify(odds.data, null, 2));
  console.log(`   raw response saved (gitignored): ${path.relative(REPO_ROOT, capturePath)}`);

  const parsed = parseOddsResponse(odds.data);
  const results = parsed.events.map((e) =>
    normalizeEventOdds(e, { observedAt: odds.receivedAt, targetBookmakers: TARGET_BOOKMAKER_KEYS }),
  );
  const report = buildCoverageReport({
    results,
    rejectedCount: parsed.rejected.length,
    books: TARGET_BOOKMAKERS,
    markets: MARKETS,
    usage: odds.usage,
    durationMs: odds.durationMs,
    receivedAt: odds.receivedAt,
  });

  console.log(
    `   ${report.eventsReturned} events, ${report.durationMs} ms, credits used by request: ${odds.usage.requestsLast ?? "?"}, remaining: ${odds.usage.requestsRemaining ?? "?"}`,
  );
  console.table(
    report.books.map((b) => ({
      book: b.displayName,
      events: b.eventsWithData,
      moneyline: b.completeMarkets.h2h,
      spread: b.completeMarkets.spreads,
      total: b.completeMarkets.totals,
      latestUpdate: b.latestUpdate ?? "—",
    })),
  );
  if (parsed.rejected.length > 0) {
    console.warn(
      `   ${parsed.rejected.length} event(s) failed schema validation:`,
      parsed.rejected,
    );
  }

  await mkdir(path.dirname(COVERAGE_DOC), { recursive: true });
  await appendFile(COVERAGE_DOC, `\n${renderCoverageMarkdown(report)}`);
  console.log(`   coverage summary appended to ${path.relative(REPO_ROOT, COVERAGE_DOC)}`);
}

main().catch((err: unknown) => {
  if (err instanceof ConfigError) {
    console.error(err.message);
  } else if (err instanceof ProviderError) {
    console.error(`Provider error [${err.code}]: ${err.message}`);
    if (err.usage?.requestsRemaining != null)
      console.error(`Credits remaining: ${err.usage.requestsRemaining}`);
  } else {
    console.error(err instanceof Error ? err.message : err);
  }
  process.exitCode = 1;
});
