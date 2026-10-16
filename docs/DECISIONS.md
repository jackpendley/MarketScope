# Architecture Decision Log

Short records of meaningful decisions. Newest at the bottom. Format: context → decision → consequences.

## ADR-001 — pnpm workspace monorepo, no Turborepo/Nx (2026-10-15)

**Context:** One web app, one worker, a few shared packages.
**Decision:** Use a plain pnpm workspace (`apps/*`, `packages/*`). Root scripts fan out with `pnpm -r`.
**Consequences:** Simple and fast enough at this size. Revisit only if build times or task graphs become a real problem.

## ADR-002 — Just-in-time internal packages (2026-10-15)

**Context:** Shared code has to be consumed by Next.js and by a Node worker.
**Decision:** Workspace packages export TypeScript source (`"exports": {".": "./src/index.ts"}`) with no build step. Next compiles them via `transpilePackages`; the collector runs through `tsx`.
**Consequences:** No dist folders and no watch builds, and edits are visible everywhere immediately. Trade-off: every consumer needs a TS-aware loader, which is fine for our two consumers. If we deploy the collector to Lambda, bundle it (esbuild) at deploy time.

## ADR-003 — Per-app environment files (2026-10-15)

**Decision:** `apps/collector/.env.local` holds `ODDS_API_KEY`, `DATABASE_URL`, and budgets. `apps/web/.env.local` will hold `DATABASE_URL` only. The collector loads env with Node's built-in `--env-file-if-exists`, so there's no dotenv dependency.
**Consequences:** The web app structurally cannot leak the odds key, because it never has it.

## ADR-004 — TypeScript 5.9, not 7.0 (2026-10-15)

**Context:** npm `latest` is TypeScript 7.0, the native compiler. `typescript-eslint` 8.71 declares `typescript >=4.8.4 <6.1.0`, and `create-next-app` 16.4 pins `typescript ^5`.
**Decision:** Pin `typescript ^5` (5.9.3) across the workspace. ESLint stays on 9 because `eslint-config-next` 16.4 pins it.
**Consequences:** Revisit when typescript-eslint and Next support TS 7.

## ADR-005 — Homebrew PostgreSQL locally, Postgres service container in CI (2026-10-15)

**Context:** No Docker on the dev machine.
**Decision:** Local development and integration tests use `postgresql@17` from Homebrew, with separate `marketscope_dev` and `marketscope_test` databases. CI uses a `postgres:17` service. A managed free-tier DB is added for scheduled collection and deployment.
**Consequences:** Dev and CI are the same major version but not byte-identical environments, which is acceptable.

## ADR-006 — Provider schema + normalizer live in `packages/shared` (for now) (2026-10-15)

**Context:** Both the fixture-backed web page (MS-003) and the collector need normalization.
**Decision:** Put them in `packages/shared/src/providers/the-odds-api/`. The HTTP client stays in the collector.
**Consequences:** Once the web app reads only from Postgres (Phase 2), consider moving provider code into the collector so the web bundle can't depend on provider shapes.

## ADR-007 — Normalizer reports issues instead of throwing or repairing (2026-10-15)

**Decision:** `normalizeEventOdds` returns `{ event, quotes, issues }`.

- Structurally invalid events are rejected individually by `parseOddsResponse`.
- Value problems (invalid price, unknown outcome name, bad timestamp, duplicate selection, missing book or market, inconsistent spread) become typed `NormalizationIssue`s.
- Data is never invented or "fixed".

**Consequences:** One bad price can't sink a whole collection run, and data quality is visible in the UI and, later, in ingestion metrics.

## ADR-008 — Split "freshness" into two concepts (2026-10-15)

**Context:** The spec's `QUOTE_FRESHNESS_MINUTES=15` would mark everything stale at 4 polls a day.
**Decision:**

- **Collection age** (`now − observed_at`) drives the "timestamped snapshot" labels.
- **Book update age** (`now − market.last_update`) decides whether a book is fresh enough for consensus.

All books in one run come from a single request, so "contemporaneous" means "same run".
**Consequences:** The UI can be honest about snapshot cadence without throwing away usable data.

