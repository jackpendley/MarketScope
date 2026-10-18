// MarketScope relational schema (PostgreSQL 17, Drizzle ORM).
//
// Design principles (see docs/DATA_DICTIONARY.md):
// - odds_observations is APPEND-ONLY. We never update a price; each collection run
//   adds a new observation, which is what makes historical replay possible.
// - Invariants that must never be violated are enforced by the database itself
//   (CHECK / UNIQUE / FK), not only by application code.
// - TypeScript keys are camelCase; columns are snake_case (drizzle `casing`).
// - Every table has Row-Level Security ENABLED with NO policies. On Supabase, tables in
//   `public` are reachable through the REST Data API with the (public) publishable key;
//   RLS without policies denies those roles everything. Our own connections use the
//   table owner, which bypasses RLS (ADR-018).

import { sql } from "drizzle-orm";
import {
  bigint,
  boolean,
  check,
  doublePrecision,
  index,
  integer,
  jsonb,
  numeric,
  pgEnum,
  pgTable,
  text,
  timestamp,
  unique,
  uuid,
} from "drizzle-orm/pg-core";

const tstz = () => timestamp({ withTimezone: true, mode: "string" });

export const marketType = pgEnum("market_type", ["h2h", "spreads", "totals"]);
export const selection = pgEnum("selection", ["HOME", "AWAY", "OVER", "UNDER"]);
export const requestType = pgEnum("request_type", ["live", "historical"]);
export const ingestionStatus = pgEnum("ingestion_status", [
  "started",
  "completed",
  "failed",
  "skipped",
]);

/** One NFL game. Team orientation comes from the provider's home/away fields, never alphabetical. */
export const events = pgTable(
  "events",
  {
    id: uuid().primaryKey().defaultRandom(),
    providerEventId: text().notNull().unique(),
    sportKey: text().notNull(),
    /** NFL season year (games in Jan/Feb belong to the previous year's season). */
    season: integer().notNull(),
    /** Not provided by the odds feed; filled later from a schedule source (ADR-009). */
    week: integer(),
    homeTeam: text().notNull(),
    awayTeam: text().notNull(),
    /** Updated on every upsert: the provider moves it for flexed games and actual kickoffs. */
    commenceTimeUtc: tstz().notNull(),
    createdAt: tstz().notNull().defaultNow(),
    updatedAt: tstz().notNull().defaultNow(),
  },
  (t) => [index("events_commence_time_idx").on(t.commenceTimeUtc)],
).enableRLS();

/** Provider feeds (bookmaker keys). Kept in sync by the collector from COLLECTED_BOOKMAKERS. */
export const bookmakers = pgTable("bookmakers", {
  key: text().primaryKey(),
  displayName: text().notNull(),
  regionHint: text(),
  /** True for a board column's preferred feed; false for fallbacks like `hardrockbet`. */
  isPrimary: boolean().notNull().default(false),
  enabled: boolean().notNull().default(true),
}).enableRLS();

/** One attempt-tracked collection job. Makes ingestion observable and idempotent. */
export const ingestionRuns = pgTable(
  "ingestion_runs",
  {
    id: uuid().primaryKey().defaultRandom(),
    /** Idempotency key: `live:nfl:<slot>` for scheduled runs, `manual:<uuid>` otherwise. */
    jobKey: text().notNull().unique(),
    provider: text().notNull(),
    requestType: requestType().notNull(),
    requestedSnapshotAt: tstz(),
    providerSnapshotAt: tstz(),
    startedAt: tstz().notNull().defaultNow(),
    finishedAt: tstz(),
    status: ingestionStatus().notNull().default("started"),
    attempt: integer().notNull().default(1),
    httpStatus: integer(),
    durationMs: integer(),
    creditsUsed: integer(),
    creditsRemaining: integer(),
    eventsSeen: integer().notNull().default(0),
    quotesSeen: integer().notNull().default(0),
    /** Normalization issue counts by code, e.g. {"BOOKMAKER_MISSING": 61}. */
    issueCounts: jsonb().$type<Record<string, number>>(),
    errorCode: text(),
    /** Sanitized: never contains request URLs or credentials. */
    errorMessage: text(),
  },
  (t) => [index("ingestion_runs_started_at_idx").on(t.startedAt.desc().nullsFirst())],
).enableRLS();

/** Raw provider response per run, so normalizer fixes can be re-applied without re-buying data. */
export const ingestionPayloads = pgTable("ingestion_payloads", {
  ingestionRunId: uuid()
    .primaryKey()
    .references(() => ingestionRuns.id, { onDelete: "cascade" }),
  receivedAt: tstz().notNull(),
  payload: jsonb().notNull(),
}).enableRLS();

