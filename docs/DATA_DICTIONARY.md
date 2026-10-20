# Data Dictionary

## Domain concepts

| Concept                     | Definition                                                                                                                    |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Market**                  | `h2h` (moneyline), `spreads` (point spread), `totals` (over/under)                                                            |
| **Selection**               | `HOME`, `AWAY` (h2h, spreads) · `OVER`, `UNDER` (totals)                                                                      |
| **Point**                   | The spread or total line. Spreads keep the book's sign (home −3.5 = home favored by 3.5). Always `null` for moneylines        |
| **American price**          | Integer with \|price\| ≥ 100. −110 means risk 110 to win 100; +150 means risk 100 to win 150. −100 ≡ +100                     |
| **Raw implied probability** | −A → A/(A+100); +A → 100/(A+100). Includes the bookmaker's margin; **not** a calibrated win probability                       |
| **Overround**               | Sum of raw implied probabilities across a complete outcome set at the same line, minus 1                                      |
| **Identical line**          | Same event, market, selection, **and point**. Prices are compared only within an identical line                               |
| **Home-oriented spread**    | For history, stats, and consensus, always use the home team's spread. A move from −3.5 to −2.5 is +1.0 (toward the away side) |

## NormalizedQuote (`packages/shared/src/domain.ts`)

| Field                | Type               | Meaning                                                                                           |
| -------------------- | ------------------ | ------------------------------------------------------------------------------------------------- |
| `providerEventId`    | string             | Provider's event ID (mapped to an internal UUID in Phase 1)                                       |
| `bookmakerKey`       | string             | Provider bookmaker key, e.g. `draftkings`                                                         |
| `market`             | Market             |                                                                                                   |
| `selection`          | Selection          | Taken from exact equality with the event's `home_team`/`away_team`, or Over/Under                 |
| `point`              | number \| null     | See above                                                                                         |
| `americanPrice`      | number             | Validated integer American odds                                                                   |
| `bookmakerUpdatedAt` | ISO string \| null | **Provider-reported** market `last_update`: when the book's market last changed, per the provider |
| `observedAt`         | ISO string         | **When we received** the response (live), or the provider's snapshot time (historical)            |
| `isLive`             | boolean            | `commence_time <= observedAt`: the event had started, so prices are in-play                       |

## Timestamp semantics

| Timestamp               | Source                                                                | Use                                                           |
| ----------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------- |
| `bookmaker_updated_at`  | Provider market `last_update`                                         | Book freshness, i.e. whether a book is stale for consensus    |
| `observed_at`           | Our collector clock at response time, or the historical snapshot time | Ordering observations and replay cursors                      |
| `requested_snapshot_at` | What we asked the historical endpoint for                             | Provenance and caching                                        |
| `provider_snapshot_at`  | What the historical endpoint actually returned                        | Becomes `observed_at` for historical rows                     |
| `commence_time`         | Provider event kickoff                                                | Pregame/live classification; can change when games are flexed |

**Rules:**

- A change seen between two observations happened somewhere in `(prev.observed_at, next.observed_at]`. We never claim an exact time.
- The first observation is "first observed", not the opening line. The last pregame observation is "last observed pregame", not the closing line.
- Never stamp historical data with the import time.

### Imported history (`source = 'oddspapi'`, ADR-026)

| Field                  | Meaning for imported rows                                                           |
| ---------------------- | ----------------------------------------------------------------------------------- |
| `observed_at`          | a **derived snapshot time** (00/06/12/18 UTC, or kickoff − 5 min), not a poll time  |
| `bookmaker_updated_at` | the provider's recorded **change time** for that price                              |
| `ingestion_run`        | one `historical` run per fixture (`oddspapi:<fixtureId>:v1`); no raw payload stored |

A quote is the book's latest active entry at the snapshot time. Prices hold between recorded changes, following the provider's change-log semantics.

## Normalization issues

Codes are defined in `NORMALIZATION_ISSUE_CODES`:

- `BOOKMAKER_MISSING` / `UNEXPECTED_BOOKMAKER`
- `MARKET_MISSING` / `UNEXPECTED_MARKET`
- `INCOMPLETE_MARKET`
- `UNKNOWN_OUTCOME`
- `DUPLICATE_SELECTION` (all copies dropped)
- `INVALID_PRICE` (dropped)
- `INVALID_POINT` (dropped)
- `UNEXPECTED_POINT` (moneyline point ignored)
- `INCONSISTENT_SPREAD` (kept and flagged)
- `INVALID_TIMESTAMP` (stored as null)

