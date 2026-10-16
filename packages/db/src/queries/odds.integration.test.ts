import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { events, ingestionRuns, oddsObservations } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import {
  gameObservationStats,
  getGame,
  latestCompletedRun,
  latestQuotesForEvents,
  listGames,
  selectionHistory,
} from "./odds";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());
beforeEach(() => resetDatabase(sql));

async function run(
  jobKey: string,
  startedAt: string,
  status: "completed" | "failed" = "completed",
) {
  const [row] = await db
    .insert(ingestionRuns)
    .values({ jobKey, provider: "the-odds-api", requestType: "live", status, startedAt })
    .returning({ id: ingestionRuns.id });
  return row!.id;
}

async function game(
  providerEventId: string,
  commenceTimeUtc: string,
  home = "Buffalo Bills",
  away = "Miami Dolphins",
) {
  const [row] = await db
    .insert(events)
    .values({
      providerEventId,
      sportKey: "americanfootball_nfl",
      season: 2026,
      homeTeam: home,
      awayTeam: away,
      commenceTimeUtc,
    })
    .returning({ id: events.id });
  return row!.id;
}

type Obs = Partial<typeof oddsObservations.$inferInsert> & {
  ingestionRunId: string;
  eventId: string;
};
async function observe(rows: Obs[]) {
  await db.insert(oddsObservations).values(
    rows.map((r) => ({
      bookmakerKey: "draftkings",
      marketType: "spreads" as const,
      selection: "HOME" as const,
      point: -3.5,
      americanPrice: -110,
      observedAt: "2026-10-16T01:00:00Z",
      isLive: false,
      ...r,
    })),
  );
}

describe("listGames", () => {
  it("returns games in [from, to) soonest first, bounded by limit, with ISO UTC kickoffs", async () => {
    await game("late", "2026-10-19T00:20:00Z");
    await game("early", "2026-10-18T17:00:00Z");
    await game("outside", "2026-10-30T17:00:00Z");

    const games = await listGames(db, {
      from: "2026-10-18T00:00:00Z",
      to: "2026-10-25T00:00:00Z",
      limit: 10,
    });
    expect(games.map((g) => g.providerEventId)).toEqual(["early", "late"]);
    expect(games[0]!.commenceTime).toBe("2026-10-18T17:00:00.000Z");

    expect(
      await listGames(db, { from: "2026-10-18T00:00:00Z", to: "2026-10-25T00:00:00Z", limit: 1 }),
    ).toHaveLength(1);
  });
});

describe("getGame", () => {
  it("returns null for an unknown id", async () => {
    expect(await getGame(db, "00000000-0000-0000-0000-000000000000")).toBeNull();
  });
});

describe("latestQuotesForEvents", () => {
  it("returns the newest observation per book/market/selection", async () => {
    const evt = await game("g1", "2026-10-18T17:00:00Z");
    const r1 = await run("r1", "2026-10-16T01:00:00Z");
    const r2 = await run("r2", "2026-10-16T07:00:00Z");
    await observe([
      {
        ingestionRunId: r1,
        eventId: evt,
        point: -3.5,
        americanPrice: -110,
        observedAt: "2026-10-16T01:00:00Z",
      },
      {
        ingestionRunId: r2,
        eventId: evt,
        point: -3,
        americanPrice: -120,
        observedAt: "2026-10-16T07:00:00Z",
      },
      {
        ingestionRunId: r1,
        eventId: evt,
        bookmakerKey: "fanduel",
        point: -3.5,
        americanPrice: -108,
        observedAt: "2026-10-16T01:00:00Z",
      },
    ]);

    const quotes = await latestQuotesForEvents(db, [evt]);
    const dk = quotes.find((q) => q.bookmakerKey === "draftkings")!;
    expect(dk).toMatchObject({
      point: -3,
      americanPrice: -120,
      observedAt: "2026-10-16T07:00:00.000Z",
    });

    // FanDuel missed the newer snapshot: its last row is still returned, with its own (older)
    // observedAt, so the caller can label it stale instead of presenting it as current.
    const fd = quotes.find((q) => q.bookmakerKey === "fanduel")!;
    expect(fd.observedAt).toBe("2026-10-16T01:00:00.000Z");
    expect(quotes).toHaveLength(2);
  });

  it("keeps markets and selections separate and returns null moneyline points", async () => {
    const evt = await game("g1", "2026-10-18T17:00:00Z");
    const r1 = await run("r1", "2026-10-16T01:00:00Z");
    await observe([
      { ingestionRunId: r1, eventId: evt, marketType: "spreads", selection: "HOME", point: -3.5 },
      { ingestionRunId: r1, eventId: evt, marketType: "spreads", selection: "AWAY", point: 3.5 },
      {
        ingestionRunId: r1,
        eventId: evt,
        marketType: "h2h",
        selection: "HOME",
        point: null,
        americanPrice: -185,
      },
    ]);
    const quotes = await latestQuotesForEvents(db, [evt]);
    expect(quotes).toHaveLength(3);
    expect(quotes.find((q) => q.market === "h2h")!.point).toBeNull();
  });

  it("returns nothing for an empty id list without querying", async () => {
    expect(await latestQuotesForEvents(db, [])).toEqual([]);
  });
});

