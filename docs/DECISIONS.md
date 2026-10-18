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

## ADR-025 — Research in Python with pre-registered designs (2026-10-17)

**Decision:**

- Studies live in `research/` (Python 3.11, pandas, psycopg; pinned `requirements.txt`) and read the database through a **read-only session**.
- Each study fixes its event definition, outcome, baseline, and minimum sample in code and in the report _before_ results are read. Below the minimum, the verdict is "inconclusive" and no claim is made.
- Inference resamples games (clustered bootstrap), because observations within a game are correlated.
- Key quantities are recomputed independently in Python (e.g. the consensus) and cross-checked against what the TypeScript engine stored.
- Synthetic data is never mixed with real data.
- Pytest runs in CI.

**Consequences:** The first study (outlier → convergence) is honestly inconclusive on 2 days of data, and the report is the reproducible baseline to re-run. Phase 7 (ML) will follow the same rules.

## ADR-026 — Historical backfill from OddsPapi as derived snapshots (2026-10-17)

**Context:** The study and ML need more games than live collection, which began 2026-10-16, can provide. OddsPapi's `/v4/historical-odds` is free and returns per-line-move history since January 2026. Validation against our own observations matched 100% for FanDuel, 92% for DraftKings, 85% for Hard Rock, and 44% for BetMGM (PROVIDER_COVERAGE.md).
**Decision:**

- Import completed NFL games that **kicked off before live collection began** (default `--to 2026-10-16T00:00Z`). The importer also refuses any game already present from another source, so **each game has exactly one source** and snapshots never mix providers.
- **Derive snapshots** from the change log on the live cadence: every 6 hours at 00/06/12/18 UTC within the 30 days before kickoff, plus a **near-close snapshot 5 minutes before kickoff**.
  - At each snapshot, a book's quote is its latest _active_ entry, following OddsPapi's change-log semantics: no heartbeats, a price holds until replaced or deactivated.
  - The main line is the market whose sides are both active and priced closest to even (matched 30/32 in validation).
  - `bookmaker_updated_at` is the provider's change time; `observed_at` is the snapshot time.
