// Historical backfill from OddsPapi (ADR-026). One idempotent run per fixture:
//   1. skip if this fixture's import (job key) already completed; refuse games we also
//      collected live, so no game ever mixes sources;
//   2. fetch line-move histories (free endpoint) with NO transaction open;
//   3. derive pregame snapshot observations (transform.ts);
//   4. ONE transaction: bookmakers, event, run (historical, completed), observations.
// Raw payloads are not stored (~90 MB per game); provenance lives on the run row.

import {
  bookmakers,
  events,
  ingestionRuns,
  oddsObservations,
  type Database,
} from "@marketscope/db";
import {
  BOARD_BOOKS,
  COLLECTED_BOOKMAKERS,
  nflSeasonForKickoff,
  REFERENCE_BOOKMAKERS,
} from "@marketscope/shared";
import { and, eq, ne, sql } from "drizzle-orm";
import { silentLogger, type Logger } from "./log";
import type { OddsPapiClient, OddsPapiFixture } from "./providers/oddspapi/client";
import {
  deriveObservations,
  type OddsPapiHistory,
  type OddsPapiMarketMeta,
} from "./providers/oddspapi/transform";

export const ODDSPAPI_SOURCE = "oddspapi";
export const ODDSPAPI_IMPORT_VERSION = 1;

/**
 * OddsPapi slug → MarketScope bookmaker key. BetMGM is deliberately absent: validation
 * against our own observations matched only 44% (sparse history, median 44 h between entries).
 */
export const ODDSPAPI_BOOK_MAP: Readonly<Record<string, string>> = {
  draftkings: "draftkings",
  fanduel: "fanduel",
  caesars: "williamhill_us",
  hardrockbet: "hardrockbet",
  pinnacle: "pinnacle",
};
/** At most 3 bookmakers per historical-odds call. */
export const ODDSPAPI_REQUEST_GROUPS: readonly (readonly string[])[] = [
  ["draftkings", "fanduel", "caesars"],
  ["hardrockbet", "pinnacle"],
];

export type ImportOutcome =
  | {
      status: "imported";
      fixtureId: string;
      eventId: string;
      observations: number;
      snapshots: number;
    }
  | { status: "already-imported" | "skipped-live-overlap"; fixtureId: string }
  | { status: "failed"; fixtureId: string; error: string };

export interface ImportDeps {
  db: Database;
  client: Pick<OddsPapiClient, "historicalOdds">;
  markets: ReadonlyMap<number, OddsPapiMarketMeta>;
  log?: Logger;
}

export function oddspapiJobKey(fixtureId: string): string {
  return `oddspapi:${fixtureId}:v${ODDSPAPI_IMPORT_VERSION}`;
}

