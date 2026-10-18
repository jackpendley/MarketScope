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

## ADR-031 — Coaching staff and play-callers: assembled, sourced, validated (2026-10-18)

**Context.** The ratings design conditions season-to-season carryover on play-caller and QB continuity, and Jack asked for coaching to be modelled. No free dataset records coordinators or play-callers. nflverse has head coaches per game, but they turned out to be stale for recent seasons: interims are missing from 2024, and the season in progress shows last season's coaches.

**Decision.**

- **Assemble rather than hand-type.**
  - Head coaches come from nflverse (exact weeks) wherever it names every head coach the Wikipedia staff page lists. Elsewhere they come from the staff page plus dated changes.
  - Coordinators come from Wikipedia's end-of-season staff (current staff templates for 2026), cited by revision.
  - The Wikipedia pages are fetched through the MediaWiki API (polite user agent, cached).
- **Play-callers are a separate fact from titles.** Several OCs did not call plays (Lombardi 2022–23) and several callers held no coordinator title (Patricia 2022, Sullivan 2023, Downing 2024, Steve Belichick 2019–23).
  - The caller for each team-week is a season list, then dated overrides, then the default rule (the side's coordinator, or the head coach when there is none).
  - Every row states its basis (`list`, `direct`, `bracketed`, `stint`, `rule`) and source. Unsourced defaults are visible, not hidden.
- **One CSV is the source of truth**, versioned in git and validated before load:
  - exactly one HC, one offensive and one defensive play-caller per team-week
  - no overlapping spans
  - a source on every sourced fact

  CI runs the same validation on the committed file.

- **Current season.** Changes are applied by hand when announced, with their effective date. A daily drift check warns when a team's Wikipedia staff page differs from the CSV.

**Consequences.**

- Offensive play-callers are sourced for about 69% of team-weeks (51% by full season lists); defensive play-callers for about 10%.
- Defensive analyses must treat the coordinator-calls default as an assumption. RATINGS.md R7 states this.
- About 40–55% of teams start each season with a new offensive play-caller, so the continuity factor has plenty of variation.

## ADR-032 — Weather and game context: reproducible point-in-time inputs (2026-10-18)

**Context.** Weather, rest, travel and time zones are standard factors in NFL models (538, ELWAY, nfelo). The factor catalog marks them `test`: they must earn their place on 2023–24 validation. For a forecast to be usable in a backtest, we must know what it said before the game, not after.

**Decision.**

- **Weather forecasts:**
  - Use Open-Meteo's Previous Runs API. `*_previous_dayN` is the value predicted N × 24 h before the hour, so forecasts at 1, 3 and 7 days are reproducible point-in-time inputs from 2024 (the archive's start). Lead 0, the latest run, is kept as a near-kickoff reference.
  - Fetch only outdoor and retractable venues. Average over the game window.
  - The daily job adds leads as they elapse. No API key, no new secret.
  - Observed game weather (nflverse) stays post-hoc and is used only to measure forecast skill.
- **A venue catalog instead of nflverse stadium strings:**
  - 49 venues with curated roof type, Wikipedia coordinates, and Open-Meteo elevation and IANA time zone.
  - An alias table maps nflverse's 64 stadium names.
  - A sourced override table fixes the 2025 international games that nflverse labels with the home team's stadium.
- **Context features are computed, not curated:** rest, bye, short week, travel, time-zone shift, body clock, altitude, road streak, and head-coach and play-caller tenure. Censored tenures are NULL rather than understated.
- **Week-18 incentives** (clinched or eliminated) need standings and tiebreakers. They move to MS-034 with the season simulation.

**Consequences.**

- Forecast skill is measured (`reports/weather-forecast-skill.md`). Temperature r = 0.98 at 1 day and 0.94 at 7 days; wind r = 0.74 at 1 day but 0.34 at 7 days. So wind enters only from short leads, and the R3 study uses 1 and 3-day leads.
- Weather exists only for 2024+, so any weather factor is validated on 2024 alone, then tested once in 2025. It must show a large effect to earn a place.

