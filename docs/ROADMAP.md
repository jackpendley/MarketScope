# MarketScope Roadmap

The approved implementation plan, distilled from `PRODUCT_SPEC.md`. Phases run in order and each one ends with something demonstrable. There is **no calendar**: we build continuously, and paid services are bought only when a milestone needs them, with explicit approval each time.

Status legend: `[x]` done · `[~]` in progress · `[ ]` not started

## Goals

1. **Product:** "Compare the market. Replay its history. **Understand the matchup.** Investigate the signals. Test the evidence."
   - The odds board for 5 books (DraftKings, FanDuel, BetMGM, Caesars, Hard Rock AZ) is the entry point.
   - Historical replay and evidence-backed signals are the differentiators.
   - **Football context (added 2026-10-17, ADR-028): "KenPom for the NFL".** MarketScope Ratings show adjusted offense, defense, special teams and pace (AdjO, AdjD, AdjST, AdjPace, AdjEM) with uncertainty, luck, strength of schedule and the Five Factors. Alongside them:
     - results
     - market-implied ratings
     - injuries and availability
     - weather, rest and travel
     - coaching and play-callers
     - a weekly Matchups page with predicted scores
     - a labeled, explained model line next to the market
     - a public live scorecard of how the model is doing

     Design: `docs/RATINGS.md`.
2. **Career:** a deployed, tested, documented, data-intensive system that Jack can explain without AI. It should demonstrate:
   - backend and API design
   - relational modeling
   - ingestion and data quality
   - cloud deployment
   - honest ML evaluation
   - multi-source pipelines (Python ↔ Postgres)
   - point-in-time feature engineering
   - state-space (Kalman) rating models
   - walk-forward evaluation and event studies
3. **Integrity:** no fabricated data, no causal claims from correlations, and uncertainty shown in the UI. Model output is always a labeled estimate with its measured error, never a pick.

**Definition of done (portfolio-ready):**

- Deployed, using real permitted data.
- Persistent history, with at least one game replayable.
- Correct exact-line comparisons; honest handling of missing and stale data.
- Observable, cost-controlled ingestion.
- Tests on the business rules, and CI.
- Architecture documented.
- At least one research hypothesis investigated.
- Jack can explain every major design decision.

## Verified provider facts (The Odds API, docs checked 2026-10-15)

| Topic         | Fact                                                                                                                                                                                                            |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Book keys     | `draftkings`, `fanduel`, `betmgm`, `williamhill_us` (Caesars, **paid plans only**), `hardrockbet_az` (us2, **empty for NFL** as of 2026-10-16), plus the fallback `hardrockbet` (us2, multi-state). See ADR-012 |
| Cost          | `/odds` = markets × regions. Named `bookmakers` count as 1 region per 10 books, so our call costs **3 credits**                                                                                                 |
| Free          | `/sports`, `/events`, and any request that returns no events                                                                                                                                                    |
| Quota headers | `x-requests-remaining`, `x-requests-used`, `x-requests-last`                                                                                                                                                    |
| Historical    | `/v4/historical/sports/{sport}/odds?date=`. Costs **10 × markets × regions = 30 credits per snapshot**. Paid only, 5-minute resolution                                                                          |
| Plans         | Free 500/mo · $30 20K · $59 100K                                                                                                                                                                                |
| Timestamps    | Bookmaker-level `last_update` is deprecated. Use market-level `last_update`                                                                                                                                     |
| 429           | No Retry-After header documented. Back off exponentially                                                                                                                                                        |

**Budget:**

- 4 polls/day ≈ 360 credits/month, which fits the free tier with about 140 left for development.
- Hourly history for one NFL week ≈ 5,040 credits.
- A full season at 6-hour resolution ≈ 15K credits, which fits the $30 tier.

---

## Phase 0 — Foundation

- [x] **MS-001 Repository initialization**
  - Delivered: pnpm monorepo, Next.js 16 + TS strict + Tailwind 4, ESLint and Prettier, CI workflow, docs set, `CLAUDE.md`.
  - _Accept:_ a fresh clone passes `install`, `lint`, `typecheck`, and `build`.
