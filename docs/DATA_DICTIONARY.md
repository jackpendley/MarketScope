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
