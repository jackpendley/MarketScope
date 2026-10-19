# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-18 (session 1, continued; MS-035c)._

## Current milestone

**Phase 9 (MarketScope Ratings): MS-029 (harness), MS-030 (Kalman engine), MS-030b (KenPom contract + `rating_snapshots`) MS-031a (QB layer) and MS-031b (non-QB availability) are done. MS-032a (factor selection, probabilities), MS-032b (ratings-v1 frozen, 2025 test, live forward test), MS-033a (ratings and team pages), MS-033b (matchups, scorecard, game panel) and MS-034 (season simulation) are done: Phase 9 is complete. Phase 10: MS-035a (pre-registration + studies R1, R3, R4, R5) and MS-035b (R6, R7, `/research`) are done; R2 and the R3 re-run wait for their gates. Next: MS-036 (market ML with football features).**

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

- **MS-031b** (#32): non-QB availability (ADR-037).
  - Expected absences per group (OL, WR/TE, RB, front 7, DB) = Σ P(miss | report or IR) × recent snap share; OLS positional values (OL −0.72, WR/TE −0.84, front 7 −0.55, DB −0.57; RB −2.41 noisy).
  - **2023–24 model MAE 10.25** (Elo 10.33, SRS 10.37, close 9.84); availability +0.08 (CI −0.00 to +0.17); vs Elo −0.08 and vs SRS −0.12, CIs include 0.
  - Report next-week estimates show QB and absence contributions.

- **MS-032a** (#33, rebase-merged to keep the pre-registration commits): factor selection and probabilities (ADR-038; rules pre-registered in separate commits).
  - None of 10 candidates kept (rest, bye, travel, time zones, body clock, altitude, division, playoffs, new HC, new play-caller); RB absence dropped.
  - Key-number margin distribution adopted (3 → 2.9×, 7 → 2.0×, ties 0.04×).
  - The model's cover probabilities vs the close are worse than a coin flip (no information against the market).

- **MS-032b** (#34, rebase-merged; #35 docs): ratings-v1 (ADR-039).
  - Frozen: params sha256 `c2f6ed74…` pinned and test-guarded.
  - **2025 test (once): MAE 10.06** (Elo 10.19, SRS 10.19, market-implied 10.30, close 9.67); vs Elo −0.13 (CI −0.42 to +0.17); vs close +0.39 (CI +0.07 to +0.70). Cover probabilities vs the close worse than a coin flip.
  - `model_runs` + `model_predictions` (migration 0013); daily `ingest predictions` (append-only, before kickoff) and `ingest model-runs`.
  - Parameter-comparison table in RATINGS.md.

- **MS-033a** (#36): ratings UI (ADR-040).
  - `/ratings`: KenPom table with week time machine, sortable ranks, AFC/NFC filter, ± SE, diverging rank shading.
  - `/teams/[abbr]`: ratings header, AdjEM trend with SE band, Five Factors with ranks, luck decomposition, schedule (opponent ranks then/now, last pre-kickoff model estimate), coaching staff.
  - `/api/ratings`; `queries/ratings.ts` with integration tests; synthetic ratings seed (`synthetic-demo`) and e2e tests; EXPLAIN on production (< 10 ms each).

- **MS-033b** (#37): matchups, scorecard and game panel (ADR-041).
  - `/matchups`: a week's games (default: the next week with an unplayed game) with model scores, win probability, a contribution waterfall (ratings, home, QB, absences), expected QBs, the board consensus (or the nflverse close once final), and quality/excitement scores.
  - `/model`: the live forward test (last pre-kickoff estimate vs result and close: margin MAE, Brier, total MAE, paired bootstrap CIs from 30 games, weekly table, calibration from 50) and the 2025 test record from `model_runs`.
  - Game pages: a model panel for the linked football game. `/api/matchups`, `/api/model`; `queries/model.ts` with integration tests; nav adds Matchups.
  - Forward test so far: 18 estimates, 0 scored (it began with today's week-6 late games).

- **MS-034** (#38): season simulation (ADR-042).
  - `ratings/simulate.py` (pure: posterior strength draws with full covariance + weekly drift, key-number games, NFL tiebreakers through SOS then coin flip, bracket with re-seeding) and `ratings/project.py` (point-in-time inputs from the running model; next week = full model estimate; final-week rest for clinched #1 seeds).
  - Game noise 12.64 (fitted 13.05 minus rating-error variance 10.55 pts², 2016–22) in `ratings/simulation.json`.
  - Tiebreakers reproduce every 2016–24 playoff field and Wild Card matchup (fixture `tests/fixtures/results_2016_2024.csv`).
  - Backtest 2016–24 (`reports/season-sim.md`): vs home-field coin flips, Brier playoffs −0.0077, division −0.018, #1 seed −0.005, wins MAE −0.22 (all CIs exclude 0); calibrated (70–80% → 69%); Super Bowl no skill; rating uncertainty ≈ no effect on scores.
  - `season_projections` (migration 0014, RLS), daily `ingest projections` (every week since 2016; 10k sims current season, 2k history); `/projections`, team-page season outlook (win distribution, odds by week), `/api/projections`; nav adds Projections.

- **MS-035a** (#39, rebase-merged; #40 fixed the SHA references): research studies (ADR-043).
  - `research/PREREGISTRATION.md` (R1–R7) committed and pushed before any study code.
  - `football_studies.py` + `run_football_studies.py` → `research/reports/football-studies-v1.md`:
    - **R1:** consensus 6 days out as accurate as the close (+0.03, −0.26 to +0.28; 77 games); no book beats the consensus.
    - **R3:** inconclusive (29 of the 30 windy games the gate needs); the market lowers totals ≈ 0.19 pts per mph.
    - **R4:** ratings carry no information beyond the close (claim not met; 2023–24 slope −0.11). Exploratory: 2026 consensus moves toward the ratings (+0.10 per pt of gap).
    - **R5:** market does not overrate lucky teams; luck does not persist.

- **MS-035b (#41, rebase-merged so the addendum stays first):** R6, R7 and the `/research` page (ADR-044).
  - **Addendum A** to `research/PREREGISTRATION.md` (145a5de on `main`; first pushed as 9314b78 in PR #41), committed before any R6 or R7 code. It fixes:
    - R6's weight rule: the Brier-optimal weight on the previous 4 week slots, model weight capped at 0.60.
    - R7's measure: observed points per drive, because filtered ratings already embed play-caller continuity in their reversion.
    - The continuity definitions.
  - **R6** (`apps/football/.../ratings/blend.py`, `run_blend.py` → `research/reports/r6-model-market-blend.md`, 570 games, 2023–24 walk-forward, frozen params):
    - Result: the blend is **worse** than the close, Δ Brier +0.0026 (+0.0006 to +0.0047).
    - The weight was 0 in 30 of 44 weeks.
    - A fixed 35% model weight was also worse. nfelo's gain does not replicate.
  - **R7** (`football_studies.py`, `run_playcaller_study.py` → `research/reports/r7-play-caller.md`, 256 pairs):
    - Play-caller: no continuity effect once the QB is held fixed, +0.02 (−0.22 to +0.25).
    - QB continuity matters: +0.33 (+0.04 to +0.61).
    - Defence: no effect.
    - Scheme: 19 movers, nothing clear.
    - Implication: ratings-v1's play-caller-keyed reversion probably proxies QB changes. That is a candidate for a future version.
  - **`/research`:** a static page from `lib/research-studies.ts`, with numbers copied from the reports and unit-tested for consistency. The nav link is enabled, plus e2e and mobile checks.

- **MS-035c, part 1 (#43): coaching-data audit (ADR-045).** Prompted by Jack's spot checks.
  - **Week-by-week coordinator audit:** `coaching_audit.py` compares each game with Wikipedia staff-template revision history. It found 13 missing mid-season coordinator changes (e.g. 2025 NYJ Wilks → Harris; 2017 OAK, 2018 ARI/MIN/TB, 2019 LAC, 2020 ATL/LV/NYJ, 2022 CAR/IND, 2024 NYJ, 2025 NYG). It now reports 0 unexplained (`reports/coaching-audit.md`).
  - **Defensive head coaches checked one by one:** 21 sourced overrides: Allen (NO 2022–24), Eberflus (CHI 2024), Quinn (ATL 2016 from week 13), Ryans (HOU 2025 weeks 1–3), Kuhr (NE 2025 from week 2), Ulbrich (NYJ 2024), Patricia (DET 2019), Saleh (TEN), Minter (BAL), Hafley (MIA 2026).
    - Verified correct: Flores (MIN), Payton taking over from Webb in DEN week 5 2026, Ryans taking over in HOU in October 2026, and Glenn (NYJ 2026).
  - **New basis `shared`:** BUF 2016 and 2025, DET 2019, ATL 2020. Team pages now show "calls defense (assumed)" for rule-only rows and "(shared)" for split calling.
  - **Effect:** defensive rule-only weeks drop from 90% to 86%. On 2023–24, margins move 0.05 pts on average; MAE goes from 10.268 to 10.259. R6 is unchanged (+0.0026).

- **MS-035c, part 2 (this PR, rebase-merged so addendum B stays first): historical injury studies (ADR-046).**
  - **Addendum B** (f431f0a on the branch), committed before any code.
  - **R2h** (`ratings/injury_priced.py`, `run_injury_priced.py`; 2016–24 walk-forward, 2,367 games): ATS residual per point of the model's availability adjustment is +0.11 (−0.27 to +0.50), so no claim. The close has priced injuries by kickoff.
  - **R2w** (`football_studies.injury_events`/`r2w`, `run_injury_moves.py`; 2026 weeks 1–6, 77 games, 80 events): the consensus moved **+0.40 pts toward the opponent per newly-out starter** (+0.14 to +0.73). **Claim met**, the first in MS-035. Non-QB only: +0.30 (added after the result, labelled). Only 5 QB events.
  - **R7 re-run** on the corrected production staff: unchanged (+0.02, −0.23 to +0.25; QB +0.33).
  - **`/research`** now lists 9 studies (R2h and R2w added).

## Tests

- **Football pytest:** 110 (unit tests, plus integration against the migrated test DB; includes validation of the committed coaching CSV and the 2016–24 seeding reproduction).
- **Research pytest:** 36.
- **TS:** db 47, shared 192, collector 51, web 108, e2e 37.

## Quotas

- **Odds API:** about 12 credits/day from the cron (≈ 372 of 500/month).
- **OddsPapi:** 9 of 250. Open-Meteo, Wikipedia and nflverse: free, no keys.

## Data (production, Supabase)

- **Size:** ≈ 75 MB of odds data plus ≈ 20 MB of football tables (team-game stats 3 MB, snaps 9 MB, injuries 3 MB, the rest small).
- **Migrations:** 0007–0014 applied in production (0014 applies on merge).

## Waiting on Jack

Nothing blocking.

## Known issues / open decisions

- **nflverse quirks found:**
  - stale head coaches for 2024+ interims and the 2026 season
  - 2025 international venues labelled with the home team's stadium
  - typos (e.g. "Jay Rosburg")

  The pipeline works around all three (ADR-031/032).

- **Defensive play-callers** are mostly the coordinator default (90% of team-weeks), so treat defensive-caller findings as provisional. This includes R7's defence result.
- **Research page upkeep:** `/research` is static; update `apps/web/lib/research-studies.ts` whenever a study is re-run (R2, R3).
- **Live injury history** begins 2026-10-18 (Week 6). Earlier weeks are final reports only.
- **Market model v2:** re-run once the live forward check has ≥ 15 games.
- **Generated reports:** run `pnpm exec prettier --write research/reports apps/football/reports apps/football/src/marketscope_football/ratings/params.json` after regenerating.
- `docs/PERFORMANCE.md` thresholds still apply. GitHub disables crons after 60 days without repo activity.

## Next task

**MS-036: market ML with football features.**

1. **Pre-register first:** the feature list, gate and comparison, before any computation, following the MS-024 pattern.
2. **Re-run the Phase 7 pipeline** (`research/src/marketscope_research/ml/`, target: |Δ consensus over 24 h| ≥ 0.5) with football features added:
   - model margin − consensus, and Δ model margin over 24 h (point in time)
   - newly-out starters since the last snapshot (R2w shows the market moves about 0.4 pts per event, so this is the most promising feature)
   - Δ forecast wind or precipitation
   - rest and travel
3. **Report the lift over the market-only baseline**, with game-clustered CIs and an ablation by feature family. Check the leakage audit covers the new features.
4. **Gates to check weekly:** the live R2 (30 events, from 2026-10-18 snapshots) and R3 (30 games with wind of at least 15 mph).
