# MarketScope Roadmap

The approved implementation plan, distilled from `PRODUCT_SPEC.md`. Phases run in order and each one ends with something demonstrable. There is **no calendar**: we build continuously, and paid services are bought only when a milestone needs them, with explicit approval each time.

Status legend: `[x]` done · `[~]` in progress · `[ ]` not started

## Goals

1. **Product:** "Compare the market. Replay its history. Investigate the signals. Test the evidence."
   - The odds board for 5 books (DraftKings, FanDuel, BetMGM, Caesars, Hard Rock AZ) is the entry point.
   - Historical replay and evidence-backed signals are the differentiators.
2. **Career:** a deployed, tested, documented, data-intensive system that Jack can explain without AI. It should demonstrate:
   - backend and API design
   - relational modeling
   - ingestion and data quality
   - cloud deployment
   - honest ML evaluation
3. **Integrity:** no fabricated data, no causal claims from correlations, and uncertainty shown in the UI.

**Definition of done (portfolio-ready):**

- Deployed, using real permitted data.
- Persistent history, with at least one game replayable.
- Correct exact-line comparisons; honest handling of missing and stale data.
- Observable, cost-controlled ingestion.
- Tests on the business rules, and CI.
- Architecture documented.
- At least one research hypothesis investigated.
- Jack can explain every major design decision.

## Verified provider facts (The Odds API, docs checked 2026-10-15)

| Topic         | Fact                                                                                                                                                                                                            |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Book keys     | `draftkings`, `fanduel`, `betmgm`, `williamhill_us` (Caesars, **paid plans only**), `hardrockbet_az` (us2, **empty for NFL** as of 2026-10-16), plus the fallback `hardrockbet` (us2, multi-state). See ADR-012 |
| Cost          | `/odds` = markets × regions. Named `bookmakers` count as 1 region per 10 books, so our call costs **3 credits**                                                                                                 |
| Free          | `/sports`, `/events`, and any request that returns no events                                                                                                                                                    |
| Quota headers | `x-requests-remaining`, `x-requests-used`, `x-requests-last`                                                                                                                                                    |
| Historical    | `/v4/historical/sports/{sport}/odds?date=`. Costs **10 × markets × regions = 30 credits per snapshot**. Paid only, 5-minute resolution                                                                          |
| Plans         | Free 500/mo · $30 20K · $59 100K                                                                                                                                                                                |
| Timestamps    | Bookmaker-level `last_update` is deprecated. Use market-level `last_update`                                                                                                                                     |
| 429           | No Retry-After header documented. Back off exponentially                                                                                                                                                        |

**Budget:**

- 4 polls/day ≈ 360 credits/month, which fits the free tier with about 140 left for development.
- Hourly history for one NFL week ≈ 5,040 credits.
- A full season at 6-hour resolution ≈ 15K credits, which fits the $30 tier.

---

## Phase 0 — Foundation

- [x] **MS-001 Repository initialization**
  - Delivered: pnpm monorepo, Next.js 16 + TS strict + Tailwind 4, ESLint and Prettier, CI workflow, docs set, `CLAUDE.md`.
  - _Accept:_ a fresh clone passes `install`, `lint`, `typecheck`, and `build`.
- [x] **MS-002 Provider verification**
  - Delivered: collector config (Zod env), Odds API client (retry/backoff, quota headers, key redaction), `pnpm verify:provider` (free checks; the paid call is gated by `--spend`), and a coverage report with no prices.
  - **Live-verified 2026-10-16:** 25 games returned, 3 credits per call. DraftKings and FanDuel complete; BetMGM current week only; Caesars absent (paid-only); Hard Rock AZ empty, so we also collect the multi-state `hardrockbet` feed (ADR-012). See `PROVIDER_COVERAGE.md`.
  - _Accept:_ at least one real NFL game fetched, normalized, and summarized in `PROVIDER_COVERAGE.md`.
- [x] **MS-003 Normalization + first UI**
  - Delivered:
    - Domain types and Zod provider schemas.
    - `normalizeEventOdds` (issues are reported, never repaired).
    - `compareIdenticalMarketPrices`.
    - The synthetic edge-case fixture.
    - `/nfl` renders the fixture with a "synthetic" banner.
    - American odds math (conversions, payout, overround).
  - _Accept:_ all tests green.

## Phase 1 — Persistence + collector (MS-004–006)

**Setup:** `brew install postgresql@17 && brew services start postgresql@17`, then create `marketscope_dev` and `marketscope_test`.