export async function importFixture(
  deps: ImportDeps,
  fixture: OddsPapiFixture,
): Promise<ImportOutcome> {
  const { db, client, markets } = deps;
  const log = deps.log ?? silentLogger;
  const jobKey = oddspapiJobKey(fixture.fixtureId);
  const home = fixture.participant1Name; // participant1 = home (verified against live data)
  const away = fixture.participant2Name;

  const [existing] = await db
    .select({ id: ingestionRuns.id, status: ingestionRuns.status })
    .from(ingestionRuns)
    .where(eq(ingestionRuns.jobKey, jobKey));
  if (existing?.status === "completed")
    return { status: "already-imported", fixtureId: fixture.fixtureId };

  // Never import a game we collected live: one source per game keeps snapshots unmixed.
  const [overlap] = await db
    .select({ id: events.id })
    .from(events)
    .where(
      and(
        eq(events.homeTeam, home),
        eq(events.awayTeam, away),
        ne(events.providerEventId, `oddspapi:${fixture.fixtureId}`),
        sql`abs(extract(epoch from (${events.commenceTimeUtc} - ${fixture.startTime}::timestamptz))) < 6 * 3600`,
      ),
    );
  if (overlap) {
    log.warn("oddspapi.skipped_live_overlap", { fixtureId: fixture.fixtureId, home, away });
    return { status: "skipped-live-overlap", fixtureId: fixture.fixtureId };
  }

  const startedAt = new Date().toISOString();
  try {
    const merged: OddsPapiHistory = { bookmakers: {} };
    for (const group of ODDSPAPI_REQUEST_GROUPS) {
      const part = await client.historicalOdds(fixture.fixtureId, group);
      Object.assign(merged.bookmakers, part.bookmakers ?? {});
    }
    const rows = deriveObservations(merged, markets, {
      kickoff: fixture.startTime,
      bookMap: ODDSPAPI_BOOK_MAP,
    });
    const snapshots = new Set(rows.map((r) => r.observedAt)).size;
    const perBook: Record<string, number> = {};
    for (const r of rows) perBook[r.bookmakerKey] = (perBook[r.bookmakerKey] ?? 0) + 1;

    const eventId = await db.transaction(async (tx) => {
      if (existing) await tx.delete(ingestionRuns).where(eq(ingestionRuns.id, existing.id)); // failed earlier
      const primaryFeeds = new Set(BOARD_BOOKS.map((b) => b.feeds[0]));
      await tx
        .insert(bookmakers)
        .values(
          [...COLLECTED_BOOKMAKERS, ...REFERENCE_BOOKMAKERS].map((b) => ({
            key: b.key,
            displayName: b.displayName,
            regionHint: b.regionHint,
            isPrimary: primaryFeeds.has(b.key),
          })),
        )
        .onConflictDoNothing({ target: bookmakers.key });

      await tx
        .insert(events)
        .values({
          providerEventId: `oddspapi:${fixture.fixtureId}`,
          sportKey: "americanfootball_nfl",
          season: nflSeasonForKickoff(fixture.startTime),
          homeTeam: home,
          awayTeam: away,
          commenceTimeUtc: fixture.startTime,
        })
        .onConflictDoNothing({ target: events.providerEventId });
      const [evt] = await tx
        .select({ id: events.id })
        .from(events)
        .where(eq(events.providerEventId, `oddspapi:${fixture.fixtureId}`));

      const [run] = await tx
        .insert(ingestionRuns)
        .values({
          jobKey,
          provider: ODDSPAPI_SOURCE,
          requestType: "historical",
          startedAt,
          finishedAt: sql`now()`,
          status: "completed",
          eventsSeen: 1,
          quotesSeen: rows.length,
          issueCounts: {
            snapshots,
            ...Object.fromEntries(Object.entries(perBook).map(([k, v]) => [`rows_${k}`, v])),
          },
        })
        .returning({ id: ingestionRuns.id });

      for (let i = 0; i < rows.length; i += 1_000) {
        await tx.insert(oddsObservations).values(
          rows.slice(i, i + 1_000).map((r) => ({
            ingestionRunId: run!.id,
            eventId: evt!.id,
            bookmakerKey: r.bookmakerKey,
            marketType: r.market,
            selection: r.selection,
            point: r.point,
            americanPrice: r.americanPrice,
            bookmakerUpdatedAt: r.bookmakerUpdatedAt,
            observedAt: r.observedAt,
            isLive: false,
            source: ODDSPAPI_SOURCE,
          })),
        );
      }
      return evt!.id;
    });

    log.info("oddspapi.imported", {
      fixtureId: fixture.fixtureId,
      home,
      away,
      observations: rows.length,
      snapshots,
    });
    return {
      status: "imported",
      fixtureId: fixture.fixtureId,
      eventId,
      observations: rows.length,
      snapshots,
    };
  } catch (err) {
    const error = (err instanceof Error ? err.message : String(err)).slice(0, 500);
    await db
      .insert(ingestionRuns)
      .values({
        jobKey,
        provider: ODDSPAPI_SOURCE,
        requestType: "historical",
        startedAt,
        finishedAt: sql`now()`,
        status: "failed",
        errorCode: "IMPORT",
        errorMessage: error,
      })
      .onConflictDoUpdate({
        target: ingestionRuns.jobKey,
        set: { status: "failed", errorCode: "IMPORT", errorMessage: error, finishedAt: sql`now()` },
      });
    log.error("oddspapi.failed", { fixtureId: fixture.fixtureId, error });
    return { status: "failed", fixtureId: fixture.fixtureId, error };
  }
}
