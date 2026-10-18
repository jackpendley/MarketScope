import type { GameCoverageRow, RunSummary } from "@marketscope/db";
import { describe, expect, it } from "vitest";
import {
  collectionStatus,
  COVERAGE_COLUMNS,
  coverageCell,
  FEED_COLUMNS,
  summarizeCoverage,
} from "./coverage-view";

const row = (over: Partial<GameCoverageRow>): GameCoverageRow => ({
  eventId: "e",
  homeTeam: "Buffalo Bills",
  awayTeam: "Miami Dolphins",
  commenceTime: "2026-10-18T17:00:00.000Z",
  sources: ["oddspapi"],
  snapshots: 10,
  firstObservedAt: "2026-10-10T00:00:00.000Z",
  lastObservedAt: "2026-10-18T16:55:00.000Z",
  snapshotsByColumn: {},
  signals: 0,
  ...over,
});

describe("coverage columns", () => {
  it("lists the five board books, then Pinnacle as a reference column", () => {
    expect(COVERAGE_COLUMNS.map((c) => c.key)).toEqual([
      "draftkings",
      "fanduel",
      "betmgm",
      "caesars",
      "hardrock",
      "pinnacle",
    ]);
    expect(COVERAGE_COLUMNS.at(-1)).toMatchObject({ label: "Pinnacle", reference: true });
  });

  it("maps every feed to its board column", () => {
    expect(FEED_COLUMNS).toMatchObject({
      hardrockbet_az: "hardrock",
      hardrockbet: "hardrock",
      williamhill_us: "caesars",
    });
  });
});

describe("coverageCell", () => {
  it.each([
    [10, undefined, 0, "none"],
    [10, 4, 0.4, "low"],
    [10, 5, 0.5, "partial"],
    [10, 9, 0.9, "full"],
    [0, 0, 0, "none"],
  ])("%i snapshots, %s covered → %f %s", (snapshots, covered, share, level) => {
    expect(coverageCell(snapshots, covered)).toEqual({ share, level });
  });
});

describe("summarizeCoverage", () => {
  it("totals games by source and averages each column over games where it appears", () => {
    const s = summarizeCoverage([
      row({
        sources: ["oddspapi"],
        snapshots: 10,
        signals: 3,
        snapshotsByColumn: { draftkings: 10 },
      }),
      row({
        sources: ["oddspapi"],
        snapshots: 4,
        signals: 1,
        snapshotsByColumn: { draftkings: 2 },
      }),
      row({ sources: ["the-odds-api"], snapshots: 2, snapshotsByColumn: { betmgm: 2 } }),
      // Three board books plus Pinnacle: eligible. Pinnacle alone never counts toward it.
      row({
        sources: ["oddspapi"],
        snapshots: 2,
        snapshotsByColumn: { draftkings: 2, fanduel: 2, hardrock: 1, pinnacle: 2 },
      }),
      row({
        sources: ["oddspapi"],
        snapshots: 2,
        snapshotsByColumn: { draftkings: 2, fanduel: 2, pinnacle: 2 },
      }),
    ]);
    expect(s).toMatchObject({
      games: 5,
      gamesBySource: [
        ["oddspapi", 4],
        ["the-odds-api", 1],
      ],
      snapshots: 20,
      signals: 4,
      consensusEligibleGames: 1,
    });
    expect(s.columnAverages.draftkings).toBeCloseTo((1 + 0.5 + 1 + 1) / 4);
    expect(s.columnAverages.betmgm).toBe(1);
    expect(s.columnAverages.caesars).toBeNull();
  });
});

describe("collectionStatus", () => {
  const run = (startedAt: string) => ({ startedAt }) as RunSummary;
  const now = new Date("2026-10-18T12:00:00Z");

  it("is ok within 12 hours of the last live run and behind after", () => {
    expect(collectionStatus(run("2026-10-18T06:07:00Z"), now)).toEqual({
      status: "ok",
      ageMinutes: 353,
    });
    expect(collectionStatus(run("2026-10-17T23:00:00Z"), now).status).toBe("behind");
  });

  it("reports no data when nothing was collected", () => {
    expect(collectionStatus(null, now)).toEqual({ status: "no-data", ageMinutes: null });
  });
});
