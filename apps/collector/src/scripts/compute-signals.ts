// Recompute signals for games kicking off from 2 days ago to 14 days ahead (or --all).
//   pnpm --filter @marketscope/collector signals:compute [--all]
import { createDb, eventIdsKickingOff } from "@marketscope/db";
import { parseArgs } from "node:util";
import { ConfigError, loadConfig, requireDatabaseUrl } from "../config";
import { jsonLogger } from "../log";
import { recomputeSignals } from "../signals-job";

const DAY = 24 * 3_600_000;

async function main() {
  const { values } = parseArgs({ options: { all: { type: "boolean", default: false } } });
  const { db, close } = createDb(requireDatabaseUrl(loadConfig()));
  try {
    const now = Date.now();
    const ids = values.all
      ? await eventIdsKickingOff(db, "1970-01-01T00:00:00Z", "2100-01-01T00:00:00Z")
      : await eventIdsKickingOff(
          db,
          new Date(now - 2 * DAY).toISOString(),
          new Date(now + 14 * DAY).toISOString(),
        );
    await recomputeSignals(db, ids, jsonLogger);
  } finally {
    await close();
  }
}

main().catch((err: unknown) => {
  if (err instanceof ConfigError) console.error(err.message);
  else
    jsonLogger.error("signals.crashed", {
      message: err instanceof Error ? err.message : String(err),
    });
  process.exitCode = 1;
});