## ADR-033 — Evaluation harness: structural point-in-time, paired comparisons, a guarded test season (2026-10-18)

**Context.** Every rating and factor from MS-030 on is judged by walk-forward accuracy on 2023–24 against simple benchmarks and the market close (RATINGS.md, Validation protocol). Each one must be scored the same way. Look-ahead must be impossible rather than just discouraged, and 2025 must stay untouched until MS-032.

**Decision.**

- **One runner for every model** (`eval/walkforward.py`). Models implement `predict(games)` and `update(results)`. For each (season, week) the runner calls `predict` with every result column removed, records the predictions, and only then calls `update`.
  - Tests: a model that reads a result column fails, and predictions don't change when later games are deleted.
- **The test season is guarded in code.** The runner raises if asked to score 2025 without `allow_test=True`, which only MS-032's one-time run will pass.
- **Pre-registered design** (`eval/design.py`): season roles, bootstrap, benchmark constants and tuning grids, fixed before any benchmark ran.
- **Benchmarks:**
  - naive home field
  - FiveThirtyEight Elo with its published constants (no tuning)
  - SRS and market-implied ratings as **one weighted-ridge estimator on two targets** (results vs past closing spreads), tuned only on 2016–22
  - the nflverse close itself
- **Win probability from a margin:** Φ(margin / σ), with σ fit by maximum likelihood on 1999–2015 closing lines, outside every scored season. The key-number-aware distribution replaces it in MS-032.
- **Paired comparisons:** every table reports bootstrap CIs resampling games and paired differences against a reference on the same games.

**Consequences.**

- On 2023–24 (570 games) the close has margin MAE 9.84; Elo 10.33, SRS 10.37 and market-implied ratings 10.37 sit about 0.5 behind (paired CI about ±0.25); naive home field is 11.16. These match the published ranges.
- Absolute MAE CIs are wide (±0.7), but paired differences are tight. So a model or factor is judged by its paired difference against a baseline, never by comparing two separate intervals.
- The bar for MS-030 is concrete: beat Elo/SRS by a margin whose paired CI excludes 0, and close part of the 0.5-point gap to the close.

## ADR-034 — Kalman unit ratings: separate channel filters, a fitted game layer, and an honest first result (2026-10-18)

**Context.** RATINGS.md specifies a Kalman filter over opponent-adjusted unit strengths, with parameters fit by maximum likelihood on 2016–22 and judged in the MS-029 harness (ADR-033). Building it required four choices the frozen design did not pin down. All four were made on 2016–22 before 2023–24 was scored, and are recorded here as deviations.

**Decision.**

- **One filter per channel, no cross-channel covariance:**
  - pass EPA/dropback, rush EPA/rush, success rate, points per drive: each with 32 offense + 32 defense units and a league mean
  - special teams: 32 units
  - This makes the likelihood fast (0.05 s) and every parameter interpretable. The cost is that correlated channels don't share strength inside the filter. The game layer combines them instead.
- **Points per drive is a channel.** KenPom's AdjO is defined in points per possession, and nfelo finds margin carries signal beyond EPA. Adding it cut in-sample MAE from 10.05 to 10.02, so it was kept before validation.
- **The game layer is OLS** of the actual margin on the filter's pre-week expected features (one weight per channel plus home field), on 2016–22. It is not part of the joint likelihood.
- **QB continuity is deferred to MS-031**, which owns QB state. Season reversion is conditioned on play-caller continuity only.
- **Burn-in:** the filter starts in 2012 (play-by-play cached from then). 2012–15 never enter the likelihood.
- **Ablations are refitted:** each measurement and structural variant is fitted from scratch. Channel ablations keep the filters and refit the game layer.

**Consequences (2023–24 validation, 570 games, run once).**

