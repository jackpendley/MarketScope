# Performance and storage review (MS-023)

Measured 2026-10-17 against production (Supabase free tier, PostgreSQL 17) after the OddsPapi import: **162,590 observations, 14,021 signals, 104 games**. Reproduce with:

```
DATABASE_URL=<production session-pooler URL> pnpm --filter @marketscope/db explain [--json]
```

The tool runs the app's own query functions with representative inputs, captures the exact SQL Drizzle sends, and re-runs each statement under `EXPLAIN (ANALYZE, BUFFERS)` in a **read-only transaction that is rolled back**. Representative inputs: the board's 7-day window, the replay index's ±14-day window, and the game with the most observations for per-game queries. All reads were buffer-cache hits (`read 0`), so the timings are execution cost, not disk.

## Hot queries (before migration 0006)

| Query (caller)                          | Exec       | Rows out | Plan                                                                         | Verdict                                                           |
| --------------------------------------- | ---------- | -------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `listGames` (board, 7 days)             | 0.2 ms     | 14       | Seq scan `events` (104 rows)                                                 | Fine. `events` stays tiny all season.                             |
| `latestQuotesForEvents` (board)         | 18 ms      | 324      | Bitmap scan on `history_idx` (2,592 rows), then sort                         | OK. It sorted because of the NULLS mismatch below; fixed by 0006. |
| `latestCompletedRun`, `recentRuns`      | 0.2 ms     | 1 / 8    | Seq scan `ingestion_runs`                                                    | Fine (about 450 rows by season end).                              |
| `databaseHasSyntheticData` (every page) | 0.06 ms    | 1        | Seq scan `ingestion_runs`                                                    | Fine.                                                             |
| `observationSummaries` (replay index)   | 48 ms      | 54       | Index scan (45,520 rows), incremental sort for `count(DISTINCT observed_at)` | Acceptable. Scales with rows per game in the ±14-day window.      |
| `gameObservationStats` (game page)      | 2.6 ms     | 1        | Index-only scan (3,550 rows)                                                 | Fine.                                                             |
| `selectionHistory` (history page)       | 2.9 ms     | 591      | Bitmap scan on `history_idx`                                                 | Fine.                                                             |
| `eventSignalObservations` (signals job) | 15 ms      | 3,550    | Bitmap scan on `history_idx`                                                 | Fine. Runs per game, offline.                                     |
| `listSignals` (game)                    | 1.9 ms     | 231      | Bitmap scan on `market_signals_event_idx`                                    | Fine.                                                             |
| `listSignals` (Signal Lab, 7 days)      | 5.4 ms     | 300      | Index range scan (708 rows), hash join, **top-N sort**                       | Reads the whole window; fixed by 0006.                            |
| `listSignals` (Signal Lab, 30 days)     | **55 ms**  | 300      | Index range scan (**7,956 rows**), hash join, **top-N sort**                 | Grows with signal volume; fixed by 0006.                          |
| `gameCoverage` (`/data`, first version) | **575 ms** | 103      | Correlated per-game subqueries re-aggregated an inlined CTE once per game    | Rewritten (below).                                                |
| `gameCoverage` (`/data`, rewrite)       | 141 ms     | 103      | One pass over 27K home-spread rows; aggregates joined                        | Acceptable for a low-traffic page; see the threshold below.       |

## After migration 0006 (production, median of 3 runs)

| Query                               | Before                              | After                     | What changed                                                                                 |
| ----------------------------------- | ----------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------- |
| `listSignals` (Signal Lab, 30 days) | 55 ms, 7,956 rows read + top-N sort | **2.1 ms, 300 rows read** | `Index Scan using market_signals_recent_idx` feeds `LIMIT` directly; no sort                 |
| `listSignals` (Signal Lab, 7 days)  | 5.4 ms, 708 rows + sort             | 2.2 ms, 300 rows          | same                                                                                         |
| `latestQuotesForEvents` (board)     | 18 ms, bitmap scan + sort           | 9.7 ms                    | `Index Scan using odds_observations_history_idx` returns rows already in `DISTINCT ON` order |
| `latestCompletedRun`, `recentRuns`  | seq scan                            | index scan                | `ingestion_runs_started_at_idx` now matches                                                  |
| `gameCoverage` (`/data`)            | 575 ms (first version)              | 153 ms                    | query rewrite                                                                                |
| everything else                     |                                     | unchanged within noise    |                                                                                              |

The first run after the index rebuild was cold and up to 2× slower. Shared free-tier hardware also varies by about ±30%, so compare medians, not single runs.

## Ratings pages (MS-033, production, 2026-10-18)

| Query (caller)                   | Exec   | Rows out | Plan                                                                        | Verdict                                                                          |
| -------------------------------- | ------ | -------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `ratingVersion` (ratings pages)  | 8.4 ms | 1        | Seq scan `rating_snapshots` (7,392 rows), group by version                  | Fine: the table grows by 32 rows a week. Revisit if several versions accumulate. |
| `ratingWeeks` (week selector)    | 3.8 ms | 231      | Index-only scan on the primary key                                          | Fine.                                                                            |
| `ratingsForWeek` (ratings table) | 0.3 ms | 32       | Index scan on the primary key `(model_version, season, week, team)`         | Fine.                                                                            |
| `teamRatingHistory` (team page)  | 0.2 ms | 6        | Index scan `rating_snapshots_team_idx`                                      | Fine.                                                                            |
| `teamGames` (team page schedule) | 1.0 ms | 17       | Per-game index lookups for opponent ranks and the last pre-kickoff estimate | Fine.                                                                            |

