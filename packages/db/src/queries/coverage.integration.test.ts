import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { events, ingestionRuns, marketSignals, oddsObservations } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import { gameCoverage } from "./coverage";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

const KICKOFF = "2026-10-18T17:00:00Z";
const FEEDS = { hardrockbet_az: "hardrock", hardrockbet: "hardrock", williamhill_us: "caesars" };
const window = {
  from: "2026-10-01T00:00:00Z",
  to: "2026-11-01T00:00:00Z",
  feedColumns: FEEDS,
  limit: 50,
};

async function setup() {
  const [run] = await db
    .insert(ingestionRuns)
    .values({
      jobKey: "r",
      provider: "the-odds-api",
      requestType: "live",
      status: "completed",
      startedAt: "2026-10-16T00:00:00Z",
    })
    .returning({ id: ingestionRuns.id });
  const [evt] = await db
    .insert(events)
    .values({
      providerEventId: "e1",
      sportKey: "americanfootball_nfl",
      season: 2026,
      homeTeam: "Buffalo Bills",
      awayTeam: "Miami Dolphins",
      commenceTimeUtc: KICKOFF,
    })
    .returning({ id: events.id });
  const obs = (
    bookmakerKey: string,
    observedAt: string,
    extra: Partial<typeof oddsObservations.$inferInsert> = {},
  ) => ({
    ingestionRunId: run!.id,
    eventId: evt!.id,
    bookmakerKey,
    marketType: "spreads" as const,
    selection: "HOME" as const,
    point: -3.5,
    americanPrice: -110,
    observedAt,
    isLive: false,
    ...extra,
  });
  await db.insert(oddsObservations).values([
    obs("draftkings", "2026-10-16T00:00:00Z"),
    obs("draftkings", "2026-10-16T06:00:00Z"),
    obs("draftkings", "2026-10-16T12:00:00Z"),
    obs("fanduel", "2026-10-16T06:00:00Z"),
    // Both Hard Rock feeds in one snapshot count once for the column.
    obs("hardrockbet_az", "2026-10-16T06:00:00Z"),
    obs("hardrockbet", "2026-10-16T06:00:00Z"),
    obs("hardrockbet", "2026-10-16T12:00:00Z"),
    // Not coverage: the away side, another market, and an in-play snapshot.
    obs("betmgm", "2026-10-16T06:00:00Z", { selection: "AWAY", point: 3.5 }),
    obs("betmgm", "2026-10-16T06:00:00Z", { marketType: "h2h", point: null }),
    obs("draftkings", "2026-10-18T18:00:00Z", { isLive: true }),
  ]);
  await db.insert(marketSignals).values({
    eventId: evt!.id,
    signalType: "line_move",
    algorithmVersion: 1,
    marketType: "spreads",
    selection: "HOME",
    detectedAt: "2026-10-16T06:00:00Z",
    windowStart: "2026-10-16T00:00:00Z",
    windowEnd: "2026-10-16T06:00:00Z",
    value: 0.5,
    details: {},
    evidenceObservationIds: [],
  });
  return evt!.id;
}

describe("gameCoverage", () => {
  it("counts pregame home-spread snapshots per game and per display column", async () => {
    const eventId = await setup();
    const [row] = await gameCoverage(db, window);
    expect(row).toMatchObject({
      eventId,
      sources: ["the-odds-api"],
      snapshots: 3,
      firstObservedAt: "2026-10-16T00:00:00.000Z",
      lastObservedAt: "2026-10-16T12:00:00.000Z",
      snapshotsByColumn: { draftkings: 3, fanduel: 1, hardrock: 2 },
      signals: 1,
    });
  });

  it("only includes games kicking off in the window", async () => {
    await setup();
    expect(await gameCoverage(db, { ...window, from: "2026-10-19T00:00:00Z" })).toEqual([]);
  });
});
