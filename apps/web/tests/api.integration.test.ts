// Calls the route handlers directly against the test database: validation, envelopes,
// status codes, freshness metadata, and stale-book handling.
import {
  createDb,
  events,
  ingestionRuns,
  oddsObservations,
  replaceEventSignals,
} from "@marketscope/db";
import { resetDatabase, TEST_DATABASE_URL } from "@marketscope/db/testing";
import { NextRequest } from "next/server";
import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { GET as getGameHistory } from "@/app/api/games/[id]/history/route";
import { GET as getGameMovements } from "@/app/api/games/[id]/movements/route";
import { GET as getGameOdds } from "@/app/api/games/[id]/odds/route";
import { GET as getGames } from "@/app/api/games/route";
import { GET as getDataHealth } from "@/app/api/health/data/route";
import { GET as getSignals } from "@/app/api/signals/route";
import { isConnectionError } from "@/lib/server/api";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());

const MIN = 60_000;
const now = Date.now();
const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();
const OLD_SNAPSHOT = iso(-120 * MIN);
const NEW_SNAPSHOT = iso(-30 * MIN);

let gameId: string;

beforeEach(async () => {
  await resetDatabase(sql);
  const [r1] = await db
    .insert(ingestionRuns)
    .values({
      jobKey: "r1",
      provider: "the-odds-api",
      requestType: "live",
      status: "completed",
      startedAt: OLD_SNAPSHOT,
    })
    .returning({ id: ingestionRuns.id });
  const [r2] = await db
    .insert(ingestionRuns)
    .values({
      jobKey: "r2",
      provider: "the-odds-api",
      requestType: "live",
      status: "completed",
      startedAt: NEW_SNAPSHOT,
      creditsRemaining: 490,
    })
    .returning({ id: ingestionRuns.id });
  const [game] = await db
    .insert(events)
    .values([
      {
        providerEventId: "soon",
        sportKey: "americanfootball_nfl",
        season: 2026,
        homeTeam: "Green Bay Packers",
        awayTeam: "Dallas Cowboys",
        commenceTimeUtc: iso(2 * 24 * 60 * MIN),
      },
      {
        providerEventId: "far",
        sportKey: "americanfootball_nfl",
        season: 2026,
        homeTeam: "Chicago Bears",
        awayTeam: "New England Patriots",
        commenceTimeUtc: iso(20 * 24 * 60 * MIN),
      },
    ])
    .returning({ id: events.id });
  gameId = game!.id;

  const base = {
    eventId: gameId,
    marketType: "spreads" as const,
    selection: "HOME" as const,
    isLive: false,
  };
  await db.insert(oddsObservations).values([
    {
      ...base,
      ingestionRunId: r1!.id,
      bookmakerKey: "fanduel",
      point: -1.5,
      americanPrice: -100,
      observedAt: OLD_SNAPSHOT,
    },
    {
      ...base,
      ingestionRunId: r2!.id,
      bookmakerKey: "draftkings",
      point: -1.5,
      americanPrice: -105,
      observedAt: NEW_SNAPSHOT,
      bookmakerUpdatedAt: iso(-35 * MIN),
    },
    {
      ...base,
      ingestionRunId: r2!.id,
      bookmakerKey: "betmgm",
      point: -1,
      americanPrice: -110,
      observedAt: NEW_SNAPSHOT,
    },
    {
      ...base,
      ingestionRunId: r2!.id,
      bookmakerKey: "hardrockbet",
      point: -1.5,
      americanPrice: -108,
      observedAt: NEW_SNAPSHOT,
    },
  ]);
});

const request = (path: string) => new NextRequest(`http://localhost${path}`);
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });

