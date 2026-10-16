# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-16 (session 1, continued)._

## Current milestone

**Phases 0–2 and MS-006b are complete. Scheduled collection is live on GitHub Actions → Supabase. Next: Phase 3 (history API, charts, deployment).**

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
- Decision: no `supabase-js` until a feature needs Auth, Realtime, or Storage.

## Tests

All green: db 21, shared 141, collector 32, web 38. lint, typecheck, build, and migration-drift check pass.

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

**Phase 3 / MS-011:**

1. `GET /api/games/:id/history`, with downsampling that keeps change points plus first and last observations.
2. Recharts step charts (point and price separate; gaps as breaks).
3. Playwright smoke tests.
4. Vercel deployment plan. Ask before creating resources.