- [x] **MS-002 Provider verification**
  - Delivered: collector config (Zod env), Odds API client (retry/backoff, quota headers, key redaction), `pnpm verify:provider` (free checks; the paid call is gated by `--spend`), and a coverage report with no prices.
  - **Live-verified 2026-10-16:** 25 games returned, 3 credits per call. DraftKings and FanDuel complete; BetMGM current week only; Caesars absent (paid-only); Hard Rock AZ empty, so we also collect the multi-state `hardrockbet` feed (ADR-012). See `PROVIDER_COVERAGE.md`.
  - _Accept:_ at least one real NFL game fetched, normalized, and summarized in `PROVIDER_COVERAGE.md`.
- [x] **MS-003 Normalization + first UI**
  - Delivered:
    - Domain types and Zod provider schemas.
    - `normalizeEventOdds` (issues are reported, never repaired).
    - `compareIdenticalMarketPrices`.
    - The synthetic edge-case fixture.
    - `/nfl` renders the fixture with a "synthetic" banner.
    - American odds math (conversions, payout, overround).
  - _Accept:_ all tests green.

## Phase 1 — Persistence + collector (MS-004–006)

**Setup:** `brew install postgresql@17 && brew services start postgresql@17`, then create `marketscope_dev` and `marketscope_test`.

- [x] **MS-004 `packages/db`.** Drizzle + postgres.js, with committed SQL migrations (`drizzle-kit generate` / `migrate`). Tables:
  - `events`: uuid PK, unique `provider_event_id`, sport_key, season, nullable week, home/away, `commence_time_utc`, timestamps. **No stored status**: derive it from `commence_time` until `/scores` is integrated.
  - `bookmakers`: the 5 books, seeded in a migration.
  - `ingestion_runs`: unique `job_key`, provider, request_type, requested/provider snapshot times, started/finished, status enum, credits used/remaining, events/quotes seen, attempt, http_status, duration_ms, error code/message (sanitized).
  - `ingestion_payloads`: run_id → raw jsonb, so normalizer bugs can be fixed by re-deriving instead of re-buying data. Confirm the terms allow storing it.
  - `odds_observations`: bigint identity PK, FKs, market/selection enums, `point numeric(5,1)`, american_price int, bookmaker_updated_at, observed_at, is_live, source.
    - UNIQUE (run, event, book, market, selection).
    - CHECK: h2h ⇔ point IS NULL; selection valid for market; price ∉ (−100, 100).
    - Indexes: `(event_id, market_type, selection, bookmaker_key, observed_at DESC)` and `(ingestion_run_id)`.
- [x] **MS-005 `pnpm collect:nfl`**
  1. **Budget guard:** monthly `sum(credits_used)` plus the estimate must stay ≤ `MONTHLY_CREDIT_BUDGET`, and the last remaining count must stay ≥ `MIN_CREDITS_REMAINING`.
  2. **Claim the run:** `INSERT … ON CONFLICT (job_key) DO NOTHING RETURNING`. The key is `live:nfl:<slot>` when scheduled, `manual:<uuid>` when run by hand.
     - If the key exists: completed → exit with no spend. Failed, or started more than 15 minutes ago → conditional reclaim (attempt+1).
  3. **Fetch** outside any transaction.
  4. **One transaction:** upsert events (update `commence_time` on flex), insert the payload and observations, mark the run completed.
  5. **On error:** record quota headers and a sanitized error in a separate statement.
- [x] **MS-006 Integration tests** against `marketscope_test`: fixture → DB, upsert, same `job_key` twice, rollback on failure, budget refusal. CI gets a `postgres:17` service and a migration-drift check.
  - **Accepted 2026-10-16:** two live runs into `marketscope_dev` produced two distinct sets of 468 observations (25 games, 4 feeds with data), 3 credits each. Re-running the same scheduled slot was a no-op.
  - _Accept:_ two runs, then SQL shows two distinct observation sets.
- [x] **MS-006b Scheduled collection** (2026-10-16): Supabase (Postgres 17, session pooler) is migrated and locked down (ADR-018). `collect-odds.yml` runs 4×/day and `migrate-production.yml` applies migrations on merge (ADR-019). Repo secrets: `DATABASE_URL`, `ODDS_API_KEY`.

## Phase 2 — Read API + Odds Board (MS-007–010)

- [x] Query layer (`packages/db/src/queries/odds.ts`): `listGames`, `getGame`, `latestQuotesForEvents` (`DISTINCT ON`, index-ordered), `gameObservationStats`, `latestCompletedRun`, `recentRuns`. ISO UTC timestamps are formatted in SQL.
- [x] Server components call the query layer directly. `GET /api/games`, `GET /api/games/:id/odds`, and `GET /api/health/data` wrap the same functions (ADR-015, `docs/API.md`).
  - Zod params; strict, bounded; `{ data, meta }` / `{ error }` envelopes; 400, 404, and 503 handling.
