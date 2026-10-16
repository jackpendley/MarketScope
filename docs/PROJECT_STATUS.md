# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-16 (session 1, continued)._

## Current milestone

**Phase 3 is in progress. MS-011/012 (history API and line-history charts) are done; next come MS-015 (Playwright e2e) and MS-013 (deployment, ask first).**

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
- Decision: no `supabase-js` until a feature needs Auth, Realtime, or Storage.

## Tests

All green: db 23, shared 152, collector 37, web 51. lint, typecheck, build, and migration-drift check pass.

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

1. **MS-015:** Playwright smoke tests (board, detail, history, filters, missing-book states, mobile width) against a seeded `marketscope_e2e_test` DB, with a CI job.
2. **MS-013:** review the Odds API terms, then propose a Vercel deployment with Deployment Protection. Ask before creating the project or setting env vars.
