# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-18 (session 1, continued; MS-028)._

## Current milestone

**Phase 8 (football data foundation) is complete: MS-026, MS-027 and MS-028 are done. Next: Phase 9, MS-029 (evaluation harness + benchmarks).**

- **Scope extended 2026-10-17 (ADR-028):** football context and MarketScope Ratings, "KenPom for the NFL". The design is frozen in `docs/RATINGS.md`.
- **Site:** deployed privately at https://marketscope-delta.vercel.app (user `marketscope`; the password is `VERCEL_SITE_PASSWORD` in `apps/web/.env.local`).

## Done so far

- **Phases 0–6:**
  - board, collector, API/UI, Supabase/Vercel, replay
  - signals and the outlier study
  - OddsPapi backfill, `/data`, EXPLAIN review

  ADRs 001–027.

- **Phase 7 (MS-024/025):**
  - Market-movement ML: pre-registered gate, leakage audit, baselines plus logistic regression.
  - v1: test AUC 0.72, but the Brier and log-loss gains are not yet distinguishable from the constant. Direction: no skill.
  - Results in `docs/MODEL_CARD.md`.
- **MS-026** (PRs #21/#22):
  - `nfl_teams`, `nfl_games`, `nfl_ingest_runs`; 3,033 games 2016–2026; all odds events linked.
  - nflverse close vs our consensus: r = 0.996, so it serves as the benchmark for 2016–25.
- **MS-027:**
  - **#23, team-game stats:**
    - Play-by-play Parquet cache with a manifest.
    - `nfl_team_game_stats`: 5,682 team-games, raw EPA plus the model channel (luck-adjusted, capped, WP-weighted EPA), Five Factors, pace/PROE, drives, special teams (ADR-029).
    - Counts match nflverse team stats 100%; EPA r = 0.996.
  - **#25, availability:**
    - `nfl_player_game_snaps` and `nfl_injury_reports`, a point-in-time history. Live rows have been captured twice daily since 2026-10-18 (ADR-030).
    - P(plays | status): Out 0%, Doubtful 0.9%, Questionable 68%. The practice-status gradient weakened in 2023–25.
  - **#26, coaching:**
    - `nfl_coaching_staff`: 1,473 sourced, validated spans; exactly one HC, offensive and defensive play-caller per team-week (ADR-031).
    - **nflverse head coaches are stale for 2024+ interims and the 2026 season.**
    - Offensive play-callers are sourced for 69% of team-weeks, defensive for 10%.
  - **Daily `football-data.yml`:** 13:00 UTC runs everything; 23:00 UTC runs injuries only. Uses the existing `DATABASE_URL` secret.
- **MS-028 (this PR):**
  - **Weather:** `nfl_weather_forecasts`, Open-Meteo Previous Runs forecasts at leads 0/1/3/7 days for 2024+, 546 games.
    - Temperature r = 0.98 at 1 day.
    - Wind r = 0.74 at 1 day but 0.34 at 7 days.
  - **Context:** `nfl_game_context` (6,066 team-games): rest, travel, time zones, body clock, altitude, road streaks, coaching tenure.
  - **Venues:** a 49-venue catalog, with overrides for nflverse's mislabelled 2025 international games (ADR-032).
  - Week-18 incentives move to MS-034.
  - Footer now credits Open-Meteo and the injury/snap sources.

## Tests

- **Football pytest:** 45 (unit tests, plus integration against the migrated test DB; includes validation of the committed coaching CSV).
- **Research pytest:** 25.
- **TS:** db 36, shared 192, collector 51, web 83, e2e 18.

## Quotas

- **Odds API:** about 12 credits/day from the cron (≈ 372 of 500/month).
- **OddsPapi:** 9 of 250. Open-Meteo, Wikipedia and nflverse: free, no keys.

## Data (production, Supabase)

- **Size:** ≈ 75 MB of odds data plus ≈ 20 MB of football tables (team-game stats 3 MB, snaps 9 MB, injuries 3 MB, the rest small).
- **Migrations:** 0007–0010 applied in production; 0011 (weather/context) is applied on merge by `migrate-production.yml`.
- **After merging this PR:**
  - `ingest context` (all seasons)
  - `ingest weather --seasons 2024-2026` (about 4 minutes)

## Waiting on Jack

Nothing blocking.

## Known issues / open decisions

- **nflverse quirks found:**
  - stale head coaches for 2024+ interims and the 2026 season
  - 2025 international venues labelled with the home team's stadium
  - typos (e.g. "Jay Rosburg")

  The pipeline works around all three (ADR-031/032).

- **Defensive play-callers** are mostly the coordinator default (90% of team-weeks), so treat defensive-caller findings as provisional.
- **Live injury history** begins 2026-10-18 (Week 6). Earlier weeks are final reports only.
- **Market model v2:** re-run once the live forward check has ≥ 15 games.
- **Generated reports:** run `pnpm exec prettier --write research/reports apps/football/reports` after regenerating.
- `docs/PERFORMANCE.md` thresholds still apply. GitHub disables crons after 60 days without repo activity.

## Next task

**Phase 9, MS-029: evaluation harness and benchmarks** (`apps/football/src/marketscope_football/eval/`).

1. **Walk-forward runner:** for each week, fit on data before that week and predict that week. Metrics: margin MAE/RMSE, win-probability Brier and log loss, with game-clustered bootstrap CIs (reuse the research bootstrap pattern). Plus an ablation runner and a report generator.
2. **Benchmarks:** naive home-field; SRS (ridge on margins, refit weekly); 538-style Elo (k, home field, margin-of-victory multiplier, season reversion); market-implied ratings (weighted least squares on nflverse close spreads); and the nflverse close itself.
3. **Sanity check:** Elo/SRS margin MAE ≈ 10–11 and the close ≈ 9.5–10 on 2023–24. First result: a benchmark table for 2023–24 (validation). 2025 stays untouched until MS-032.

**Then:** MS-030, the Kalman unit ratings in the KenPom output contract.