- [x] Freshness metadata: collection age vs book update age, labeled `recent` or `snapshot`. Stale-book detection (ADR-016).
- [x] UI:
  - `/nfl`: games grouped by ET date, filters for team, market, kickoff window, and books (GET form, ADR-017).
  - `/nfl/games/[id]`: board, per-feed coverage, history counts.
  - Consensus shown only with ≥ 3 current books.
  - Empty and error states for: DB unavailable, no snapshots, no games, no matches, unknown game.
  - No horizontal page scroll at 390 px.
- [x] Tests: query integration tests (db), API route integration tests and view-model unit tests (web).
- Deferred: shadcn/ui (ADR-017).

## Phase 3 — History + deployment (MS-011–015)

- [x] **MS-011** `GET /api/games/:id/history` (market, selection, books, from/to, resolution, gapMinutes, includeLive). Value-based changes as intervals; explicit gaps; `changes` downsampling keeps every movement (ADR-020).
- [x] **MS-012** `/nfl/games/[id]/history`:
  - Recharts step charts, line and price separate, breaks at gaps, change dots.
  - Toggle legend and crosshair tooltip.
  - Per-book first/last-observed table, change log, data-gap list.
  - Synthetic-data banners across the app (ADR-021).
- [x] **MS-015** Playwright e2e against a synthetic e2e DB, seeded through the real collector. Covers the board, filters, empty and missing-book states, detail, history charts and legend toggles, moneyline price-only view, 404, health, and phone width. Runs in a CI job; the suite was stable over 3 repeats.
- [x] **MS-013** Deployment (2026-10-16): **https://marketscope-delta.vercel.app** (private).
  - Terms reviewed (ADR-022).
  - App-level Basic auth on everything except liveness.
  - Transaction-pooler support and footer disclaimers.
  - Vercel project linked to the repo; runbook in `docs/DEPLOYMENT.md`.
- [x] **MS-014** Scheduled collection: done in MS-006b via GitHub Actions. Lambda + EventBridge stays an optional upgrade.

## Phase 4 — Market Replay (MS-016–017)

- [x] **MS-016** Replay cursor on `/nfl/games/[id]/history`:
  - Steps through actual snapshots (slider, prev/next/latest, keyboard).
  - State-at-T table, one feed per board book.
  - Consensus and dispersion at T.
  - Cursor line on both charts.
  - Movement timeline that jumps the cursor (ADR-023).
- [x] **MS-017** Data-quality correctness:
  - Stale books flagged with their age, never carried forward.
  - "First observed" / "last observed (pregame)" labels.
  - Value-based changes reported as intervals, with "across gap" flags.
  - Key-number crossings (3 and 7; crossed, landed-on, left; sign-safe).
  - `GET /api/games/:id/movements`; `/replay` index of games with history; Market Replay in the nav.

## Phase 5 — Signal Lab + first study (MS-018–021)

- [x] **MS-018/019/020** Signals A–F as pure, versioned functions (`computeSignals`):
  - Stored in `market_signals` with evidence observation ids.
  - Idempotent recompute after every scheduled collection.
  - `/signals` lab with filters, definitions, and replay deep links; game-page signals; `/api/signals`.
  - Documented in `docs/SIGNAL_DEFINITIONS.md` and ADR-024.
- [x] **MS-021** First study (`research/`, Python):
  - Pre-registered design; point-in-time `book_divergence` onsets; outcome = consensus 18–30 h later moved toward / away / not at all.
  - Chance baseline; game-clustered bootstrap CI; Python consensus cross-checked against stored signals.
  - **v1 result (2026-10-17): inconclusive.** 9 scored events from 5 games, below the pre-registered 30/15 minimum. Cross-check 13/13.
  - Re-run as history accumulates (`research/reports/outlier-convergence-v1.md`).
  - 2026-10-17 re-run with OddsPapi history: **conclusive**. 476 events from 83 games; toward-rate 29.0% vs a 10.3% chance baseline. Exploratory check: 63% of consensus moves went toward the book (CI 58.5–68.6%).

## Phase 6 — Historical data expansion

