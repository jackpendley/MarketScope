import { createDb, events, ingestionRuns, oddsObservations } from "@marketscope/db";
import { resetDatabase, TEST_DATABASE_URL } from "@marketscope/db/testing";
import { eq } from "drizzle-orm";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { importFixture, oddspapiJobKey } from "./oddspapi-import";
import type { OddsPapiFixture } from "./providers/oddspapi/client";
import type { OddsPapiHistory, OddsPapiMarketMeta } from "./providers/oddspapi/transform";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 3 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

const markets = new Map<number, OddsPapiMarketMeta>([
  [
    100,
    {
      marketId: 100,
      marketType: "spreads",
      handicap: -3,
      period: "result",
      playerProp: false,
      outcomes: [
        { outcomeId: 100, outcomeName: "1" },
        { outcomeId: 101, outcomeName: "2" },
      ],
    },
  ],
  [
    141,
    {
      marketId: 141,
      marketType: "moneyline",
      handicap: 0,
      period: "result",
      playerProp: false,
      outcomes: [
        { outcomeId: 141, outcomeName: "1" },
        { outcomeId: 142, outcomeName: "2" },
      ],
    },
  ],
]);
const entry = (createdAt: string, price: number) => ({ createdAt, price, active: true });
const book = () => ({
  markets: {
    "100": {
      outcomes: {
        "100": { players: { "0": [entry("2026-10-10T08:00:00Z", 1.91)] } },
        "101": { players: { "0": [entry("2026-10-10T08:00:00Z", 1.91)] } },
      },
    },
    "141": {
      outcomes: {
        "141": { players: { "0": [entry("2026-10-10T08:00:00Z", 1.5)] } },
        "142": { players: { "0": [entry("2026-10-10T08:00:00Z", 2.75)] } },
      },
    },
  },
});
const fixture: OddsPapiFixture = {
  fixtureId: "id1",
  participant1Name: "Green Bay Packers",
  participant2Name: "Chicago Bears",
  startTime: "2026-10-11T17:00:00.000Z",
  statusId: 2,
};

function fakeClient(fail = false) {
  return {
    historicalOdds: vi.fn(
      async (_id: string, books: readonly string[]): Promise<OddsPapiHistory> => {
        if (fail) throw new Error("HTTP 500");
        return { bookmakers: Object.fromEntries(books.map((b) => [b, book()])) };
      },
    ),
  };
}

describe("importFixture", () => {
  it("stores derived snapshots for mapped books as a completed historical run", async () => {
    const client = fakeClient();
    const outcome = await importFixture({ db, client, markets }, fixture);
    expect(outcome).toMatchObject({ status: "imported", snapshots: 6 });
    expect(client.historicalOdds).toHaveBeenCalledTimes(2);

    const [evt] = await db.select().from(events).where(eq(events.providerEventId, "oddspapi:id1"));
    expect(evt).toMatchObject({
      homeTeam: "Green Bay Packers",
      awayTeam: "Chicago Bears",
      season: 2026,
    });

    const [run] = await db.select().from(ingestionRuns);
    expect(run).toMatchObject({
      provider: "oddspapi",
      requestType: "historical",
      status: "completed",
      jobKey: oddspapiJobKey("id1"),
    });

    const books = await sql<{ bookmaker_key: string; n: number }[]>`
      SELECT bookmaker_key, count(*)::int AS n FROM odds_observations GROUP BY 1 ORDER BY 1`;
    // 5 mapped books (betmgm is not requested/mapped), 6 snapshots x 4 selections each.
    expect(books.map((b) => b.bookmaker_key)).toEqual([
      "draftkings",
      "fanduel",
      "hardrockbet",
      "pinnacle",
      "williamhill_us",
    ]);
    expect(books.every((b) => b.n === 24)).toBe(true);
    const sources = await sql<{ source: string }[]>`SELECT DISTINCT source FROM odds_observations`;
    expect(sources.map((s) => s.source)).toEqual(["oddspapi"]);
  });

  it("is idempotent: a completed fixture is skipped without fetching", async () => {
    await importFixture({ db, client: fakeClient(), markets }, fixture);
    const client = fakeClient();
    expect(await importFixture({ db, client, markets }, fixture)).toMatchObject({
      status: "already-imported",
    });
    expect(client.historicalOdds).not.toHaveBeenCalled();
    expect(await db.$count(oddsObservations)).toBe(120);
  });

  it("refuses a game that was collected live, so sources never mix", async () => {
    await db.insert(events).values({
      providerEventId: "odds-api-abc",
      sportKey: "americanfootball_nfl",
      season: 2026,
      homeTeam: "Green Bay Packers",
      awayTeam: "Chicago Bears",
      commenceTimeUtc: "2026-10-11T17:00:00Z",
    });
    const client = fakeClient();
    expect(await importFixture({ db, client, markets }, fixture)).toMatchObject({
      status: "skipped-live-overlap",
    });
    expect(client.historicalOdds).not.toHaveBeenCalled();
  });

  it("records a failure and retries cleanly", async () => {
    expect(await importFixture({ db, client: fakeClient(true), markets }, fixture)).toMatchObject({
      status: "failed",
    });
    const [failed] = await db.select().from(ingestionRuns);
    expect(failed).toMatchObject({ status: "failed", errorCode: "IMPORT" });
    expect(await db.$count(oddsObservations)).toBe(0);

    expect(await importFixture({ db, client: fakeClient(), markets }, fixture)).toMatchObject({
      status: "imported",
    });
    expect(await db.$count(ingestionRuns)).toBe(1);
    expect(await db.$count(oddsObservations)).toBe(120);
  });
});
