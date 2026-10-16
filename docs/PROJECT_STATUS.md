# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-16 (session 1, continued)._

## Current milestone

**Phase 0 is complete. Phase 1 (MS-004: database) is next.**

## Done so far

- **MS-001:** monorepo, Next.js 16.4, TS 5.9 strict, Tailwind 4, ESLint and Prettier, CI, docs, `CLAUDE.md`.
- **MS-002:** collector config, Odds API client, `verify:provider`, `probe:books`.
  - **Live-verified 2026-10-16:** 25 games, 3 credits per call. DraftKings and FanDuel complete; BetMGM current week only; Caesars absent (paid-only).
  - Hard Rock AZ is empty, so we also collect the `hardrockbet` multi-state feed (ADR-012).
- **MS-003:** normalizer, exact-line comparison, odds math (implemented by Claude), and the fixture-backed `/nfl` board with Hard Rock AZ-to-IN fallback.
- Working rules changed (2026-10-16):
  - No coding exercises for Jack.
  - Claude merges its own PRs once CI is green.
  - Claude spends Odds API credits within the collector's budget guards.
  - The managed DB will be Supabase.

## Tests

All green: shared 118, collector 15, web 9. lint, typecheck, and build pass.

## Credits

496 of 500 remaining this billing period: one `/odds` verification (3) and one Hard Rock probe (1).

## Waiting on Jack

- Nothing blocks Phase 1.
- Before MS-006b (scheduled collection): create a free Supabase project. Then put its connection string in `apps/collector/.env.local` as `DATABASE_URL_SUPABASE`, or tell Claude where it is. Claude will ask before adding GitHub repo secrets.

## Known issues / open decisions

- Odds API terms: confirm that storing raw payloads and public display are allowed. Required before Phase 3 deployment.
- Revisit TS 7 when typescript-eslint supports it (ADR-004).

## Next task

**MS-004:** install `postgresql@17` via Homebrew, create `marketscope_dev` and `marketscope_test`, scaffold `packages/db` (Drizzle + postgres.js), and write the first migration. Seed the bookmakers table with all 6 collected feeds.