- [x] **Paid-data decision gate:** replaced by **OddsPapi**: free line-move history since Jan 2026, evaluated and validated 2026-10-17 (PROVIDER_COVERAGE.md).
- [x] **MS-022 Historical import** (`import:oddspapi`, ADR-026):
  - Completed pre-live games, stored as derived 6-hourly plus near-close snapshots.
  - One idempotent run per fixture; refuses games collected live (no mixed sources).
  - BetMGM excluded; Pinnacle stored as a reference book; no raw payloads.
- [x] **MS-023** Coverage, performance, storage (`docs/PERFORMANCE.md`, ADR-027):
  - `/data` page: live collection health, history by source, per-game × per-book spread coverage.
  - `pnpm --filter @marketscope/db explain`: EXPLAIN ANALYZE of the app's own queries, read-only.
  - Migration 0006: sort-matching `DESC NULLS FIRST` indexes (Signal Lab `LIMIT` stops early).
  - Fix: run-health queries count live runs only. Storage projection: about 35% of the free tier by the Super Bowl.

## Phase 7 — Market ML baseline (MS-024–025)

Market-only first, so Phase 10 can measure what football features add. Lives in `research/src/marketscope_research/ml/`.

- [x] **MS-024** Targets, gate, feature table. **Gate passed 2026-10-18**: 79 games, 292 positives; test week 5 has 15 games and 79 positives. Leakage audit clean (`research/reports/market-ml-gate-v1.md`).
  - **Primary target:** |consensus(t+24h) − consensus(t)| ≥ 0.5, using the nearest snapshot within ±3 h. If none exists, the label is missing. Board books only, at least 3.
  - **Secondary target:** direction, given a move.
  - **Gate,** pre-registered before results: ≥ 60 games, ≥ 150 positives, ≥ 15 test games. Otherwise exploratory only.
  - **Features:** dispersion, movement, volatility, quote age, key-number proximity, active divergence, Pinnacle − board (with a missingness flag), totals movement.
  - **Leakage audit:** a planted leaky feature must fail it.
  - **Split:** chronological and grouped by game.
- [x] **MS-025** Baselines and model card. **v1 result (2026-10-18):** logistic regression ranks moves (test AUC 0.72, CI 0.57–0.86) but its Brier and log-loss gains over the constant baseline are not yet distinguishable (the CIs include 0). Direction shows no skill. See `docs/MODEL_CARD.md` and `research/reports/market-baseline-v1.md`; re-run as v2 once the live forward check reaches 15 games.
  - Models: majority, empirical rate, volatility heuristic, logistic regression, and an outlier-direction rule.
  - Metrics: Brier, log loss, reliability, precision/recall, each with a game-clustered CI, broken out by time-to-kickoff window.
  - `docs/MODEL_CARD.md`.

## Phase 8 — Football data foundation (MS-026–028)

New Python app `apps/football/` (nflreadpy, polars, psycopg). The schema stays in Drizzle. Raw play-by-play stays in a gitignored Parquet cache; only aggregates go to Postgres.

- [x] **MS-026** (2026-10-18; 3,033 games for 2016–2026 in production; 104 of 104 odds events linked; nflverse close vs our consensus: correlation 0.996, 98.7% within 1 point) Migration 0007:
  - Tables: `nfl_teams`, `nfl_games` (results, venue, observed weather, referee, coaches, home-oriented nflverse close), `nfl_ingest_runs`.
  - Linker from odds `events` to games.
  - Seasons 2016–2026.
  - Data-quality check: the nflverse close vs our last-pregame consensus, which also confirms the sign convention.
- [x] **MS-027** Data tables:
  - [x] Team-game efficiency channels: raw, neutral and luck-adjusted variants (`nfl_team_game_stats`, 5,682 team-games 2016–2026, ADR-029). Counts match nflverse team stats 100%; EPA r = 0.996 when aligned.
  - [x] Snaps (`nfl_player_game_snaps`) and injuries (`nfl_injury_reports`, live history twice daily from 2026-10-18, ADR-030); depth charts stay in nflverse (read directly by MS-031).
  - [x] Curated `nfl_coaching_staff` with play-callers and sources: 1,473 spans 2016–2026, validated per team-week; nflverse head coaches found stale for 2024+ interims (ADR-031).
  - [x] P(plays | status, position): Out 0%, Doubtful 0.9%, Questionable 68% (2016–22); the practice-status gradient weakened in 2023–25 (`reports/plays-given-status.md`).
  - [x] `football-data.yml`, using the existing secret (daily: schedules/results/links + team stats).
