# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-18 (session 1, continued; MS-031b)._

## Current milestone

**Phase 9 (MarketScope Ratings): MS-029 (harness), MS-030 (Kalman engine), MS-030b (KenPom contract + `rating_snapshots`) MS-031a (QB layer) and MS-031b (non-QB availability) are done. Next: MS-032 (factor selection, probabilities, 2025 test, freeze v1).**

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
- **MS-028** (#27):
  - **Weather:** `nfl_weather_forecasts`, Open-Meteo Previous Runs forecasts at leads 0/1/3/7 days for 2024+, 546 games.
    - Temperature r = 0.98 at 1 day.
    - Wind r = 0.74 at 1 day but 0.34 at 7 days.
  - **Context:** `nfl_game_context` (6,066 team-games): rest, travel, time zones, body clock, altitude, road streaks, coaching tenure.
  - **Venues:** a 49-venue catalog, with overrides for nflverse's mislabelled 2025 international games (ADR-032).
  - Week-18 incentives move to MS-034.
  - Footer now credits Open-Meteo and the injury/snap sources.
- **MS-029** (#28): evaluation harness in `apps/football/src/marketscope_football/eval/` (ADR-033).
  - Walk-forward runner: results removed before `predict`; the runner refuses 2025 unless MS-032's one-time run asks.
  - Pre-registered `eval/design.py`; paired game-bootstrap scoring; ablation runner.
  - 2023–24 margin MAE: close 9.84, Elo 10.33, SRS 10.37, market-implied 10.37, naive 11.16. Elo/SRS trail the close by ≈ 0.5 (paired CI ±0.25).
  - Report: `apps/football/reports/benchmarks.md`; summary in RATINGS.md Results.

- **MS-030** (#29): Kalman unit ratings in `apps/football/src/marketscope_football/ratings/` (ADR-034).
  - One filter per channel: pass, rush, success rate, points per drive (offense/defense + league mean); special teams.
  - ML fit on 2016–22, frozen in `ratings/params.json`; burn-in from 2012 (play-by-play 2012–15 now cached).
  - **2023–24: ties Elo/SRS** (MAE 10.33; paired CIs ±0.2). Better in weeks 1–4 (−0.31 vs SRS). The bar (beat Elo/SRS) is not met by unit ratings alone.
  - Ablations: none of luck/cap/WP weighting/channels/play-caller continuity is distinguishable; the filter beats a half-life ridge (+0.17).
  - Report: `apps/football/reports/kalman-ratings.md`, including current ratings through 2026 week 6.
  - New dependency: scipy 1.16.3.

- **MS-030b** (#30): the KenPom contract (ADR-035).
  - `rating_snapshots` (migration 0012, RLS): AdjEM/AdjO/AdjD/AdjST/AdjPace with SEs and ranks, luck + decomposition, SOS (played, remaining, non-division), Five Factors, prior weight. Every team after every week since 2016 (≈ 7.4k rows); `ingest ratings` rebuilds it daily (Actions cache for play-by-play).
  - A pace filter feeds AdjPace and totals: 2023–24 total MAE 10.22, −0.36 vs naive, +0.26 vs the close.
  - Luck fits: logistic on per-game net adjusted EPA (home term kept: home teams beat their efficiency by ≈ 1.4 pts); Pythagorean exponent 2.79.
  - Classic KenPom agrees with the Kalman ranks: ≈ 0.6 at week 4, ≈ 0.92 at the end of the season.
  - Report: `apps/football/reports/ratings-contract.md`, with the current table and model estimates for next week.

- **MS-031a** (#31): QB layer (ADR-036).
  - Expected starter: previous starter, injury report (Out/Doubtful → depth chart), week-1 depth chart; Questionable plays 64%. Names the actual starter 92% of the time (vs 88%).
  - QB ratings (shrunk, decayed adjusted EPA/dropback; replacement −0.106), team QB baseline, game feature.
  - 2023–24: overall null (Δ −0.00); QB-change games −0.19 (CI −0.53 to +0.16); oracle starter would add 0.08.
  - Play-by-play cache now includes `passer_id` (Actions cache key bumped to `pbp-v2`).

- **MS-031b (this PR):** non-QB availability (ADR-037).
  - Expected absences per group (OL, WR/TE, RB, front 7, DB) = Σ P(miss | report or IR) × recent snap share; OLS positional values (OL −0.72, WR/TE −0.84, front 7 −0.55, DB −0.57; RB −2.41 noisy).
  - **2023–24 model MAE 10.25** (Elo 10.33, SRS 10.37, close 9.84); availability +0.08 (CI −0.00 to +0.17); vs Elo −0.08 and vs SRS −0.12, CIs include 0.
  - Report next-week estimates show QB and absence contributions.

## Tests

- **Football pytest:** 81 (unit tests, plus integration against the migrated test DB; includes validation of the committed coaching CSV).
- **Research pytest:** 25.
- **TS:** db 36, shared 192, collector 51, web 83, e2e 18.

## Quotas

- **Odds API:** about 12 credits/day from the cron (≈ 372 of 500/month).
- **OddsPapi:** 9 of 250. Open-Meteo, Wikipedia and nflverse: free, no keys.

## Data (production, Supabase)

- **Size:** ≈ 75 MB of odds data plus ≈ 20 MB of football tables (team-game stats 3 MB, snaps 9 MB, injuries 3 MB, the rest small).
- **Migrations:** 0007–0012 applied in production.

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
- **Generated reports:** run `pnpm exec prettier --write research/reports apps/football/reports apps/football/src/marketscope_football/ratings/params.json` after regenerating.
- `docs/PERFORMANCE.md` thresholds still apply. GitHub disables crons after 60 days without repo activity.

## Next task

**MS-032: factor selection, probabilities, the 2025 test, freeze `ratings-v1`.**

1. **Factor selection on 2023–24** (pre-register the rule first: keep a factor if its paired Δ MAE or Δ log loss CI excludes 0, or if it is a design-core component that does not hurt). Candidates are the catalog's `test` factors:
   - rest/bye, travel, time zones and body clock, division game
   - venue-specific home field, weather (2024 only), new head coach/play-caller
   - playoffs, RB value shrinkage
2. **Probabilities:** a key-number-aware margin distribution conditional on the expected margin (fit on 1999–2015), giving win probability and cover/total probabilities; reliability curves.
3. **Run the 2025 test once** (`allow_test=True`), logged in a new `model_runs` table.
4. **Parameter-comparison table** vs 538, ELWAY, nfelo and Inpredictable.
5. **Freeze `ratings-v1`;** start immutable pre-kickoff `model_predictions` for 2026 (live forward test).