describe("GET /api/games", () => {
  it("returns games in the default 7-day window with coverage", async () => {
    const res = await getGames(request("/api/games"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.meta).toMatchObject({
      count: 1,
      limit: 50,
      source: expect.stringContaining("snapshots"),
    });
    expect(body.data).toHaveLength(1);
    expect(body.data[0]).toMatchObject({
      id: gameId,
      homeTeam: "Green Bay Packers",
      started: false,
      coverage: {
        latestObservedAt: NEW_SNAPSHOT,
        feedsInLatestSnapshot: ["draftkings", "betmgm", "hardrockbet"],
        feedsMissing: ["fanduel", "williamhill_us", "hardrockbet_az"],
      },
    });
  });

  it("honors an explicit window", async () => {
    const res = await getGames(request(`/api/games?from=${iso(0)}&to=${iso(30 * 24 * 60 * MIN)}`));
    expect((await res.json()).data).toHaveLength(2);
  });

  it.each([
    ["from=yesterday", "from"],
    ["limit=0", "limit"],
    ["limit=500", "limit"],
    [`from=${iso(0)}&to=${iso(-60 * MIN)}`, "to"],
    [`from=${iso(0)}&to=${iso(40 * 24 * 60 * MIN)}`, "to"],
  ])("rejects %s with 400", async (query, path) => {
    const res = await getGames(request(`/api/games?${query}`));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error.code).toBe("INVALID_PARAMETERS");
    expect(body.error.details.map((d: { path: string }) => d.path)).toContain(path);
  });

  it("rejects unknown parameters instead of silently ignoring them", async () => {
    const res = await getGames(request("/api/games?week=7"));
    expect(res.status).toBe(400);
  });
});

describe("GET /api/games/:id/odds", () => {
  it("returns latest quotes with collection age, book-update age, and stale flags", async () => {
    const res = await getGameOdds(request(`/api/games/${gameId}/odds`), ctx(gameId));
    expect(res.status).toBe(200);
    const { data, meta } = await res.json();

    const dk = data.quotes.find((q: { bookmakerKey: string }) => q.bookmakerKey === "draftkings");
    expect(dk.freshness).toMatchObject({ label: "snapshot", stale: false });
    expect(dk.freshness.collectionAgeMinutes).toBeCloseTo(30, 0);
    expect(dk.freshness.bookUpdateAgeMinutes).toBeCloseTo(35, 0);

    const fd = data.quotes.find((q: { bookmakerKey: string }) => q.bookmakerKey === "fanduel");
    expect(fd.freshness.stale).toBe(true);

    // Consensus uses current, displayed feeds only: DK −1.5, MGM −1, HR(IN) −1.5 → −1.5.
    expect(data.consensus).toEqual({
      homePoint: -1.5,
      bookmakerKeys: ["betmgm", "draftkings", "hardrockbet"],
    });
    expect(meta.coverage.feedsMissing).toContain("fanduel");
    expect(meta.recentThresholdMinutes).toBe(15);
  });

  it("returns 400 for a malformed id", async () => {
    const res = await getGameOdds(request("/api/games/abc/odds"), ctx("abc"));
    expect(res.status).toBe(400);
    expect((await res.json()).error.code).toBe("INVALID_PARAMETERS");
  });

  it("returns 404 for an unknown game", async () => {
    const id = "00000000-0000-4000-8000-000000000000";
    const res = await getGameOdds(request(`/api/games/${id}/odds`), ctx(id));
    expect(res.status).toBe(404);
    expect((await res.json()).error.code).toBe("NOT_FOUND");
  });
});

describe("GET /api/health/data", () => {
  it("summarizes the latest completed run", async () => {
    const res = await getDataHealth();
    const { data } = await res.json();
    expect(data.status).toBe("ok");
    expect(data.latestCompletedRun).toMatchObject({ creditsRemaining: 490 });
    expect(data.latestCompletedRun.ageMinutes).toBeGreaterThanOrEqual(29);
    expect(data.recentRuns).toHaveLength(2);
  });

  it("reports no-data on an empty database", async () => {
    await resetDatabase(sql);
    const { data } = await (await getDataHealth()).json();
    expect(data).toMatchObject({ status: "no-data", latestCompletedRun: null });
  });
});

describe("isConnectionError", () => {
  it("detects connection failures nested in error causes", () => {
    const err = new Error("query failed", {
      cause: Object.assign(new Error("refused"), { code: "ECONNREFUSED" }),
    });
    expect(isConnectionError(err)).toBe(true);
    expect(isConnectionError(new Error("syntax error"))).toBe(false);
  });
});