- [x] **MS-028** Weather and context:
  - [x] Open-Meteo point-in-time forecasts (`nfl_weather_forecasts`, 2024+, leads 0/1/3/7 days). Wind skill fades by 7 days (r 0.74 → 0.34), so wind uses short leads only (ADR-032).
  - [x] Rest, travel, time zones, body clock, altitude, road streaks, coaching tenure (`nfl_game_context`), from a 49-venue catalog with overrides for nflverse's mislabelled 2025 international games.
  - Week-18 clinch/elimination state moved to MS-034 (needs tiebreakers).

## Phase 9 — MarketScope Ratings (MS-029–034)

- [x] **MS-029** Evaluation harness:
  - Walk-forward runner, clustered CIs, ablations.
  - Benchmarks: naive, SRS, Elo, market-implied ratings.
  - 2023–24 margin MAE: close 9.84, Elo 10.33, SRS 10.37, market-implied 10.37, naive 11.16 (ADR-033, `apps/football/reports/benchmarks.md`).
- [x] **MS-030** Kalman unit ratings (engine and evaluation):
  - Channel filters (pass, rush, success rate, points per drive, special teams), ML fit on 2016–22, game layer, ablations.
  - 2023–24: ties Elo/SRS (10.33); better in weeks 1–4; bar not met by unit ratings alone (ADR-034).
- [x] **MS-030b** KenPom contract outputs (ADR-035):
  - AdjO, AdjD, AdjST, AdjPace, AdjEM, each with a standard error.
  - Luck and its decomposition, SOS, Five Factors.
  - `kenpom_classic` benchmark.
  - Point-in-time `rating_snapshots` for 2016–26.
  - Totals from pace × points per drive (2023–24: −0.36 vs naive, +0.26 vs the close).
- [x] **MS-031a** QB layer (ADR-036):
  - Point-in-time expected starter (92% accurate), shrunk QB ratings, team QB baseline, P(plays | Questionable).
  - Oracle vs expected starter quantified. 2023–24: overall null; QB-change games −0.19 (CI includes 0).
- [x] **MS-031b** Non-QB availability (ADR-037):
  - Snap-share-weighted absences by position group × learned values, expected value over P(plays | status).
  - 2023–24: model MAE 10.25 (Elo 10.33, SRS 10.37, close 9.84); availability +0.08 (borderline).
- [x] **MS-032a** Factor selection and probabilities (ADR-038):
  - Pre-registered rule; none of 10 candidates kept; RB absence dropped.
  - Key-number margin distribution adopted.
  - Against the close the model's cover probabilities are worse than a coin flip.
- [x] **MS-032b** Freeze `ratings-v1`, 2025 test (once), parameter comparison, live `model_predictions` (ADR-039):
  - 2025: MAE 10.06 (Elo 10.19, SRS 10.19, close 9.67); vs Elo −0.13 (CI includes 0), vs close +0.39.
- [x] **MS-033a** Ratings UI (ADR-040):
  - `/ratings` (KenPom table, week time machine, sortable ranks, conference filter), `/teams/[abbr]` (ratings, trend, Five Factors, luck, schedule with model estimates, staff), `/api/ratings`.
  - Synthetic ratings seed for e2e; EXPLAIN review.
- [x] **MS-033b** Matchups, scorecard and game panel (ADR-041):
  - `/matchups` (FanMatch analog: model scores, win probability, contribution waterfall, expected QBs, consensus or close, quality and excitement), `/model` (live forward test vs results and the close, 2025 test record), the game-page model panel, `/api/matchups`, `/api/model`.
- [x] **MS-034** Season simulation (ADR-042):
  - Posterior strength draws + weekly drift, key-number games, NFL tiebreakers through SOS (reproduce every 2016–24 playoff field), bracket.
  - `season_projections` for every week since 2016; `/projections`, team-page season outlook, `/api/projections`.
  - Backtest 2016–24: better than coin flips on playoffs/division/#1 seed/wins (CIs exclude 0), calibrated; no Super Bowl skill.

## Phase 10 — Research studies + ML with football features (MS-035–036)

