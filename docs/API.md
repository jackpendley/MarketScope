# HTTP API

Next.js route handlers in `apps/web/app/api`. All data comes from MarketScope's own PostgreSQL database. **The browser never calls the odds provider.**

## Conventions

- Success: `{ "data": …, "meta": { "generatedAt": ISO, … } }`
- Error: `{ "error": { "code", "message", "details"? } }`, with codes `INVALID_PARAMETERS` (400), `NOT_FOUND` (404), `DATA_SOURCE_UNAVAILABLE` (503), and `INTERNAL_ERROR` (500).
- Timestamps are ISO 8601 UTC (`…Z`).
- Query parameters are validated with Zod (`apps/web/lib/params.ts`). Unknown parameters are rejected, not ignored.
- Results are always bounded (max 100 games; windows up to 31 days).
- Odds are **periodic snapshots**, never presented as live.

## `GET /api/games`

NFL games in a kickoff window, each with feed coverage from its latest snapshot.

| Param   | Default                                     | Rules                                        |
| ------- | ------------------------------------------- | -------------------------------------------- |
| `from`  | now − 4 h (keeps in-progress games visible) | ISO datetime                                 |
| `to`    | now + 7 days                                | ISO datetime, after `from`, window ≤ 31 days |
| `limit` | 50                                          | 1–100                                        |

Each game includes `id`, teams, `commenceTime`, `season`, `week` (nullable), `started`, and `coverage: { latestObservedAt, feedsInLatestSnapshot[], feedsMissing[] }`.

## `GET /api/games/:id/odds`

The latest observed quote for each (book, market, selection), for one game.

- `data.quotes[]`: `bookmakerKey`, `market`, `selection`, `point` (null for moneylines), `americanPrice`, `isLive`, `observedAt`, `bookmakerUpdatedAt`, plus `freshness`:
  - `collectionAgeMinutes`: how long ago **we** collected it.
  - `bookUpdateAgeMinutes`: how long ago the **book** reported an update (nullable).
  - `label`: `recent` within `QUOTE_FRESHNESS_MINUTES` (default 15), otherwise `snapshot`.
  - `stale`: the book was absent from the game's newest snapshot, so this is its last-seen quote.
- `data.consensus`: either `{ homePoint, bookmakerKeys }`, the median home spread across ≥ 3 current pregame books, or `{ homePoint: null, reason }`.
- `meta.coverage`: same shape as in `/api/games`.
- 400 if `id` isn't a UUID; 404 if the game is unknown.

## `GET /api/games/:id/history`

Per-book time series for one selection of one game.

| Param         | Default                                 | Rules                                                                                                          |
| ------------- | --------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `market`      | `spreads`                               | `h2h`, `spreads`, `totals`                                                                                     |
| `selection`   | `HOME` (spreads, h2h) / `OVER` (totals) | must be valid for the market. Spreads are the chosen team's line as posted; HOME is the consistent orientation |
| `books`       | all                                     | comma-separated feed keys                                                                                      |
| `from`, `to`  | all history                             | ISO datetimes                                                                                                  |
| `resolution`  | `changes`                               | `changes` keeps first, last, every change, and both edges of every gap; `all` returns every observation        |
| `gapMinutes`  | 720                                     | 30–10080. Consecutive observations further apart than this are a gap                                           |
| `includeLive` | `false`                                 | in-play observations are excluded by default                                                                   |

`data.series[]`, one per feed:

- `observations`, `firstObservedAt`, `lastObservedAt`.
- `points[]`: `observedAt`, `point`, `americanPrice`, `kinds` (`first`, `change`, `gap-start`, `gap-end`, `last`, `observation`).
- `changes[]`: `type` (`point`/`price`/`both`), `intervalStart`, `intervalEnd`, from/to point and price, `pointDelta`, `acrossGap`.
- `gaps[]`: `from`, `to`, `minutes`.

Changes are detected by **value**, and each one happened somewhere in `(intervalStart, intervalEnd]`.

`meta` includes `observations`, `truncated` (capped at 20,000 rows), `sources` (`"synthetic"` marks demo data), and `orientation`.

## `GET /api/games/:id/movements`

Detected movements for one selection, oldest first.

| Param        | Default         | Rules                           |
| ------------ | --------------- | ------------------------------- |
| `market`     | `spreads`       | `spreads`, `totals`, `h2h`      |
| `selection`  | `HOME` / `OVER` | must match the market           |
| `pointsOnly` | `false`         | `true` drops price-only changes |

Each movement has the `LineChange` fields from `/history` (interval, from/to point and price, `pointDelta`, `acrossGap`), plus:

