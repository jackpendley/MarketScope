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

| Topic         | Fact                                                                                                                                   |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Book keys     | `draftkings`, `fanduel`, `betmgm`, `williamhill_us` (Caesars, **paid plans only**), `hardrockbet_az` (region us2)                      |
| Cost          | `/odds` = markets × regions. Named `bookmakers` count as 1 region per 10 books, so our call costs **3 credits**                        |
| Free          | `/sports`, `/events`, and any request that returns no events                                                                           |
| Quota headers | `x-requests-remaining`, `x-requests-used`, `x-requests-last`                                                                           |
| Historical    | `/v4/historical/sports/{sport}/odds?date=`. Costs **10 × markets × regions = 30 credits per snapshot**. Paid only, 5-minute resolution |
| Plans         | Free 500/mo · $30 20K · $59 100K                                                                                                       |
| Timestamps    | Bookmaker-level `last_update` is deprecated. Use market-level `last_update`                                                            |
| 429           | No Retry-After header documented. Back off exponentially                                                                               |

**Budget:**

- 4 polls/day ≈ 360 credits/month, which fits the free tier with about 140 left for development.
- Hourly history for one NFL week ≈ 5,040 credits.
- A full season at 6-hour resolution ≈ 15K credits, which fits the $30 tier.

---

## Phase 0 — Foundation

- [x] **MS-001 Repository initialization**
  - Delivered: pnpm monorepo, Next.js 16 + TS strict + Tailwind 4, ESLint and Prettier, CI workflow, docs set, `CLAUDE.md`.
  - _Accept:_ a fresh clone passes `install`, `lint`, `typecheck`, and `build`.
- [~] **MS-002 Provider verification**
  - Delivered: collector config (Zod env), Odds API client (retry/backoff, quota headers, key redaction), `pnpm verify:provider` (free checks; the paid call is gated by `--spend`), and a coverage report with no prices.
  - Tested against a mock server. **Pending: live run with Jack's API key.**
  - _Accept:_ at least one real NFL game fetched, normalized, and summarized in `PROVIDER_COVERAGE.md`.
- [~] **MS-003 Normalization + first UI**
  - Delivered:
    - Domain types and Zod provider schemas.
    - `normalizeEventOdds` (issues are reported, never repaired).
    - `compareIdenticalMarketPrices`.
    - The synthetic edge-case fixture.
    - `/nfl` renders the fixture with a "synthetic" banner.
  - **Pending: Jack implements `americanToImpliedProbability`, `americanToDecimal`, and `decimalToAmerican` in `packages/shared/src/odds.ts`** until `odds.test.ts` passes.
  - _Accept:_ all tests green.

## Phase 1 — Persistence + collector (MS-004–006)

**Setup:** `brew install postgresql@17 && brew services start postgresql@17`, then create `marketscope_dev` and `marketscope_test`.

- [ ] **MS-004 `packages/db`.** Drizzle + postgres.js, with committed SQL migrations (`drizzle-kit generate` / `migrate`). Tables:
  - `events`: uuid PK, unique `provider_event_id`, sport_key, season, nullable week, home/away, `commence_time_utc`, timestamps. **No stored status**: derive it from `commence_time` until `/scores` is integrated.
  - `bookmakers`: the 5 books, seeded in a migration.
  - `ingestion_runs`: unique `job_key`, provider, request_type, requested/provider snapshot times, started/finished, status enum, credits used/remaining, events/quotes seen, attempt, http_status, duration_ms, error code/message (sanitized).
  - `ingestion_payloads`: run_id → raw jsonb, so normalizer bugs can be fixed by re-deriving instead of re-buying data. Confirm the terms allow storing it.
  - `odds_observations`: bigint identity PK, FKs, market/selection enums, `point numeric(5,1)`, american_price int, bookmaker_updated_at, observed_at, is_live, source.
    - UNIQUE (run, event, book, market, selection).
    - CHECK: h2h ⇔ point IS NULL; selection valid for market; price ∉ (−100, 100).
    - Indexes: `(event_id, market_type, selection, bookmaker_key, observed_at DESC)` and `(ingestion_run_id)`.
