// MS-006: collector ↔ PostgreSQL integration tests. The provider is faked with the
// synthetic fixture; everything below the HTTP client is real (Drizzle, constraints,
// transactions).

import {
  createDb,
  events,
  ingestionPayloads,
  ingestionRuns,
  oddsObservations,
} from "@marketscope/db";
import { resetDatabase, TEST_DATABASE_URL } from "@marketscope/db/testing";
import {
  COLLECTED_BOOKMAKER_KEYS,
  normalizeEventOdds,
  parseOddsResponse,
} from "@marketscope/shared";
import { SYNTHETIC_NFL_ODDS } from "@marketscope/shared/fixtures";
import { eq, sql as dsql } from "drizzle-orm";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { collectNflOdds, scheduledJobKey, type CollectDeps } from "./collect";
import { ProviderError, type ProviderResponse } from "./providers/the-odds-api/client";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 3 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

const RECEIVED_AT = "2026-10-15T18:00:00.000Z";
const config: CollectDeps["config"] = {
  MONTHLY_CREDIT_BUDGET: 400,
  MAX_CREDITS_PER_RUN: 3,
  MIN_CREDITS_REMAINING: 25,
};

function oddsResponse(
  data: unknown = SYNTHETIC_NFL_ODDS,
  overrides: Partial<ProviderResponse<unknown>> = {},
): ProviderResponse<unknown> {
  return {
    data,
    usage: { requestsRemaining: 497, requestsUsed: 3, requestsLast: 3 },
    httpStatus: 200,
    durationMs: 12,
    receivedAt: RECEIVED_AT,
    attempts: 1,
    ...overrides,
  };
}

function fakeClient(...responses: (ProviderResponse<unknown> | Error)[]) {
  const fetchOdds = vi.fn(async () => {
    const next = responses.shift() ?? oddsResponse();
    if (next instanceof Error) throw next;
    return next;
  });
  return { fetchOdds };
}

/** How many quotes the normalizer produces for the synthetic fixture. */
const EXPECTED_QUOTES = parseOddsResponse(SYNTHETIC_NFL_ODDS).events.reduce(
  (n, e) =>
    n +
    normalizeEventOdds(e, { observedAt: RECEIVED_AT, targetBookmakers: COLLECTED_BOOKMAKER_KEYS })
      .quotes.length,
  0,
);

async function run(jobKey: string, client = fakeClient(), cfg = config) {
  return collectNflOdds({ db, client, config: cfg }, { jobKey });
}

describe("collectNflOdds — happy path", () => {
  it("persists events, payload, observations, and a completed run", async () => {
    const outcome = await run("manual:a");

    expect(outcome).toMatchObject({
      status: "completed",
      attempt: 1,
      eventsSeen: 3,
      quotesInserted: EXPECTED_QUOTES,
      creditsUsed: 3,
      creditsRemaining: 497,
    });
    expect(await db.$count(events)).toBe(3);
    expect(await db.$count(oddsObservations)).toBe(EXPECTED_QUOTES);
    expect(await db.$count(ingestionPayloads)).toBe(1);

    const [runRow] = await db.select().from(ingestionRuns);
    expect(runRow).toMatchObject({
      status: "completed",
      jobKey: "manual:a",
      eventsSeen: 3,
      quotesSeen: EXPECTED_QUOTES,
      creditsUsed: 3,
      creditsRemaining: 497,
      httpStatus: 200,
    });
    expect(runRow!.issueCounts).toMatchObject({ BOOKMAKER_MISSING: expect.any(Number) });
  });

  it("stores home orientation, spread signs, null moneyline points, and both timestamps", async () => {
    await run("manual:a");
    const rows = await sql<
      {
        home_team: string;
        point: string | null;
        market_type: string;
        observed_at: Date;
        bookmaker_updated_at: Date | null;
      }[]
    >`
      SELECT e.home_team, o.point, o.market_type, o.observed_at, o.bookmaker_updated_at
      FROM odds_observations o JOIN events e ON e.id = o.event_id
      WHERE e.provider_event_id = 'synthetic-evt-001' AND o.bookmaker_key = 'draftkings'
        AND o.selection = 'HOME' ORDER BY o.market_type`;
    expect(rows.map((r) => [r.market_type, r.point])).toEqual([
      ["h2h", null],
      ["spreads", "-3.5"],
    ]);
    expect(rows[0]!.home_team).toBe("Buffalo Bills");
    expect(new Date(rows[0]!.observed_at).toISOString()).toBe(RECEIVED_AT);
    expect(new Date(rows[0]!.bookmaker_updated_at!).toISOString()).toBe("2026-10-15T17:52:10.000Z");
  });

  it("stores the Hard Rock AZ and IN feeds as separate bookmakers", async () => {
    await run("manual:a");
    const books = await sql<{ bookmaker_key: string }[]>`
      SELECT DISTINCT bookmaker_key FROM odds_observations ORDER BY bookmaker_key`;
    expect(books.map((b) => b.bookmaker_key)).toEqual([
      "betmgm",
      "draftkings",
      "fanduel",
      "hardrockbet",
      "hardrockbet_az",
    ]);
  });
});

