# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-16 (session 1, continued)._

## Current milestone

**Phase 2 is complete (pending merge of its PR). Next: MS-006b scheduled collection (blocked on Jack's Supabase project) and Phase 3 (history API, charts, deployment).**

## Done so far

- **Phase 0:** monorepo, CI, Odds API client and verification, normalizer, odds math, exact-line comparison. Hard Rock AZ is empty, so we collect the multi-state feed as a fallback (ADR-012).
- **Phase 1:** Postgres schema with DB-enforced invariants; idempotent, budget-guarded collector (ADR-013); 17 integration tests; CI with Postgres 17 and a migration-drift check.
- **Phase 2:**
  - Query layer: `DISTINCT ON` latest quotes, verified index use (ADR-016).
  - `/api/games`, `/api/games/:id/odds`, `/api/health/data` (`docs/API.md`).
  - `/nfl` board from Postgres with GET-form filters (ADR-017).
  - `/nfl/games/[id]` detail page with per-feed coverage.
  - Stale books flagged and never ranked.
  - Median consensus requiring ≥ 3 current books.
  - Verified in a real browser (Playwright screenshots at 1400 px and 390 px).
  - Fixed a horizontal-overflow bug caused by `sr-only` labels escaping scroll containers.

## Tests

All green: db 17, shared 141, collector 32, web 38. lint, typecheck, build, and migration-drift check pass.

## Credits

490 of 500 remaining this billing period (no spend in Phase 2).

## Local data

`marketscope_dev` holds 2 real snapshots (Oct 16 ~01:43 UTC, 25 games). Run `pnpm collect:nfl` for a fresh one (3 credits).

## Waiting on Jack (MS-006b only)

1. Create a free **Supabase** project.
2. Put its **Session pooler** connection string in `apps/collector/.env.local` as `SUPABASE_DATABASE_URL=...` (don't paste it in chat), then tell Claude.
3. Claude migrates it and asks once before adding the GitHub secrets for the 4×/day cron.

Until then, history only grows when collection runs locally.

## Known issues / open decisions

- Odds API terms: confirm that storing raw payloads and public display are allowed **before the Phase 3 deployment** (Vercel Deployment Protection stays on until then).
- 400 credits/month allows about 4 polls/day. Denser history needs the $30 plan (ask first).
- Revisit TS 7 when typescript-eslint supports it (ADR-004).

## Next task

**Phase 3 / MS-011:**

1. `GET /api/games/:id/history` (market, selection, books, from/to). Downsampling keeps every change point plus the first and last observations.
2. Recharts step charts: point and price on separate charts, gaps rendered as breaks.
3. Playwright smoke tests.
4. Deployment prep (Vercel + Supabase). Ask before creating any resources.
