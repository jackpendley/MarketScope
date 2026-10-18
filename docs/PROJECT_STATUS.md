# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-17 (session 1, continued)._

## Current milestone

**Phases 0–6 are complete. Next: Phase 7 (ML baseline).** The site is deployed privately at https://marketscope-delta.vercel.app (user `marketscope`; the password is `VERCEL_SITE_PASSWORD` in `apps/web/.env.local`).

## Done so far

- **Phase 0:** monorepo, CI, Odds API client, normalizer, odds math, exact-line comparison, Hard Rock fallback (ADR-012).
- **Phase 1:** Postgres schema with DB-enforced invariants; idempotent, budget-guarded collector (ADR-013).
- **Phase 2:** read API (`docs/API.md`), plus the `/nfl` board and game pages (ADR-015–017).
- **Phase 3:**
  - Supabase production DB, locked down (ADR-018); collection 4×/day plus migrate-on-merge (ADR-019).
  - History charts (ADR-020); synthetic demo data (ADR-021).
  - Private Vercel deploy behind Basic auth (ADR-022); Playwright e2e.
- **Phase 4:** market replay with state at T, a movement timeline, and `/replay` (ADR-023).
- **Phase 5:** six versioned signals, `/signals` (ADR-024). The research package (ADR-025) holds the outlier study, now **conclusive**:
  - 29.0% toward-rate vs a 10.3% chance baseline, from 83 games.
  - 63% of consensus moves went toward the outlier (exploratory check).
- **MS-022:** free OddsPapi backfill of 79 Weeks 1–6 games as derived snapshots (ADR-026).
- **MS-023 (2026-10-17):**
  - **`/data` page:** collection health, history by source, per-game × per-book coverage.
  - **EXPLAIN tool:** `pnpm --filter @marketscope/db explain`.
  - **Migration 0006:** sort-matching indexes; Signal Lab 30-day went from 55 ms to 2 ms.
  - **Bug fix:** run health counts live runs only. The import had been making the board label and `/api/health/data` show the import time.
  - **`docs/PERFORMANCE.md`:** plans, fixes, storage projection, and revisit thresholds (ADR-027).

## Tests

All green: db 34, shared 192, collector 51, web 83, e2e 18, research 13 (pytest). lint, typecheck, build, and migration-drift check pass.

## Quotas

- **Odds API:** about 12 credits/day from the cron (≈372 of 500/month). Avoid local `collect:nfl` runs.
- **OddsPapi:** 9 of 250 billable requests used this month. History calls are free.

## Data (production, Supabase)

- **Size:** 74.5 MB of 500 MB. Projected ≈ 175 MB by the Super Bowl, as an upper bound (`docs/PERFORMANCE.md`).
- **Observations:** 159K from `oddspapi` (79 games, kickoffs Sep 10 → Oct 13); live `the-odds-api` from 2026-10-16 onward (about 1,800 rows/day).
- No game has more than one source.

## Waiting on Jack

Nothing blocking. Optional: mark the GitGuardian false-positive incident as resolved.

## Known issues / open decisions

- **Phase 7 data gate:** decide thresholds from current data before modelling (games, positive labels per class). The study's 476 scored events from 83 games suggests a modest but workable sample.
- **Revisit thresholds** are in `docs/PERFORMANCE.md`. The main one: `gameCoverage` > 500 ms means moving it to a summary table.
- GitHub disables scheduled workflows after 60 days without repo activity.
- Revisit TS 7 when typescript-eslint supports it (ADR-004).

## Next task

**Phase 7, MS-024: ML data gate and feature table.**

1. Define the prediction target. Candidate: "the consensus home spread moves ≥ 0.5 pts in the next 24 h", from the point-in-time consensus series.
2. Count eligible snapshots and positives per game. Document the gate thresholds; if the data falls short, publish exploratory analysis only.
3. Build a point-in-time feature table (SQL/pandas in `research/`): dispersion, divergence state, recent moves, time to kickoff, key-number proximity. Include a leakage audit.
4. Use chronological, game-grouped splits.

**Then MS-025:** baselines (majority, empirical frequency, volatility heuristic, logistic regression); Brier, log loss, calibration, game-clustered CIs; `docs/MODEL_CARD.md`.