describe("collectNflOdds — history and idempotency", () => {
  it("two runs with different job keys create two observation sets but one copy of each event", async () => {
    await run("manual:a");
    await run(
      "manual:b",
      fakeClient(oddsResponse(SYNTHETIC_NFL_ODDS, { receivedAt: "2026-10-15T19:00:00.000Z" })),
    );

    expect(await db.$count(ingestionRuns)).toBe(2);
    expect(await db.$count(events)).toBe(3);
    expect(await db.$count(oddsObservations)).toBe(EXPECTED_QUOTES * 2);
    const times = await sql<
      { observed_at: Date }[]
    >`SELECT DISTINCT observed_at FROM odds_observations`;
    expect(times).toHaveLength(2);
  });

  it("re-running a completed job key does nothing and spends no credits", async () => {
    const client = fakeClient();
    await run("live:nfl:slot-1", client);
    const second = await run("live:nfl:slot-1", client);

    expect(second.status).toBe("already-completed");
    expect(client.fetchOdds).toHaveBeenCalledTimes(1);
    expect(await db.$count(oddsObservations)).toBe(EXPECTED_QUOTES);
  });

  it("a run still in progress is not claimed twice", async () => {
    await db
      .insert(ingestionRuns)
      .values({ jobKey: "live:nfl:busy", provider: "the-odds-api", requestType: "live" });
    const client = fakeClient();
    expect((await run("live:nfl:busy", client)).status).toBe("in-progress");
    expect(client.fetchOdds).not.toHaveBeenCalled();
  });

  it("a crashed run (started > 15 min ago) is reclaimed", async () => {
    await db.insert(ingestionRuns).values({
      jobKey: "live:nfl:crashed",
      provider: "the-odds-api",
      requestType: "live",
      startedAt: dsql`now() - interval '20 minutes'`,
    });
    const outcome = await run("live:nfl:crashed");
    expect(outcome).toMatchObject({ status: "completed", attempt: 2 });
  });

  it("updates kickoff time on re-collection but keeps the same event row", async () => {
    await run("manual:a");
    const moved = structuredClone(SYNTHETIC_NFL_ODDS) as { id: string; commence_time: string }[];
    moved[0]!.commence_time = "2026-10-18T20:25:00Z"; // flexed
    await run("manual:b", fakeClient(oddsResponse(moved)));

    const [evt] = await db
      .select()
      .from(events)
      .where(eq(events.providerEventId, "synthetic-evt-001"));
    expect(new Date(evt!.commenceTimeUtc).toISOString()).toBe("2026-10-18T20:25:00.000Z");
    expect(await db.$count(events)).toBe(3);
  });

  it("drops (and reports) quotes if the provider flips home/away for a known event", async () => {
    await run("manual:a");
    const flipped = structuredClone(SYNTHETIC_NFL_ODDS) as {
      id: string;
      home_team: string;
      away_team: string;
    }[];
    const e = flipped[0]!;
    [e.home_team, e.away_team] = [e.away_team, e.home_team];
    const outcome = await run("manual:b", fakeClient(oddsResponse(flipped)));

    expect(outcome.status).toBe("completed");
    if (outcome.status === "completed") {
      expect(outcome.issueCounts.EVENT_TEAMS_CHANGED).toBe(1);
    }
    const [row] = await sql<{ count: number }[]>`
      SELECT count(*)::int AS count FROM odds_observations o JOIN events ev ON ev.id = o.event_id
      JOIN ingestion_runs r ON r.id = o.ingestion_run_id
      WHERE ev.provider_event_id = 'synthetic-evt-001' AND r.job_key = 'manual:b'`;
    expect(row?.count).toBe(0);
  });
});

