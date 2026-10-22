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
  // Finished, but some requested data is missing (e.g. a book's history too large to parse). Never
  // reported as completed, so the gap stays visible and can be retried (ADR-071).
  "partial",
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

/**
 * Minute-level main-line history (MS-042, ADR-052): one row each time a book's main line
 * changed, from provider change logs (OddsPapi). Separate from odds_observations, whose rows
 * are snapshots on our collection cadence. Both sides travel together so a no-vig price can
 * be computed from any row. Side 1 = HOME (spreads, h2h) or OVER (totals). A row with no
 * prices records a suspension (the main line was off the board for at least a minute).
 */
export const lineMoves = pgTable(
  "line_moves",
  {
    eventId: uuid()
      .notNull()
      .references(() => events.id, { onDelete: "cascade" }),
    bookmakerKey: text()
      .notNull()
      .references(() => bookmakers.key),
    marketType: marketType().notNull(),
    /** Provider time of the change. */
    changedAt: tstz().notNull(),
    /** Home team's spread or the total; NULL for moneylines and suspensions. */
    point: numeric({ precision: 5, scale: 1, mode: "number" }),
    price1: integer(),
    price2: integer(),
    /** Maximum stake per side, kept for the reference books only (Pinnacle, Bookmaker.eu). */
    limit1: integer(),
    limit2: integer(),
    source: text().notNull(),
    ingestedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    // Also the index for "one book's history in one game, in time order".
    primaryKey({ columns: [t.eventId, t.bookmakerKey, t.marketType, t.changedAt] }),
    check("line_moves_prices_paired", sql`(${t.price1} IS NULL) = (${t.price2} IS NULL)`),
    check(
      "line_moves_point_matches_market",
      sql`CASE WHEN ${t.price1} IS NULL OR ${t.marketType} = 'h2h' THEN ${t.point} IS NULL
        ELSE ${t.point} IS NOT NULL END`,
    ),
    check(
      "line_moves_valid_american_prices",
      sql`${t.price1} IS NULL OR ((${t.price1} <= -100 OR ${t.price1} >= 100)
        AND (${t.price2} <= -100 OR ${t.price2} >= 100))`,
    ),
  ],
).enableRLS();

/**
 * Ghost-market corrections to line_moves (MS-058, ADR-065): for a book and market whose main line
 * the feed's dead markets distorted, the whole corrected timeline. line_moves stays as derived
 * (pre-registered studies read it); the replay page reads line_moves with these applied.
 */
export const lineMoveFixes = pgTable(
  "line_move_fixes",
  {
    eventId: uuid()
      .notNull()
      .references(() => events.id, { onDelete: "cascade" }),
    bookmakerKey: text()
      .notNull()
      .references(() => bookmakers.key),
    marketType: marketType().notNull(),
    changedAt: tstz().notNull(),
    point: numeric({ precision: 5, scale: 1, mode: "number" }),
    price1: integer(),
    price2: integer(),
    limit1: integer(),
    limit2: integer(),
    source: text().notNull(),
    ingestedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    primaryKey({ columns: [t.eventId, t.bookmakerKey, t.marketType, t.changedAt] }),
    check("line_move_fixes_prices_paired", sql`(${t.price1} IS NULL) = (${t.price2} IS NULL)`),
    check(
      "line_move_fixes_point_matches_market",
      sql`CASE WHEN ${t.price1} IS NULL OR ${t.marketType} = 'h2h' THEN ${t.point} IS NULL
        ELSE ${t.point} IS NOT NULL END`,
    ),
    check(
      "line_move_fixes_valid_american_prices",
      sql`${t.price1} IS NULL OR ((${t.price1} <= -100 OR ${t.price1} >= 100)
        AND (${t.price2} <= -100 OR ${t.price2} >= 100))`,
    ),
  ],
).enableRLS();

/**
 * Paper portfolio (MS-045b, ADR-056): hypothetical positions from pre-registered systems, placed
 * before kickoff at a real book's posted line and graded after the game. Hypothetical only: nothing
 * here is a wager. Placement columns are immutable (trigger in migration 0018); only the grading
 * columns change. mode: live (placed before kickoff by the scheduled job), reconstructed (from
 * snapshots stored before kickoff, created afterwards) or synthetic (demo/e2e databases only).
 */
