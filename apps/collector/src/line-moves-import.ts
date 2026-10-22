// Minute-level line moves from OddsPapi (MS-042, ADR-052). One idempotent run per fixture:
//   1. skip if this fixture's line-move import (job key) already completed;
//   2. fetch line-move histories (free endpoint) with NO transaction open;
//   3. derive main-line moves (providers/oddspapi/line-moves.ts);
//   4. ONE transaction: bookmakers, the game's event (matched to an existing one, live or
//      imported, else created), a fresh set of this game's OddsPapi moves, and the run row.
// Unlike the snapshot import (ADR-026), games we also collected live are welcome: line_moves
// is a separate table, so sources never mix inside odds_observations.

import {
  bookmakers,
  events,
  ingestionRuns,
  lineMoveFixes,
  lineMoves,
  type Database,
} from "@marketscope/db";
import {
  BOARD_BOOKS,
  COLLECTED_BOOKMAKERS,
  LINE_MOVE_ONLY_BOOKMAKERS,
  nflSeasonForKickoff,
  REFERENCE_BOOKMAKERS,
} from "@marketscope/shared";
import { and, eq, inArray, sql } from "drizzle-orm";
import { silentLogger, type Logger } from "./log";
import type { OddsPapiClient, OddsPapiFixture } from "./providers/oddspapi/client";
import { deriveLineMoves, ghostFixRows } from "./providers/oddspapi/line-moves";
import type { Market } from "@marketscope/shared";
import type { OddsPapiHistory, OddsPapiMarketMeta } from "./providers/oddspapi/transform";

export const LINE_MOVES_SOURCE = "oddspapi";
/** v2: limits kept for the reference books only (FanDuel's limit changes were half of v1's rows). */
export const LINE_MOVES_IMPORT_VERSION = 2;

/**
 * OddsPapi slug → MarketScope bookmaker key: the market makers (Pinnacle, Circa,
 * Bookmaker.eu) and the retail books we can validate. BetMGM stays out (ADR-026: sparse).
 */
export const LINE_MOVE_BOOK_MAP: Readonly<Record<string, string>> = {
  pinnacle: "pinnacle",
  circasports: "circa",
  "bookmaker.eu": "bookmaker_eu",
  draftkings: "draftkings",
  fanduel: "fanduel",
  caesars: "williamhill_us",
  hardrockbet: "hardrockbet",
};
/** Books whose reported limits are kept: the market makers, where a limit means something. */
export const LINE_MOVE_LIMIT_BOOKS: ReadonlySet<string> = new Set([
  "pinnacle",
  "circa",
  "bookmaker_eu",
]);
/** At most 3 bookmakers per historical-odds call. */
export const LINE_MOVE_REQUEST_GROUPS: readonly (readonly string[])[] = [
  ["pinnacle", "circasports", "bookmaker.eu"],
  ["draftkings", "fanduel", "caesars"],
  ["hardrockbet"],
];

/** A set of books imported together, with its own job key (so each set is idempotent on its own). */
export interface LineMoveProfile {
  name: "books" | "exchanges" | "fixes";
  jobKey: (fixtureId: string) => string;
  bookMap: Readonly<Record<string, string>>;
  requestGroups: readonly (readonly string[])[];
  limitBooks: ReadonlySet<string>;
  recordLimitBooks?: ReadonlySet<string>;
  markets?: readonly Market[];
  /** Write ghost-market corrections to line_move_fixes instead of rows to line_moves. */
  ghostFixes?: boolean;
}

export const BOOKS_PROFILE: LineMoveProfile = {
  name: "books",
  jobKey: (fixtureId) => `oddspapi-moves:${fixtureId}:v${LINE_MOVES_IMPORT_VERSION}`,
  bookMap: LINE_MOVE_BOOK_MAP,
  requestGroups: LINE_MOVE_REQUEST_GROUPS,
  limitBooks: LINE_MOVE_LIMIT_BOOKS,
};

/**
 * Exchanges (MS-051, Addendum K): top-of-book prices for spreads and totals. The size available
 * is stored with each row but never creates a row by itself; moneylines are skipped (storage).
 */
export const EXCHANGES_PROFILE: LineMoveProfile = {
  name: "exchanges",
  jobKey: (fixtureId) => `oddspapi-moves-ex:${fixtureId}:v1`,
  bookMap: { "novig.us": "novig", prophetx: "prophetx", kalshi: "kalshi" },
  // One exchange per call: three together can exceed V8's maximum string length.
  requestGroups: [["novig.us"], ["prophetx"], ["kalshi"]],
  limitBooks: new Set(),
  recordLimitBooks: new Set(["novig", "prophetx", "kalshi"]),
  markets: ["spreads", "totals"],
};