describe("collectNflOdds — failures", () => {
  it("records a provider failure with its error code and lets the same job key retry", async () => {
    const client = fakeClient(
      new ProviderError(
        "UPSTREAM_5XX",
        "GET /v4/sports/americanfootball_nfl/odds/ failed: HTTP 503",
        503,
        true,
        {
          requestsRemaining: 497,
          requestsUsed: 3,
          requestsLast: 0,
        },
      ),
    );
    const failed = await run("live:nfl:slot-2", client);
    expect(failed).toMatchObject({ status: "failed", errorCode: "UPSTREAM_5XX" });
    expect(await db.$count(oddsObservations)).toBe(0);

    const retried = await run("live:nfl:slot-2", client);
    expect(retried).toMatchObject({ status: "completed", attempt: 2 });
    expect(await db.$count(ingestionRuns)).toBe(1);
    expect(await db.$count(oddsObservations)).toBe(EXPECTED_QUOTES);
  });

  it("rolls back everything if persistence fails mid-transaction, but keeps the credit headers", async () => {
    // Make the database reject one bookmaker's rows after events/payload were written.
    await sql`CREATE OR REPLACE FUNCTION reject_betmgm() RETURNS trigger AS $$
      BEGIN IF NEW.bookmaker_key = 'betmgm' THEN RAISE EXCEPTION 'simulated failure'; END IF; RETURN NEW; END;
      $$ LANGUAGE plpgsql`;
    await sql`CREATE TRIGGER reject_betmgm BEFORE INSERT ON odds_observations FOR EACH ROW EXECUTE FUNCTION reject_betmgm()`;
    try {
      const outcome = await run("manual:boom");
      expect(outcome).toMatchObject({ status: "failed", errorCode: "PERSISTENCE" });
      if (outcome.status === "failed") expect(outcome.errorMessage).toContain("simulated failure");

      expect(await db.$count(events)).toBe(0);
      expect(await db.$count(ingestionPayloads)).toBe(0);
      expect(await db.$count(oddsObservations)).toBe(0);
      const [runRow] = await db.select().from(ingestionRuns);
      expect(runRow).toMatchObject({ status: "failed", creditsUsed: 3, creditsRemaining: 497 });
    } finally {
      await sql`DROP TRIGGER IF EXISTS reject_betmgm ON odds_observations`;
      await sql`DROP FUNCTION IF EXISTS reject_betmgm()`;
    }
  });

  it("fails cleanly when the payload is not an array", async () => {
    const outcome = await run("manual:bad", fakeClient(oddsResponse({ message: "nope" })));
    expect(outcome).toMatchObject({ status: "failed", errorCode: "PERSISTENCE" });
    expect(await db.$count(events)).toBe(0);
  });
});

describe("collectNflOdds — budget guard", () => {
  it("skips without calling the provider when the monthly budget would be exceeded", async () => {
    const client = fakeClient();
    const outcome = await run("manual:x", client, { ...config, MONTHLY_CREDIT_BUDGET: 2 });
    expect(outcome.status).toBe("skipped");
    expect(client.fetchOdds).not.toHaveBeenCalled();
    const [runRow] = await db.select().from(ingestionRuns);
    expect(runRow).toMatchObject({ status: "skipped", errorCode: "BUDGET" });
  });

  it("counts credits already spent this month", async () => {
    await run("manual:1");
    await run("manual:2");
    const client = fakeClient();
    const outcome = await run("manual:3", client, { ...config, MONTHLY_CREDIT_BUDGET: 8 });
    expect(outcome.status).toBe("skipped"); // 3 + 3 spent, +3 > 8
    expect(client.fetchOdds).not.toHaveBeenCalled();
  });

  it("respects the remaining-credits floor reported by the provider", async () => {
    await run(
      "manual:1",
      fakeClient(
        oddsResponse(SYNTHETIC_NFL_ODDS, {
          usage: { requestsRemaining: 27, requestsUsed: 473, requestsLast: 3 },
        }),
      ),
    );
    const client = fakeClient();
    const outcome = await run("manual:2", client);
    expect(outcome.status).toBe("skipped"); // 27 − 3 < 25
    expect(client.fetchOdds).not.toHaveBeenCalled();
  });

  it("a skipped job key can be retried once the budget allows", async () => {
    await run("live:nfl:slot-3", fakeClient(), { ...config, MONTHLY_CREDIT_BUDGET: 0 });
    const outcome = await run("live:nfl:slot-3");
    expect(outcome).toMatchObject({ status: "completed", attempt: 2 });
  });
});

describe("scheduledJobKey", () => {
  it("maps every time in a slot to the same key", () => {
    expect(scheduledJobKey(new Date("2026-10-16T07:59:00Z"), 360)).toBe(
      "live:nfl:2026-10-16T06:00:00.000Z",
    );
    expect(scheduledJobKey(new Date("2026-10-16T06:00:00Z"), 360)).toBe(
      "live:nfl:2026-10-16T06:00:00.000Z",
    );
    expect(scheduledJobKey(new Date("2026-10-16T12:00:00Z"), 360)).toBe(
      "live:nfl:2026-10-16T12:00:00.000Z",
    );
  });
});
