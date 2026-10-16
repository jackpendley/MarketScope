// MS-005: collect current NFL odds into PostgreSQL.
//
//   pnpm collect:nfl                     manual run (fresh job key every time)
//   pnpm collect:nfl --scheduled         one job key per COLLECT_SLOT_MINUTES slot (cron-safe)
//   pnpm collect:nfl --job-key <key>     retry a specific job (completed keys are not re-run)

import { createDb } from "@marketscope/db";
import { parseArgs } from "node:util";
import { collectNflOdds, manualJobKey, scheduledJobKey } from "../collect";
import { ConfigError, loadConfig, requireDatabaseUrl, requireOddsApiKey } from "../config";
import { jsonLogger } from "../log";
import { createTheOddsApiClient } from "../providers/the-odds-api/client";

async function main() {
  const { values } = parseArgs({
    options: {
      scheduled: { type: "boolean", default: false },
      "job-key": { type: "string" },
    },
  });
  const config = loadConfig();
  const jobKey =
    values["job-key"] ??
    (values.scheduled ? scheduledJobKey(new Date(), config.COLLECT_SLOT_MINUTES) : manualJobKey());

  const client = createTheOddsApiClient({
    apiKey: requireOddsApiKey(config),
    baseUrl: config.ODDS_API_BASE_URL,
    timeoutMs: config.HTTP_TIMEOUT_MS,
  });
  const { db, close } = createDb(requireDatabaseUrl(config));
  try {
    const outcome = await collectNflOdds({ db, client, config, log: jsonLogger }, { jobKey });
    if (outcome.status === "failed") process.exitCode = 1;
  } finally {
    await close();
  }
}

main().catch((err: unknown) => {
  if (err instanceof ConfigError) console.error(err.message);
  else
    jsonLogger.error("collect.crashed", {
      message: err instanceof Error ? err.message : String(err),
    });
  process.exitCode = 1;
});
