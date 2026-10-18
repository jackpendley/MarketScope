// Proves the database itself rejects invalid odds, independent of application code.
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "./client";
import { events, ingestionRuns, oddsObservations } from "./schema";
import { resetDatabase, TEST_DATABASE_URL } from "./testing";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());

let runId: string;
let eventId: string;

beforeEach(async () => {
  await resetDatabase(sql);
  const [run] = await db
    .insert(ingestionRuns)
    .values({ jobKey: "test:constraints", provider: "test", requestType: "live" })
    .returning({ id: ingestionRuns.id });
  const [event] = await db
    .insert(events)
    .values({
      providerEventId: "evt-1",
      sportKey: "americanfootball_nfl",
      season: 2026,
      homeTeam: "Buffalo Bills",
      awayTeam: "Miami Dolphins",
      commenceTimeUtc: "2026-10-18T17:00:00Z",
    })
    .returning({ id: events.id });
  runId = run!.id;
  eventId = event!.id;
});

type ObservationInput = typeof oddsObservations.$inferInsert;
function observation(overrides: Partial<ObservationInput> = {}): ObservationInput {
  return {
    ingestionRunId: runId,
    eventId,
    bookmakerKey: "draftkings",
    marketType: "spreads",
    selection: "HOME",
    point: -3.5,
    americanPrice: -110,
    observedAt: "2026-10-16T01:21:46Z",
    isLive: false,
    ...overrides,
  };
}

/** Drizzle wraps driver errors; the Postgres constraint name lives on `cause`. */
async function constraintViolated(promise: Promise<unknown>): Promise<string | undefined> {
  try {
    await promise;
  } catch (err) {
    const cause = (err as { cause?: { constraint_name?: string } }).cause;
    return cause?.constraint_name;
  }
  return undefined;
}

describe("odds_observations constraints", () => {
  it("accepts a valid spread and stores the point exactly", async () => {
    await db.insert(oddsObservations).values(observation());
    const [row] = await db.select().from(oddsObservations);
    expect(row).toMatchObject({ point: -3.5, americanPrice: -110, marketType: "spreads" });
  });

  it("rejects a moneyline with a point", async () => {
    expect(
      await constraintViolated(
        db.insert(oddsObservations).values(observation({ marketType: "h2h", point: 0 })),
      ),
    ).toBe("odds_observations_point_matches_market");
  });

  it("rejects a spread without a point", async () => {
    expect(
      await constraintViolated(db.insert(oddsObservations).values(observation({ point: null }))),
    ).toBe("odds_observations_point_matches_market");
  });

  it("rejects OVER/UNDER on a spread", async () => {
    expect(
      await constraintViolated(
        db.insert(oddsObservations).values(observation({ selection: "OVER" })),
      ),
    ).toBe("odds_observations_selection_matches_market");
  });

  it("rejects American prices between −100 and +100", async () => {
    expect(
      await constraintViolated(
        db.insert(oddsObservations).values(observation({ americanPrice: 50 })),
      ),
    ).toBe("odds_observations_valid_american_price");
  });

  it("rejects a duplicate selection within the same run", async () => {
    await db.insert(oddsObservations).values(observation());
    expect(
      await constraintViolated(
        db.insert(oddsObservations).values(observation({ americanPrice: -115 })),
      ),
    ).toBe("odds_observations_run_selection_time_uq");
  });

  it("rejects an unknown bookmaker", async () => {
    expect(
      await constraintViolated(
        db.insert(oddsObservations).values(observation({ bookmakerKey: "bovada" })),
      ),
    ).toBe("odds_observations_bookmaker_key_bookmakers_key_fk");
  });

  it("allows one historical run to hold the same selection at different snapshot times", async () => {
    await db.insert(oddsObservations).values(observation());
    await db.insert(oddsObservations).values(observation({ observedAt: "2026-10-16T07:21:46Z" }));
    expect(await db.$count(oddsObservations)).toBe(2);
  });

  it("allows the same selection in a different run (that's history)", async () => {
    const [run2] = await db
      .insert(ingestionRuns)
      .values({ jobKey: "test:constraints:2", provider: "test", requestType: "live" })
      .returning({ id: ingestionRuns.id });
    await db.insert(oddsObservations).values(observation());
    await db.insert(oddsObservations).values(observation({ ingestionRunId: run2!.id }));
    expect(await db.$count(oddsObservations)).toBe(2);
  });
});

describe("ingestion_runs", () => {
  it("enforces a unique job_key", async () => {
    expect(
      await constraintViolated(
        db
          .insert(ingestionRuns)
          .values({ jobKey: "test:constraints", provider: "test", requestType: "live" }),
      ),
    ).toBe("ingestion_runs_jobKey_unique");
  });
});

describe("Data API lock-down (ADR-018)", () => {
  it("enables row-level security on every table", async () => {
    const rows = await sql<{ relname: string; relrowsecurity: boolean }[]>`
      SELECT c.relname, c.relrowsecurity FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname`;
    expect(rows.map((r) => r.relname)).toEqual([
      "bookmakers",
      "events",
      "ingestion_payloads",
      "ingestion_runs",
      "market_signals",
      "nfl_games",
      "nfl_ingest_runs",
      "nfl_teams",
      "odds_observations",
    ]);
    expect(rows.every((r) => r.relrowsecurity)).toBe(true);
  });
});
