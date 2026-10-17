import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { createDb } from "../client";
import { events, ingestionRuns, oddsObservations } from "../schema";
import { resetDatabase, TEST_DATABASE_URL } from "../testing";
import {
  eventIdsKickingOff,
  eventSignalObservations,
  listSignals,
  replaceEventSignals,
  type SignalWrite,
} from "./signals";

const { db, sql, close } = createDb(TEST_DATABASE_URL, { max: 2 });
afterAll(() => close());

let eventId: string;
let obsIds: number[];
beforeEach(async () => {
  await resetDatabase(sql);
  const [run] = await db
    .insert(ingestionRuns)
    .values({ jobKey: "r1", provider: "the-odds-api", requestType: "live", status: "completed" })
    .returning({ id: ingestionRuns.id });
  const [evt] = await db
    .insert(events)
    .values({
      providerEventId: "g1",
      sportKey: "americanfootball_nfl",
      season: 2026,
      homeTeam: "Buffalo Bills",
      awayTeam: "Miami Dolphins",
      commenceTimeUtc: "2026-10-18T17:00:00Z",
    })
    .returning({ id: events.id });
  eventId = evt!.id;
  const rows = await db
    .insert(oddsObservations)
    .values([
      {
        ingestionRunId: run!.id,
        eventId,
        bookmakerKey: "draftkings",
        marketType: "spreads",
        selection: "HOME",
        point: -3,
        americanPrice: -110,
        observedAt: "2026-10-16T01:00:00Z",
        isLive: false,
      },
      {
        ingestionRunId: run!.id,
        eventId,
        bookmakerKey: "fanduel",
        marketType: "h2h",
        selection: "HOME",
        point: null,
        americanPrice: -150,
        observedAt: "2026-10-16T01:00:00Z",
        isLive: false,
      },
      {
        ingestionRunId: run!.id,
        eventId,
        bookmakerKey: "betmgm",
        marketType: "spreads",
        selection: "HOME",
        point: -7,
        americanPrice: -110,
        observedAt: "2026-10-18T18:00:00Z",
        isLive: true,
      },
    ])
    .returning({ id: oddsObservations.id });
  obsIds = rows.map((r) => r.id);
});

const signal = (overrides: Partial<SignalWrite> = {}): SignalWrite => ({
  type: "line_move",
  version: 1,
  market: "spreads",
  selection: "HOME",
  bookmakerKey: "draftkings",
  detectedAt: "2026-10-16T07:00:00Z",
  windowStart: "2026-10-16T01:00:00Z",
  windowEnd: "2026-10-16T07:00:00Z",
  value: -0.5,
  details: { direction: "toward-home" },
  evidence: [1, 2],
  ...overrides,
});

describe("eventSignalObservations", () => {
  it("returns pregame observations of every market with ids", async () => {
    const rows = await eventSignalObservations(db, eventId);
    expect(rows.map((r) => [r.id, r.market])).toEqual([
      [obsIds[0], "spreads"],
      [obsIds[1], "h2h"],
    ]);
  });
});

describe("replaceEventSignals", () => {
  it("is idempotent per (type, version) and leaves other types alone", async () => {
    const defs = [{ type: "line_move", version: 1 }];
    await replaceEventSignals(db, eventId, defs, [signal(), signal({ value: -1 })]);
    await replaceEventSignals(
      db,
      eventId,
      [{ type: "price_move", version: 1 }],
      [signal({ type: "price_move", value: -10 })],
    );
    await replaceEventSignals(db, eventId, defs, [signal()]); // recompute line_move only

    const rows = await listSignals(db, { eventId });
    expect(rows.map((r) => [r.type, r.value]).sort()).toEqual([
      ["line_move", -0.5],
      ["price_move", -10],
    ]);
    expect(rows[0]).toMatchObject({
      homeTeam: "Buffalo Bills",
      evidence: [1, 2],
      details: { direction: "toward-home" },
    });
  });

  it("rolls back entirely when an insert fails", async () => {
    await replaceEventSignals(db, eventId, [{ type: "line_move", version: 1 }], [signal()]);
    await expect(
      replaceEventSignals(
        db,
        eventId,
        [{ type: "line_move", version: 1 }],
        [signal({ bookmakerKey: "bovada" })],
      ),
    ).rejects.toThrow();
    expect(await listSignals(db, { eventId })).toHaveLength(1); // old row survived
  });
});

describe("listSignals", () => {
  it("filters by type and time window, newest first, bounded", async () => {
    await replaceEventSignals(
      db,
      eventId,
      [
        { type: "line_move", version: 1 },
        { type: "key_number", version: 1 },
      ],
      [
        signal({ detectedAt: "2026-10-16T07:00:00Z" }),
        signal({ detectedAt: "2026-10-16T13:00:00Z", windowEnd: "2026-10-16T13:00:00Z" }),
        signal({ type: "key_number", value: -3 }),
      ],
    );
    const all = await listSignals(db, {});
    expect(all.map((r) => r.detectedAt)).toEqual([
      "2026-10-16T13:00:00.000Z",
      "2026-10-16T07:00:00.000Z",
      "2026-10-16T07:00:00.000Z",
    ]);
    expect(await listSignals(db, { types: ["key_number"] })).toHaveLength(1);
    expect(await listSignals(db, { from: "2026-10-16T12:00:00Z" })).toHaveLength(1);
    expect(await listSignals(db, { limit: 1 })).toHaveLength(1);
  });
});

describe("eventIdsKickingOff", () => {
  it("returns games in the kickoff window", async () => {
    expect(await eventIdsKickingOff(db, "2026-10-18T00:00:00Z", "2026-10-19T00:00:00Z")).toEqual([
      eventId,
    ]);
    expect(await eventIdsKickingOff(db, "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z")).toEqual(
      [],
    );
  });
});