- [x] **MS-004 `packages/db`.** Drizzle + postgres.js, with committed SQL migrations (`drizzle-kit generate` / `migrate`). Tables:
  - `events`: uuid PK, unique `provider_event_id`, sport_key, season, nullable week, home/away, `commence_time_utc`, timestamps. **No stored status**: derive it from `commence_time` until `/scores` is integrated.
  - `bookmakers`: the 5 books, seeded in a migration.
  - `ingestion_runs`: unique `job_key`, provider, request_type, requested/provider snapshot times, started/finished, status enum, credits used/remaining, events/quotes seen, attempt, http_status, duration_ms, error code/message (sanitized).
  - `ingestion_payloads`: run_id → raw jsonb, so normalizer bugs can be fixed by re-deriving instead of re-buying data. Confirm the terms allow storing it.
  - `odds_observations`: bigint identity PK, FKs, market/selection enums, `point numeric(5,1)`, american_price int, bookmaker_updated_at, observed_at, is_live, source.
    - UNIQUE (run, event, book, market, selection).
    - CHECK: h2h ⇔ point IS NULL; selection valid for market; price ∉ (−100, 100).
    - Indexes: `(event_id, market_type, selection, bookmaker_key, observed_at DESC)` and `(ingestion_run_id)`.
- [x] **MS-005 `pnpm collect:nfl`**
  1. **Budget guard:** monthly `sum(credits_used)` plus the estimate must stay ≤ `MONTHLY_CREDIT_BUDGET`, and the last remaining count must stay ≥ `MIN_CREDITS_REMAINING`.
  2. **Claim the run:** `INSERT … ON CONFLICT (job_key) DO NOTHING RETURNING`. The key is `live:nfl:<slot>` when scheduled, `manual:<uuid>` when run by hand.
     - If the key exists: completed → exit with no spend. Failed, or started more than 15 minutes ago → conditional reclaim (attempt+1).
  3. **Fetch** outside any transaction.
  4. **One transaction:** upsert events (update `commence_time` on flex), insert the payload and observations, mark the run completed.
  5. **On error:** record quota headers and a sanitized error in a separate statement.
- [x] **MS-006 Integration tests** against `marketscope_test`: fixture → DB, upsert, same `job_key` twice, rollback on failure, budget refusal. CI gets a `postgres:17` service and a migration-drift check.
  - **Accepted 2026-10-16:** two live runs into `marketscope_dev` produced two distinct sets of 468 observations (25 games, 4 feeds with data), 3 credits each. Re-running the same scheduled slot was a no-op.
  - _Accept:_ two runs, then SQL shows two distinct observation sets.
- [x] **MS-006b Scheduled collection** (2026-10-16): Supabase (Postgres 17, session pooler) is migrated and locked down (ADR-018). `collect-odds.yml` runs 4×/day and `migrate-production.yml` applies migrations on merge (ADR-019). Repo secrets: `DATABASE_URL`, `ODDS_API_KEY`.

## Phase 2 — Read API + Odds Board (MS-007–010)

- [x] Query layer (`packages/db/src/queries/odds.ts`): `listGames`, `getGame`, `latestQuotesForEvents` (`DISTINCT ON`, index-ordered), `gameObservationStats`, `latestCompletedRun`, `recentRuns`. ISO UTC timestamps are formatted in SQL.
- [x] Server components call the query layer directly. `GET /api/games`, `GET /api/games/:id/odds`, and `GET /api/health/data` wrap the same functions (ADR-015, `docs/API.md`).
  - Zod params; strict, bounded; `{ data, meta }` / `{ error }` envelopes; 400, 404, and 503 handling.
- [x] Freshness metadata: collection age vs book update age, labeled `recent` or `snapshot`. Stale-book detection (ADR-016).
- [x] UI:
  - `/nfl`: games grouped by ET date, filters for team, market, kickoff window, and books (GET form, ADR-017).
  - `/nfl/games/[id]`: board, per-feed coverage, history counts.
  - Consensus shown only with ≥ 3 current books.
  - Empty and error states for: DB unavailable, no snapshots, no games, no matches, unknown game.
  - No horizontal page scroll at 390 px.
- [x] Tests: query integration tests (db), API route integration tests and view-model unit tests (web).
- Deferred: shadcn/ui (ADR-017).

## Phase 3 — History + deployment (MS-011–015)

- [x] **MS-011** `GET /api/games/:id/history` (market, selection, books, from/to, resolution, gapMinutes, includeLive). Value-based changes as intervals; explicit gaps; `changes` downsampling keeps every movement (ADR-020).
- [x] **MS-012** `/nfl/games/[id]/history`:
  - Recharts step charts, line and price separate, breaks at gaps, change dots.
  - Toggle legend and crosshair tooltip.
  - Per-book first/last-observed table, change log, data-gap list.
  - Synthetic-data banners across the app (ADR-021).
