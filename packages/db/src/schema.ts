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
  primaryKey,
  text,
  timestamp,
  unique,
  uniqueIndex,
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

/** One team's offense (and own special teams) in one final game, aggregated from nflverse
 *  play-by-play (`apps/football/.../team_stats.py`). A team's defense is its opponent's row.
 *  Rates are NULL when they have no denominator. Rebuilt whole per season, so a definition
 *  change is a new `stats_version`, never a silent mix. */
export const nflTeamGameStats = pgTable(
  "nfl_team_game_stats",
  {
    gameId: text()
      .notNull()
      .references(() => nflGames.gameId, { onDelete: "cascade" }),
    team: text()
      .notNull()
      .references(() => nflTeams.abbr),
    opponent: text()
      .notNull()
      .references(() => nflTeams.abbr),
    season: integer().notNull(),
    /** REG or POST. */
    seasonType: text().notNull(),
    week: integer().notNull(),
    isHome: boolean().notNull(),
    /** Scrimmage plays with EPA: passes (incl. sacks, scrambles) and runs, incl. penalty-nullified ones. */
    plays: integer().notNull(),
    dropbacks: integer().notNull(),
    rushes: integer().notNull(),
    earlyDownPlays: integer().notNull(),
    /** Win probability 20-80%, quarters 1-4, not the last 2 minutes of a half. */
    neutralPlays: integer().notNull(),
    /** Raw EPA per play. */
    epaPerPlay: doublePrecision(),
    epaPerDropback: doublePrecision(),
    epaPerRush: doublePrecision(),
    earlyDownEpaPerPlay: doublePrecision(),
    /** Model channel: luck-adjusted, capped (±4.5), WP-weighted EPA per play (design.py). */
    adjEpaPerPlay: doublePrecision(),
    adjEpaPerDropback: doublePrecision(),
    adjEpaPerRush: doublePrecision(),
    /** Sum of WP weights (effective plays) behind adj_epa_per_play. */
    adjWeight: doublePrecision().notNull(),
    successRate: doublePrecision(),
    dropbackSuccessRate: doublePrecision(),
    rushSuccessRate: doublePrecision(),
    /** Passes of 20+ and runs of 10+ yards, per play. */
    explosiveRate: doublePrecision(),
    /** Explosiveness: mean EPA on successful plays. */
    epaPerSuccess: doublePrecision(),
    /** Completion % over expected, in percentage points. */
    cpoe: doublePrecision(),
    sacks: integer().notNull(),
    sackRate: doublePrecision(),
    neutralPassRate: doublePrecision(),
    /** Pass rate over expected (pass - xpass) on neutral plays, as a fraction. */
    proe: doublePrecision(),
    /** Pace: seconds between consecutive neutral snaps of one drive (gaps over 60 s excluded). */
    neutralSecondsPerPlay: doublePrecision(),
    shotgunRate: doublePrecision(),
    noHuddleRate: doublePrecision(),
    interceptions: integer().notNull(),
    /** Passes defensed by the opponent, interceptions included. */
    passesDefensed: integer().notNull(),
    /** Own fumbles on scrimmage plays. */
    fumbles: integer().notNull(),
    fumblesLost: integer().notNull(),
    /** Actual minus expected EPA from fumble recoveries (positive = lucky). */
    fumbleLuckEpa: doublePrecision().notNull(),
    /** Actual minus expected EPA from interceptions given passes defensed (positive = lucky). */
    intLuckEpa: doublePrecision().notNull(),
    fourthDownAttempts: integer().notNull(),
    fourthDownConversions: integer().notNull(),
    drives: integer().notNull(),
    /** Points scored by the offense on its drives (TDs incl. tries, FGs). */
    drivePoints: integer().notNull(),
    /** Average drive start, own yard line (1-99). */
    avgStartYardline: doublePrecision(),
    /** Drives that reached the opponent 40. */
    scoringOpps: integer().notNull(),
    scoringOppPoints: integer().notNull(),
    stPlays: integer().notNull(),
    /** Net special-teams EPA from this team's perspective (both teams sum to 0). */
    stEpa: doublePrecision().notNull(),
    fgAttempts: integer().notNull(),
    fgMade: integer().notNull(),
    /** Expected FGs made from a distance-only make model (2016-22 fit). */
    fgExpected: doublePrecision().notNull(),
    xpAttempts: integer().notNull(),
    xpMade: integer().notNull(),
    /** Kick and punt return TDs scored. */
    returnTds: integer().notNull(),
    /** Interception and fumble return TDs scored by this team on defense. */
    defensiveTds: integer().notNull(),
    /** Flags against the team (incl. declined/offsetting, as nflverse counts). */
    penalties: integer().notNull(),
    penaltyYards: integer().notNull(),
    statsVersion: text().notNull(),
    updatedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    primaryKey({ columns: [t.gameId, t.team] }),
    index("nfl_team_game_stats_team_season_idx").on(t.team, t.season, t.week),
  ],
).enableRLS();