- **Books:** DraftKings, FanDuel, Caesars → `williamhill_us`, Hard Rock → `hardrockbet` (the provider's generic feed), and Pinnacle as a **reference book** (`REFERENCE_BOOKMAKERS`; never on the board or in consensus). **BetMGM is excluded.**
- One idempotent run per fixture (`oddspapi:<fixtureId>:v1`, `request_type = historical`) and one transaction per game. Failures are recorded and retried cleanly.
- **Raw payloads are not stored** (about 90 MB per game; Supabase free tier is 500 MB).
- The per-run unique constraint gains `observed_at` (migration 0005), because a historical run holds many snapshot times. Live runs are unaffected since they have one `observed_at`.

**Consequences:**

- About 3,500 rows per game; 79 games from Weeks 1–6 is roughly 280K rows.
- Replay, signals, and the study work unchanged on imported games. The replay page labels the source.
- Carry-forward depends on OddsPapi capturing every change, which is why BetMGM is excluded. Treat imported timing as approximate within a snapshot.
- Uses about 1 billable request per run (fixtures). History calls are free.

## ADR-027 — Sort-matching indexes, live-only run health, coverage page (2026-10-17)

**Context:** MS-023 reviewed the hot queries with `EXPLAIN ANALYZE` against production (about 160K observations after the OddsPapi import).
**Decision:**

- **Indexes match the query's ORDER BY exactly, including null ordering.** A plain `ORDER BY x DESC` means `NULLS FIRST`, and Drizzle's `.desc()` index generates `NULLS LAST`. The planner won't treat those as the same ordering, even on a NOT NULL column. So:
  - Signal Lab read every row in its window and heap-sorted it.
  - `latestQuotesForEvents` sorted instead of reading groups off the index.

  Migration 0006 rebuilds the three `DESC` indexes as `DESC NULLS FIRST`. The signals index becomes `(detected_at DESC, id)` to match `listSignals`' tie-breaker.

- **Run health counts live collection only.** `latestCompletedRun` and `recentRuns` filter `request_type = 'live'`. Before this, the import's 79 `completed` runs made the board's "snapshot collected" label and `/api/health/data` report the import time, which would have masked a dead cron.
- **Coverage page** (`/data`): counts only, never prices. Coverage is measured on the home spread, the one market every book posts. Feeds are mapped to board columns in SQL so Hard Rock's two feeds count once per snapshot.
- **Reproducible EXPLAIN tool** (`packages/db/src/scripts/explain.ts`): runs the real query functions, captures their SQL via Drizzle's logger, and explains each one in a read-only transaction.

**Consequences:**

- Index matching is now a review rule for any new `ORDER BY … DESC` query.
- The coverage query aggregates once and joins. Correlated per-game subqueries cost 575 ms; the rewrite costs 141 ms. If it passes about 500 ms as history grows, move it to a summary table refreshed after each collection run.

## ADR-028 — Football context and MarketScope Ratings ("KenPom for the NFL") (2026-10-17)

**Context:** Jack asked for MarketScope to model the football itself as well as the market: results, home/away, weather, injuries and active players, snap counts, coaching and play-callers. The core is an internal team model of offense, defense and special teams built on EPA, in the style of KenPom (adjusted efficiency, tempo, luck, strength of schedule). The original spec listed weather, injuries and team stats as later ML features, "subject to licensed point-in-time availability". Free, licensed sources now cover them:

- nflverse (CC-BY 4.0): play-by-play with EPA since 1999, schedules, injuries, PFR snap counts, depth charts, rosters, officials.
- Open-Meteo Previous Runs (CC-BY 4.0): point-in-time forecasts from 2024.

**Decision:**

- **New product pillar, "Football context."** MarketScope Ratings follow a KenPom output contract:
  - AdjO and AdjD in points per drive, AdjPace, AdjST, and AdjEM in points per game, each with a standard error.
  - Luck (actual minus expected wins) and its decomposition.
  - SOS (played, remaining, non-division, opponents' AdjO/AdjD) and the Five Factors.
  - A weekly Matchups page with predicted scores, and a week-by-week time machine.

  The full design is frozen in `docs/RATINGS.md` before any data is seen.

- **The engine is a dynamic, opponent-adjusted Kalman filter** (Glickman–Stern state-space) over unit strengths. It is fed luck-adjusted, win-probability-weighted EPA channels and has a QB layer and an availability layer.
  - Continuity of play-caller and QB conditions the between-season carryover.
  - A classic KenPom iterative adjustment runs alongside it as an explainable benchmark.
- **The model line is shown in the app** (Jack's decision), labeled "model estimate" with its measured historical error. It is never presented as a pick.
  - The displayed rating uses no market inputs. Market-implied ratings are shown beside it for comparison.
  - A model + market blend is research only.
- **Validation:**
  - Walk-forward, week by week.
  - Seasons: 2016–22 for fitting, 2023–24 for validation and factor selection, 2025 as a test run exactly once.
  - **2026 is a live forward test**, with immutable predictions written before kickoff.
  - Benchmarks: naive, SRS, Elo, market-implied ratings, and the closing line.
  - A candidate factor enters the model only if it improves validation beyond noise.
- **New Python app `apps/football/`.**
  - Why Python: nflverse and the numerical tooling are Python-native. `research/` stays read-only.
  - The schema stays in Drizzle migrations, with RLS on every table.
  - Raw play-by-play and participation stay in a gitignored local cache; only aggregates go to Supabase.
  - Coordinators and play-callers come from a curated, sourced CSV, because no free dataset covers them.
- **Order** (Jack's decision): the market-only ML baseline first (Phase 7), then football data (8), ratings (9), and studies plus ML with football features (10). That way the football features' lift is measured, not assumed.
- **Player depth** (Jack's decision): team ratings plus an availability adjustment (snap-share-weighted, probabilistic by injury status, separate QB value). Player on-field impact from participation data is local research only, because FTN's data is CC-BY-SA and only arrives after each season.

**Consequences:**

- New CLAUDE.md rules: point-in-time features, no same-game results, the nflverse close as a labeled benchmark, labeled model output, attribution, immutable predictions, no market inputs in the displayed rating, factors earn their place.
- Storage: aggregates, snaps for the current and previous season, ratings and predictions are estimated at about 30–40 MB. Measured after the backfill against the PERFORMANCE.md thresholds.
- A new scheduled workflow (`football-data.yml`) reuses the existing `DATABASE_URL` secret. No new secrets, cloud resources or paid plans.
- Expected and stated up front: the model should beat SRS and Elo and lose to the closing line. The interesting findings are which components matter, and where performance and price disagree.

## ADR-029 — Team-game measurement layer: definitions frozen before ratings (2026-10-18)

**Context.** MarketScope Ratings (ADR-028) observe each team-game through efficiency "channels". How those channels are defined (which plays count, how garbage time and turnovers are treated) shapes every rating. Choosing definitions after seeing ratings would be tuning on the answer.

**Decision.**

- **One row per team per final game** (`nfl_team_game_stats`), offense plus own special teams. Defense is the opponent's row, so offense and defense come from the same observations.
- **Raw and model channels side by side.** Raw EPA follows nflfastR conventions (passes incl. sacks/scrambles and runs, including penalty-nullified plays). The model channel (`adj_*`) applies, in order:
  1. a **luck adjustment** that replaces fumble-recovery and interception outcomes with expectations (recoveries at the 2016–22 lost rate, 46.1%; interceptions at 19.0% of passes defensed);
  2. a **cap** at ±4.5 EPA per play (≈ the 1st/99th percentile), so one return touchdown cannot dominate a game;
  3. **win-probability weighting**: full weight inside 10–90% WP, falling linearly to 0.25 at the extremes (FPI-style garbage-time handling without discarding plays).
- **Constants are fit on 2016–22 only** (`python -m marketscope_football.luck_fit`) and frozen in `design.py`. Changing any of them bumps `STATS_VERSION`, and each season is replaced wholesale, so versions never mix.
- **Play-by-play stays out of Postgres.** A gitignored Parquet cache with a manifest (nflreadpy version, rows, SHA-256) records exactly what each run aggregated. The DB holds ~6K rows (≈ 2 MB).
- **Cross-check, not trust.** Counts must match nflverse's independently built team stats; EPA must match once aligned to their definition. The report is committed.
- **Automation.** `football-data.yml` runs daily at 13:00 UTC for the current season (schedules/results/links, then team stats), reusing the existing `DATABASE_URL` secret. Runs are idempotent per UTC day and data hash.

**Consequences.** Whether each treatment helps (luck adjustment, WP weighting, cap) is an ablation in MS-030, measured on 2023–24, not an assumption. League-wide luck relative to the 2016–22 baseline is not exactly zero in later seasons (interception rates fell), which shifts all teams equally and cancels in opponent-adjusted ratings.

## ADR-030 — Availability data: injury snapshots, snap counts, and what stays out of Postgres (2026-10-18)

**Context.** Availability (who plays) is a large part of any NFL prediction (ELWAY, FPI). Three nflverse sources matter: injury reports (2009+), PFR snap counts (2012+) and depth charts (2001+, daily snapshots from 2025). Two questions: what is point-in-time, and what belongs in the database.

**Decision.**

- **Injury reports are captured as a history, not a table of final values.** nflverse publishes the latest report for each week, so intermediate statuses are lost unless we record them. Twice a day (13:00 and 23:00 UTC), `nfl_injury_reports` appends any change seen before the team's kickoff, with `first_seen_at`. This is our only irreplaceable football capture, and it feeds the R2 injury-news event study.
- **History is backfill, not live.** Rows first seen after kickoff, including every past season, get `first_seen_at` NULL and are assumed known before kickoff, because teams must publish the final status report the day before the game. The import time is never assigned to history (the same rule as odds, ADR-026).
- **Postgres holds what the product shows plus irreplaceable captures:** injury reports and snap counts for the current and previous season (≈ 11 MB). Modelling reads older seasons, and depth charts, directly from nflverse. They are re-fetchable, and depth charts would add tens of MB for nothing the UI shows yet.
- **P(plays | status) is measured, not assumed** (`reports/plays-given-status.md`):
  - Out: 0%. Doubtful: 0.9%, against ELWAY's ≈ 7% for quarterbacks.
  - Questionable: 68% (2016–22) and 66% (2023–25).
  - The last practice of the week moved the Questionable rate from 41% (missed) to 85% (full) in 2016–22, but only from 52% to 71% in 2023–25. MS-031 therefore lets the practice effect drift instead of freezing 2016–22 values.

**Consequences.** Live injury history starts on 2026-10-18 (Week 6). Earlier 2026 weeks and 2025 exist only as final reports. Injury-news timing studies can use only live rows, and timing is known only to the interval between two snapshots, as with odds.
