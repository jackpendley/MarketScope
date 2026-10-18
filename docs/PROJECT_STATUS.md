# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-16 (session 1, continued)._

## Current milestone

**Phase 5 is complete (Signal Lab + first study). Deployed privately at https://marketscope-delta.vercel.app (user `marketscope`, password in `apps/web/.env.local` as `VERCEL_SITE_PASSWORD`). Next: Phase 6 decision (paid historical data?) or keep accumulating real history.**

## Done so far

- **Phase 0:** monorepo, CI, Odds API client and verification, normalizer, odds math, exact-line comparison, Hard Rock fallback (ADR-012).
- **Phase 1:** Postgres schema with DB-enforced invariants; idempotent, budget-guarded collector (ADR-013).
- **Phase 2:** read API (`docs/API.md`), Postgres-backed `/nfl` board and `/nfl/games/[id]` (ADR-015–017).
- **MS-006b:**
  - Supabase migrated (4 migrations) and locked down: RLS on every table, `anon`/`authenticated` privileges revoked (ADR-018). REST reads and writes with the publishable key verified as 401.
  - `createDb` requires TLS for remote hosts.
  - `collect-odds.yml` runs 4×/day; `migrate-production.yml` runs on merge (ADR-019).
  - First Supabase run: 25 games, 468 quotes.
- Supabase agent skills installed at `.claude/skills/` (reviewed: markdown only).
- **MS-011/012:**
  - `GET /api/games/:id/history` with value-based changes as intervals, explicit gaps, and change-preserving downsampling.
  - `/nfl/games/[id]/history` with stepped Recharts line and price charts (palette validated for the dark theme), a change log, and gap lists (ADR-020).
  - Deterministic synthetic history through the real collector, guarded to demo/e2e DBs, with banners everywhere (ADR-021).
  - Local `marketscope_demo` is seeded with 18 synthetic snapshots for UI work.
- **MS-021 research study:**
  - `research/` (Python) with a pre-registered outlier → consensus-convergence study.
  - **v1 result: inconclusive** (9 events from 5 games; minimum 30/15). Python consensus cross-check 13/13.
  - Pytest in CI (ADR-025).
- **Phase 5 (MS-018–020):**
  - Six versioned signals with evidence ids in `market_signals`.
  - `signals:compute` after each scheduled collection.
  - `/signals` lab, game-page signals, `/api/signals`, replay deep links (`?at=`).
  - `docs/SIGNAL_DEFINITIONS.md`, ADR-024.
- **Phase 4 (MS-016/017):**
  - Replay cursor over snapshots, state at T with stale and no-data states, consensus and dispersion at T, cursor line on charts.
  - Movement timeline with direction and key-number badges.
  - `/api/games/:id/movements` and the `/replay` index (ADR-023).
- **MS-013:**
  - Odds API terms reviewed (ADR-022).
  - Basic-auth proxy that fails closed on Vercel.
  - Transaction pooler, footer disclaimers.
  - Vercel project created via the CLI; secrets set as sensitive env vars (never printed).
  - Production verified: 401 without credentials, 200 with them, real data.
- **MS-015:**
  - Playwright e2e: 10 desktop tests and 1 mobile test against `marketscope_e2e_test` (synthetic), plus a CI job.
  - `/api/health/live` liveness endpoint.
  - API error logs now record the driver's cause and code, not SQL text.
- Decision: no `supabase-js` until a feature needs Auth, Realtime, or Storage.

## Tests

All green: db 30, shared 192, collector 38, web 73, e2e 17, research 11 (pytest). lint, typecheck, build, and migration-drift check pass.

## Credits

487 of 500 remaining. The cron uses about 12/day (≈372/month), leaving little headroom for local runs. **Avoid local `collect:nfl` runs against the free tier**, or upgrade (ask first).

## Data

- **Production (Supabase):** collecting 4×/day since 2026-10-16.
- **Local `marketscope_dev`:** 2 snapshots, for development only.

## Waiting on Jack

Nothing blocking. Optional: mark the GitGuardian false-positive incident as resolved.

## Known issues / open decisions

- Odds API terms: confirm that storing raw payloads and public display are allowed **before Phase 3 deployment** (Vercel Deployment Protection stays on until then).
- GitHub disables scheduled workflows after 60 days without repo activity.
- Revisit TS 7 when typescript-eslint supports it (ADR-004).

## Next task

**Phase 6 decision gate:** is the paid historical plan worth it?

- Real history began 2026-10-16 (about 4 snapshots/day). Both the study and Phase 7 ML need far more games.
- Option A, keep accumulating for free: the study reaches its 15-game minimum in roughly 1–2 weeks of NFL slates.
- Option B, buy the $30/20K plan (ask Jack first): a historical import at 6-hour resolution for past weeks costs about 30 credits per snapshot.
- Otherwise, polish and accessibility (Phase 8 items), or re-run the study weekly.