/**
 * Ghost-market corrections for the books (MS-058, ADR-065): the same histories, derived with and
 * without the ghost rule; only the books and markets that differ are written, to line_move_fixes.
 * line_moves is never touched, so the pre-registered studies keep reading exactly what they did.
 */
export const FIXES_PROFILE: LineMoveProfile = {
  ...BOOKS_PROFILE,
  name: "fixes",
  jobKey: (fixtureId) => `oddspapi-moves-fix:${fixtureId}:v1`,
  ghostFixes: true,
};

export type LineMoveImportOutcome =
  | {
      status: "imported";
      fixtureId: string;
      eventId: string;
      moves: number;
      /** Books requested but not imported (history too large to parse): the run is `partial`. */
      missingBooks: string[];
    }
  | { status: "already-imported"; fixtureId: string }
  | { status: "failed"; fixtureId: string; error: string };

export interface LineMoveImportDeps {
  db: Database;
  client: Pick<OddsPapiClient, "historicalOdds">;
  markets: ReadonlyMap<number, OddsPapiMarketMeta>;
  log?: Logger;
}

export function lineMovesJobKey(fixtureId: string): string {
  return BOOKS_PROFILE.jobKey(fixtureId);
}

export interface LineMoveImportOptions {
  /** Re-attempt fixtures whose last run was `partial` (by default they are kept, like completed ones). */
  retryPartial?: boolean;
}