/** Snap counts per player per game (PFR via nflverse), current and previous season only;
 *  older seasons are read from nflverse directly for modelling (ADR-030). */
export const nflPlayerGameSnaps = pgTable(
  "nfl_player_game_snaps",
  {
    gameId: text()
      .notNull()
      .references(() => nflGames.gameId, { onDelete: "cascade" }),
    season: integer().notNull(),
    week: integer().notNull(),
    pfrPlayerId: text().notNull(),
    /** nflverse/NFL id (joins injury reports and play-by-play); NULL when PFR id is unmapped. */
    gsisId: text(),
    player: text().notNull(),
    position: text(),
    team: text()
      .notNull()
      .references(() => nflTeams.abbr),
    offenseSnaps: integer().notNull(),
    offensePct: doublePrecision(),
    defenseSnaps: integer().notNull(),
    defensePct: doublePrecision(),
    stSnaps: integer().notNull(),
    stPct: doublePrecision(),
  },
  (t) => [
    primaryKey({ columns: [t.gameId, t.pfrPlayerId] }),
    index("nfl_player_game_snaps_gsis_idx").on(t.gsisId, t.season, t.week),
  ],
).enableRLS();

/** Injury-report history (nflverse), current and previous season. Append-only before kickoff:
 *  each status change seen before the team's kickoff is a new row with `first_seen_at` = when
 *  our daily job first saw it (live). Rows first seen after kickoff, and all history, are
 *  backfill rows with `first_seen_at` NULL: the final report, assumed known pre-game (ADR-030). */
export const nflInjuryReports = pgTable(
  "nfl_injury_reports",
  {
    id: bigint({ mode: "number" }).primaryKey().generatedAlwaysAsIdentity(),
    season: integer().notNull(),
    week: integer().notNull(),
    gameType: text().notNull(),
    team: text()
      .notNull()
      .references(() => nflTeams.abbr),
    /** The team's game that week (NULL if not in nfl_games). */
    gameId: text().references(() => nflGames.gameId, { onDelete: "set null" }),
    gsisId: text().notNull(),
    fullName: text().notNull(),
    position: text(),
    /** Out, Doubtful, Questionable, or NULL (practice report only). */
    reportStatus: text(),
    reportPrimaryInjury: text(),
    reportSecondaryInjury: text(),
    practiceStatus: text(),
    practicePrimaryInjury: text(),
    contentHash: text().notNull(),
    firstSeenAt: tstz(),
    lastSeenAt: tstz(),
  },
  (t) => [
    index("nfl_injury_reports_week_idx").on(t.season, t.week, t.team),
    index("nfl_injury_reports_player_idx").on(t.gsisId),
    unique("nfl_injury_reports_live_key").on(t.season, t.week, t.team, t.gsisId, t.firstSeenAt),
    uniqueIndex("nfl_injury_reports_backfill_key")
      .on(t.season, t.week, t.team, t.gsisId)
      .where(sql`${t.firstSeenAt} IS NULL`),
  ],
).enableRLS();
