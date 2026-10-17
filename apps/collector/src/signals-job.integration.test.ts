import { createDb, eventIdsKickingOff, listSignals } from "@marketscope/db";
import { resetDatabase, TEST_DATABASE_URL } from "@marketscope/db/testing";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { collectNflOdds } from "./collect";
import { recomputeSignals } from "./signals-job";
import { generateSyntheticHistory } from "./synthetic";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 3 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

async function seed() {
  for (const snap of generateSyntheticHistory({ now: new Date("2026-10-16T12:00:00Z") })) {
    await collectNflOdds(
      {
        db,
        client: {
          fetchOdds: async () => ({
            data: snap.payload,
            usage: { requestsRemaining: null, requestsUsed: null, requestsLast: null },
            httpStatus: 200,
            durationMs: 0,
            receivedAt: snap.receivedAt,
            attempts: 1,
          }),
        },
        config: { MONTHLY_CREDIT_BUDGET: 0, MAX_CREDITS_PER_RUN: 0, MIN_CREDITS_REMAINING: 0 },
        source: "synthetic",
      },
      { jobKey: `synthetic:${snap.receivedAt}` },
    );
  }
  return eventIdsKickingOff(db, "1970-01-01T00:00:00Z", "2100-01-01T00:00:00Z");
}

describe("recomputeSignals", () => {
  it("stores evidence-backed signals for every game and is idempotent", async () => {
    const ids = await seed();
    const first = await recomputeSignals(db, ids);
    expect(first.events).toBe(3);
    expect(first.signals).toBeGreaterThan(0);
    expect(first.byType.line_move).toBeGreaterThan(0);

    const second = await recomputeSignals(db, ids);
    expect(second).toEqual(first);
    const stored = await listSignals(db, { limit: 500 });
    expect(stored).toHaveLength(Math.min(first.signals, 500));

    // Evidence ids point at real observations of the same game.
    const sample = stored[0]!;
    const [row] = await sql<{ n: number }[]>`
      SELECT count(*)::int AS n FROM odds_observations
      WHERE id = ANY(${sample.evidence}) AND event_id = ${sample.eventId}`;
    expect(row?.n).toBe(sample.evidence.length);
  });
});