- Margin MAE 10.33, the same as Elo (Δ +0.00, CI −0.20 to +0.21) and SRS (Δ −0.04, CI −0.21 to +0.14). **The bar set in ADR-033 (beat Elo/SRS with a CI excluding 0) is not met by unit ratings alone.**
- The model is better early in the season: weeks 1–4 Δ −0.31 vs SRS (CI −0.61 to −0.00) and −0.28 vs Elo. That is where season reversion matters. From week 5 on it is level.
- The filter itself matters: ridge with a half-life on the same EPA is 0.17 worse (CI +0.01 to +0.32).
- None of the ADR-029 measurement adjustments (luck, cap, WP weighting) is distinguishable at this sample size. The same holds for play-caller continuity (likelihood-ratio p = 0.66 on 2016–22) and for any single channel. They stay in the model because the design specifies them and none of them hurts. Factor selection is MS-032's job.
- Offense carries over between seasons more than defense (pass ρ 0.72 vs 0.40; rush 0.58 vs 0.58). Offensive team spread is wider than defensive in every channel.
- The validation seasons have now been looked at once for this model. Further changes are decided on 2016–22, and 2025 remains the clean test.
- The expected source of further lift is MS-031 (QB and availability). That is consistent with MS-029's finding that the close's edge comes from news in the week of the game.

## ADR-035 — The KenPom contract: weekly point-in-time snapshots in Postgres (2026-10-18)

**Context.** The Kalman engine (ADR-034) estimates unit strengths. The product promise is KenPom-style output: AdjO, AdjD, AdjEM, pace, luck, SOS and the Five Factors, with uncertainty, for any past week. MS-033's pages need it in Postgres.

**Decision.**

- **One table, `rating_snapshots`.**
  - One row per model version, season, week and team. Week 0 is the preseason prior; week w is after all of week w's games.
  - Everything is computed from games played by then (plus the published schedule for remaining SOS), so every row is point-in-time.
- **AdjO/AdjD are in points per drive, derived through the game layer:** AdjO = league points per drive + (weighted offensive channel units ÷ league drives).
  - AdjEM = (AdjO − AdjD) × drives + AdjST therefore holds exactly, and AdjEM is the expected margin against an average team.
  - SEs come from the filters' covariances. The channels are independent filters, so variances add.
- **Pace and totals:**
  - A pace filter with 32 units and a league mean observes each game's drives per team as mean + pace[H] + pace[A], as in KenPom's tempo.
  - The game total = expected drives × both offenses' expected points per drive, calibrated linearly on 2016–22.
  - Each team's predicted score = (total ± margin) ÷ 2, so the scores sum to the total and differ by the margin.
- **Luck:**
  - Expected wins come from a logistic of each game's net adjusted EPA with a home term, fitted on 2016–22.
  - Pythagorean exponent fitted on 2016–22.
  - The decomposition: one-score games, fumble, INT and FG luck, and return TDs.
- **Classic KenPom** (iterative multiplicative adjustment on raw points per drive) is implemented as a benchmark. It is reported by rank correlation, not stored.
- **A week is published only when complete:** a week whose final games lack play-by-play is held back.
- **Daily refresh:**
  - `ingest ratings` rebuilds every snapshot for the version: about 7.4k rows, 20 s. Filtered snapshots are deterministic, so history is rewritten identically.
  - Play-by-play for 2012+ is kept in the Actions cache.
  - The model version stays `kalman-v0` until `ratings-v1` is frozen in MS-032.

**Consequences.**

- **Home term:** home teams outscore their scrimmage efficiency by about 1.4 points (2016–22). The expected-wins model keeps that as a home term rather than counting it as luck. Penalties, whose plays the channel excludes, are a plausible cause.
- **Pythagorean exponent:** 2.79 (classic 2.37).
- **Agreement with classic KenPom:** about 0.6 rank correlation at week 4 and about 0.92 at the end of the regular season. They agree on who is good once data accumulates; early on the Kalman engine leans on its prior.
- **Totals on 2023–24:** MAE 10.22, better than naive (−0.36, CI −0.64 to −0.10) and 0.26 behind the close (CI +0.04 to +0.48). That is a smaller gap than on margins (0.49).
- **Not yet built:** remaining-schedule projections (projected record) need the season simulation (MS-034).

