# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-18 (session 1, continued; MS-026)._

## Current milestone

**Phase 7 is complete; Phase 8 is underway. MS-026 (football data foundation) is done. Next: MS-027 (play-by-play → team-game stats, snaps, injuries, depth charts, coaching staff, daily workflow).**

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
- **MS-026** (PR #21):
  - Migration 0007: `nfl_teams`, `nfl_games`, `nfl_ingest_runs`, with RLS.
  - New Python app `apps/football`: nflreadpy schedule ingest, idempotent runs, and a linker.
  - Production holds 3,033 games (2016–2026, 2,841 final). **All 104 odds events are linked.**
  - nflverse close vs our last pregame consensus: correlation 0.996, 98.7% within 1 point. The sign convention (store `−spread_line`) is confirmed (`research/reports/close-vs-consensus.md`).
  - `/data` gains a football panel; the footer credits nflverse.
  - CI gains a `football` job (Drizzle migrate, then pytest).

## Tests

- **All green before MS-025:** db 34, shared 192, collector 51, web 83, e2e 18.
- **Research pytest:** 25. **Football pytest:** 10 (unit, plus integration against the migrated test DB). **db:** 36.

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

- **Football schedules are not yet scheduled.** For now, run the ingest by hand after each game day. The daily workflow (`football-data.yml`, existing `DATABASE_URL` secret) is part of MS-027.
- **`nflreadpy.load_injuries` for 2025–26:** still to verify (a 2025 issue reported it broken).
- **Coaching staff** (coordinators, play-callers): no free dataset exists, so this becomes a curated, sourced CSV (MS-027).
- **Market model v2:** re-run once the live forward check has ≥ 15 games.
- **Generated reports:** run `pnpm exec prettier --write research/reports` after regenerating; CI checks formatting.
- `docs/PERFORMANCE.md` thresholds still apply. GitHub disables crons after 60 days without repo activity. TS 7 is still waiting on typescript-eslint (ADR-004).

## Next task

**Phase 8, MS-027: play-by-play → team-game channels, snaps, injuries, depth charts, coaching staff.**

1. Cache play-by-play for 2016–2026 locally as Parquet (gitignored), recording the version and hash.
2. Compute `nfl_team_game_stats` with pure, unit-tested aggregations:
   - EPA per play, per dropback and per rush; success rate; early-down EPA; explosive rate; PROE; CPOE; sack rate; turnovers; red-zone TD rate; neutral pace; special-teams EPA.
   - Raw, neutral and luck-adjusted variants.
   - Cross-check against `load_team_stats`.
3. Add `nfl_player_game_snaps` (current and previous season), `nfl_injury_reports` (daily live snapshots with `fetched_at`), `nfl_depth_charts`, and the curated `nfl_coaching_staff` CSV with a source on every row. Derive P(plays | status, position).
4. Add `football-data.yml`: daily schedules, results and injuries; a Tuesday play-by-play job.

**Then:** MS-028 (Open-Meteo forecasts, stadium coordinates, rest, travel and time-zone context), then Phase 9 (ratings).
