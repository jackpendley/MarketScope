// Coverage probe: which of these bookmaker keys return NFL events right now?
//
//   pnpm --filter @marketscope/collector probe:books --books hardrockbet,hardrockbet_az --markets h2h
//
// Costs markets × ceil(books / 10) credits. Prints counts only (no prices).

import { parseArgs } from "node:util";
import { ConfigError, loadConfig, requireOddsApiKey } from "../config";
import {
  createTheOddsApiClient,
  estimateOddsCost,
  ProviderError,
} from "../providers/the-odds-api/client";

const SPORT_KEY = "americanfootball_nfl";

async function main() {
  const { values } = parseArgs({
    options: {
      books: { type: "string" },
      markets: { type: "string", default: "h2h" },
    },
  });
  if (!values.books) throw new ConfigError("--books is required (comma-separated bookmaker keys)");
  const books = values.books
    .split(",")
    .map((b) => b.trim())
    .filter(Boolean);
  const markets = values.markets
    .split(",")
    .map((m) => m.trim())
    .filter(Boolean);

  const config = loadConfig();
  const client = createTheOddsApiClient({
    apiKey: requireOddsApiKey(config),
    baseUrl: config.ODDS_API_BASE_URL,
    timeoutMs: config.HTTP_TIMEOUT_MS,
  });

  const cost = estimateOddsCost(markets, books);
  const events = await client.fetchEvents(SPORT_KEY); // free; also reports remaining credits
  const remaining = events.usage.requestsRemaining;
  if (remaining !== null && remaining - cost < config.MIN_CREDITS_REMAINING) {
    throw new Error(
      `Only ${remaining} credits remain; refusing to go below MIN_CREDITS_REMAINING=${config.MIN_CREDITS_REMAINING}`,
    );
  }

  console.log(
    `Probing ${books.length} book(s), markets=${markets.join(",")}, estimated ${cost} credit(s)`,
  );
  const odds = await client.fetchOdds({ sportKey: SPORT_KEY, bookmakers: books, markets });
  const payload = Array.isArray(odds.data) ? odds.data : [];

  const counts = new Map<string, number>(books.map((b) => [b, 0]));
  for (const event of payload as { bookmakers?: { key: string }[] }[]) {
    for (const bm of event.bookmakers ?? []) counts.set(bm.key, (counts.get(bm.key) ?? 0) + 1);
  }
  console.table([...counts].map(([book, eventsWithData]) => ({ book, eventsWithData })));
  console.log(
    `Events in response: ${payload.length}. Credits: this request ${odds.usage.requestsLast ?? "?"}, remaining ${odds.usage.requestsRemaining ?? "?"}`,
  );
}

main().catch((err: unknown) => {
  if (err instanceof ConfigError || err instanceof ProviderError) {
    console.error(err.message);
  } else {
    console.error(err instanceof Error ? err.message : err);
  }
  process.exitCode = 1;
});