export async function importLineMoves(
  deps: LineMoveImportDeps,
  fixture: OddsPapiFixture,
  profile: LineMoveProfile = BOOKS_PROFILE,
  options: LineMoveImportOptions = {},
): Promise<LineMoveImportOutcome> {
  const { db, client, markets } = deps;
  const log = deps.log ?? silentLogger;
  const jobKey = profile.jobKey(fixture.fixtureId);
  const home = fixture.participant1Name; // participant1 = home (verified against live data)
  const away = fixture.participant2Name;

  const [existing] = await db
    .select({
      id: ingestionRuns.id,
      status: ingestionRuns.status,
      issues: ingestionRuns.issueCounts,
    })
    .from(ingestionRuns)
    .where(eq(ingestionRuns.jobKey, jobKey));
  // Runs before ADR-071 recorded a skipped book as `completed` with a too_large_* issue: still partial.
  const partial =
    existing?.status === "partial" ||
    (existing?.status === "completed" &&
      Object.keys(existing.issues ?? {}).some((k) => k.startsWith("too_large_")));
  if ((existing?.status === "completed" || partial) && !(partial && options.retryPartial))
    return { status: "already-imported", fixtureId: fixture.fixtureId };

  const startedAt = new Date().toISOString();
  try {
    const merged: OddsPapiHistory = { bookmakers: {} };
    const tooLarge: string[] = [];
    for (const group of profile.requestGroups) {
      try {
        const part = await client.historicalOdds(fixture.fixtureId, group);
        Object.assign(merged.bookmakers, part.bookmakers ?? {});
      } catch (err) {
        // A busy exchange's full history can exceed V8's maximum string length (~512 MB). Skip
        // that book for this game, record it on the run, and keep the others.
        if (!(err instanceof Error) || !/longer than 0x[0-9a-f]+ characters/.test(err.message))
          throw err;
        tooLarge.push(...group);
        log.warn("line_moves.too_large", { fixtureId: fixture.fixtureId, books: group });
      }
    }
    const derive = (ghostRule: boolean) =>
      deriveLineMoves(merged, markets, {
        kickoff: fixture.startTime,
        bookMap: profile.bookMap,
        limitBooks: profile.limitBooks,
        recordLimitBooks: profile.recordLimitBooks,
        markets: profile.markets,
        ghostRule,
      });
    const rows = profile.ghostFixes ? ghostFixRows(derive(false), derive(true)) : derive(false);
    const table = profile.ghostFixes ? lineMoveFixes : lineMoves;
    const perBook: Record<string, number> = {};
    for (const r of rows) perBook[r.bookmakerKey] = (perBook[r.bookmakerKey] ?? 0) + 1;

    const eventId = await db.transaction(async (tx) => {
      if (existing) await tx.delete(ingestionRuns).where(eq(ingestionRuns.id, existing.id)); // failed earlier
      const primaryFeeds = new Set(BOARD_BOOKS.map((b) => b.feeds[0]));
      await tx
        .insert(bookmakers)
        .values(
          [...COLLECTED_BOOKMAKERS, ...REFERENCE_BOOKMAKERS, ...LINE_MOVE_ONLY_BOOKMAKERS].map(
            (b) => ({
              key: b.key,
              displayName: b.displayName,
              regionHint: b.regionHint,
              isPrimary: primaryFeeds.has(b.key),
            }),
          ),
        )
        .onConflictDoNothing({ target: bookmakers.key });

      // The same game from any source: our own OddsPapi event, else a live (Odds API) one.
      const [match] = await tx
        .select({ id: events.id })
        .from(events)
        .where(
          and(
            eq(events.homeTeam, home),
            eq(events.awayTeam, away),
            sql`abs(extract(epoch from (${events.commenceTimeUtc} - ${fixture.startTime}::timestamptz))) < 6 * 3600`,
          ),
        )
        .orderBy(sql`${events.providerEventId} = ${`oddspapi:${fixture.fixtureId}`} DESC`)
        .limit(1);
      let id = match?.id;
      if (!id) {
        const [created] = await tx
          .insert(events)
          .values({
            providerEventId: `oddspapi:${fixture.fixtureId}`,
            sportKey: "americanfootball_nfl",
            season: nflSeasonForKickoff(fixture.startTime),
            homeTeam: home,
            awayTeam: away,
            commenceTimeUtc: fixture.startTime,
          })
          .returning({ id: events.id });
        id = created!.id;
      }

      await tx.delete(table).where(
        and(
          eq(table.eventId, id),
          eq(table.source, LINE_MOVES_SOURCE),
          // Only this profile's books: importing exchanges never touches the books' rows.
          inArray(table.bookmakerKey, Object.values(profile.bookMap)),
        ),
      );
      for (let i = 0; i < rows.length; i += 1_000) {
        await tx.insert(table).values(
          rows.slice(i, i + 1_000).map((r) => ({
            eventId: id,
            bookmakerKey: r.bookmakerKey,
            marketType: r.market,
            changedAt: r.changedAt,
            point: r.point,
            price1: r.price1,
            price2: r.price2,
            limit1: r.limit1,
            limit2: r.limit2,
            source: LINE_MOVES_SOURCE,
          })),
        );
      }

      await tx.insert(ingestionRuns).values({
        jobKey,
        provider: LINE_MOVES_SOURCE,
        requestType: "historical",
        startedAt,
        finishedAt: sql`now()`,
        // A skipped book is missing data, not a success: `partial` keeps the gap visible (ADR-071).
        status: tooLarge.length ? "partial" : "completed",
        eventsSeen: 1,
        quotesSeen: rows.length,
        issueCounts: {
          ...Object.fromEntries(Object.entries(perBook).map(([k, v]) => [`moves_${k}`, v])),
          ...Object.fromEntries(tooLarge.map((b) => [`too_large_${b}`, 1])),
        },
      });
      return id;
    });

    log.info("line_moves.imported", {
      fixtureId: fixture.fixtureId,
      home,
      away,
      moves: rows.length,
    });
    return {
      status: "imported",
      fixtureId: fixture.fixtureId,
      eventId,
      moves: rows.length,
      missingBooks: tooLarge,
    };
  } catch (err) {
    const error = (err instanceof Error ? err.message : String(err)).slice(0, 500);
    await db
      .insert(ingestionRuns)
      .values({
        jobKey,
        provider: LINE_MOVES_SOURCE,
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
    log.error("line_moves.failed", { fixtureId: fixture.fixtureId, error });
    return { status: "failed", fixtureId: fixture.fixtureId, error };
  }
}

export interface CrossCheckRow {
  bookmakerKey: string;
  snapshots: number;
  matched: number;
}

/**
 * Do the stored moves reproduce the stored OddsPapi snapshots? For each snapshot quote within
 * the moves' window, the move in effect at that time must carry the same line and price.
 * Small gaps are expected where the 1-second settle or the 1-minute suspension rule applies.
 */
export async function crossCheckSnapshots(db: Database, windowDays = 14): Promise<CrossCheckRow[]> {
  const rows = await db.execute<{ bookmaker_key: string; snapshots: number; matched: number }>(sql`
    SELECT o.bookmaker_key,
           count(*)::int AS snapshots,
           count(*) FILTER (WHERE
             (CASE WHEN o.selection IN ('HOME', 'OVER') THEN m.price1 ELSE m.price2 END)
               = o.american_price
             AND (CASE WHEN o.market_type = 'spreads' AND o.selection = 'AWAY' THEN -m.point
                       ELSE m.point END) IS NOT DISTINCT FROM o.point
           )::int AS matched
    FROM odds_observations o
    JOIN events e ON e.id = o.event_id
    JOIN LATERAL (
      SELECT m.point, m.price1, m.price2 FROM line_moves m
      WHERE m.event_id = o.event_id AND m.bookmaker_key = o.bookmaker_key
        AND m.market_type = o.market_type AND m.changed_at <= o.observed_at
      ORDER BY m.changed_at DESC LIMIT 1
    ) m ON true
    WHERE o.source = 'oddspapi'
      AND o.observed_at >= e.commence_time_utc - make_interval(days => ${windowDays})
    GROUP BY 1 ORDER BY 1`);
  return rows.map((r) => ({
    bookmakerKey: r.bookmaker_key,
    snapshots: r.snapshots,
    matched: r.matched,
  }));
}
