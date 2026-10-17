// Recompute Signal Lab detections for a set of games from their stored observations.
// Idempotent: each game's current-version signals are replaced in one transaction.

import { eventSignalObservations, replaceEventSignals, type Database } from "@marketscope/db";
import { computeSignals, SIGNAL_DEFINITIONS } from "@marketscope/shared";
import { silentLogger, type Logger } from "./log";

const CURRENT_DEFINITIONS = Object.values(SIGNAL_DEFINITIONS).map(({ type, version }) => ({
  type,
  version,
}));

export interface SignalsJobResult {
  events: number;
  signals: number;
  byType: Record<string, number>;
}

export async function recomputeSignals(
  db: Database,
  eventIds: readonly string[],
  log: Logger = silentLogger,
): Promise<SignalsJobResult> {
  const byType: Record<string, number> = {};
  let signals = 0;
  for (const eventId of eventIds) {
    const observations = await eventSignalObservations(db, eventId);
    const detections = computeSignals(observations);
    await replaceEventSignals(db, eventId, CURRENT_DEFINITIONS, detections);
    signals += detections.length;
    for (const d of detections) byType[d.type] = (byType[d.type] ?? 0) + 1;
  }
  const result = { events: eventIds.length, signals, byType };
  log.info("signals.recomputed", { ...result });
  return result;
}