- [ ] **MS-035** Pre-registered studies (`research/PREREGISTRATION.md`, ADR-043/044).
  - **035a done:** R1, R3, R4 and R5 in `research/reports/football-studies-v1.md`. No primary claim was met; R3 was one windy game short of its gate.
  - **035b done:**
    - R6 (the blend is worse than the close) and R7 (no play-caller continuity effect once the QB is held fixed), under addendum A.
    - The `/research` page.
  - **035c done:**
    - Coaching-data audit (ADR-045). R6 and R7 re-run on the corrected data, both unchanged.
    - Historical injury studies R2h (no claim) and R2w (claim met: about 0.4 pts per newly-out starter), ADR-046.
  - **Remaining:** the live R2 and the R3 re-run, once their gates are met.
  - R1: market accuracy over time.
  - R2: injury-news event study.
  - R3: weather → totals.
  - R4: is performance priced?
  - R5: luck regression.
  - R6: model + market blend.
  - R7: play-caller impact.
- [x] **MS-036** Re-run the Phase 7 pipeline with football features (ADR-047, `research/reports/market-football-v1.md`). No lift on will-it-move, and worse on direction (overfit on a 32-game training set). Forward check pending.

## Phase 11 — Portfolio release (MS-037+)

- [x] **MS-037** Portfolio release (ADR-048):
  - Architecture diagram and schema overview (ARCHITECTURE.md).
  - Screenshots from the synthetic database (`docs/screenshots/`).
  - Accessibility pass: axe-core WCAG 2.1 AA on every page in CI, contrast and link fixes, a skip link (ACCESSIBILITY.md).
  - Secret audit: clean (SECURITY.md).
  - README rewrite and case study (CASE_STUDY.md).

---

## Post-release projects

- [x] **MS-038** Invite-only accounts (ADR-049). Better Auth (username or email + password), a login page, `/account` (change password), the account CLI, a rate-limited and CSRF-guarded sign-in. Replaces the shared Basic-auth password.
- [x] **MS-039** ratings-v2 (QB-keyed offensive reversion, ADR-050). Pre-registered, tested and **not adopted**: the likelihood was 38.4 vs 38.6, and the 2023–24 changes were within noise. ratings-v1 stays.
- [x] **MS-040** ML Lab page (`/ml-lab`): the market-movement experiments, their verdicts and the model's main features.
- [x] **MS-040** Chart text alternatives for screen readers (line history, rating trend). A live VoiceOver walkthrough is still to do.

---

## Phase 12 — Sharp-Market Lab (MS-041+, ADR-051)

The goal is to study the market for moves that indicate sharp betting, learn from them, and test whether any signals or systems are profitable. CLV is the yardstick.

- [x] **MS-041** Data-source evaluation (`docs/DATA_SOURCES.md`). OddsPapi's free history has Pinnacle, Circa, Bookmaker.eu and the exchanges at minute level, with limits (tested). Paid options are costed; licensed splits come from Sportradar (quote) or SharpAPI (terms to confirm).
- [x] **MS-042** Line-move event store (`line_moves`), minute-level for sharp and retail books, every 2026 game, with a nightly job. Storage is measured first.
- [ ] **MS-043** Sharp-market study, pre-registered: lead-lag, steam, stale retail lines, limits and key numbers, each scored by CLV. New versioned signals.
  - [x] Pre-registration (Addenda C, D), study code, discovery run on weeks 1–6 (ADR-053): S1, S2 and S3 met as discovery claims.
  - [ ] Confirmation run on weeks 7–14 (after 2026-12-16), then signals only for what holds.
- [x] **MS-044** System backtester and Wong teasers (2016–25 nflverse closes, plus 2026 from our lines). Primary: no claim at −125 (ADR-054); `/systems`.
- [x] **MS-045a** System catalogue F1–F10 (pre-registered; 0 of 10 supported; ADR-055).
- [x] **MS-045** Paper portfolio (immutable pre-kickoff paper positions, graded, with CLV; `/portfolio`; ADR-056).
- [ ] **MS-046** Machine learning on minute-level market state (pre-registered, Addenda G and H).
  - [x] Discovery, walk-forward on weeks 3–6 (ADR-057): G1 Pinnacle direction, no claim (worse than baseline); G2 retail value, no claim (break-even). Price-aware re-score of S2: −2.0%.
  - [ ] Confirmation on weeks 7–14, with MS-043's (after 2026-12-16).
- [ ] **MS-047** Injury news and the line (pre-registered, Addendum I).
  - [x] Discovery, weeks 2–6 (ADR-058): I1 no claim (the official report window holds almost none of the move; about two-thirds is priced four days out); I2 inconclusive (18 cases, gate 50).
  - [ ] Confirmation on weeks 7–14 (after 2026-12-16).
