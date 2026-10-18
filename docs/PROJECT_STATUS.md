# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-17 (session 1, continued)._

## Current milestone

**Phases 0–5 and MS-022 (historical import) are complete.** The site is deployed privately at https://marketscope-delta.vercel.app (user `marketscope`; the password is `VERCEL_SITE_PASSWORD` in `apps/web/.env.local`).

**Next:** MS-023 (coverage dashboard, query and storage review), then the Phase 7 ML baseline. The data gate now looks reachable.

## Done so far

- **Phase 0:** monorepo, CI, Odds API client, normalizer, odds math, exact-line comparison, Hard Rock fallback (ADR-012).
- **Phase 1:** Postgres schema with DB-enforced invariants; idempotent, budget-guarded collector (ADR-013).
- **Phase 2:** read API (`docs/API.md`), plus the `/nfl` board and game pages (ADR-015–017).
- **Phase 3:**
  - Supabase production DB, locked down (ADR-018); collection 4×/day plus migrate-on-merge (ADR-019).
  - History charts (ADR-020); synthetic demo data (ADR-021).
  - Private Vercel deploy behind Basic auth (ADR-022); Playwright e2e.
- **Phase 4:** market replay with state at T, a movement timeline, and `/replay` (ADR-023).
- **Phase 5:** six versioned signals, `/signals`, `/api/signals` (ADR-024); Python research package with pytest in CI (ADR-025).
- **MS-022 (2026-10-17), OddsPapi backfill (ADR-026):**
  - **Import:** `import:oddspapi` turns free line-move history into derived 6-hourly plus near-close snapshots.
  - **Scope:** one idempotent run per fixture; games collected live are refused, so no game mixes sources.
  - **Books:** BetMGM excluded; Pinnacle stored as a reference book outside consensus.
  - **Schema:** migration 0005 adds `observed_at` to the per-run unique constraint.
  - **Production:** 79 games (Weeks 1–6) imported with 0 failures; 159K observations and 13.7K signals.
- **Study re-run (2026-10-17):** conclusive.
  - 476 scored events from 83 games; the consensus moved toward the diverging book in 29.0% of events (CI 24.7–33.2%) vs a 10.3% chance baseline.
  - Exploratory check (not pre-registered): 63.3% of consensus moves went toward the book (CI 58.5–68.6%), consistent across DK, FD, Caesars, and Hard Rock.
  - Python cross-check: 571/571.
  - See `research/reports/outlier-convergence-v1.md` for limitations (derived snapshots, source imbalance).

## Tests

All green: db 31, shared 192, collector 51, web 73, e2e 17, research 13 (pytest). lint, typecheck, build, and migration-drift check pass.

## Quotas

- **Odds API:** about 12 credits/day from the cron (≈372 of 500/month). Avoid local `collect:nfl` runs.
- **OddsPapi:** 9 of 250 billable requests used this month. History calls are free (5 s cooldown).

## Data (production, Supabase)

- **Size:** 74 MB of the 500 MB free tier. `odds_observations` is 58 MB.
- **Observations:** 159,014 from `oddspapi` (79 games, 2026-08-11 → 2026-10-15 kickoffs); 3,576 from `the-odds-api` (live, 25 games, from 2026-10-16).
- No game has more than one source.

## Waiting on Jack

Nothing blocking. Optional: mark the GitGuardian false-positive incident as resolved.

## Known issues / open decisions

- **Re-import cadence:** completed games that kicked off after 2026-10-16 are covered by live collection, so no re-import is needed. A new importer version would use job key `v2`.
- **Storage growth:** about 2K rows per game per week live; imported games add about 2K rows each. Review in MS-023.
- GitHub disables scheduled workflows after 60 days without repo activity.
- Revisit TS 7 when typescript-eslint supports it (ADR-004).

## Next task

**MS-023:**

- A coverage view: games × books × sources, snapshots per game.
- `EXPLAIN ANALYZE` on the hot queries (board, history, signals) against production volume.
- A storage projection to season end.

**Then Phase 7:** the ML gate (thresholds from this data), a point-in-time feature table, and chronological splits.
