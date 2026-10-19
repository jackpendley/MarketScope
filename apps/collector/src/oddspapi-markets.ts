// OddsPapi market catalog (all sports, ~17 MB) with a local cache, so imports bill it once.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { OddsPapiClient } from "./providers/oddspapi/client";
import type { OddsPapiMarketMeta } from "./providers/oddspapi/transform";

const REPO_ROOT = path.resolve(import.meta.dirname, "../../..");
export const ODDSPAPI_CACHE_DIR = path.join(REPO_ROOT, "fixtures/oddspapi/local"); // gitignored
const MARKETS_CACHE = path.join(ODDSPAPI_CACHE_DIR, "markets.json");
const AMERICAN_FOOTBALL = 14;

/** American-football markets by id. Billable (1 request) only when the cache is missing. */
export async function loadNflMarkets(
  client: Pick<OddsPapiClient, "markets">,
): Promise<Map<number, OddsPapiMarketMeta>> {
  let catalog: OddsPapiMarketMeta[];
  if (existsSync(MARKETS_CACHE)) {
    catalog = JSON.parse(readFileSync(MARKETS_CACHE, "utf8"));
  } else {
    catalog = await client.markets();
    mkdirSync(ODDSPAPI_CACHE_DIR, { recursive: true });
    writeFileSync(MARKETS_CACHE, JSON.stringify(catalog));
  }
  return new Map(
    catalog
      .filter((m) => m.sportId === undefined || m.sportId === AMERICAN_FOOTBALL)
      .map((m) => [m.marketId, m]),
  );
}