describe("GET /api/games/:id/history", () => {
  async function addOlderDraftKings() {
    const [run] = await db
      .insert(ingestionRuns)
      .values({
        jobKey: "r0",
        provider: "the-odds-api",
        requestType: "live",
        status: "completed",
        startedAt: iso(-180 * MIN),
      })
      .returning({ id: ingestionRuns.id });
    await db.insert(oddsObservations).values({
      ingestionRunId: run!.id,
      eventId: gameId,
      bookmakerKey: "draftkings",
      marketType: "spreads",
      selection: "HOME",
      point: -1.5,
      americanPrice: -110,
      observedAt: iso(-180 * MIN),
      isLive: false,
    });
  }

  it("returns per-book series with value-based changes reported as intervals", async () => {
    await addOlderDraftKings();
    const res = await getGameHistory(request(`/api/games/${gameId}/history`), ctx(gameId));
    expect(res.status).toBe(200);
    const { data, meta } = await res.json();
    expect(data).toMatchObject({ market: "spreads", selection: "HOME" });
    expect(meta).toMatchObject({
      resolution: "changes",
      gapMinutes: 720,
      includeLive: false,
      sources: ["the-odds-api"],
    });
    expect(meta.orientation).toContain("home team");

    const dk = data.series.find((s: { bookmakerKey: string }) => s.bookmakerKey === "draftkings");
    expect(dk).toMatchObject({ displayName: "DraftKings", observations: 2 });
    expect(dk.changes).toEqual([
      expect.objectContaining({
        type: "price",
        fromPrice: -110,
        toPrice: -105,
        intervalStart: iso(-180 * MIN),
        intervalEnd: NEW_SNAPSHOT,
        acrossGap: false,
      }),
    ]);
  });

  it("filters books and validates the selection against the market", async () => {
    const res = await getGameHistory(
      request(`/api/games/${gameId}/history?books=betmgm`),
      ctx(gameId),
    );
    const { data } = await res.json();
    expect(data.series.map((s: { bookmakerKey: string }) => s.bookmakerKey)).toEqual(["betmgm"]);

    const bad = await getGameHistory(
      request(`/api/games/${gameId}/history?market=totals&selection=HOME`),
      ctx(gameId),
    );
    expect(bad.status).toBe(400);
    expect((await bad.json()).error.details[0].path).toBe("selection");
  });

  it("defaults totals to OVER and returns empty series when nothing was observed", async () => {
    const { data } = await (
      await getGameHistory(request(`/api/games/${gameId}/history?market=totals`), ctx(gameId))
    ).json();
    expect(data).toMatchObject({ market: "totals", selection: "OVER", series: [] });
  });

  it("returns 400 for bad ids/params and 404 for unknown games", async () => {
    expect((await getGameHistory(request("/api/games/x/history"), ctx("x"))).status).toBe(400);
    expect(
      (await getGameHistory(request(`/api/games/${gameId}/history?resolution=hourly`), ctx(gameId)))
        .status,
    ).toBe(400);
    const id = "00000000-0000-4000-8000-000000000000";
    expect((await getGameHistory(request(`/api/games/${id}/history`), ctx(id))).status).toBe(404);
  });
});

