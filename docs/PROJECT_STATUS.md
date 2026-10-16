# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-16 (session 1, continued)._

## Current milestone

**Phase 1 (MS-004–006) is complete. Next: MS-006b scheduled collection (needs Jack's Supabase project), then Phase 2 (read API + odds board from Postgres).**

## Done so far

- **Phase 0:** monorepo, CI, Odds API client and verification, normalizer, exact-line comparison, odds math, fixture-backed `/nfl`. Hard Rock AZ is empty, so the multi-state feed is the fallback (ADR-012).
- **MS-004:** `packages/db` with a Drizzle schema and two committed migrations (`0000_init`, `0001_seed_bookmakers`).
  - DB-level CHECK, UNIQUE, and FK constraints, each with an integration test.
- **MS-005:** `pnpm collect:nfl`: claim by job key, then budget guard, then fetch outside any transaction, then one transaction (ADR-013).
  - Scheduled keys are per 6-hour slot.
  - Failed or stale runs are reclaimed with attempt + 1.
- **MS-006:** 17 collector integration tests: happy path, history, idempotency, stale reclaim, kickoff update, home/away flip guard, provider failure and retry, mid-transaction rollback, budget guards.
  - CI has a Postgres 17 service and a migration-drift check.
- **Live acceptance:** two real runs into `marketscope_dev` gave 2 × 468 observations across 25 games.
- **Finding:** the provider's `last_update` advances without price changes, so movement detection must compare values (DATA_DICTIONARY).

## Tests

All green: db 9, shared 124, collector 32, web 9. lint, typecheck, build, and migration-drift check pass.

## Credits

490 of 500 remaining this billing period. Spent: verify 3, probe 1, two collector runs 6.

## Waiting on Jack (MS-006b only; Phase 2 can proceed without it)

1. Create a free **Supabase** project (any name, e.g. `marketscope`).
2. Copy its **Session pooler** connection string (Project Settings → Database). Put it in `apps/collector/.env.local` as `SUPABASE_DATABASE_URL=...` and tell Claude it's there. Don't paste it in chat.
3. Claude will migrate it and ask once before adding the `DATABASE_URL` and `ODDS_API_KEY` GitHub secrets for the cron workflow.

## Known issues / open decisions

- Odds API terms: confirm that storing raw payloads and public display are allowed. Required before Phase 3 deployment.
- A free-tier budget of 400 credits/month allows about 4 polls/day (360). More frequent collection needs the $30 plan.
- Revisit TS 7 when typescript-eslint supports it (ADR-004).

## Next task

**Phase 2 / MS-007:**

1. `packages/db` query layer: `listUpcomingGames` and `latestOddsForEvent` (`DISTINCT ON`).
2. Switch `/nfl` from the fixture to Postgres.
3. Add `/api/games` and `/api/games/:id/odds` with Zod params and freshness metadata.