## Database tables

Source of truth: `packages/db/src/schema.ts`. Migrations live in `packages/db/drizzle/` (committed SQL). Every timestamp is `timestamptz`, which stores an absolute instant. psql displays it in your session's time zone; the API will always emit ISO 8601 UTC.

### `events`: one NFL game

| Column                     | Type             | Notes                                                                                                                                                                                      |
| -------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `id`                       | uuid PK          | Internal ID used by all foreign keys                                                                                                                                                       |
| `provider_event_id`        | text, **unique** | The Odds API event ID; the upsert key                                                                                                                                                      |
| `sport_key`                | text             | `americanfootball_nfl`                                                                                                                                                                     |
| `season`                   | int              | NFL season year; Jan/Feb games belong to the prior year (`nflSeasonForKickoff`)                                                                                                            |
| `week`                     | int, nullable    | Not in the odds feed; filled later (ADR-009)                                                                                                                                               |
| `home_team`, `away_team`   | text             | From the provider's home/away fields. **Never rewritten after insert**: if the provider flips orientation, that run's quotes for the game are dropped and counted as `EVENT_TEAMS_CHANGED` |
| `commence_time_utc`        | timestamptz      | Updated on upsert (flexed games, actual kickoff)                                                                                                                                           |
| `created_at`, `updated_at` | timestamptz      | `updated_at` changes only when the kickoff time changes                                                                                                                                    |

Index: `commence_time_utc` (upcoming-games queries).

### `bookmakers`: provider feeds

`key` (PK, provider bookmaker key), `display_name`, `region_hint`, `is_primary` (the preferred feed of a board column), `enabled`. Seeded by migration `0001` and upserted by every collector run from `COLLECTED_BOOKMAKERS`.

### `ingestion_runs`: one collection job (observability + idempotency)

| Column                              | Notes                                                                                                                                    |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `job_key` (**unique**)              | `live:nfl:<slot start>` for scheduled runs, `manual:<uuid>` for manual ones                                                              |
| `status`                            | `started` → `completed` / `failed` / `skipped` (budget guard)                                                                            |
| `attempt`                           | Increments when a failed, skipped, or stale (`started` > 15 min) key is reclaimed                                                        |
| `request_type`                      | `live` or `historical`. `requested_snapshot_at` / `provider_snapshot_at` are for historical imports (Phase 6)                            |
| `http_status`, `duration_ms`        | Provider response metadata                                                                                                               |
| `credits_used`, `credits_remaining` | From `x-requests-last` / `x-requests-remaining`. **Recorded even for failed runs**, because credits are spent once the provider responds |
| `events_seen`, `quotes_seen`        | Counts for the run                                                                                                                       |
| `issue_counts`                      | jsonb, normalization issues by code (plus `SCHEMA_REJECTED`, `EVENT_TEAMS_CHANGED`)                                                      |
| `error_code`, `error_message`       | Sanitized: provider error code or `PERSISTENCE` / `BUDGET` / `UNEXPECTED`. Never contains URLs or credentials                            |

Index: `started_at DESC` (latest runs, monthly budget sum).

### `ingestion_payloads`: raw provider response per run

`ingestion_run_id` (PK/FK, cascade delete), `received_at`, `payload` (jsonb). Lets a normalizer fix be re-applied to past runs without re-buying data.

### `odds_observations`: append-only quote history

| Column                                          | Notes                                                                |
| ----------------------------------------------- | -------------------------------------------------------------------- |
| `id`                                            | bigint identity                                                      |
| `ingestion_run_id`, `event_id`, `bookmaker_key` | FKs                                                                  |
| `market_type`, `selection`                      | Postgres enums                                                       |
| `point`                                         | `numeric(5,1)`, exact (not float). NULL **iff** moneyline            |
| `american_price`                                | int, never in (−100, 100)                                            |
| `bookmaker_updated_at`                          | Provider market `last_update`. **Not a change marker** (see below)   |
| `observed_at`                                   | When we received the response; identical for every row of a live run |
| `is_live`                                       | Event had started at `observed_at`                                   |

Constraints:

- `UNIQUE (ingestion_run_id, event_id, bookmaker_key, market_type, selection)`: one row per selection per run.
- `CHECK`s: point matches market; selection matches market; valid American price.

Indexes:

- The unique constraint above (which also serves "rows of run X", because it leads with `ingestion_run_id`).
- `(event_id, market_type, selection, bookmaker_key, observed_at DESC)`: per-book history and latest quote.

