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
  (t) => [index("ingestion_runs_started_at_idx").on(t.startedAt.desc())],
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
    // One observation per selection per run (featured markets have one line each).
    // Leading with ingestion_run_id also makes this the index for "rows of run X".
    unique("odds_observations_run_selection_uq").on(
      t.ingestionRunId,
      t.eventId,
      t.bookmakerKey,
      t.marketType,
      t.selection,
    ),
    // Serves "history of one selection at one book, newest first" and latest-quote lookups.
    index("odds_observations_history_idx").on(
      t.eventId,
      t.marketType,
      t.selection,
      t.bookmakerKey,
      t.observedAt.desc(),
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
    index("market_signals_detected_at_idx").on(t.detectedAt.desc()),
    index("market_signals_event_idx").on(t.eventId, t.signalType, t.algorithmVersion),
    check("market_signals_window_order", sql`${t.windowStart} <= ${t.windowEnd}`),
  ],
).enableRLS();