/** Append-only: one bookmaker price for one selection, as observed by one ingestion run. */
export const oddsObservations = pgTable(
  "odds_observations",
  {
    id: bigint({ mode: "number" }).primaryKey().generatedAlwaysAsIdentity(),
    ingestionRunId: uuid()
      .notNull()
      .references(() => ingestionRuns.id),
    eventId: uuid()
      .notNull()
      .references(() => events.id),
    bookmakerKey: text()
      .notNull()
      .references(() => bookmakers.key),
    marketType: marketType().notNull(),
    selection: selection().notNull(),
    /** Spread/total line; NULL for moneylines. numeric (not float) so −3.5 is stored exactly. */
    point: numeric({ precision: 5, scale: 1, mode: "number" }),
    americanPrice: integer().notNull(),
    /** Provider-reported market last_update. */
    bookmakerUpdatedAt: tstz(),
    /** When our collector received the response (or the historical snapshot time). */
    observedAt: tstz().notNull(),
    isLive: boolean().notNull(),
    source: text().notNull().default("the-odds-api"),
  },
  (t) => [
    // One observation per selection per run per observed_at (featured markets have one
    // line each). Live runs have a single observed_at; historical imports derive many
    // snapshot times within one run. Leading with ingestion_run_id also makes this the
    // index for "rows of run X".
    unique("odds_observations_run_selection_time_uq").on(
      t.ingestionRunId,
      t.eventId,
      t.bookmakerKey,
      t.marketType,
      t.selection,
      t.observedAt,
    ),
    // Serves "history of one selection at one book, newest first" and latest-quote lookups.
    index("odds_observations_history_idx").on(
      t.eventId,
      t.marketType,
      t.selection,
      t.bookmakerKey,
      // NULLS FIRST matches "ORDER BY observed_at DESC" (see market_signals_recent_idx).
      t.observedAt.desc().nullsFirst(),
    ),
    check(
      "odds_observations_point_matches_market",
      sql`(${t.marketType} = 'h2h') = (${t.point} IS NULL)`,
    ),
    check(
      "odds_observations_selection_matches_market",
      sql`(${t.marketType} IN ('h2h', 'spreads') AND ${t.selection} IN ('HOME', 'AWAY'))
        OR (${t.marketType} = 'totals' AND ${t.selection} IN ('OVER', 'UNDER'))`,
    ),
    check(
      "odds_observations_valid_american_price",
      sql`${t.americanPrice} <= -100 OR ${t.americanPrice} >= 100`,
    ),
  ],
).enableRLS();

/**
 * Derived market signals (Signal Lab). Recomputed from odds_observations by versioned,
 * pure definitions in @marketscope/shared; each row cites the observations it came from.
 * Recompute replaces rows per (event, signal_type, algorithm_version) in one transaction.
 */
export const marketSignals = pgTable(
  "market_signals",
  {
    id: bigint({ mode: "number" }).primaryKey().generatedAlwaysAsIdentity(),
    eventId: uuid()
      .notNull()
      .references(() => events.id, { onDelete: "cascade" }),
    /** e.g. line_move, book_divergence (text: new types don't need a migration). */
    signalType: text().notNull(),
    algorithmVersion: integer().notNull(),
    marketType: marketType().notNull(),
    selection: selection(),
    bookmakerKey: text().references(() => bookmakers.key),
    /** When the signal became observable (end of its evidence window). */
    detectedAt: tstz().notNull(),
    windowStart: tstz().notNull(),
    windowEnd: tstz().notNull(),
    /** Points, cents, or a signed key number, depending on signal_type. */
    value: doublePrecision().notNull(),
    details: jsonb().$type<Record<string, unknown>>().notNull(),
    evidenceObservationIds: bigint({ mode: "number" }).array().notNull(),
    computedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    // Matches listSignals' ORDER BY (detected_at DESC, id) so LIMIT stops early instead of
    // sorting every row in the window (MS-023 EXPLAIN review, docs/PERFORMANCE.md).
    // NULLS FIRST is what a plain "ORDER BY … DESC" means; the planner won't match an index
    // with different null ordering, even on a NOT NULL column.
    index("market_signals_recent_idx").on(t.detectedAt.desc().nullsFirst(), t.id),
    index("market_signals_event_idx").on(t.eventId, t.signalType, t.algorithmVersion),
    check("market_signals_window_order", sql`${t.windowStart} <= ${t.windowEnd}`),
  ],
).enableRLS();