- [x] **MS-015** Playwright e2e against a synthetic e2e DB, seeded through the real collector. Covers the board, filters, empty and missing-book states, detail, history charts and legend toggles, moneyline price-only view, 404, health, and phone width. Runs in a CI job; the suite was stable over 3 repeats.
- [x] **MS-013** Deployment (2026-10-16): **https://marketscope-delta.vercel.app** (private).
  - Terms reviewed (ADR-022).
  - App-level Basic auth on everything except liveness.
  - Transaction-pooler support and footer disclaimers.
  - Vercel project linked to the repo; runbook in `docs/DEPLOYMENT.md`.
- [x] **MS-014** Scheduled collection: done in MS-006b via GitHub Actions. Lambda + EventBridge stays an optional upgrade.

## Phase 4 — Market Replay (MS-016–017)

- [x] **MS-016** Replay cursor on `/nfl/games/[id]/history`:
  - Steps through actual snapshots (slider, prev/next/latest, keyboard).
  - State-at-T table, one feed per board book.
  - Consensus and dispersion at T.
  - Cursor line on both charts.
  - Movement timeline that jumps the cursor (ADR-023).
- [x] **MS-017** Data-quality correctness:
  - Stale books flagged with their age, never carried forward.
  - "First observed" / "last observed (pregame)" labels.
  - Value-based changes reported as intervals, with "across gap" flags.
  - Key-number crossings (3 and 7; crossed, landed-on, left; sign-safe).
  - `GET /api/games/:id/movements`; `/replay` index of games with history; Market Replay in the nav.

## Phase 5 — Signal Lab + first study (MS-018–021)

- [ ] Signals A–F (spec §14) as pure functions with `ALGORITHM_VERSION`.
  - Stored in `market_signals` with evidence observation IDs.
  - Recompute is idempotent per (event, version).
  - Formal definitions go in `docs/SIGNAL_DEFINITIONS.md`.
- [ ] Python `research/` venv. Study: _does an outlier book predict consensus convergence within 24h?_
  - Report game-clustered sample sizes, a baseline, and limitations.
  - Null results get published too.

## Phase 6 — Historical import (decision gate: $30 plan?)

- [ ] Present the cost math for approval first.
- [ ] Importer:
  - `job_key = hist:nfl:<ts>`, which gives caching and resumability.
  - Store `requested_snapshot_at` and `provider_snapshot_at`; `observed_at` = snapshot time.
  - Hard credit cap.
- [ ] Coverage dashboard, `EXPLAIN ANALYZE` review, index and storage review.

## Phase 7 — ML baseline (MS-024–025)

- [ ] Gate: enough distinct games and positive labels, with thresholds documented. Otherwise publish exploratory analysis only.
- [ ] Point-in-time features. Label: |consensus(t+24h) − consensus(t)| ≥ 0.5, with tolerance; missing labels stay missing.
- [ ] Chronological, game-grouped split.
- [ ] Baselines: majority class, empirical rate, volatility heuristic, logistic regression.
- [ ] Report Brier, log loss, calibration, and bootstrap CIs. Write `docs/MODEL_CARD.md`.

## Phase 8 — Portfolio release (MS-026–028)

- [ ] Architecture diagram, schema docs, screenshots, accessibility pass, secret audit, case-study write-up.

---

## Approval checkpoints

**Standing approvals (2026-10-16):**

- Claude merges its own PRs once CI is green.
- Claude spends Odds API credits within the collector's guards (`MONTHLY_CREDIT_BUDGET=400`, `MIN_CREDITS_REMAINING=25`).

**Still ask before:**

- Adding repo secrets.
- Creating any cloud resource.
- Buying any paid plan or raising the credit budget.
- Making a deployment public.

Managed DB: **Supabase**, used as Postgres only (ADR-018). Its session-pooler URL is stored locally as `SUPABASE_DATABASE_URL` in `apps/collector/.env.local`, and in GitHub as the `DATABASE_URL` secret.

## Concepts (Claude implements; explains these in milestone summaries)

Jack doesn't write code for the project. These are the ideas he should be able to explain in interviews, and each milestone summary should cover the relevant ones:

- American odds, implied probability, and overround: Phase 0
- Normalization at the boundary; why team orientation comes from event metadata: Phase 0
- The run claim/retry state machine and idempotency keys: Phase 1
- `bookmaker_updated_at` vs `observed_at` vs `provider_snapshot_at`: Phase 1
- Transactions, constraints, and indexes on an append-only table: Phase 1
- `DISTINCT ON` for latest-quote-per-book: Phase 2
- `LAG()` window functions for line movement: Phase 4
- Data leakage and chronological, game-grouped splits: Phase 7

## Out of scope until the core works

Props, alternate lines, live betting, bet placement, other leagues, betting splits, sharp-book references, CLV tracking, and alerts. See spec §5 "Future releases".

One cheap future option: the 10-book region group has 5 free slots, so a sharp reference book could be added at zero extra credit cost.