**Unchanged prices are stored on purpose.** Two runs that see the same line produce two rows. That is evidence the line was still there at the second time. Movement detection compares consecutive observations by **value** (point and price), never by `bookmaker_updated_at`. Live data on 2026-10-16 showed DraftKings' `last_update` advancing between runs while its line stayed at −1.5 (−105).

### `market_signals`: derived Signal Lab detections

| Column                                      | Notes                                                                      |
| ------------------------------------------- | -------------------------------------------------------------------------- |
| `id`                                        | bigint identity                                                            |
| `event_id`                                  | FK `events` (cascade delete)                                               |
| `signal_type`, `algorithm_version`          | e.g. `book_divergence`, `1` (definitions: `docs/SIGNAL_DEFINITIONS.md`)    |
| `market_type`, `selection`, `bookmaker_key` | selection and book are null for market-wide signals (e.g. consensus moves) |
| `detected_at`                               | when the signal became observable (end of its window)                      |
| `window_start`, `window_end`                | the evidence interval (`window_start <= window_end`, enforced by CHECK)    |
| `value`                                     | points, cents, or a signed key number, depending on type                   |
| `details`                                   | jsonb (from/to values, direction, consensus, best/worst books, …)          |
| `evidence_observation_ids`                  | bigint[] of `odds_observations.id`                                         |
| `computed_at`                               | recompute time                                                             |

RLS is enabled. Rows are replaced per (event, type, version) on recompute.

### `line_moves`: minute-level main-line history (MS-042, ADR-052)

| Column                  | Notes                                                                                     |
| ----------------------- | ----------------------------------------------------------------------------------------- |
| `event_id`              | FK `events` (cascade delete); the game's existing event, whichever source created it      |
| `bookmaker_key`         | FK `bookmakers`; includes the reference books `pinnacle`, `circa`, `bookmaker_eu`         |
| `market_type`           | `h2h`, `spreads`, `totals`                                                                |
| `changed_at`            | provider time of the change (for a suspension, when the line went off)                    |
| `point`                 | home team's spread or the total; NULL for moneylines and suspensions                      |
| `price1`, `price2`      | American prices. Side 1 = HOME (spreads, h2h) or OVER (totals). Both NULL = suspended     |
| `limit1`, `limit2`      | maximum stake per side, reference books only (Pinnacle, Bookmaker.eu; Circa reports none) |
| `source`, `ingested_at` | `oddspapi`; import time (never used as a market time)                                     |

Primary key `(event_id, bookmaker_key, market_type, changed_at)`, which also serves "one book's history in one game, in time order". `CHECK`s: prices are both set or both NULL; point matches market (NULL for moneylines and suspensions); valid American prices. RLS is enabled.

A row means the main line changed; the line stays in effect until the next row. Changes under 1 s apart are merged, suspensions under 60 s are ignored, and only the last 14 days before kickoff are kept (plus the line in effect at the start).

## Football tables (ADR-028)