export const paperPositions = pgTable(
  "paper_positions",
  {
    id: bigint({ mode: "number" }).primaryKey().generatedAlwaysAsIdentity(),
    /** e.g. wong-V0, F1 … F10 (definitions: research/PREREGISTRATION.md Addenda E and F). */
    strategy: text().notNull(),
    mode: text().notNull(),
    gameId: text()
      .notNull()
      .references(() => nflGames.gameId),
    season: integer().notNull(),
    week: integer().notNull(),
    kickoffUtc: tstz().notNull(),
    /** spread, total or teaser_leg (a teaser leg's price applies when legs are paired). */
    market: text().notNull(),
    /** nflverse team abbreviation, or over/under. */
    side: text().notNull(),
    /** The book's line from the side's perspective (team spread) or the total. */
    line: numeric({ precision: 5, scale: 1, mode: "number" }).notNull(),
    teasedLine: numeric({ precision: 5, scale: 1, mode: "number" }),
    price: integer(),
    bookmakerKey: text()
      .notNull()
      .references(() => bookmakers.key),
    /** When the quote used was observed (a snapshot before kickoff). */
    quoteObservedAt: tstz().notNull(),
    placedAt: tstz().notNull().defaultNow(),
    result: text(),
    /** Pinnacle's closing line for the same side (or the nflverse close), and CLV in points. */
    closeLine: numeric({ precision: 5, scale: 1, mode: "number" }),
    closeSource: text(),
    clv: doublePrecision(),
    gradedAt: tstz(),
  },
  (t) => [
    unique("paper_positions_strategy_game_mode_uq").on(t.strategy, t.gameId, t.mode),
    index("paper_positions_season_idx").on(t.season, t.strategy),
    check("paper_positions_mode", sql`${t.mode} IN ('live', 'reconstructed', 'synthetic')`),
    check("paper_positions_market", sql`${t.market} IN ('spread', 'total', 'teaser_leg')`),
    check(
      "paper_positions_result",
      sql`${t.result} IS NULL OR ${t.result} IN ('win', 'loss', 'push')`,
    ),
    check("paper_positions_quote_before_kickoff", sql`${t.quoteObservedAt} < ${t.kickoffUtc}`),
    check(
      "paper_positions_live_before_kickoff",
      sql`${t.mode} <> 'live' OR ${t.placedAt} < ${t.kickoffUtc}`,
    ),
    check(
      "paper_positions_teaser_shape",
      sql`(${t.market} = 'teaser_leg') = (${t.teasedLine} IS NOT NULL)
        AND (${t.market} = 'teaser_leg' OR ${t.price} IS NOT NULL)`,
    ),
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

/** Coaching staff and play-callers by team-week span (ADR-031), loaded from the curated
 *  `apps/football/data/coaching_staff.csv`. Exactly one head coach, one offensive and one
 *  defensive play-caller cover every week of every team-season (validated before load).
 *  role: HC, OC, DC, STC, or PC (called plays without one of those titles). */
export const nflCoachingStaff = pgTable(
  "nfl_coaching_staff",
  {
    id: bigint({ mode: "number" }).primaryKey().generatedAlwaysAsIdentity(),
    season: integer().notNull(),
    team: text()
      .notNull()
      .references(() => nflTeams.abbr),
    role: text().notNull(),
    /** Stable across teams: the Wikipedia article title when one exists, else `name:<slug>`. */
    coachId: text().notNull(),
    coachName: text().notNull(),
    fromWeek: integer().notNull(),
    toWeek: integer().notNull(),
    offensePlaycaller: boolean().notNull(),
    defensePlaycaller: boolean().notNull(),
    /** Where the title comes from (nflverse schedules, a Wikipedia revision, or a news source). */
    sourceUrl: text(),
    /** list | direct | bracketed | stint | rule (see DATA_DICTIONARY); NULL when not a play-caller. */
    playcallerBasis: text(),
    playcallerSourceUrl: text(),
  },
  (t) => [
    unique("nfl_coaching_staff_span_key").on(t.season, t.team, t.role, t.coachId, t.fromWeek),
    index("nfl_coaching_staff_coach_idx").on(t.coachId),
    check("nfl_coaching_staff_weeks", sql`${t.fromWeek} <= ${t.toWeek}`),
    check("nfl_coaching_staff_role", sql`${t.role} IN ('HC', 'OC', 'DC', 'STC', 'PC')`),
  ],
).enableRLS();

/** Point-in-time weather forecasts for a game's window (kickoff hour + 3), from Open-Meteo's
 *  Previous Runs API (ADR-032): lead_days N = predicted at least N x 24 h before the hour.
 *  Lead 0 = the latest run before kickoff. Outdoor and retractable-roof venues only. */
export const nflWeatherForecasts = pgTable(
  "nfl_weather_forecasts",
  {
    gameId: text()
      .notNull()
      .references(() => nflGames.gameId, { onDelete: "cascade" }),
    leadDays: integer().notNull(),
    forecastHourUtc: tstz().notNull(),
    temperatureF: doublePrecision().notNull(),
    windMph: doublePrecision().notNull(),
    gustMph: doublePrecision().notNull(),
    precipIn: doublePrecision().notNull(),
    source: text().notNull(),
    fetchedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    primaryKey({ columns: [t.gameId, t.leadDays] }),
    check("nfl_weather_forecasts_lead", sql`${t.leadDays} BETWEEN 0 AND 7`),
  ],
).enableRLS();

/** Pre-game context per team per game (ADR-032): rest, travel, time zones, altitude, road
 *  streaks, coaching tenure. All known before kickoff. */
export const nflGameContext = pgTable(
  "nfl_game_context",
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
    week: integer().notNull(),
    /** False for both teams at a neutral site. */
    isHome: boolean().notNull(),
    neutralSite: boolean().notNull(),
    divisionGame: boolean().notNull(),
    venueKey: text().notNull(),
    /** outdoor, dome, retractable (open/closed unknown before the game). */
    roofType: text().notNull(),
    restDays: integer(),
    restDiff: integer(),
    byeBefore: boolean(),
    shortWeek: boolean(),
    homeVenueKey: text().notNull(),
    travelKm: doublePrecision().notNull(),
    /** Venue UTC offset minus the team's home UTC offset at kickoff. */
    tzShiftHours: doublePrecision().notNull(),
    /** Kickoff in the team's home time zone (e.g. 10.0 for a Pacific team at 1 pm ET). */
    bodyClockKickoffHour: doublePrecision().notNull(),
    venueLocalKickoffHour: doublePrecision().notNull(),
    altitudeM: integer().notNull(),
    altitudeChangeM: integer().notNull(),
    /** Consecutive games away from home (neutral counts), this one included; 0 at home. */
    roadStreak: integer().notNull(),
    hcCoach: text(),
    offPlaycaller: text(),
    defPlaycaller: text(),
    /** Consecutive prior games with the franchise; NULL when the run began before our data. */
    hcTenureGames: integer(),
    offPlaycallerTenureGames: integer(),
    defPlaycallerTenureGames: integer(),
    newOffPlaycaller: boolean(),
    newDefPlaycaller: boolean(),
  },
  (t) => [
    primaryKey({ columns: [t.gameId, t.team] }),
    index("nfl_game_context_team_season_idx").on(t.team, t.season, t.week),
  ],
).enableRLS();

/**
 * MarketScope Ratings snapshots (MS-030b, ADR-035): the KenPom contract for every team after every
 * week (week 0 = preseason prior), filtered = point-in-time. Written by apps/football; one row per
 * (model_version, season, week, team). See docs/DATA_DICTIONARY.md and docs/RATINGS.md.
 */
export const ratingSnapshots = pgTable(
  "rating_snapshots",
  {
    modelVersion: text().notNull(),
    season: integer().notNull(),
    /** Ratings after all games through this week; 0 = preseason (after season reversion). */
    week: integer().notNull(),
    team: text()
      .notNull()
      .references(() => nflTeams.abbr),
    /** Expected margin vs an average team on a neutral field, points per game. */
    adjEm: doublePrecision().notNull(),
    adjEmSe: doublePrecision().notNull(),
    adjEmRank: integer().notNull(),
    /** Points per drive vs an average defense (higher is better). */
    adjO: doublePrecision().notNull(),
    adjOSe: doublePrecision().notNull(),
    adjORank: integer().notNull(),
    /** Points per drive allowed vs an average offense (lower is better; rank 1 = best). */
    adjD: doublePrecision().notNull(),
    adjDSe: doublePrecision().notNull(),
    adjDRank: integer().notNull(),
    /** Special-teams points per game vs average. */
    adjSt: doublePrecision().notNull(),
    adjStSe: doublePrecision().notNull(),
    adjStRank: integer().notNull(),
    /** Drives per team-game vs an average opponent (rank 1 = fastest). */
    adjPace: doublePrecision().notNull(),
    adjPaceSe: doublePrecision().notNull(),
    adjPaceRank: integer().notNull(),
    /** ≈ share of the rating still carried by the preseason prior (variance now / variance at week 0). */
    priorWeight: doublePrecision().notNull(),
    /** Unit ratings, EPA/play (success: rate; ppd: points per drive) above average; defense = allowed. */
    passOff: doublePrecision().notNull(),
    passDef: doublePrecision().notNull(),
    rushOff: doublePrecision().notNull(),
    rushDef: doublePrecision().notNull(),
    succOff: doublePrecision().notNull(),
    succDef: doublePrecision().notNull(),
    ppdOff: doublePrecision().notNull(),
    ppdDef: doublePrecision().notNull(),
    games: integer().notNull(),
    wins: integer().notNull(),
    losses: integer().notNull(),
    ties: integer().notNull(),
    pointsFor: integer().notNull(),
    pointsAgainst: integer().notNull(),
    /** Sum over games of P(win | that game's net adjusted EPA, venue). */
    expectedWins: doublePrecision().notNull(),
    pythagWins: doublePrecision().notNull(),
    /** Wins (+ half ties) minus expected wins. */
    luck: doublePrecision().notNull(),
    luckRank: integer().notNull(),
    /** Luck decomposition: one-score games (wins), fumble and INT luck (EPA), FG luck (points), return/defensive TDs. */
    oneScoreLuck: doublePrecision().notNull(),
    fumbleLuck: doublePrecision().notNull(),
    intLuck: doublePrecision().notNull(),
    fgLuck: doublePrecision().notNull(),
    returnTdDiff: integer().notNull(),
    /** Venue-adjusted mean current AdjEM of opponents played; NULL before a team's first game. */
    sos: doublePrecision(),
    sosRank: integer(),
    oppAdjO: doublePrecision(),
    oppAdjD: doublePrecision(),
    nondivSos: doublePrecision(),
    /** Remaining regular-season opponents (NULL when none remain). */
    remainingSos: doublePrecision(),
    remainingGames: integer().notNull(),
    /** Five Factors, season to date (raw): success rate, EPA per successful play, average start yard line, points per trip inside the 40, turnovers per game. */
    offSuccessRate: doublePrecision(),
    defSuccessRate: doublePrecision(),
    offExplosiveness: doublePrecision(),
    defExplosiveness: doublePrecision(),
    offStartYardline: doublePrecision(),
    defStartYardline: doublePrecision(),
    offPointsPerOpp: doublePrecision(),
    defPointsPerOpp: doublePrecision(),
    offTurnovers: doublePrecision(),
    defTurnovers: doublePrecision(),
    computedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    primaryKey({ columns: [t.modelVersion, t.season, t.week, t.team] }),
    index("rating_snapshots_team_idx").on(t.team, t.season, t.week),
  ],
).enableRLS();

/**
 * Season projections (MS-034, ADR-042): simulated rest-of-season odds for every team before week 1
 * (week 0) and after every regular-season week, from the same point-in-time state as
 * rating_snapshots. Written by apps/football (`ingest projections`); replaced per model version.
 */
export const seasonProjections = pgTable(
  "season_projections",
  {
    modelVersion: text().notNull(),
    season: integer().notNull(),
    /** Projection after all games through this week (matches rating_snapshots.week); 0 = preseason. */
    week: integer().notNull(),
    team: text()
      .notNull()
      .references(() => nflTeams.abbr),
    /** Simulated seasons behind the probabilities. */
    sims: integer().notNull(),
    /** Regular-season games whose results were fixed (not simulated). */
    gamesPlayed: integer().notNull(),
    /** Team strength used for playoff games: points vs average on a neutral field, incl. its QB term. */
    strength: doublePrecision().notNull(),
    /** Mean regular-season wins and P(exactly k wins) for k = 0..17. */
    meanWins: doublePrecision().notNull(),
    winDist: jsonb().$type<number[]>().notNull(),
    playoffP: doublePrecision().notNull(),
    divisionP: doublePrecision().notNull(),
    seed1P: doublePrecision().notNull(),
    /** Wins the conference (reaches the Super Bowl) / wins the Super Bowl. */
    confP: doublePrecision().notNull(),
    sbP: doublePrecision().notNull(),
    computedAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    primaryKey({ columns: [t.modelVersion, t.season, t.week, t.team] }),
    index("season_projections_team_idx").on(t.team, t.season, t.week),
    check(
      "season_projections_p_range",
      sql`${t.playoffP} BETWEEN 0 AND 1 AND ${t.divisionP} BETWEEN 0 AND 1 AND ${t.seed1P} BETWEEN 0 AND 1 AND ${t.confP} BETWEEN 0 AND 1 AND ${t.sbP} BETWEEN 0 AND 1`,
    ),
  ],
).enableRLS();

/**
 * Model evaluation runs (MS-032b, ADR-039): one row per scored run of a frozen model version, e.g. the
 * one-time 2025 test. A version can have only one "test" run.
 */
export const modelRuns = pgTable(
  "model_runs",
  {
    id: uuid().primaryKey().defaultRandom(),
    modelVersion: text().notNull(),
    /** validation, test (the untouched season, once), forward (live scorecard snapshots). */
    runKind: text().notNull(),
    seasons: text().notNull(),
    games: integer().notNull(),
    /** Per-model metrics with CIs, as written by the report generator. */
    metrics: jsonb().$type<Record<string, unknown>>().notNull(),
    /** sha256 of the canonical params JSON the run used. */
    paramsSha256: text().notNull(),
    codeSha: text().notNull(),
    notes: text(),
    ranAt: tstz().notNull(),
    createdAt: tstz().notNull().defaultNow(),
  },
  (t) => [
    check("model_runs_kind", sql`${t.runKind} IN ('validation', 'test', 'forward')`),
    uniqueIndex("model_runs_one_test_per_version")
      .on(t.modelVersion)
      .where(sql`${t.runKind} = 'test'`),
  ],
).enableRLS();

/**
 * Live forward test (MS-032b, ADR-039): append-only model estimates made before kickoff. Each daily run
 * adds a row per upcoming game; rows are never updated. The scorecard uses the last row before kickoff.
 */
export const modelPredictions = pgTable(
  "model_predictions",
  {
    modelVersion: text().notNull(),
    gameId: text()
      .notNull()
      .references(() => nflGames.gameId, { onDelete: "cascade" }),
    predictedAt: tstz().notNull(),
    kickoffUtc: tstz().notNull(),
    homeTeam: text().notNull(),
    awayTeam: text().notNull(),
    /** Expected home margin (points) and the model's total. */
    expectedMargin: doublePrecision().notNull(),
    expectedTotal: doublePrecision(),
    homeScore: doublePrecision(),
    awayScore: doublePrecision(),
    pHome: doublePrecision().notNull(),
    /** Expected starting QBs (gsis ids) and the probability each plays. */
    homeQb: text(),
    awayQb: text(),
    homeQbP: doublePrecision(),
    awayQbP: doublePrecision(),
    /** Additive contributions to the margin, e.g. {"ratings": 3.1, "home": 0.3, "qb": -1.2, "absences": -0.4}. */
    contributions: jsonb().$type<Record<string, number>>().notNull(),
    /**
     * Provenance (ADR-074): the frozen parameters, feature schema, code commit and a content hash of
     * the inputs (results, play-by-play channels, expected starters) behind this estimate. Null for
     * rows written before it was recorded.
     */
    paramsSha256: text(),
    featureSchemaSha256: text(),
    codeSha: text(),
    inputSha256: text(),
  },
  (t) => [
    primaryKey({ columns: [t.modelVersion, t.gameId, t.predictedAt] }),
    check("model_predictions_before_kickoff", sql`${t.predictedAt} < ${t.kickoffUtc}`),
    check("model_predictions_p_range", sql`${t.pHome} >= 0 AND ${t.pHome} <= 1`),
    index("model_predictions_game_idx").on(t.gameId),
  ],
).enableRLS();

// ---- Site accounts (MS-038, ADR-049) ------------------------------------------------------------
// Better Auth's core tables (user, session, account, verification) plus its username plugin fields
// and database-backed rate limiting. Invite-only: there is no sign-up endpoint; accounts are
// created by `pnpm --filter @marketscope/web user:create`. Passwords live hashed (scrypt) in
// auth_accounts.password, never in auth_users. Better Auth works with Date objects, so these
// tables use mode "date" timestamps.
const authTs = () => timestamp({ withTimezone: true, mode: "date" });

export const authUsers = pgTable("auth_users", {
  id: text().primaryKey(),
  name: text().notNull(),
  email: text().notNull().unique(),
  emailVerified: boolean().notNull().default(false),
  image: text(),
  /** Login name (lower-cased by Better Auth); displayUsername keeps the original casing. */
  username: text().unique(),
  displayUsername: text(),
  createdAt: authTs().notNull().defaultNow(),
  updatedAt: authTs().notNull().defaultNow(),
}).enableRLS();

export const authSessions = pgTable(
  "auth_sessions",
  {
    id: text().primaryKey(),
    /** Random session token; the browser holds it in a signed, httpOnly cookie. */
    token: text().notNull().unique(),
    userId: text()
      .notNull()
      .references(() => authUsers.id, { onDelete: "cascade" }),
    expiresAt: authTs().notNull(),
    ipAddress: text(),
    userAgent: text(),
    createdAt: authTs().notNull().defaultNow(),
    updatedAt: authTs().notNull().defaultNow(),
  },
  (t) => [index("auth_sessions_user_idx").on(t.userId)],
).enableRLS();

export const authAccounts = pgTable(
  "auth_accounts",
  {
    id: text().primaryKey(),
    /** "credential" for username/email + password; OAuth providers would add rows here. */
    providerId: text().notNull(),
    accountId: text().notNull(),
    userId: text()
      .notNull()
      .references(() => authUsers.id, { onDelete: "cascade" }),
    password: text(),
    accessToken: text(),
    refreshToken: text(),
    idToken: text(),
    accessTokenExpiresAt: authTs(),
    refreshTokenExpiresAt: authTs(),
    scope: text(),
    createdAt: authTs().notNull().defaultNow(),
    updatedAt: authTs().notNull().defaultNow(),
  },
  (t) => [index("auth_accounts_user_idx").on(t.userId)],
).enableRLS();

export const authVerifications = pgTable("auth_verifications", {
  id: text().primaryKey(),
  identifier: text().notNull(),
  value: text().notNull(),
  expiresAt: authTs().notNull(),
  createdAt: authTs().notNull().defaultNow(),
  updatedAt: authTs().notNull().defaultNow(),
}).enableRLS();

/** Login rate limiting shared by every serverless instance (in-memory counters would not be). */
export const authRateLimits = pgTable("auth_rate_limits", {
  id: text().primaryKey(),
  key: text().notNull().unique(),
  count: integer().notNull(),
  lastRequest: bigint({ mode: "number" }).notNull(),
}).enableRLS();
