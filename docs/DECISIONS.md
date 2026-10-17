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

## ADR-015 — Read path: server components call the query layer; API routes wrap the same functions (2026-10-16)

**Decision:** Pages (`/nfl`, `/nfl/games/[id]`) call `apps/web/lib/server/games.ts` → `@marketscope/db` queries directly. The `/api/*` route handlers wrap the same functions for external clients. Pages never make HTTP calls to their own API.

- DB-backed pages call `connection()`, so they render per request and the build never needs a database.
- `@marketscope/db` splits its entry points: runtime (`.`), `./migrate` (filesystem access, never bundled into the web app), and `./testing`.

**Consequences:** One data path, two presentations. The web app gets `DATABASE_URL` only (ADR-003).

## ADR-016 — Latest quote = DISTINCT ON; absent books are stale, not current (2026-10-16)

**Decision:** "Latest odds" is the newest observation per (event, market, selection, book), via `DISTINCT ON`. The column order matches `odds_observations_history_idx`, and `EXPLAIN` confirmed the index is used per event.

- A book missing from a game's **newest snapshot** still has an older row. The UI shows it italic as "last seen …" and the API flags it `stale: true`. It is never ranked for best price and never counted in consensus.
- Consensus (`calculateConsensusSpread`) is the median home spread across current, pregame, displayed feeds, and needs ≥ 3 books. An even count can produce a quarter point, which is documented as a summary statistic, not a bettable line.

## ADR-017 — No shadcn/ui yet; filters are a server-rendered GET form (2026-10-16)

**Context:** The spec suggests shadcn/ui "where useful". The board needs dense tables, a select, and checkboxes.
**Decision:** Plain Tailwind and native form controls for now. Filters (`q`, `market`, `days`, `books`) live in URL search params, submitted with a GET form and parsed on the server (`lib/board-filters.ts`). That needs no client JavaScript, and URLs are shareable.
**Consequences:** Fewer dependencies. Revisit when Market Replay needs interactive client components (charts, time cursor).

## ADR-018 — Supabase as managed Postgres only; Data API locked down (2026-10-16)

**Context:** Supabase's default privileges grant the `anon`/`authenticated` roles access to new tables in `public`, and those roles are reachable through its REST Data API with the **publishable key**, which is public by design. Unprotected, the odds tables would have been readable and writable by anyone holding the key, which also conflicts with the provider's no-redistribution terms.
**Decision:**