## ADR-009 — No stored `events.status`; nullable `events.week` (2026-10-15)

**Context:** `/odds` and `/events` don't provide game status or NFL week. `/scores` costs credits.
**Decision:** Derive pregame/started from `commence_time` at read time. Keep `week` nullable and fill it later from a season calendar or the nflverse schedule.

## ADR-010 — Real provider captures are never committed (2026-10-15)

**Context:** The repo is public, and the provider's terms restrict redistributing raw data.
**Decision:** Raw responses go in gitignored `fixtures/the-odds-api/local/`. Committed tests use the hand-authored synthetic fixture, and committed docs contain coverage summaries without prices.

## ADR-011 — Next.js Cache Components off for now (2026-10-15)

**Context:** Next 16 offers Cache Components (`"use cache"`, PPR) as an opt-in model.
**Decision:** Scaffold without it. Pages are static or dynamic by default, which is easy to reason about while the data layer is built.
**Consequences:** Revisit in Phase 2/3, when caching DB reads per collection run may be worthwhile.

## ADR-012 — Collect Hard Rock AZ and the multi-state feed; board prefers AZ (2026-10-16)

**Context:** In the live check, `hardrockbet_az` returned 0 NFL games. `hardrockbet` (the docs call it the Indiana feed, "same odds as several other states"), `hardrockbet_fl`, and `hardrockbet_oh` each returned the 14 current-week games.
**Decision:** Collect both `hardrockbet_az` and `hardrockbet`. Six named books still cost one region-equivalent, so a call stays at 3 credits. The two are stored as separate feeds and never merged.

- The odds board has five columns (`BOARD_BOOKS`), each listing feeds in preference order. The Hard Rock column shows AZ when present and otherwise falls back to the IN feed, labeled "IN feed".
- Best-price comparison uses only the feed each column displays, so a book can never be counted twice.

**Consequences:** Research and consensus code must choose feeds explicitly (default: one feed per board book, using the same preference order). Re-probe AZ occasionally with `pnpm --filter @marketscope/collector probe:books --books hardrockbet_az`.

## ADR-013 — Collection runs: claim by job key, guard budget, fetch outside the transaction (2026-10-16)

**Context:** Scheduled jobs get retried and can overlap. Credits cost money. Partial writes would corrupt history.
**Decision:**

1. **Claim:** `INSERT … ON CONFLICT (job_key) DO NOTHING`. If the key exists, a conditional `UPDATE … WHERE status IN ('failed','skipped') OR (status='started' AND started_at < now() − 15 min)` reclaims it with `attempt + 1`. Postgres row locking means only one racing worker can match. A completed key never re-runs.
2. **Budget guard** before any paid call. The run is marked `skipped` if any of these trips: the estimated cost exceeds `MAX_CREDITS_PER_RUN`; this calendar month's (UTC) recorded spend plus the cost would exceed `MONTHLY_CREDIT_BUDGET`; or the last provider-reported remaining minus the cost would fall below `MIN_CREDITS_REMAINING`.
3. **Fetch with no transaction open**, so slow HTTP never holds locks.
4. **One transaction** writes bookmakers, events, the raw payload, the observations, and run completion. A failure rolls everything back, and the run is marked `failed` in a separate statement that keeps the credit headers.

**Consequences:** A failed run leaves no observations, so a retry produces one clean set. Scheduled slots are exactly-once in effect. Manual runs always get a fresh key.

## ADR-014 — Index choices for odds_observations (2026-10-16)

**Decision:** No separate `(ingestion_run_id)` index. The unique constraint `(ingestion_run_id, event_id, bookmaker_key, market_type, selection)` already provides a B-tree whose leading column is `ingestion_run_id`, so "all rows of run X" can use it. The history index `(event_id, market_type, selection, bookmaker_key, observed_at DESC)` serves both per-book history and latest-quote-per-book (`DISTINCT ON`).
**Consequences:** One fewer index to maintain on the hottest write path. Revisit with `EXPLAIN ANALYZE` once Phase 2 queries exist.