- [ ] **MS-005 `pnpm collect:nfl`**
  1. **Budget guard:** monthly `sum(credits_used)` plus the estimate must stay ≤ `MONTHLY_CREDIT_BUDGET`, and the last remaining count must stay ≥ `MIN_CREDITS_REMAINING`.
  2. **Claim the run:** `INSERT … ON CONFLICT (job_key) DO NOTHING RETURNING`. The key is `live:nfl:<slot>` when scheduled, `manual:<uuid>` when run by hand.
     - If the key exists: completed → exit with no spend. Failed, or started more than 15 minutes ago → conditional reclaim (attempt+1).
  3. **Fetch** outside any transaction.
  4. **One transaction:** upsert events (update `commence_time` on flex), insert the payload and observations, mark the run completed.
  5. **On error:** record quota headers and a sanitized error in a separate statement.
- [ ] **MS-006 Integration tests** against `marketscope_test`: fixture → DB, upsert, same `job_key` twice, rollback on failure, budget refusal. CI gets a `postgres:17` service.
  - _Accept:_ two runs, then SQL shows two distinct observation sets.
- [ ] **MS-006b Scheduled collection** (needs approval: free Neon/Supabase DB plus repo secrets). A GitHub Actions cron runs about 4×/day into the managed DB, so real history starts accumulating as early as possible.

## Phase 2 — Read API + Odds Board (MS-007–010)

- [ ] Query layer: `listUpcomingGames` and `latestOddsForEvent`. The latter uses `DISTINCT ON … ORDER BY observed_at DESC`, and **Jack writes it as an exercise**.
- [ ] Server components call the query layer directly. `GET /api/games` and `GET /api/games/:id/odds` wrap the same functions.
  - Zod params; `{ data, meta }` / `{ error: { code, message } }` envelopes; limits; 400/404 handling.
- [ ] Freshness metadata: collection age vs book update age, labeled "snapshot" vs "recent". The dashboard never claims to be real-time.
- [ ] UI with shadcn/ui:
  - `/nfl`: games grouped by date, filters for market, team search, and book visibility.
  - `/nfl/games/[id]`: all 5 books, each in an explicit state (not offered / not in plan / stale).
  - Consensus only when ≥3 fresh books report it.
- [ ] API tests against the test DB. Add `apps/web/.env.example` (`DATABASE_URL` only; the web app never gets the odds key).

## Phase 3 — History + deployment (MS-011–015)

- [ ] `GET /api/games/:id/history` (market, selection, books, from/to, resolution). Downsampling keeps every change point plus the first and last observations.
- [ ] Recharts step-after charts: point and price on separate charts. Gaps longer than the threshold render as breaks, never interpolated. Spreads are home-oriented.
- [ ] Deploy (approval needed): Vercel + managed Postgres. **Deployment Protection stays on until the Odds API display terms are reviewed.** Optionally move the scheduler to Lambda + EventBridge with CloudWatch alarms.
- [ ] Playwright smoke tests on fixture-seeded data. `GET /api/health/data`.

## Phase 4 — Market Replay (MS-016–017)

- [ ] Cursor at time T shows each book's latest observation ≤ T within the freshness window. Missing books stay missing, never carried forward.
- [ ] Labels: "first observed" (never "open"), "last observed pregame".
- [ ] `detectLineChanges` via SQL `LAG()` (**Jack's exercise**). Changes are reported as intervals.
- [ ] `detectKeyNumberCrossings` for 3 and 7: sign-safe, covering both "crosses" and "lands on". Direction tests included.

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

Ask before:

- Pushing or merging.
- Repo secrets.
- Creating any cloud resource.
- Any paid plan.
- Making a deployment public.
- Every paid `--spend` call after the first verification.

## Exercises (Jack implements; Claude reviews)

- [~] American odds conversions (`packages/shared/src/odds.ts`): Phase 0
- [ ] Design the run claim/retry state machine on paper before reading the code: Phase 1
- [ ] Explain `bookmaker_updated_at` vs `observed_at` vs `provider_snapshot_at`: Phase 1
- [ ] `DISTINCT ON` latest-quote-per-book query: Phase 2
- [ ] `LAG()` line-movement query: Phase 4
- [ ] Find the leakage in a deliberately leaky ML feature: Phase 7

## Out of scope until the core works

Props, alternate lines, live betting, bet placement, other leagues, betting splits, sharp-book references, CLV tracking, and alerts. See spec §5 "Future releases".

One cheap future option: the 10-book region group has 5 free slots, so a sharp reference book could be added at zero extra credit cost.