Written only by `apps/football` (Python). The schema is still owned by Drizzle. Source: [nflverse](https://github.com/nflverse) (CC-BY 4.0).

### `nfl_teams`

`abbr` (PK, nflverse abbreviation). `franchise` is the current franchise: relocated or alias abbreviations map to it (`OAK`→`LV`, `SD`→`LAC`, `STL`→`LA`, `LAR`→`LA`), so ratings follow the franchise. Also `full_name`, `nickname`, `conference` and `division`. `odds_api_name` is the exact `events.home_team`/`away_team` string; it is set only for current franchises.

### `nfl_games`: one game from the nflverse schedule

| Column                                                                                   | Notes                                                                                                                                            |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `game_id`                                                                                | PK, e.g. `2026_01_NE_SEA`                                                                                                                        |
| `season`, `game_type`, `week`                                                            | `game_type`: REG, WC, DIV, CON, SB                                                                                                               |
| `kickoff_utc`                                                                            | From nflverse `gameday` + `gametime`, which are US Eastern                                                                                       |
| `home_team`, `away_team`                                                                 | FKs to `nfl_teams`. `neutral_site` is true when `location = Neutral` (designated home team)                                                      |
| `home_score`, `away_score`, `overtime`                                                   | Results. **Post-hoc: never a feature for the same game**                                                                                         |
| `final_observed_at`                                                                      | When our ingest first saw the final score. NULL for games already final at backfill (no import time on history)                                  |
| `roof`, `surface`, `stadium_id`, `stadium`                                               | As played. A retractable roof's status is unknown before the game                                                                                |
| `observed_temp_f`, `observed_wind_mph`                                                   | Weather as played. **Post-hoc**; forecasts arrive in MS-028                                                                                      |
| `referee`, `home_coach`, `away_coach`                                                    |                                                                                                                                                  |
| `home_qb_id`, `away_qb_id`                                                               | Starting QBs as played. Post-hoc; used only for the oracle-vs-expected-starter study                                                             |
| `nflverse_close_home_spread`                                                             | nflverse `spread_line` (positive = home favored) stored as **−`spread_line`**, our home orientation. A labeled benchmark, never an observation   |
| `nflverse_close_total`, `nflverse_close_home_moneyline`, `nflverse_close_away_moneyline` | nflverse closing total and moneylines                                                                                                            |
| `event_id`                                                                               | Unique FK to `events`. Set by the linker: exact team names, same orientation, kickoff within 36 h. Swapped orientation is reported, never linked |

Indexes: `(season, week)` and `kickoff_utc`. CHECKs: the teams differ; both scores are set or neither is.

### `nfl_team_game_stats`: one team's offense in one final game (MS-027)

Aggregated from nflverse play-by-play by `apps/football/src/marketscope_football/team_stats.py`, using the frozen constants in `design.py` (ADR-029). PK `(game_id, team)`. **A team's defense in a game is its opponent's row.** Only games final in `nfl_games` get rows; each season is replaced wholesale, and `stats_version` names the definitions. Rates are NULL without a denominator; counts are 0. Post-hoc, like every result: features for a game use only rows from earlier games.

| Group             | Columns                                                                                                                                                                                                                      | Definition                                                                                                                                                                                                                                |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity          | `game_id`, `team`, `opponent`, `season`, `season_type` (REG/POST), `week`, `is_home`                                                                                                                                         | `is_home` follows the nflverse designated home team (also on neutral sites)                                                                                                                                                               |
| Volume            | `plays`, `dropbacks`, `rushes`, `early_down_plays`, `neutral_plays`                                                                                                                                                          | Scrimmage plays = passes (incl. sacks, scrambles) and runs with an EPA value, **including penalty-nullified ones** (nflfastR team-efficiency convention). Neutral: win probability 20–80%, quarters 1–4, not the last 2 minutes of a half |
| Raw efficiency    | `epa_per_play`, `epa_per_dropback`, `epa_per_rush`, `early_down_epa_per_play`                                                                                                                                                | Plain means of nflverse `epa`                                                                                                                                                                                                             |
| **Model channel** | `adj_epa_per_play`, `adj_epa_per_dropback`, `adj_epa_per_rush`, `adj_weight`                                                                                                                                                 | Luck-adjusted, capped at ±4.5, win-probability-weighted EPA (weight 1 inside 10–90% WP, falling linearly to 0.25 at 0/100%). `adj_weight` is the sum of weights (effective plays), which sets observation noise in the ratings            |
| Five Factors      | `success_rate` (+ dropback/rush), `explosive_rate` (passes 20+, runs 10+ yards), `epa_per_success`, `avg_start_yardline` (own yard line), `scoring_opps` / `scoring_opp_points` (drives reaching the opponent 40), turnovers | Connelly's efficiency, explosiveness, field position, finishing drives, turnovers                                                                                                                                                         |
| Passing           | `cpoe` (percentage points), `sacks`, `sack_rate`                                                                                                                                                                             |                                                                                                                                                                                                                                           |
| Scheme / pace     | `neutral_pass_rate`, `proe` (pass − xpass on neutral plays, as a fraction), `neutral_seconds_per_play`, `shotgun_rate`, `no_huddle_rate`                                                                                     | Pace = seconds between consecutive neutral snaps of one drive; gaps over 60 s (timeouts, reviews, quarter breaks) are excluded                                                                                                            |
| Drives            | `drives`, `drive_points`                                                                                                                                                                                                     | Drives with at least one scrimmage, punt, field-goal or kneel play (kickoffs excluded). Drive points = the offense's own score change on the drive (TD + try, FG). Final score − `drive_points` = defensive/return TDs and safeties       |
| Turnover luck     | `interceptions`, `passes_defensed` (by the opponent, interceptions included), `fumbles` (own, scrimmage), `fumbles_lost`, `fumble_luck_epa`, `int_luck_epa`                                                                  | Luck = actual − expected EPA (positive = lucky). Fumbles: recovery treated as a coin flip at the 2016–22 rate (46.1% lost). Interceptions: 19.0% of passes defensed expected to be picked                                                 |
| Situational       | `fourth_down_attempts`, `fourth_down_conversions`, `penalties`, `penalty_yards`                                                                                                                                              | Penalties = flags against the team, including declined/offsetting, as nflverse counts them                                                                                                                                                |
| Special teams     | `st_plays`, `st_epa`, `fg_attempts`, `fg_made`, `fg_expected`, `xp_attempts`, `xp_made`, `return_tds`, `defensive_tds`                                                                                                       | `st_epa` is net from this team's perspective (the two rows of a game sum to 0). `fg_expected` uses a distance-only make model fitted on 2016–22 (50 yards → 70%)                                                                          |

Cross-checked against nflverse `load_team_stats` for every team-game 2016–2026 (`apps/football/reports/team-stats-crosscheck.md`): sacks, interceptions, FG and XP attempts/makes match 100%; penalties 98–99.8%; EPA correlates 0.996 once aligned to the nflverse definition.

Index: `(team, season, week)`.

### `nfl_player_game_snaps`: snap counts per player per game (MS-027)

PFR snap counts via nflverse, **current and previous season only** (older seasons are read from nflverse directly for modelling; ADR-030). PK `(game_id, pfr_player_id)`. `gsis_id` (the NFL id used by injury reports and play-by-play) is attached through nflverse `load_players`; it is NULL for the ≈ 0.2% of PFR ids that are unmapped. Also `season`, `week`, `player`, `position`, `team`, and `offense_snaps`/`offense_pct`, `defense_snaps`/`defense_pct`, `st_snaps`/`st_pct`. Each season is replaced wholesale; rows for games not in `nfl_games` are dropped. Index `(gsis_id, season, week)`.

### `nfl_injury_reports`: injury-report history (MS-027)

nflverse injury reports, current and previous season, as a **point-in-time history** (ADR-030).

| Column                                                                                           | Notes                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `id`                                                                                             | Identity PK                                                                                                                                                                                                              |
| `season`, `week`, `game_type`, `team`, `game_id`                                                 | `game_id` is the team's game that week (NULL if unknown)                                                                                                                                                                 |
| `gsis_id`, `full_name`, `position`                                                               |                                                                                                                                                                                                                          |
| `report_status`                                                                                  | Out, Doubtful, Questionable, or NULL (listed on the practice report only)                                                                                                                                                |
| `report_primary_injury`, `report_secondary_injury`, `practice_status`, `practice_primary_injury` | `practice_status` is the last practice of the week (Full / Limited / Did Not Participate)                                                                                                                                |
| `content_hash`                                                                                   | Hash of the reported fields (not the name); a change means a new status                                                                                                                                                  |
| `first_seen_at`, `last_seen_at`                                                                  | **Live rows:** when our job first and last saw this exact content, always before the team's kickoff. **Backfill rows** (all history, and anything first seen after kickoff): both NULL. Never the import time on history |

Live history is append-only before kickoff: a status change adds a row, an unchanged fetch only bumps `last_seen_at`, and nothing changes after kickoff. Backfill rows are corrected in place if nflverse revises them. A player removed from a report mid-week is not recorded as a change. Unique: one backfill row per (season, week, team, player); live rows unique on (season, week, team, player, `first_seen_at`). Indexes `(season, week, team)` and `gsis_id`.

The "known before kickoff" assumption for backfill rows: NFL teams must publish their final game-status report the day before a game (two days before for Monday games), so the final weekly report precedes kickoff. Rates of players actually playing by status are in `apps/football/reports/plays-given-status.md`.

### `nfl_coaching_staff`: coaches and play-callers by team-week span (MS-027)

Loaded from the curated, versioned `apps/football/data/coaching_staff.csv` (ADR-031), which `coaching_build.py` assembles from:

1. **Head coaches:** nflverse schedules (per game, exact change weeks), except where nflverse is stale (missing interim head coaches; the season in progress still shows last season's coaches). There the Wikipedia staff page plus dated changes are used.
2. **Coordinators** (OC, DC, special teams): each team's Wikipedia season article (`{{NFL final staff}}`), or its current staff template for the season in progress. The source is cited by revision (`oldid`). Facts only; no text is copied.
3. **Curated inputs**, one cited source per row:
   - `coordinator_changes.csv`: mid-season changes with effective dates; co-coordinators; listed coaches who did not serve.
   - `playcaller_lists.csv`: season-wide lists of every team's offensive play-caller (ESPN 2023–26, 4for4 2020, partial 2016/2018 head-coach lists).
   - `playcaller_overrides.csv`: dated exceptions and handoffs.

| Column                                      | Notes                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `season`, `team`, `role`                    | `role`: HC, OC, DC, STC, or PC (called plays without one of those titles, e.g. Steve Belichick 2019–23, Mike Sullivan 2023)                                                                                                                                                                                                                                                   |
| `coach_id`, `coach_name`                    | `coach_id` is stable across teams: the Wikipedia article title, else `name:<slug>`                                                                                                                                                                                                                                                                                            |
| `from_week`, `to_week`                      | NFL weeks (postseason 19–22). Spans are continuous across byes: a change made during a bye covers it                                                                                                                                                                                                                                                                          |
| `offense_playcaller`, `defense_playcaller`  | Exactly one of each per team-week (validated before load). When a caller holds two titles, the flag sits on the side's coordinator row, else the HC row                                                                                                                                                                                                                       |
| `source_url`                                | Source of the title: nflverse, a Wikipedia revision, or a news report                                                                                                                                                                                                                                                                                                         |
| `playcaller_basis`, `playcaller_source_url` | `list`, `direct` (source about that coach and season), `bracketed` (same coach in lists before and after), `stint` (source covering the tenure), `shared` (sources say two coaches split the calls; the row names the one reported as primary), or `rule` (unsourced default: the side's coordinator, or the head coach when there is none; shown as "assumed" on team pages) |

Coverage by basis, plus play-caller turnover by season: `apps/football/reports/coaching-staff.md`. About 31% of offensive and 86% of defensive team-weeks rest on the rule, because defensive play-calling is rarely reported team by team. Coordinator titles are audited week by week against Wikipedia staff-template history (`apps/football/reports/coaching-audit.md`, ADR-045).

The table is replaced whole on each load (job key = CSV hash). A daily drift check compares the CSV with each team's current Wikipedia staff template and prints warnings. Unique `(season, team, role, coach_id, from_week)`; index `coach_id`.

### `nfl_weather_forecasts`: point-in-time forecasts per game (MS-028)

From Open-Meteo's Previous Runs API (CC-BY 4.0), for outdoor and retractable-roof venues from 2024 (ADR-032). PK `(game_id, lead_days)`.

- `lead_days` N ∈ {1, 3, 7} means the value was predicted at least N × 24 h before the hour, so it can feed a prediction made N days out. Lead 0 is the latest run before kickoff: a near-kickoff estimate, not an observation.
- `forecast_hour_utc`: the kickoff hour.
- Over the game window (kickoff hour + 3): `temperature_f` and `wind_mph` are means, `gust_mph` the maximum, `precip_in` the sum.
- Also `source` and `fetched_at`.
- A lead is stored only once it has elapsed.

Skill against observed game weather: `apps/football/reports/weather-forecast-skill.md`.

### `nfl_game_context`: pre-game context per team per game (MS-028)

Computed from `nfl_games`, the venue catalog (`apps/football/data/venues.csv`, `venue_aliases.csv`, `venue_overrides.csv`) and `coaching_staff.csv`. Everything is known before kickoff. PK `(game_id, team)`.

| Column                                                                      | Definition                                                                                                                                                                                   |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `is_home`, `neutral_site`, `division_game`                                  | `is_home` is false for both teams at a neutral site                                                                                                                                          |
| `venue_key`, `roof_type`                                                    | Venue from the alias table, corrected by `venue_overrides.csv` where nflverse is wrong (2025 international games carry the home team's own stadium). `roof_type`: outdoor, dome, retractable |
| `rest_days`, `rest_diff`, `bye_before` (rest ≥ 13), `short_week` (rest ≤ 5) | From nflverse rest days                                                                                                                                                                      |
| `home_venue_key`, `travel_km`                                               | Great-circle distance from the team's main home venue that season                                                                                                                            |
| `tz_shift_hours`, `body_clock_kickoff_hour`, `venue_local_kickoff_hour`     | Offsets at kickoff (daylight saving respected); body clock = kickoff in the team's home time zone                                                                                            |
| `altitude_m`, `altitude_change_m`                                           | Venue elevation (Open-Meteo) and change from home                                                                                                                                            |
| `road_streak`                                                               | Consecutive games away from home (neutral counts), this one included                                                                                                                         |
| `hc_coach`, `off_playcaller`, `def_playcaller` and their `*_tenure_games`   | Consecutive prior games with the franchise. Head-coach tenure is seeded with 1999–2015 nflverse games; play-caller tenure is NULL when the run began before 2016 (left-censored)             |
| `new_off_playcaller`, `new_def_playcaller`                                  | First game with this caller (NULL when censored)                                                                                                                                             |

Week-18 clinch/elimination state moves to MS-034, where the tiebreakers are implemented.

### `rating_snapshots`: MarketScope Ratings, the KenPom contract per team per week (MS-030b)

Written by `ingest ratings` (ADR-035). The Kalman filter is replayed from 2012 with the frozen parameters in `apps/football/src/marketscope_football/ratings/params.json`. A snapshot `(season, week)` is the filtered state **after all games through that week**; week 0 is the preseason prior (after season reversion). It uses only games played by then, plus the published schedule for remaining SOS. A week is published only when every final game in it has play-by-play. PK `(model_version, season, week, team)`, all 32 franchises in every snapshot. Values are model estimates.

| Column                                                            | Definition                                                                                                                                                                                        |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `model_version`                                                   | `kalman-v0` until `ratings-v1` is frozen in MS-032                                                                                                                                                |
| `adj_em`, `adj_em_se`, `adj_em_rank`                              | Expected margin vs an average team on a neutral field, points per game = (AdjO − AdjD) × league drives per team-game + AdjST                                                                      |
| `adj_o`, `adj_d` (+ `_se`, `_rank`)                               | Points per drive scored / allowed vs an average opponent, from the channel units through the game-layer weights. `adj_d` rank 1 = lowest (best)                                                   |
| `adj_st` (+ `_se`, `_rank`)                                       | Special-teams points per game vs average                                                                                                                                                          |
| `adj_pace` (+ `_se`, `_rank`)                                     | Drives per team-game vs an average opponent; rank 1 = most drives                                                                                                                                 |
| `prior_weight`                                                    | ≈ share of the rating still carried by the preseason prior: AdjEM variance now ÷ variance at week 0                                                                                               |
| `pass_off` … `ppd_def`                                            | Unit ratings centred on the league: pass/rush EPA per play, success rate, points per drive. Defense = allowed (negative is good)                                                                  |
| `games`, `wins`, `losses`, `ties`, `points_for`, `points_against` | Season to date, playoffs included                                                                                                                                                                 |
| `expected_wins`                                                   | Σ over games of P(win \| that game's net adjusted EPA, venue), logistic fitted on 2016–22                                                                                                         |
| `pythag_wins`                                                     | games × PF^x ÷ (PF^x + PA^x), x fitted on 2016–22                                                                                                                                                 |
| `luck`, `luck_rank`                                               | wins + ½ ties − expected wins. League luck sums to 0 in every snapshot                                                                                                                            |
| `one_score_luck`                                                  | Σ (result − expected) in games decided by ≤ 8 points                                                                                                                                              |
| `fumble_luck`, `int_luck`                                         | Own minus opponents' turnover luck (EPA, ADR-029); positive = lucky                                                                                                                               |
| `fg_luck`                                                         | 3 × [(own FG made − expected) − (opponents' made − expected)]                                                                                                                                     |
| `return_td_diff`                                                  | Own special-teams return and defensive TDs minus opponents'                                                                                                                                       |
| `sos`, `sos_rank`, `opp_adj_o`, `opp_adj_d`, `nondiv_sos`         | Average **current** AdjEM (AdjO, AdjD) of opponents played. SOS is venue-adjusted: ± the model's home advantage when the game was at the opponent's / own home. NULL before the first game        |
| `remaining_sos`, `remaining_games`                                | The same over remaining regular-season games (NULL when none)                                                                                                                                     |
| `off_*` / `def_*` Five Factors                                    | Season to date, raw: success rate (play-weighted), explosiveness (EPA per successful play), average starting yard line, points per trip inside the 40, turnovers per game (giveaways / takeaways) |
| `computed_at`                                                     | When the row was written. A rebuild rewrites identical history (filtered snapshots don't change when later games arrive)                                                                          |

### `model_runs`: scored evaluation runs (MS-032b)

One row per scored run of a frozen model version, loaded from the committed records in `apps/football/reports/model_runs/` by `ingest model-runs` (ADR-039). A partial unique index allows one `test` run per version.

| Column                                          | Definition                                                                              |
| ----------------------------------------------- | --------------------------------------------------------------------------------------- |
| `model_version`, `run_kind`, `seasons`, `games` | e.g. `ratings-v1`, `test`, `2025`, 285. Kinds: validation, test, forward                |
| `metrics`                                       | Per-model point estimates and 95% CIs, paired differences vs benchmarks, cover log loss |
| `params_sha256`, `code_sha`                     | The frozen parameters and the commit that ran the evaluation                            |
| `ran_at`, `created_at`                          | When the evaluation ran / was loaded                                                    |

### `model_predictions`: the live forward test (MS-032b)

Append-only model estimates made before kickoff by the daily job (`ingest predictions`), one row per upcoming game (next 8 days) per run. Rows are never updated; a CHECK requires `predicted_at < kickoff_utc`. The scorecard uses each game's last row before kickoff. PK `(model_version, game_id, predicted_at)`. Model estimates, never picks.

| Column                                                          | Definition                                                                                        |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `expected_margin`, `expected_total`, `home_score`, `away_score` | Home margin and total (points). Team scores = (total ± margin) / 2                                |
| `p_home`                                                        | P(home win) from the key-number margin distribution (ties count half)                             |
| `home_qb`, `away_qb`, `home_qb_p`, `away_qb_p`                  | Expected starters (gsis id) and the probability each plays (Questionable: 0.64)                   |
| `contributions`                                                 | Additive parts of the margin: `ratings` (unit channels + special teams), `home`, `qb`, `absences` |

### `season_projections`: simulated season odds (MS-034)

Written by the daily job (`ingest projections`), replaced per model version: every team before week 1 (week 0) and after every completed regular-season week of every season since 2016, from the same point-in-time state as `rating_snapshots` (the week matches). 10,000 simulated seasons for the current season, 2,000 for history. PK `(model_version, season, week, team)`; a CHECK keeps the probabilities in [0, 1]. Model estimates, never picks.

| Column                               | Definition                                                                                                                                         |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sims`, `games_played`               | Simulated seasons; regular-season games whose results were fixed (the latest projection also counts final results whose play-by-play isn't in yet) |
| `strength`                           | Points vs an average team on a neutral field used for playoff games (ratings plus the team's current QB term)                                      |
| `mean_wins`, `win_dist`              | Mean regular-season wins; P(exactly k wins), k = 0..17 (JSON array)                                                                                |
| `playoff_p`, `division_p`, `seed1_p` | Made the playoffs, won the division, earned the conference's #1 seed                                                                               |
| `conf_p`, `sb_p`                     | Won the conference (reached the Super Bowl), won the Super Bowl                                                                                    |

### Site accounts: `auth_users`, `auth_sessions`, `auth_accounts`, `auth_verifications`, `auth_rate_limits` (MS-038)

Better Auth's tables (ADR-049), written by the web app and the account CLI (`pnpm --filter @marketscope/web users`). RLS is on, as on every table.

| Table                | Contents                                                                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `auth_users`         | One row per invited person: `email` (unique, lower-cased), `username` (unique, lower-cased) and `display_username` (as typed), `name`, `email_verified` (true for invited accounts). No password here. |
| `auth_accounts`      | How a user signs in. `provider_id = 'credential'` rows hold the salted scrypt `password` hash. OAuth columns are unused.                                                                               |
| `auth_sessions`      | One row per signed-in browser: random `token` (in an httpOnly cookie), `expires_at` (30 days, sliding daily), `ip_address`, `user_agent`. Deleted on sign-out, password reset or `users sign-out`.     |
| `auth_verifications` | Short-lived tokens for flows such as email verification (unused until email is added).                                                                                                                 |
| `auth_rate_limits`   | Request counters per key (IP + path) and window, shared by every serverless instance. Sign-in allows 5 a minute.                                                                                       |

### `nfl_ingest_runs`

The same claim pattern as `ingestion_runs`. `job_key` is unique (`schedules:<seasons>:<UTC date>`, `team-stats:<seasons>:<UTC date>:<data hash>`, `snaps:<seasons>:<UTC date>:<data hash>`, `injuries:<seasons>:<UTC hour>`, `coaching:<csv hash>`, `context:<UTC date>:<hash>`, `weather:<seasons>:<UTC hour>[:recent]`, or a manual key). Also `dataset`, `status`, `attempt` (increments when a failed or stale run is reclaimed), `rows_upserted`, `source_version` (nflreadpy version + dataset SHA-256), and a sanitized `error_message`.