## ADR-036 — QB layer: point-in-time expected starter, shrunk QB ratings, a team baseline (2026-10-18)

**Context.** MS-029 found that the close's edge over the ratings is news in the week of the game. The biggest single piece of that news is who plays quarterback. RATINGS.md specifies a QB layer that compares the expected starter's value with the team's QB baseline (538-style), using P(plays | status) from the injury history.

**Decision.**

- **Expected starter (rule R5, chosen on 2016–22 among five rules):**
  - Default: the team's previous starter.
  - If the injury report lists him Out or Doubtful: depth-chart QB1, or QB2 when QB1 is the injured starter.
  - In a team's first game of a season: depth-chart QB1.
  - If listed Questionable: he plays with probability 0.637 (2016–22: 79 of 124 started), else his replacement.
- **Sources and timing:**
  - Depth charts are weekly through 2024. From 2025 they are timestamped, and we take the latest chart at least 24 h before kickoff.
  - The injury report is the final weekly report.
  - Weekly charts showed no sign of leaking the actual starter: they predict starter changes worse (37%) than the timestamped charts (62%).
- **Accuracy (names the actual starter):**
  - 2016–22: 92.3%, vs 88.2% for the previous starter alone.
  - 2023–24: 91.0%. 2025–26: 93.1%.
  - A "the main starter returns" refinement was rejected: it mistakes benchings for injuries.
- **QB rating:**
  - Time-decayed (half-life 730 days), shrunk mean of the QB's adjusted EPA per dropback relative to the league. Same measurement as the pass channel.
  - Prior: 250 dropbacks at replacement level, −0.106 EPA/dropback (the first 150 dropbacks of QBs who debuted 2013–22).
- **Team baseline:** the dropback-weighted, time-decayed (half-life 112 days) average of the current ratings of the QBs who threw the team's recent passes. That is the QB quality its pass ratings were learned from.
- **Game feature:** league dropbacks per game × (expected starter rating − baseline), home minus away. It is added to the OLS game layer (weight 0.51; with the actual starter in hindsight, 0.89).
- **Settings:** the three settings were chosen on a 27-point grid by in-sample MAE. Two sit at the grid's edge; the grid was not extended.
- **AdjEM stays a team rating without the QB term.** The QB adjustment is a game-level factor, like home field.

**Consequences.**

- **In-sample (2016–22):** MAE 10.019 → 9.986 with the expected starter; 9.947 with the actual starter in hindsight.
- **Validation (2023–24, run once):**
  - Overall: no change (Δ −0.00, CI −0.09 to +0.09).
  - In the 87 games where a team's expected starter changed or might not play: Δ −0.19 (CI −0.53 to +0.16), Brier −0.008.
  - Knowing the actual starter would add 0.08 (CI −0.20 to +0.02).
  - The layer points the right way where it should matter, but 87 games is too few to show it.
- **QB continuity at the season boundary is not modeled separately.** The QB feature's baseline already handles a new starter in week 1.
- **Cross-season and live use:** expected starters for upcoming games use today's depth chart and injury report, so the report's model estimates for the next week include them.

## ADR-037 — Non-QB availability: expected absences from the injury report and recent snap shares (2026-10-18)

**Context.** ELWAY values non-QB injuries at 0.5–1 point typically (max about 2). RATINGS.md specifies snap-share-weighted absences by position group × learned positional values, as an expected value over P(plays | status).

**Decision.**

- **Absence per group:** absence[group] = Σ P(miss) × recent share.
  - Groups: OL, WR/TE, RB, DL+LB, DB.
  - Recent share: the player's mean offensive or defensive snap share over the team's previous 3 games this season (0 for games he missed).
  - P(miss) comes from this week's final injury report (Out 1.0, Doubtful 0.991, Questionable 0.323: P(plays | status) for 2016–22, ADR-030) or a reserve roster status (IR, PUP and so on: 1.0).
