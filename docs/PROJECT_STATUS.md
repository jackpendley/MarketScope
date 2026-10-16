# Project Status

_Rewrite this file at the end of every session. Last updated: 2026-10-15 (session 1)._

## Current milestone

**Phase 0: MS-002 and MS-003 are waiting on Jack.** MS-001 is complete.

## Last session (2026-10-15)

- Cloned `git@github.com:jackpendley/MarketScope.git` (public) to `~/Projects/MarketScope`. Set global git identity to `Jack Pendley <jackpendley9@gmail.com>`.
- **MS-001:** pnpm monorepo, Next.js 16.4 / React 19.3 / Tailwind 4 / TS 5.9 strict, ESLint 9 + Prettier, CI (`.github/workflows/ci.yml`), full docs set, `CLAUDE.md`.
- **MS-002:** `apps/collector` with Zod config, Odds API client (retry/backoff, quota headers, key redaction), and `pnpm verify:provider` (paid call gated by `--spend`). Exercised end-to-end against a local mock server; **not yet run against the real API**.
- **MS-003:**
  - Domain types, Zod schemas, `normalizeEventOdds` (typed issues), `compareIdenticalMarketPrices`, and formatters.
  - Synthetic edge-case fixture.
  - `/nfl` renders it with a "synthetic" banner.
  - Odds-math stubs plus a full test suite (validated against a throwaway reference implementation, which was then removed).

## Tests

- Passing: normalizer and format (shared), collector client and coverage (15), web view model (6).
- **Failing by design:** `packages/shared/src/odds.test.ts`, plus the compare tests and the `/nfl` page that depend on it. They need Jack's odds-math implementation.
- lint, typecheck, and build pass.

## Waiting on Jack

1. **Implement** `americanToImpliedProbability`, `americanToDecimal`, and `decimalToAmerican` in `packages/shared/src/odds.ts`. Run `pnpm --filter @marketscope/shared test` until green, then `pnpm dev` and look at `/nfl`.
2. **Get an Odds API key** (free Starter plan). Put it in `apps/collector/.env.local`, then run `pnpm verify:provider` and `pnpm verify:provider --spend`.
3. After odds.ts passes, tell Claude to push `ms-002-003-provider-normalization` and open the PR. Merge once CI is green.

## Git state

- `main`: MS-001, pushed to origin. CI green.
- Branch `ms-002-003-provider-normalization`: MS-002 and MS-003 commits, **local only (not pushed)**. Held until odds.ts is implemented, since its tests and the `/nfl` build fail on the stubs.

## Known issues / open decisions

- Odds API terms: confirm that storing raw payloads (`ingestion_payloads`) and public display are allowed. Required before Phase 3 deployment.
- Revisit TS 7 when typescript-eslint supports it (ADR-004).

## Next task

**Phase 1 / MS-004:** `brew install postgresql@17`, create the dev and test DBs, scaffold `packages/db` with Drizzle, and write the first migration (events, bookmakers, ingestion_runs, ingestion_payloads, odds_observations). Before coding, explain the schema and constraints to Jack.
