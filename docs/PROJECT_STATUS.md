# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-16 (session 1, continued)._

## Current milestone

**Phase 5 is in progress. MS-018–020 (Signal Lab) are done. Next: MS-021, the first research study. Deployed privately at https://marketscope-delta.vercel.app (user `marketscope`, password in `apps/web/.env.local` as `VERCEL_SITE_PASSWORD`).**

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

All green: db 30, shared 192, collector 38, web 73, e2e 17. lint, typecheck, build, and migration-drift check pass.

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

**MS-021, first research study:** does a book's divergence from consensus predict that the consensus moves toward it within 24 h?

- Python `research/` (venv, pandas, psycopg) reading Postgres read-only.
- Point-in-time events from `book_divergence` onsets.
- Outcome: consensus 18–30 h later moves toward, away, or not at all.
- Baselines: the same rate for non-divergent books, and a random-book comparison.
- Game-clustered counts with bootstrap CIs, plus limitations.
- Publish even if null; report the sample size honestly (real history only began 2026-10-16).