describe("gameObservationStats", () => {
  it("counts observations and distinct snapshots", async () => {
    const evt = await game("g1", "2026-10-18T17:00:00Z");
    const r1 = await run("r1", "2026-10-16T01:00:00Z");
    const r2 = await run("r2", "2026-10-16T07:00:00Z");
    await observe([
      { ingestionRunId: r1, eventId: evt, observedAt: "2026-10-16T01:00:00Z" },
      {
        ingestionRunId: r1,
        eventId: evt,
        bookmakerKey: "fanduel",
        observedAt: "2026-10-16T01:00:00Z",
      },
      { ingestionRunId: r2, eventId: evt, observedAt: "2026-10-16T07:00:00Z" },
    ]);
    expect(await gameObservationStats(db, evt)).toEqual({
      observations: 3,
      snapshots: 2,
      firstObservedAt: "2026-10-16T01:00:00.000Z",
      lastObservedAt: "2026-10-16T07:00:00.000Z",
    });
  });

  it("handles a game with no observations", async () => {
    const evt = await game("g1", "2026-10-18T17:00:00Z");
    expect(await gameObservationStats(db, evt)).toEqual({
      observations: 0,
      snapshots: 0,
      firstObservedAt: null,
      lastObservedAt: null,
    });
  });
});

describe("latestCompletedRun", () => {
  it("ignores failed runs", async () => {
    await run("ok", "2026-10-16T01:00:00Z");
    await run("bad", "2026-10-16T07:00:00Z", "failed");
    expect((await latestCompletedRun(db))?.jobKey).toBe("ok");
  });
});

describe("selectionHistory", () => {
  it("returns one selection's observations by book then time, excluding in-play by default", async () => {
    const evt = await game("g1", "2026-10-18T17:00:00Z");
    const r1 = await run("r1", "2026-10-16T01:00:00Z");
    const r2 = await run("r2", "2026-10-16T07:00:00Z");
    const r3 = await run("r3", "2026-10-18T18:00:00Z");
    await observe([
      {
        ingestionRunId: r2,
        eventId: evt,
        point: -3,
        americanPrice: -120,
        observedAt: "2026-10-16T07:00:00Z",
      },
      {
        ingestionRunId: r1,
        eventId: evt,
        point: -3.5,
        americanPrice: -110,
        observedAt: "2026-10-16T01:00:00Z",
      },
      {
        ingestionRunId: r1,
        eventId: evt,
        bookmakerKey: "betmgm",
        point: -3.5,
        observedAt: "2026-10-16T01:00:00Z",
      },
      {
        ingestionRunId: r1,
        eventId: evt,
        selection: "AWAY",
        point: 3.5,
        observedAt: "2026-10-16T01:00:00Z",
      },
      {
        ingestionRunId: r3,
        eventId: evt,
        point: -7,
        observedAt: "2026-10-18T18:00:00Z",
        isLive: true,
      },
    ]);

    const { rows, truncated } = await selectionHistory(db, {
      eventId: evt,
      market: "spreads",
      selection: "HOME",
    });
    expect(truncated).toBe(false);
    expect(rows.map((r) => [r.bookmakerKey, r.observedAt, r.point])).toEqual([
      ["betmgm", "2026-10-16T01:00:00.000Z", -3.5],
      ["draftkings", "2026-10-16T01:00:00.000Z", -3.5],
      ["draftkings", "2026-10-16T07:00:00.000Z", -3],
    ]);
    expect(rows[0]!.source).toBe("the-odds-api");

    const withLive = await selectionHistory(db, {
      eventId: evt,
      market: "spreads",
      selection: "HOME",
      includeLive: true,
    });
    expect(withLive.rows).toHaveLength(4);
  });

  it("filters by books and time window and reports truncation", async () => {
    const evt = await game("g1", "2026-10-18T17:00:00Z");
    const r1 = await run("r1", "2026-10-16T01:00:00Z");
    const r2 = await run("r2", "2026-10-16T07:00:00Z");
    await observe([
      { ingestionRunId: r1, eventId: evt, observedAt: "2026-10-16T01:00:00Z" },
      { ingestionRunId: r2, eventId: evt, observedAt: "2026-10-16T07:00:00Z" },
      {
        ingestionRunId: r2,
        eventId: evt,
        bookmakerKey: "fanduel",
        observedAt: "2026-10-16T07:00:00Z",
      },
    ]);
    const base = { eventId: evt, market: "spreads" as const, selection: "HOME" as const };
    expect((await selectionHistory(db, { ...base, bookmakerKeys: ["fanduel"] })).rows).toHaveLength(
      1,
    );
    expect(
      (await selectionHistory(db, { ...base, from: "2026-10-16T06:00:00Z" })).rows,
    ).toHaveLength(2);
    expect(await selectionHistory(db, { ...base, limit: 2 })).toMatchObject({ truncated: true });
  });
});