- `direction`: `toward-home`, `toward-away` (home orientation), `total-up`, `total-down`, or `price-only`.
- `keyNumbers[]`: `{ key, signedKey, kind: crossed | landed-on | left }`.
- `displayName`.

## `GET /api/signals`

Stored signal detections (definitions: `docs/SIGNAL_DEFINITIONS.md`), newest first.

| Param         | Default           | Rules                                                                                                                               |
| ------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `type`        | all               | comma-separated: `line_move`, `price_move`, `key_number`, `book_divergence`, `rapid_consensus_move`, `same_line_price_disagreement` |
| `from` / `to` | last 7 days / now | ISO datetimes on `detectedAt`                                                                                                       |
| `event`       | all               | game UUID                                                                                                                           |
| `limit`       | 200               | 1–500                                                                                                                               |

Rows include:

- `type`, `version`, `market`, `selection`, `bookmakerKey`
- `detectedAt`, `windowStart`, `windowEnd`, `value`, `details`
- `evidence`: observation ids
- game teams and kickoff

`meta.definitions` carries every definition and its limitations. `meta.disclaimer` states that signals are not betting advice.

## `GET /api/ratings`

MarketScope Ratings for one weekly snapshot, best AdjEM first (definitions: `docs/RATINGS.md`, `docs/DATA_DICTIONARY.md` → `rating_snapshots`).

| Param    | Default                    | Rules                                                                                     |
| -------- | -------------------------- | ----------------------------------------------------------------------------------------- |
| `season` | latest                     | a season with snapshots; otherwise the latest                                             |
| `week`   | latest week of that season | 0 = preseason prior; a week without a snapshot falls back to the season's latest snapshot |

Rows carry the KenPom contract: AdjEM/AdjO/AdjD/AdjST/AdjPace with SEs and ranks, record, expected and Pythagorean wins, luck and its decomposition, SOS, and the Five Factors. `meta` gives `modelVersion` (`ratings-v1`; a synthetic demo database shows `synthetic-demo`), `season`, `week` and a disclaimer. Values are point-in-time model estimates, not betting advice. 404 `NOT_FOUND` before any ratings exist.

## `GET /api/matchups`

One week's games with pre-game MarketScope Ratings and the last model estimate stored before kickoff (`docs/DATA_DICTIONARY.md` → `model_predictions`).

| Param    | Default                             | Rules                                                                 |
| -------- | ----------------------------------- | --------------------------------------------------------------------- |
| `season` | the next week with an unplayed game | a season from the first forward-test season on; otherwise the default |
| `week`   | that week                           | a week without games falls back to the default week, then the latest  |

Each row: game identity and kickoff, franchise abbreviations and names, final score (null until final), linked odds `eventId`, the nflverse close (home orientation, a labeled benchmark), each team's AdjEM and rank from the last snapshot before the game, and `estimate` (null when none was stored): expected margin and total, team scores, home win probability, expected QBs by name with their probability of playing, and the additive margin `contributions` (`ratings`, `home`, `qb`, `absences`). `meta` gives `modelVersion`, `season`, `week` and a disclaimer.

## `GET /api/model`

The live forward-test scorecard and the committed evaluation records. `data.scorecard`: games scored; margin MAE, win-probability Brier (the close's from no-vig moneylines) and total MAE for the model and the close, with the paired difference and a 95% game-bootstrap interval from 30 games; the share of games the model favorite won; a per-week table; calibration bins from 50 games. `data.games` lists every scored game, `data.pending` counts estimated games not yet final, and `data.runs` holds the `model_runs` records (the one-time 2025 test first). 404 `NOT_FOUND` before any model output exists.

## `GET /api/projections`

Simulated season odds for every team after one week, best playoff odds first (`docs/DATA_DICTIONARY.md` → `season_projections`). Params `season` and `week` as for `/api/ratings`. Rows: team, names, `sims`, `gamesPlayed`, `strength`, `meanWins`, `winDist` (18 probabilities), `playoffP`, `divisionP`, `seed1P`, `confP`, `sbP`, plus the same week's record and AdjEM. `meta` gives `modelVersion`, `season`, `week`, `sims` and a disclaimer. 404 `NOT_FOUND` before any projections exist.

## `GET /api/health/live`

Liveness only: `{ "status": "ok" }` without touching the database. Used by the Playwright web-server check and suitable for process supervisors. Readiness and data health live in `/api/health/data`.

## `GET /api/health/data`

Ingestion health, with no credentials or infrastructure details.

- `status`: `ok`, `behind` (no completed **live** run in 12 h), or `no-data`. Historical imports are excluded (ADR-027).
- `latestCompletedRun`: `startedAt`, `ageMinutes`, counts, `creditsRemaining`, `issueCounts`.
- `recentRuns[]`: status, start time, and error code for the last 10 runs.