## Matchups and scorecard (MS-033b, production, 2026-10-18)

| Query (caller)                       | Exec    | Rows out | Plan                                                                                         | Verdict                                               |
| ------------------------------------ | ------- | -------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `matchupWeeks` (week picker)         | 0.4 ms  | 18       | Index-only scans: `model_predictions` primary key, `nfl_games_season_week_idx`               | Fine.                                                 |
| `currentWeek` (default week)         | 0.07 ms | 1        | Index scan `nfl_games_kickoff_idx`, first row                                                | Fine.                                                 |
| `matchupsForWeek` (matchups page)    | 1.9 ms  | 14       | Per-game lookups: snapshot week, both teams' snapshots, last estimate, QB names by `gsis_id` | Fine.                                                 |
| `forwardTest` (scorecard, 2 queries) | 0.6 ms  | 0 / 1    | `DISTINCT ON` over the `model_predictions` primary key, then `nfl_games_pkey`                | Fine; grows by about 16 rows a week (≈ 300 a season). |

## Projections (MS-034, production, 2026-10-19)

| Query (caller)                          | Exec    | Rows out | Plan                                                             | Verdict |
| --------------------------------------- | ------- | -------- | ---------------------------------------------------------------- | ------- |
| `projectionWeeks` (week picker)         | 2.4 ms  | 191      | Index-only scan on the primary key (6,112 rows)                  | Fine.   |
| `projectionsForWeek` (projections page) | 0.3 ms  | 32       | Primary-key scans on `season_projections` and `rating_snapshots` | Fine.   |
| `teamProjectionHistory` (team page)     | 0.07 ms | 6        | Index scan `season_projections_team_idx`                         | Fine.   |

## Findings and fixes

1. **Index null ordering must match the query (migration 0006).**
   - A plain `ORDER BY x DESC` means `DESC NULLS FIRST`. Drizzle's `.desc()` on an index generates `DESC NULLS LAST`.
   - Postgres doesn't treat those as the same ordering, even for a NOT NULL column. So no `DESC` index could satisfy an `ORDER BY` in this codebase.
   - Signal Lab fetched every signal in its window and heap-sorted them to return 300.
   - Fix:
     - Rebuild `odds_observations_history_idx` and `ingestion_runs_started_at_idx` as `DESC NULLS FIRST`.
     - Replace `market_signals_detected_at_idx` with `market_signals_recent_idx (detected_at DESC NULLS FIRST, id)`, matching `listSignals`' tie-breaker.
   - Verified locally: the plan becomes `Limit → Nested Loop → Index Scan using market_signals_recent_idx` with no sort node.
2. **Correlated subqueries over a CTE.** Postgres 12+ inlines a CTE referenced once. Used inside a per-row subquery, it was re-aggregated for every game. The rewrite computes each aggregate once (`per_game`, `per_column`, `signal_counts`) and joins them, cutting the time 4×.
3. **Run health ignored request type (correctness, not speed).** After the import, the newest `completed` run was a historical one. The board's "snapshot collected" label and `/api/health/data` would have stayed green even if the cron died. Both queries now count live runs only (ADR-027).

## Storage

| Table                | Rows    | Heap    | Indexes | Total                 | Per row              |
| -------------------- | ------- | ------- | ------- | --------------------- | -------------------- |
| `odds_observations`  | 162,590 | 21.1 MB | 37.2 MB | 58.3 MB               | ~376 B               |
| `market_signals`     | 14,021  | 4.5 MB  | 0.7 MB  | 5.2 MB                | ~389 B               |
| `ingestion_payloads` | 8       |         |         | 0.1 MB                | ~7.7 KB per live run |
| everything else      |         |         |         | < 0.3 MB              |                      |
| **Database**         |         |         |         | **74.5 MB** of 500 MB |                      |

Index notes:

- The largest index is the per-run unique constraint (18.7 MB): 6 columns, including two UUIDs.
- It's kept because it enforces "one row per selection per run per snapshot", the idempotency guarantee behind retries and imports. `history_idx` is 15 MB.

**Projection to the Super Bowl (2027-02-14, about 120 days).** This is an upper bound, assuming the current live volume continues every day:

| Growth source     | Rate (measured)                                         | By season end                         |
| ----------------- | ------------------------------------------------------- | ------------------------------------- |
| Live observations | 447 rows/run × 4 runs/day = 1,788 rows/day              | ≈ 215K rows ≈ **81 MB**               |
| Live raw payloads | 7.7 KB/run × 4/day                                      | ≈ 4 MB                                |
| Signals           | ~170 per game (imported average) × ~200 remaining games | ≈ 34K rows ≈ 13 MB                    |
| Imports           | none planned: games after 2026-10-16 are collected live | 0                                     |
| **Total**         |                                                         | **≈ 175 MB (≈ 35% of the free tier)** |

The live rate will fall in the playoffs (fewer games on the board), so the real figure should be lower. Adding a full past season through OddsPapi (about 270 games × ~2K rows × 376 B ≈ 200 MB) would still fit, but it's the first thing that would push toward the limit.

## Thresholds to revisit

- **`gameCoverage` > 500 ms:** move per-game coverage into a summary table refreshed after each collection run.
- **`observationSummaries` > 200 ms:** store per-game snapshot counts on `events`, or add a covering index including `is_live`.
- **Database > 350 MB:** drop raw payloads older than 30 days. Observations can be re-derived only while payloads exist, so decide which matters more first.
- **Re-run this review** after any new query on `odds_observations` or `market_signals`, and check every `ORDER BY … DESC` against its index's null ordering.