- [ ] **MS-048** (needs a near-real-time feed: OddsPapi permission or a paid plan) Live collector and alerts; live paper positions for market-signal strategies.
- [ ] **MS-049** (needs licensed splits) Reverse line movement.
- [ ] **MS-050** Openers and totals, price-aware (pre-registered, Addendum J).
  - [x] Discovery, weeks 1–6 (ADR-059): J1 openers no claim (21 cases); J2 stale totals −1.8% (below 0); J3 better-than-Pinnacle totals −3.0%.
  - [ ] Confirmation on weeks 7–14 (after 2026-12-16).
- [ ] **MS-051** Exchanges, price-aware with fees (pre-registered, Addenda K and L).
  - [x] Exchange import (Novig, ProphetX, Kalshi spreads and totals; 217k rows, about 46 MB) and discovery, weeks 1–6 (ADR-060): K1 stale exchange prices −1.2% after fees (below 0); K2 −3.0%. Novig +0.4% (exploratory), registered as K1n.
  - [ ] Confirmation on weeks 7–14 (after 2026-12-16).
- [x] **Phase 12 write-up:** `docs/CASE_STUDY.md` and the README updated with the market findings; screenshots refreshed.

---

## Approval checkpoints

**Standing approvals (2026-10-16):**

- Claude merges its own PRs once CI is green.
- Claude spends Odds API credits within the collector's guards (`MONTHLY_CREDIT_BUDGET=400`, `MIN_CREDITS_REMAINING=25`).

**Still ask before:**

- Adding repo secrets.
- Creating any cloud resource.
- Buying any paid plan or raising the credit budget.
- Opening the site (a sign-up page or no login).

Managed DB: **Supabase**, used as Postgres only (ADR-018). Its session-pooler URL is stored locally as `SUPABASE_DATABASE_URL` in `apps/collector/.env.local`, and in GitHub as the `DATABASE_URL` secret.

## Concepts (Claude implements; explains these in milestone summaries)

Jack doesn't write code for the project. These are the ideas he should be able to explain in interviews, and each milestone summary should cover the relevant ones:

- American odds, implied probability, and overround: Phase 0
- Normalization at the boundary; why team orientation comes from event metadata: Phase 0
- The run claim/retry state machine and idempotency keys: Phase 1
- `bookmaker_updated_at` vs `observed_at` vs `provider_snapshot_at`: Phase 1
- Transactions, constraints, and indexes on an append-only table: Phase 1
- `DISTINCT ON` for latest-quote-per-book: Phase 2
- `LAG()` window functions for line movement: Phase 4
- Data leakage and chronological, game-grouped splits: Phase 7
- Point-in-time joins; filtered vs smoothed estimates (Kalman): Phases 8–9
- Opponent adjustment (classic KenPom iteration vs state-space filter): Phase 9
- Walk-forward evaluation, ablations, and why the closing line is the benchmark: Phase 9
- Event studies (injury news, weather): Phase 10

## Phase 13 — Real value on NFL spreads, totals and moneylines (MS-052+, ADR-061)

**Goal:** test the sources of main-line value that sharp bettors actually use, on better fair prices. Phase 12 tested whether following Pinnacle pays, which it doesn't, with tight intervals. Phase 13 tests:

- being early on information;
- a model that predicts the move from the open;
- one market mis-priced against another: moneyline versus spread, alternate lines and teasers.

The phase is NFL only and free first. A criteria-based gate decides whether paid history is worth buying.

- [x] **MS-052** Research data lake (ADR-061, ADR-064): full spread, total and moneyline ladders for 10 books and exchanges as Parquet (DuckDB), streamed with no size limit, rebuilt on demand from free history. 93 games and 37.3 million entries in 151 MB; matches `line_moves` at 100% (Kalshi 99.93%).
- [x] **MS-053** Fair-value engine v2 (ADR-062): kernel margin model (−0.13 log loss; the total turned out not to help), kernel total model (−0.09), Shin devig; frozen parameters in `fair_value_params.json`.
- [ ] **MS-054** Cross-market value: moneyline against the book's own spread; same-line retail prices against the consensus fair price.
  - [x] Discovery (ADR-064):
    - A: −4.9%, the opposite of the hypothesis.
    - B: +3.6% as registered, but weakened by ghost markets and engine tails. After corrections it is +2.2% (−0.1 to +4.3) direct-scored, so inconclusive.
  - [ ] Confirmation on weeks 7–14, counting only prices our own collector also saw (Addendum S).