- Use Supabase purely as managed PostgreSQL 17 through the **session pooler** (port 5432; direct connections are IPv6-only on the free tier and GitHub runners can't reach them). Access stays server-side through Drizzle.
- Do **not** add `supabase-js`, `@supabase/ssr`, or the shadcn Supabase blocks until a feature needs Auth, Realtime, or Storage.
- Every table has RLS **enabled with no policies** (`.enableRLS()` in `schema.ts`, migration 0002). Migration 0003 also revokes current and default privileges from `anon`/`authenticated`; it's a no-op where those roles don't exist (local, CI).
- Our connections use the table owner, which bypasses RLS.
- `createDb` requires TLS for any non-local host.

**Verified 2026-10-16:** REST reads and writes with the publishable key return 401 permission denied on every table.
**Consequences:** If a browser-side Supabase feature is added later, it must come with explicit, minimal grants and RLS policies, and be reviewed against the provider's terms.

## ADR-019 — Scheduled collection on GitHub Actions; migrations applied on merge (2026-10-16)

**Decision:**

- `collect-odds.yml` runs at 00:07, 06:07, 12:07, and 18:07 UTC (plus manual dispatch) with `--scheduled`. The job key is the 6-hour slot, so late or duplicate cron runs still collect once per slot. About 124 runs/month × 3 credits ≈ 372, under `MONTHLY_CREDIT_BUDGET=400`.
- `migrate-production.yml` applies committed migrations to Supabase when `packages/db/drizzle/**` changes on `main` (CI has already run them against Postgres 17).
- Secrets `DATABASE_URL` (Supabase pooler) and `ODDS_API_KEY` are GitHub repository secrets.

**Caveats:**

- GitHub cron can run late or skip runs under load.
- GitHub disables scheduled workflows in public repos after 60 days without repo activity.
- Failure emails go to the account that last changed the cron.
- The monthly budget sum is per database: local dev runs don't count toward Supabase's total. The provider-reported remaining-credits floor (`MIN_CREDITS_REMAINING`) is account-wide, so it still protects the quota.

AWS Lambda + EventBridge remains an optional later upgrade (Phase 3).

## ADR-020 — Line history semantics and charts (2026-10-16)

**Decision:**

- History is computed per book (`buildBookSeries`).
  - A **change** is a different point or price from the previous observation. It's detected by value and reported as an interval, never an exact time.
  - A **gap** is consecutive observations more than 12 h apart (2× the collection interval).
  - The default `changes` resolution keeps first, last, changes, and gap edges, so downsampling never drops a movement.
- Charts (Recharts, client component) use step-after lines and hold a value only _within_ a continuous segment:
  - null before a book's first and after its last observation;
  - null across gaps, so the line breaks.
- Point and price are separate charts (never a dual axis).
- Prices are plotted on a continuous scale (−110 → −10, +110 → +10), so moves through even money aren't exaggerated by the 200-point jump between −101 and +101. Ticks are labeled in American odds.
- Each feed has a fixed color (`FEED_COLORS`). The palette was validated for CVD and contrast on the dark surface, and a legend, change dots, and change tables mean color is never the only cue.

## ADR-021 — Synthetic history for demos and end-to-end tests (2026-10-16)

**Context:** Real history accumulates slowly (4 snapshots a day), but the history UI and e2e tests need multi-day data now. Fabricated odds must never be mistaken for real data.
**Decision:**

- `generateSyntheticHistory` (deterministic PRNG) produces provider-shaped payloads.
- `seed:synthetic` runs them through the **real collector** with `source = "synthetic"` and job keys `synthetic:<time>`. Synthetic runs skip the credit-budget guard.
- The seed script refuses any database whose name lacks `e2e` or `demo`, and it doesn't read `.env.local`.
- Every page shows a "Synthetic data: not real odds" banner when synthetic rows are present.

**Consequences:** UI work and Playwright tests are reproducible without touching production or spending credits.

## ADR-022 — Odds API terms review; private deployment (2026-10-16)

**Terms review** (https://the-odds-api.com/terms-and-conditions.html, read 2026-10-16; not legal advice):

- **Allowed:**
  - Displaying data in a website or app, including commercially, as long as the data isn't "the primary product being sold or redistributed".
  - "Storing our data and retaining it indefinitely" (this covers `ingestion_payloads`).
  - Research, analytical dashboards, and training ML models.
- **Prohibited:** reselling or redistributing the data "as a standalone data product", including "through your own API, data feed, downloadable files", or as a competing raw-data source.
- **Optional:** attribution. **Encouraged:** responsible-gambling messaging. Brand names may be used for identification only.

**Decision:**

- Deploy privately for now. `proxy.ts` enforces HTTP Basic auth on every page and API route whenever `BASIC_AUTH_PASSWORD` is set. That covers `/api/*` too, because a public JSON API would be redistribution.
- `/api/health/live` stays open; it returns no data.
- Comparisons are constant-time over SHA-256 digests.
- Auth is app-level rather than Vercel Deployment Protection, so it works on any plan and protects the production domain too.
- **Fails closed:** on Vercel (`VERCEL` set), a missing `BASIC_AUTH_PASSWORD` returns 503 instead of serving data.
- A site-wide footer adds the not-betting-advice notice, "Gamble responsibly. 21+ where legal. 1-800-GAMBLER", and a statement that MarketScope isn't affiliated with any sportsbook.

**Consequences:** For a portfolio launch, the UI could go public (permitted) while `/api/*` stays behind auth. Revisit the matcher then.

## ADR-023 — Market replay semantics (2026-10-16)

**Decision:**

- **State at T** (`stateAt`): each book's latest observation at or before T. If it's older than the freshness window (12 h, the same as the gap threshold), the book is _stale_. It's shown as "last seen … (N h old)" and excluded from consensus and dispersion. Books with nothing yet show "no data yet". Nothing is carried forward silently, and nothing after T is ever used.
- **Exact replay needs every observation.** The replay page loads `resolution: "all"`, because change-compressed series would make unchanged-but-observed books look stale.
- **One feed per board book at T:** the preferred feed if it's fresh, otherwise any feed with data. Hard Rock AZ and IN are never both counted.
- **Consensus at T:** the median line of fresh books (≥ 3), with dispersion (range, σ, mean absolute deviation, books ≥ 0.5 off) from `calculateBookDispersion`. Moneylines have no line consensus.
- **Movements** (`describeMovement`) give direction in home orientation:
  - The home spread rising (−3.5 → −2.5) moves _toward the away team_; AWAY series are sign-flipped so labels agree.
  - Totals move up or down; price-only changes are labeled as such.
- **Key numbers** (`detectKeyNumberCrossings`, 3 and 7) use signed values, so −3.5 → +3.5 crosses −3 and +3 while −1.5 → +1.5 crosses nothing. Events are classified as crossed, landed-on, or left. This is descriptive only.
- The replay cursor steps through actual snapshot times only, never interpolated times.

**Consequences:** The Signal Lab (Phase 5) can reuse `stateAt`, consensus, dispersion, and `describeMovement` directly.

## ADR-024 — Signal Lab: pure versioned definitions, stored with evidence (2026-10-17)

**Decision:**

- Six v1 signals (`docs/SIGNAL_DEFINITIONS.md`) are computed by `computeSignals`, a pure and deterministic function (total ordering) over a game's pregame observations.
- They're stored in `market_signals` with type, version, window, value, details, and `evidence_observation_ids`.
- Recompute is idempotent: delete and insert per (game, type, version) in one transaction. It runs after every scheduled collection (`signals:compute`, games kicking off from −2 d to +14 d) and on demand.
- Contemporaneous signals compare only same-snapshot quotes, with one feed per board book.
- **Divergence** uses the full-snapshot median. This replaces my initial leave-one-out design after a test showed it flags the non-outliers when only 3 books report.

**Consequences:**

- The UI (`/signals`, plus game pages) and `/api/signals` only read stored rows.
- Every signal deep-links to the replay at its snapshot (`?at=`).
- Changing a definition means bumping its version; old rows remain for comparison.