// ---- Football context (ADR-028) -------------------------------------------------------------
// Written only by the Python app `apps/football` (nflverse ingest). The schema lives here so
// there is one migration history, one drift check, and RLS on every table.

/** NFL teams by nflverse abbreviation. Relocated teams keep their historical abbreviation
 *  (OAK, SD, STL) and point at the current franchise, so ratings follow the franchise. */
export const nflTeams = pgTable("nfl_teams", {
  abbr: text().primaryKey(),
  /** Current franchise abbreviation (OAK -> LV, SD -> LAC, STL -> LA; otherwise itself). */
  franchise: text().notNull(),
  fullName: text().notNull(),
  nickname: text().notNull(),
  conference: text().notNull(),
  division: text().notNull(),
  /** Exact `home_team`/`away_team` string used by the odds feeds, for linking events. */
  oddsApiName: text(),
}).enableRLS();

/** One-attempt-tracked football ingest job (same claim/idempotency pattern as ingestion_runs). */
export const nflIngestRuns = pgTable(
  "nfl_ingest_runs",
  {
    id: uuid().primaryKey().defaultRandom(),
    /** e.g. `schedules:2016-2026:<utc date>` or `manual:<uuid>`. */
    jobKey: text().notNull().unique(),
    dataset: text().notNull(),
    startedAt: tstz().notNull().defaultNow(),
    finishedAt: tstz(),
    status: ingestionStatus().notNull().default("started"),
    attempt: integer().notNull().default(1),
    rowsUpserted: integer().notNull().default(0),
    /** nflverse release tag / file checksum, so a dataset version is reproducible. */
    sourceVersion: text(),
    errorMessage: text(),
  },
  (t) => [index("nfl_ingest_runs_started_at_idx").on(t.startedAt.desc().nullsFirst())],
).enableRLS();

/** One NFL game from the nflverse schedule. Results and observed weather are POST-HOC: they
 *  never feed features for the same game (CLAUDE.md football rules 1-2). */
export const nflGames = pgTable(
  "nfl_games",
  {
    /** nflverse game_id, e.g. `2026_01_NE_SEA`. */
    gameId: text().primaryKey(),
    season: integer().notNull(),
    /** REG, WC, DIV, CON, SB. */
    gameType: text().notNull(),
    week: integer().notNull(),
    kickoffUtc: tstz().notNull(),
    homeTeam: text()
      .notNull()
      .references(() => nflTeams.abbr),
    awayTeam: text()
      .notNull()
      .references(() => nflTeams.abbr),
    neutralSite: boolean().notNull(),
    divisionGame: boolean().notNull(),
    homeRestDays: integer(),
    awayRestDays: integer(),
    homeScore: integer(),
    awayScore: integer(),
    overtime: boolean(),
    /** When our ingest first saw the final score. Null for games already final at backfill:
     *  the import time is never assigned to historical data. */
    finalObservedAt: tstz(),
    stadiumId: text(),
    stadium: text(),
    /** dome, outdoors, open, closed (as played; retractable status is unknown pre-game). */
    roof: text(),
    surface: text(),
    observedTempF: integer(),
    observedWindMph: integer(),
    referee: text(),
    homeCoach: text(),
    awayCoach: text(),
    /** Starting QBs as played (post-hoc: used only for the oracle-vs-expected-starter study). */
    homeQbId: text(),
    awayQbId: text(),
    /** nflverse closing line, converted to OUR home orientation (negative = home favored).
     *  A labeled benchmark: never copied into odds_observations (no observation timestamp). */
    nflverseCloseHomeSpread: numeric({ precision: 4, scale: 1, mode: "number" }),
    nflverseCloseTotal: numeric({ precision: 4, scale: 1, mode: "number" }),
    nflverseCloseHomeMoneyline: integer(),
    nflverseCloseAwayMoneyline: integer(),
    /** Link to the odds event for the same game (teams + kickoff within 36 h). */
    eventId: uuid()
      .unique()
      .references(() => events.id, { onDelete: "set null" }),
    updatedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    index("nfl_games_season_week_idx").on(t.season, t.week),
    index("nfl_games_kickoff_idx").on(t.kickoffUtc),
    check("nfl_games_teams_differ", sql`${t.homeTeam} <> ${t.awayTeam}`),
    check("nfl_games_scores_together", sql`(${t.homeScore} IS NULL) = (${t.awayScore} IS NULL)`),
  ],
).enableRLS();