- [ ] **MS-055** Alternate lines and model-based teasers ("Wong 2.0").
  - [x] MS-055a model-priced teaser legs (ADR-063): 74.5% on 2023–25, break-even, no claim; `wong-model` paper strategy.
  - [x] MS-055b alternate ladders (ADR-064): +4.3% as registered, withdrawn as an engine-tail artifact. Against the sharp books' own same-line prices it is −3.6%. Confirmation on weeks 7–14 under Addendum R.
- [ ] **MS-056** Information timing (Addendum U, ADR-068): weather-forecast revisions from archived Open-Meteo runs, as event studies.
  - [x] Discovery: inconclusive (2 games with events); Pinnacle shows no detectable reaction to ECMWF wind revisions (908 runs).
  - [ ] Confirmation on weeks 7–18 (after week 18).
  - Injury half not registered: no free source with minute-level publication times (a paid-data case).
- [ ] **MS-057** Does the market move toward the MarketScope model from the open?
  - [x] Discovery (ADR-063): slope +0.116 (+0.048 to +0.189), a discovery claim; early-line value −1.0%, no claim.
  - [ ] Confirmation on weeks 7–14; then the paid-data decision.
- [x] **MS-058** Ghost markets in the collector (ADR-065): near-even and flat-pair rules checked against our own The Odds API snapshots; corrections in `line_move_fixes` (backfilled), shown on the replay page; `line_moves` unchanged for the registered studies.
- [ ] **Future pre-registrations confirm on weeks 7–18** (plus playoffs where the question allows): about 55% more games than weeks 7–14, at no cost. Registered confirmations keep weeks 7–14.
- [x] **MS-059** Fair-value engine v3 (ADR-066): logit-scale line conversion fitted to the sharp books' own alternate prices (outcome-free); adopted for spreads (KL −19%) and totals (−46%), moneylines stay v2; v3 secondaries in the MS-054/055b/057 confirmation reports.
- [ ] **Paid-data gate:** buy The Odds API history ($119, one month) only if MS-057 or MS-054 B shows a positive estimate too uncertain to decide on one season.

## Phase 14 — Evidence, reproducibility and operations (ADR-067+)

Prompted by an external review (of commit `7a62f87`), reconciled against the local state on 2026-10-22. Ordered by dependency; each item has acceptance criteria in the plan recorded in `docs/PROJECT_STATUS.md`.

- [x] **Timestamps and reconstruction** (ADR-067): instants, not text; zone required; per-outcome order asserted; ties kept in provider order. Measured impact on existing data: none.
- [x] **Evaluation boundaries** (Addenda V and W, ADR-069): frozen-first subsets, week-block bootstrap, declared confirmation family with a Holm sensitivity, and MS-057's shared-line check (a market baseline and permutation nulls).
- [x] **Dataset identity and reproducible runs** (ADR-070; dataset `lake-2d40bfbafd04b8f2`; durable private copy still needs approval): lake manifest v2 (schema and transform versions, file and catalog hashes, coverage), dataset ID independent of build time, atomic resumable builds, run records per report, peak-memory measurement, and a snapshot/restore command. Durable private copy: needs approval (a Supabase Storage bucket).
- [x] **Generated results** (ADR-072): five cards (C1, C2, A1, M3, F1) read runner output; the older cards move over when their runners next run.
- [ ] **Operations:**
  - [x] partial imports marked `partial` and retryable; gap-based freshness per dataset in `/api/health/data` (ADR-071);
  - [ ] backup and restore of the serving database demonstrated;
  - [ ] streaming JSON in the TypeScript importer, so `--retry-partial` can succeed.
- [ ] **One complete ML workflow:** ratings-v1 with a versioned dataset, feature schema, reloadable artifact, prediction provenance, and a generated model card.
- [x] **Data and service gap analysis** in `docs/DATA_SOURCES.md` (no purchases).
- [ ] **Reviewer documentation:** README, case study and architecture around three stories, plus a synthetic walkthrough.

## Out of scope until the core works

Props, alternate lines, live betting, bet placement, other leagues, betting splits, CLV tracking, and alerts. (Sharp-book references are done: Pinnacle is a reference book since MS-022.) See spec §5 "Future releases".

One cheap future option: the 10-book region group has 5 free slots, so a sharp reference book could be added at zero extra credit cost.
