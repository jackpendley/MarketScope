import { createDb, events, ingestionRuns, lineMoves } from "@marketscope/db";
import { resetDatabase, TEST_DATABASE_URL } from "@marketscope/db/testing";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { crossCheckSnapshots, importLineMoves, lineMovesJobKey } from "./line-moves-import";
import { importFixture } from "./oddspapi-import";
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
const entry = (createdAt: string, price: number, limit: number | null = null) => ({
  createdAt,
  price,
  active: true,
  limit,
});
const book = () => ({
  markets: {
    "100": {
      outcomes: {
        "100": { players: { "0": [entry("2026-10-10T08:00:00Z", 1.91, 5000)] } },
        "101": { players: { "0": [entry("2026-10-10T08:00:00Z", 1.91, 5000)] } },
      },
    },
    "141": {
      outcomes: {
        "141": {
          players: {
            "0": [entry("2026-10-10T08:00:00Z", 1.5), entry("2026-10-11T03:00:00Z", 1.45)],
          },
        },
        "142": {
          players: {
            "0": [entry("2026-10-10T08:00:00Z", 2.75), entry("2026-10-11T03:00:00Z", 2.9)],
          },
        },
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

describe("importLineMoves", () => {
  it("stores each mapped book's moves under a new event, as a completed run", async () => {
    const client = fakeClient();
    const outcome = await importLineMoves({ db, client, markets }, fixture);
    // 7 books: spreads 1 row + moneyline 2 rows each.
    expect(outcome).toMatchObject({ status: "imported", moves: 21 });
    expect(client.historicalOdds).toHaveBeenCalledTimes(3);

    const books = await sql<{ bookmaker_key: string; n: number }[]>`
      SELECT bookmaker_key, count(*)::int AS n FROM line_moves GROUP BY 1 ORDER BY 1`;
    expect(books.map((b) => b.bookmaker_key)).toEqual([
      "bookmaker_eu",
      "circa",
      "draftkings",
      "fanduel",
      "hardrockbet",
      "pinnacle",
      "williamhill_us",
    ]);
    const [spread] = await sql`
      SELECT point, price1, price2, limit1, changed_at FROM line_moves
      WHERE bookmaker_key = 'pinnacle' AND market_type = 'spreads'`;
    expect(spread).toMatchObject({ point: "-3.0", price1: -110, price2: -110, limit1: 5000 });

    const [run] = await db.select().from(ingestionRuns);
    expect(run).toMatchObject({
      jobKey: lineMovesJobKey("id1"),
      status: "completed",
      quotesSeen: 21,
    });
    const [evt] = await db.select().from(events);
    expect(evt).toMatchObject({ providerEventId: "oddspapi:id1", season: 2026 });
  });

  it("attaches to the game's existing live event instead of creating one", async () => {
    const [live] = await db
      .insert(events)
      .values({
        providerEventId: "the-odds-api-event",
        sportKey: "americanfootball_nfl",
        season: 2026,
        homeTeam: "Green Bay Packers",
        awayTeam: "Chicago Bears",
        commenceTimeUtc: "2026-10-11T17:00:00Z",
      })
      .returning({ id: events.id });
    const outcome = await importLineMoves({ db, client: fakeClient(), markets }, fixture);
    expect(outcome).toMatchObject({ status: "imported", eventId: live!.id });
    expect(await db.$count(events)).toBe(1);
  });

  it("is idempotent: a completed fixture is skipped without fetching", async () => {
    await importLineMoves({ db, client: fakeClient(), markets }, fixture);
    const client = fakeClient();
    expect(await importLineMoves({ db, client, markets }, fixture)).toMatchObject({
      status: "already-imported",
    });
    expect(client.historicalOdds).not.toHaveBeenCalled();
    expect(await db.$count(lineMoves)).toBe(21);
  });

  it("records a failure, then a retry replaces it with a completed run", async () => {
    expect(await importLineMoves({ db, client: fakeClient(true), markets }, fixture)).toMatchObject(
      { status: "failed" },
    );
    const [failed] = await db.select().from(ingestionRuns);
    expect(failed).toMatchObject({ status: "failed", errorCode: "IMPORT" });
    expect(await importLineMoves({ db, client: fakeClient(), markets }, fixture)).toMatchObject({
      status: "imported",
    });
    const runs = await db.select().from(ingestionRuns);
    expect(runs.map((r) => r.status)).toEqual(["completed"]);
  });
});

describe("crossCheckSnapshots", () => {
  it("finds every stored snapshot reproduced by the stored moves", async () => {
    await importFixture({ db, client: fakeClient(), markets }, fixture);
    await importLineMoves({ db, client: fakeClient(), markets }, fixture);
    const rows = await crossCheckSnapshots(db);
    expect(rows.map((r) => r.bookmakerKey)).toEqual([
      "draftkings",
      "fanduel",
      "hardrockbet",
      "pinnacle",
      "williamhill_us",
    ]);
    expect(rows.every((r) => r.snapshots > 0 && r.matched === r.snapshots)).toBe(true);
  });

  it("counts a snapshot whose price disagrees as unmatched", async () => {
    await importFixture({ db, client: fakeClient(), markets }, fixture);
    await importLineMoves({ db, client: fakeClient(), markets }, fixture);
    await sql`UPDATE line_moves SET price1 = -150 WHERE bookmaker_key = 'pinnacle' AND market_type = 'h2h'`;
    const pinnacle = (await crossCheckSnapshots(db)).find((r) => r.bookmakerKey === "pinnacle")!;
    expect(pinnacle.matched).toBeLessThan(pinnacle.snapshots);
  });
});
