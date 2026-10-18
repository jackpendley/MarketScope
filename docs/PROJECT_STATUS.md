# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-18 (session 1, continued)._

## Current milestone

**Phase 7 (market ML baseline) is complete. Next: Phase 8, MS-026 (football data foundation).**

- **Scope extended 2026-10-17 (ADR-028):** football context and MarketScope Ratings, "KenPom for the NFL". The design is frozen in `docs/RATINGS.md`.
- **Site:** deployed privately at https://marketscope-delta.vercel.app (user `marketscope`; the password is `VERCEL_SITE_PASSWORD` in `apps/web/.env.local`).

## Done so far

- **Phases 0–6:**
  - board, persistence and collector
  - API and UI
  - Supabase and Vercel deployment, history charts, replay
  - signals and the outlier study (conclusive: 29.0% toward-rate vs a 10.3% chance baseline)
  - OddsPapi backfill (79 games, Weeks 1–5)
  - `/data` coverage page, EXPLAIN review, sort-matching indexes

  ADRs 001–027.

- **Plan (PR #18, ADR-028):**
  - ROADMAP Phases 7–11.
  - CLAUDE.md football rules 1–8.
  - `docs/RATINGS.md`: prior-art review (538, ELWAY, nfelo, FPI, DVOA, KenPom, Inpredictable, Glickman–Stern), the KenPom output contract, factor catalog (including coaching and play-callers), Kalman architecture, validation protocol.
- **MS-024** (PR #19): target, split and gate, pre-registered and committed before any label was computed.
  - 22 point-in-time features.
  - Mechanical leakage audit: perturb everything after t; a planted leak is caught.
  - **Gate passed:** 79 games, 292 positives; test week 5 has 15 games and 79 positives.
  - The positive rate rises by week (9% → 23%).
- **MS-025:** model protocol pre-registered before fitting.
  - Baselines plus logistic regression; game-clustered bootstrap CIs; `docs/MODEL_CARD.md`.
  - **v1 result:** logistic regression _ranks_ moves (test AUC 0.72, CI 0.57–0.86), but its Brier and log-loss gains are not yet distinguishable from the constant baseline (the CIs include 0).
  - Direction: no skill.
  - Live forward check: pending at 13 of 15 games.

## Tests

- **All green before MS-025:** db 34, shared 192, collector 51, web 83, e2e 18.
- **Research pytest:** 24 (20 at MS-024; 4 more in MS-025).

## Quotas

- **Odds API:** about 12 credits/day from the cron (≈ 372 of 500/month). Avoid local `collect:nfl` runs.
- **OddsPapi:** 9 of 250 billable requests used this month. History calls are free.

## Data (production, Supabase)

- **Size:** 74.5 MB of 500 MB. Projected ≈ 175 MB by the Super Bowl, before football data. ADR-028 estimates 30–40 MB more.
- **Observations:** 159K from `oddspapi` (79 games, Sep 10 → Oct 13), plus live `the-odds-api` since 2026-10-16.
- No game has more than one source.
- GitHub cron runs fire 2–4 h late. That's normal, and inside the 12 h health threshold.

## Waiting on Jack

Nothing blocking. Optional: mark the GitGuardian false-positive incident as resolved.

## Known issues / open decisions

- **Phase 8 first-contact checks:**
  - `nflreadpy.load_injuries` for 2025–26 (a 2025 issue reported it broken).
  - The sign of nflverse `spread_line`, checked against our consensus.
  - Python ↔ Drizzle schema ownership in CI (migrate the test DB before football pytest).
- **Coaching staff:** coordinators and play-callers have no free dataset, so this becomes a curated, sourced CSV (MS-027).
- **Market model v2:** re-run when the forward check has ≥ 15 live games. Consider rolling-origin evaluation once there are more weeks.
- **Generated reports:** run `pnpm exec prettier --write research/reports` after regenerating (CI checks formatting).
- `docs/PERFORMANCE.md` thresholds. GitHub disables crons after 60 days without repo activity. TS 7 is still waiting on typescript-eslint (ADR-004).

## Next task

**Phase 8, MS-026: schema, schedules/results, linking** (new Python app `apps/football/`).

1. Scaffold `apps/football`: pyproject, pinned requirements (nflreadpy, polars, pyarrow, psycopg, numpy, scipy, scikit-learn, httpx, pytest), gitignored Parquet cache, CI job.
2. Migration 0007 (Drizzle, RLS):
   - `nfl_teams` (name mapping, stadium lat/lon, roof, surface, altitude, time zone)
   - `nfl_games` (results, venue, observed weather, referee, coaches, home-oriented nflverse close, `event_id` FK)
   - `nfl_ingest_runs` (job-key claims)
3. Ingest 2016–2026 schedules. Link odds `events` to games (teams + kickoff ±36 h); show unmatched rows on `/data`.
4. Data-quality report: nflverse close vs our last-pregame consensus. Confirm the sign; record the result in PROVIDER_COVERAGE.

**Then:** MS-027 (play-by-play → team-game channels, snaps, injuries, depth charts, coaching staff, `football-data.yml`), MS-028 (weather and context).