describe("GET /api/games/:id/movements", () => {
  async function addDraftKings(point: number, price: number, minutesAgo: number, key: string) {
    const [run] = await db
      .insert(ingestionRuns)
      .values({
        jobKey: key,
        provider: "the-odds-api",
        requestType: "live",
        status: "completed",
        startedAt: iso(-minutesAgo * MIN),
      })
      .returning({ id: ingestionRuns.id });
    await db.insert(oddsObservations).values({
      ingestionRunId: run!.id,
      eventId: gameId,
      bookmakerKey: "draftkings",
      marketType: "spreads",
      selection: "HOME",
      point,
      americanPrice: price,
      observedAt: iso(-minutesAgo * MIN),
      isLive: false,
    });
  }

  it("returns movements oldest first with home-orientation direction and key numbers", async () => {
    await addDraftKings(-3.5, -110, 300, "m1"); // then -3.5 -115 (price), then NEW -1.5 -105
    await addDraftKings(-3.5, -115, 240, "m2");
    const res = await getGameMovements(request(`/api/games/${gameId}/movements`), ctx(gameId));
    expect(res.status).toBe(200);
    const { data, meta } = await res.json();
    expect(data).toMatchObject({ market: "spreads", selection: "HOME" });
    const dk = data.movements.filter(
      (m: { bookmakerKey: string }) => m.bookmakerKey === "draftkings",
    );
    expect(dk.map((m: { direction: string }) => m.direction)).toEqual([
      "price-only",
      "toward-away",
    ]);
    expect(dk[1]).toMatchObject({
      fromPoint: -3.5,
      toPoint: -1.5,
      pointDelta: 2,
      keyNumbers: [{ key: 3, signedKey: -3, kind: "crossed" }],
      displayName: "DraftKings",
    });
    expect(meta).toMatchObject({ gapMinutes: 720, sources: ["the-odds-api"] });

    const pointsOnly = await (
      await getGameMovements(request(`/api/games/${gameId}/movements?pointsOnly=true`), ctx(gameId))
    ).json();
    expect(
      pointsOnly.data.movements.every((m: { direction: string }) => m.direction !== "price-only"),
    ).toBe(true);
  });

  it("validates the market/selection combination and ids", async () => {
    expect(
      (
        await getGameMovements(
          request(`/api/games/${gameId}/movements?market=h2h&selection=OVER`),
          ctx(gameId),
        )
      ).status,
    ).toBe(400);
    expect((await getGameMovements(request("/api/games/x/movements"), ctx("x"))).status).toBe(400);
    const id = "00000000-0000-4000-8000-000000000000";
    expect((await getGameMovements(request(`/api/games/${id}/movements`), ctx(id))).status).toBe(
      404,
    );
  });
});

describe("GET /api/signals", () => {
  async function addSignals() {
    const base = {
      version: 1,
      market: "spreads" as const,
      selection: "HOME" as const,
      bookmakerKey: "draftkings",
      windowStart: iso(-120 * MIN),
      windowEnd: iso(-30 * MIN),
      details: {},
      evidence: [1, 2],
    };
    await replaceEventSignals(
      db,
      gameId,
      [
        { type: "line_move", version: 1 },
        { type: "key_number", version: 1 },
      ],
      [
        { ...base, type: "line_move", value: -0.5, detectedAt: iso(-30 * MIN) },
        { ...base, type: "key_number", value: -3, detectedAt: iso(-30 * MIN) },
        {
          ...base,
          type: "line_move",
          value: -1,
          detectedAt: iso(-10 * 24 * 60 * MIN),
          windowStart: iso(-10 * 24 * 60 * MIN - 360 * MIN),
          windowEnd: iso(-10 * 24 * 60 * MIN),
        },
      ],
    );
  }

  it("returns recent signals newest first with definitions and a disclaimer", async () => {
    await addSignals();
    const res = await getSignals(request("/api/signals"));
    expect(res.status).toBe(200);
    const { data, meta } = await res.json();
    expect(data).toHaveLength(2); // default window is 7 days
    expect(data[0]).toMatchObject({
      eventId: gameId,
      homeTeam: "Green Bay Packers",
      evidence: [1, 2],
    });
    expect(meta.definitions.line_move).toMatchObject({ version: 1, title: "Line move" });
    expect(meta.disclaimer).toContain("not betting advice");
  });

  it("filters by type, game, and window", async () => {
    await addSignals();
    const byType = await (await getSignals(request("/api/signals?type=key_number"))).json();
    expect(byType.data.map((r: { type: string }) => r.type)).toEqual(["key_number"]);
    const wide = await (
      await getSignals(request(`/api/signals?from=${iso(-30 * 24 * 60 * MIN)}&event=${gameId}`))
    ).json();
    expect(wide.data).toHaveLength(3);
  });

  it("rejects unknown types and bad params", async () => {
    expect((await getSignals(request("/api/signals?type=sharp_money"))).status).toBe(400);
    expect((await getSignals(request("/api/signals?event=nope"))).status).toBe(400);
    expect((await getSignals(request("/api/signals?limit=1000"))).status).toBe(400);
  });
});