- **Window effects:**
  - Long-term absences drop out of the 3-game window. By then the filter's ratings reflect the team without the player.
  - Returning players are not credited, a known asymmetry.
  - A game with no snap rows enters the window as one where nobody played. A unit test caught that such games were being skipped.
- **Game features:** home − away absence per group in the OLS game layer, fitted on 2016–22 alongside the QB feature.
- **Data:** snap counts (PFR via nflverse) start in 2013, so 2013–15 give history before the fit seasons.

**Consequences.**

- **Positional values** (points of margin per missing full-time starter): OL −0.72, WR/TE −0.84, front seven −0.55, secondary −0.57, all inside ELWAY's range.
  - RB −2.41 is implausibly large. RB absences are rare and small (mean 0.09 starter-equivalents), so the estimate is noisy. MS-032's factor selection should shrink or drop it.
- **In-sample (2016–22) MAE:**

  | Model          | MAE    |
  | -------------- | ------ |
  | unit ratings   | 10.019 |
  | + QB           | 9.986  |
  | + availability | 9.950  |
  | oracle starter | 9.912  |

- **Validation (2023–24, run once):**
  - Model MAE 10.25 (was 10.33).
  - Without the availability layer it is +0.08 worse (CI −0.00 to +0.17), borderline.
  - Vs Elo −0.08 (CI −0.31 to +0.15); vs SRS −0.12 (CI −0.31 to +0.08).
  - The model now leads both benchmarks, but not yet beyond noise. The close remains 0.41 ahead.

## ADR-038 — Factor selection and win probabilities for ratings-v1 (2026-10-18)

**Context.** The factor catalog marks rest, travel, time zones, altitude, division, playoffs and coaching changes as `test`: each must earn its place. RATINGS.md also specifies a key-number-aware margin distribution. Both rules were pre-registered in `ratings/selection_design.py` and committed before any candidate or distribution was fitted (commits 25c9382 and 193548f).

**Decision.**

- **Selection rule:** a candidate is added alone to the MS-031 game layer and kept only if both:
  - its 2016–22 coefficient has the expected sign with |t| ≥ 2 (HC1), and
  - on 2023–24, paired against the MS-031 model, Δ MAE ≤ 0 and Δ log loss ≤ 0.

  The RB absence value faced the same test by removal.

- **Speed-up:** candidates are tested by refitting only the linear game layer on the recorded walk-forward feature matrix. This is identical to the harness; the matrix reproduces the frozen layer exactly.
- **Margin distribution:** a normal kernel on integer margins times key-number multipliers for |k| ≤ 21.
  - Shape fitted on 1999–2015 closing lines; scale refitted on the model's 2016–22 predictions.
  - Win probability = P(k > 0) + ½ P(0).
  - Adopted only if its 2023–24 log loss is no worse than Φ(m / σ).

**Consequences.**

- **No candidate factor passed.**
  - Rest, bye, travel, time zones, body clock and altitude are near zero or the wrong sign on 2016–22. That is consistent with the post-2011 rest null (arXiv 2408.10867).
  - Playoff home edge: +1.2 points (t 0.9).
  - New head coach: −1.4 points per game (t −2.2, the only one past |t| = 2), but no 2023–24 improvement.
  - RB absence (t −1.8) is dropped.
- **ratings-v1 game layer:** unit channels + QB + four absence groups + home. Its 2023–24 Δ vs the MS-031 model is +0.01 (CI −0.03 to +0.06).
- **Key-number multipliers:** 3 → 2.9×, 7 → 2.0×, 10 → 1.4×, 14 → 1.4×, ties 0.04×. Scale 13.66 for the close, 13.05 for the model (in-sample).
  - Adopted: log loss 0.6352 vs 0.6362 (Δ −0.0010, CI −0.0048 to +0.0025).
  - It also gives push and cover probabilities.
- **Against the closing line:** the model's P(home covers the close) has a log loss of 0.715, worse than a coin flip (0.693). Its disagreements with the market carry no information about who covers. That is the expected result for a model 0.4 points less accurate than the close, and it is why the UI shows a model estimate, never a pick.
