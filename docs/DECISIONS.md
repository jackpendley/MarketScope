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

**Context.** The factor catalog marks rest, travel, time zones, altitude, division, playoffs and coaching changes as `test`: each must earn its place. RATINGS.md also specifies a key-number-aware margin distribution. Both rules were pre-registered in `ratings/selection_design.py` and committed before any candidate or distribution was fitted (commits a48d601 and 73a9f33 on main).

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

## ADR-039 — Freezing ratings-v1, the one-time 2025 test, and the live forward test (2026-10-18)

**Context.** RATINGS.md's validation protocol has three stages:

- 2023–24 for selection
- 2025 as an untouched test, evaluated once
- 2026 as a live forward test with immutable pre-kickoff predictions

The test is only honest if the model is fixed before it runs and cannot be re-run after a peek.

**Decision.**

- **Freeze.** `ratings-v1` is the MS-032a parameters. Their canonical sha256 (`c2f6ed74…`) is pinned in `ratings/version.py`, and a test fails if `params.json` changes, so a change requires a new version. Snapshots are written under `ratings-v1`; the earlier `kalman-v0` rows are removed.
- **Test, once.** `ratings/run_test.py`:
  - refuses to run if its report exists or if the parameters differ from the frozen ones
  - requires `--confirm-once`
  - was rehearsed on 2024 (already scored) so a bug could not spend the test
  - writes `reports/test-2025.md` and a run record (`reports/model_runs/`) that `ingest model-runs` loads into `model_runs`

  `model_runs` allows one `test` row per version (a partial unique index).

  Commit order: freeze, test script, result, preserved on main by a rebase merge (8ab2547, af4c08f, a7b8cc9; on the PR #34 branch they were 20d04a0, 30ab657 and f567682, which is why the record's `code_sha` reads 30ab657). The record's NaN entries for metrics a model does not produce were rewritten as JSON null so Postgres accepts them; no result changed.

- **Live forward test.** `model_predictions` is append-only:
  - The daily job adds one row per upcoming game (next 8 days) with the margin, total, team scores, P(home), the expected QBs and the additive contributions (ratings, home, QB, absences).
  - Rows are never updated, and a CHECK requires `predicted_at < kickoff_utc`.
  - The scorecard (MS-033) uses each game's last row before kickoff.
- **Daily inputs.** Depth charts, injury reports, snap counts and weekly rosters are cached per season, and the daily job refreshes only the current season.

**Consequences (2025, 285 games).**

| Model                  | Margin MAE |
| ---------------------- | ---------- |
| ratings-v1             | 10.06      |
| Elo                    | 10.19      |
| SRS                    | 10.19      |
| market-implied ratings | 10.30      |
| close                  | 9.67       |

- Paired results:
  - vs Elo −0.13 (CI −0.42 to +0.17)
  - vs SRS −0.13 (CI −0.39 to +0.14)
  - vs market-implied −0.24 (CI −0.57 to +0.08)
  - vs the close +0.39 (CI +0.07 to +0.70)
- Totals: MAE 10.60 (close 10.42, naive 11.01).
- P(cover the close) scores worse than a coin flip again (0.714 vs 0.693).
- **The honest summary:** across validation and test, ratings-v1 is consistently a little better than Elo and SRS, but never beyond noise. It is clearly behind the market, and it holds no information about the market's errors. The interesting results are the components (QB, absences, luck, the parameter table), not a better line.
- Any later model is `ratings-v2`, with new rows. 2025 is no longer a clean test for it; the live 2026 forward test is.

## ADR-040 — Ratings pages: server-rendered KenPom table, URL state, honest labels (2026-10-18)

**Context.** MS-033 puts the KenPom contract (`rating_snapshots`) and the live forward test (`model_predictions`) on the site. The pages must read like KenPom: dense, ranked, browsable by week. They must also follow the model rules: point-in-time, labeled model estimates with their error, and no pick language.

**Decision.**

- **Server components only.**
  - `/ratings` and `/teams/[abbr]` query Postgres directly (`queries/ratings.ts`).
  - Sorting, conference filter, season and week live in the URL (plain GET forms and header links, like the odds board). That makes them shareable and back-button friendly, with no client JavaScript.
- **Which model is shown:** the frozen `ratings-v1` when present, else the newest other version. A version name containing "synthetic" triggers the synthetic-data banner; the e2e database is seeded with `synthetic-demo`. `/api/ratings` returns the same snapshot.
- **Ranks:**
  - Each sortable column sorts by its rank (AdjD's rank 1 = fewest points allowed).
  - Rank cells use a diverging scale: accent for the top eighths, danger for the bottom eighths, neutral in between.
  - The rank number is always shown, so color is never the only signal.
  - Five Factors ranks are computed on the page from the same snapshot.
- **Team pages:**
  - a server-rendered SVG trend of AdjEM with a ±1 SE band (one series, so no legend; native tooltips per point)
  - Five Factors, the luck decomposition, and the coaching staff with play-callers
  - a schedule with opponent ranks then/now and the last pre-kickoff model estimate (team perspective)
- **Labels:** the ratings intro states that every value is a point-in-time model estimate and gives the 2025-test error next to the market's. Schedule estimates say "not picks".

**Consequences.**

- **Speed:** every ratings query runs in under 10 ms on production (PERFORMANCE.md).
- **Mobile:** tables scroll inside their cards, with no page-level horizontal scroll (an e2e check at Pixel 7 width).
- **Followed by** `/matchups`, the `/model` scorecard and the game-page panel (ADR-041).

## ADR-041 — Matchups, scorecard and game panel: stored estimates only, scored in the open (2026-10-18)

**Context.** MS-033b shows the model's game estimates (a KenPom FanMatch analog), a live scorecard, and the estimate on each game page. Three risks: showing an estimate that wasn't made before kickoff, comparing against the wrong market number, and a scorecard that overstates a handful of games.

**Decision.**

- **Only stored estimates.** Every page reads `model_predictions` and uses each game's newest row created before kickoff. Nothing is recomputed in the web app, so what the scorecard grades is exactly what was shown before the game. Games before the forward test (it began 2026-10-18, week 6) say there is no stored estimate and point to the 2023–25 evaluation.
- **Which market number.** Upcoming games show the board's current consensus (median home spread, at least 3 books, the same rule as the odds board; "n/a" with the book count otherwise). Final games show the nflverse close, labeled. The scorecard grades against the close: margin MAE, Brier with the close's no-vig moneyline probability, and total MAE.
- **Scorecard statistics.** Differences are paired on the same games, with a 95% bootstrap interval that resamples games (2,000 draws, fixed seed, so the page is reproducible). The interval appears from 30 scored games and calibration bins from 50; before that the page shows the point values and says why. The one-time 2025 test record is read from `model_runs` and shown with its intervals, the params hash and the code SHA.
- **Contributions.** Shown as a diverging waterfall that sums to the expected margin: team ratings, home field, quarterbacks, other absences. Expected QBs are named, with their probability of playing when it is below 1.
- **Quality and excitement** are descriptive only. Quality (0–100) is the average league percentile of the two teams' AdjEM ranks going in. Excitement scales it by expected closeness, 1 − |2p − 1|.
- **Labels.** Each page calls the numbers model estimates, gives the 2025-test error next to the close's (10.1 vs 9.7), and says "not betting advice". No pick language anywhere, including "the model's favorite won" rather than a record of picks.

**Consequences.**

- **Speed:** all new queries run in under 3 ms on production (PERFORMANCE.md).
- **Small samples:** the scorecard starts with zero scored games and will be noisy for weeks. The intervals and minimums make that visible rather than hiding it.
- **e2e:** the synthetic seed links week-4 games to the synthetic odds events, adds estimates for played weeks, closes, QB names and a synthetic test record, so every page and the game panel are covered with a synthetic banner.

## ADR-042 — Season simulation: posterior draws, NFL tiebreakers, stored per week (2026-10-18)

**Context.** MS-034 adds playoff, division, #1-seed, conference and Super Bowl odds. The choices: how to carry rating uncertainty, how far to take the tiebreakers, what to assume about future weeks, and how to check it all without touching the 2025 test season.

**Decision.**

- **Uncertainty by posterior draws, not in-branch updating.** Each simulated season draws all 32 true strengths once from the filter posterior (full covariance on the points scale, mapped from the channel filters through the game-layer weights), then adds the filter's weekly random-walk drift. Updating ratings inside a branch (538, ELWAY) approximates the same thing; drawing from the posterior is exact for this model.
- **No double-counted noise.** The key-number distribution's scale was fitted on model errors, which include rating error, so games are played with scale √(13.05² − 10.55) = 12.64. The 10.55 pts² is the average rating-error variance of a matchup at prediction time over 2016–22 (`ratings/simulation.json`).
- **Point in time.** Next week's games use the full model estimate (the same as the stored predictions). Later games use ratings, home field and each team's current QB term: future injury reports aren't known. A team that has clinched the #1 seed (no rival can reach its win total) rests its starter in the final week with probability ⅔ (ELWAY), costing the starter-vs-replacement QB gap.
- **Tiebreakers through strength of schedule, then a coin flip** (nflseedR's default depth): the points-based steps need simulated scores and almost never decide. Division and wild-card procedures follow the NFL's two-club and multi-club rules, including the revert-to-step-one rule and one club per division in wild-card ties.
- **Verification before use.** On the real results the tiebreakers reproduce every 2016–24 playoff field and Wild Card matchup (a committed fixture and test). The backtest covers 2016–24 only, nothing is tuned on it, and it is published with its baselines.
- **Storage.** `season_projections` holds every team after every week since 2016 (10,000 simulated seasons for the current season, 2,000 for history), rebuilt daily with fixed seeds per (season, week), so history is reproducible.
- **Labels.** "100%" means every simulated season, never "clinched". All pages call the odds model estimates.

**Consequences.**

- **Backtest:** clearly better than home-field coin flips for playoffs, division, #1 seed, conference and wins; well calibrated; no skill for the Super Bowl winner. Rating uncertainty barely changes the scores.
- **Cost:** about 2 minutes per daily run (10,000 seasons take ≈ 2 s; history dominates).
- **Not modeled:** seeds other than #1 resting starters, in-season coaching changes beyond the filter's bumps, and future injuries.

## ADR-043 — Research studies: pre-registration committed before code, rating studies stop at 2024 (2026-10-18)

**Context.** Phase 10 runs seven studies over market and football data. With many possible tests and a public repo, the results are only credible if the questions, windows, metrics and decision rules are fixed before any outcome is seen, and if the ratings-v1 test season stays clean.

**Decision.**

- **Pre-registration first.** `research/PREREGISTRATION.md` (all seven studies, one primary hypothesis each, gates, decision rules) was committed and pushed (88adf4f on `main`; first pushed as 168538a, see PR #39) before any study code was written. Study code follows in a later commit, and the PR is rebase-merged so the order survives on `main`. Before writing it, only data counts were looked at, and the doc says so. It also states what was already known (R4 expected null from MS-032).
- **Seasons.** Rating-based studies use 2016–24 only; 2025 remains the untouched ratings-v1 test season. Studies without model output (R1 market accuracy, R3 weather) may use 2025–26.
- **Inference and reporting.** Game-resampled 95% intervals plus HC1 errors; a claim needs its interval to exclude zero in the stated direction. Gates are enforced: a study one game short is reported as inconclusive, with the estimate shown for transparency. Nulls are published. Secondary results are labelled exploratory, with no multiple-comparison correction but every test visible.

**Consequences.**

- **v1 results (R1, R3, R4, R5):** no primary claim met. The consensus 6 days out was as accurate as the close (77 games, 2026). The wind study missed its gate by one windy game. Ratings carry no information beyond the close, and the market does not overrate lucky teams.
- **Re-runs.** R2 (injury news) waits for live injury history; R3 is re-run when the windy-game gate is met. A re-run reuses the frozen design; any change to the design is a new pre-registration.

## ADR-044 — R6 and R7 operational rules (pre-registration addendum A); a static /research page (2026-10-18)

**Context.** The R6 and R7 entries in the pre-registration left details open: the blend's weight rule, which seasons warm it up, how to define "same play-caller" and "same QB". R7 also named a measure (the end-of-season points-per-drive rating) that would build in the effect it tests: ratings-v1 reverts less between seasons when the play-caller stays.

**Decision.**

- **Addendum before code.** Addendum A to `research/PREREGISTRATION.md` (145a5de on `main`, first pushed as 9314b78 in PR #41, before any R6 or R7 code) fixes the rules and says what was already known.
  - **R6 weight:** the Brier-optimal weight on the previous four week slots, clipped to [0, 0.60].
  - **R7 measure:** observed season points per drive instead of the filtered rating.
  - **R7 continuity definitions:** the engine's play-caller boundary rule, and the QB with the most starts.
- **R6 runs in the football eval harness**, a stated exception to "studies read the database only": the walk-forward predictions exist only there. Its pure functions and tests live in `apps/football/.../ratings/blend.py`, and the report goes to `research/reports/`.
- **The `/research` page is static.** `apps/web/lib/research-studies.ts` copies each headline number from a committed report. There is no database table, because results change only when a study is re-run. A unit test checks the shape: every completed study has an estimate inside its interval, a claim needs an interval that excludes zero, and there is no wagering language.

**Consequences.**

- **R6:** the blend is worse than the close (Δ Brier +0.0026, +0.0006 to +0.0047). The displayed rating stays market-free (rule 7) and nothing changes in the product.
- **R7:** no play-caller continuity effect once QB continuity is held fixed; QB continuity matters. This questions ratings-v1's play-caller-keyed reversion. That is a candidate for a future model version, not a change to the frozen one.
- **Upkeep:** the page has to be edited by hand when R2 or R3 is run.

## ADR-045 — Coaching-data audit: week-by-week coordinator check, sourced defensive play-callers, "assumed" and "shared" labels (2026-10-18)

**Context.** A review prompted by Jack found the coaching CSV wrong in two systematic ways.

1. **Mid-season coordinator changes were missed.** Coordinators came from each season article's latest Wikipedia revision, which shows the end-of-season staff. Mid-season changes were captured only through `coordinator_changes.csv`. Any change missing there was applied to the whole season: for example, 2025 NYJ showed Chris Harris, who only took over with three games left.
2. **Defensive head coaches who call their own defence were often missed.** 90% of defensive team-weeks rest on the coordinator rule because no season-wide list of defensive play-callers exists, and some defensive head coaches call the defence themselves.

**Decision.**

- **Week-by-week audit.** `coaching_audit.py` compares the CSV's coordinators for every game with the team's Wikipedia staff template as it stood before game day, using the template's revision history.
  - Disagreements become spans to check against a dated news source.
  - Explained spans are listed with a reason in `data/coaching_audit_accepted.csv`; the target is 0 unexplained.
  - The audit needs the network, so it runs on demand, not in CI.
  - First run: 20 spans. 13 were real coordinator changes, now added to `coordinator_changes.csv`. 7 are explained title differences with no play-calling effect.
- **Defensive head coaches checked one by one.** 21 sourced overrides were added, including:
  - Allen (New Orleans 2022–24, through his firing)
  - Eberflus (Chicago 2024, through his firing)
  - Quinn (Atlanta 2016 from week 13)
  - Ryans (Houston 2025 weeks 1–3)
  - Kuhr (New England 2025 from week 2)
  - Ulbrich (Jets 2024, all season)
  - Saleh, Minter and Hafley (2026)
- **Ambiguity is recorded, not hidden.**
  - A new basis, `shared`, marks seasons where sources say two coaches split the calls: Buffalo 2016 and 2025, Detroit 2019 and Atlanta 2020. The row names the coach reported as primary, because the engine needs one caller per side.
  - `rule` rows are shown as "calls defense (assumed)" on team pages, with an explanation. The page no longer presents an inference as a fact.
- **Corrections flow into the ratings.** ratings-v1's parameters are unchanged. Play-caller continuity is an input, and the daily job rebuilds `rating_snapshots` from it, so corrected data changes the filtered history the way any upstream data fix would.
  - Stored `model_predictions` stay immutable.
  - The 2025 test record stays as it was run.
  - On 2023–24 the corrections move game margins by 0.05 points on average (at most 0.84). Margin MAE goes from 10.268 to 10.259 and Brier from 0.2219 to 0.2216.

**Consequences.**

- **Coverage:** defensive team-weeks resting on the rule fall from 90% to 86%. The rest stay unverified: the coordinator is the likely caller, but no source confirms it.
- **Studies re-run:** R6 is unchanged. R7 is re-run once production holds the corrected staff.
- **Upkeep:** re-run the audit before any study that uses play-callers, and after each season.

## ADR-046 — Historical injury studies R2h and R2w (pre-registration addendum B) (2026-10-19)

**Context.** The live R2 event study needs a timestamp for when a player was first listed Out. Only the daily injury snapshots (from 2026-10-18) record that time, so R2 will wait weeks for its gate. Jack asked whether the historical injury reports could be used. They can, but they carry no publication time, and odds history with movement exists only from August 2026.

**Decision.**

- **Two new studies, live R2 unchanged.** Addendum B was committed before any code (00d778b on `main`, first pushed as f431f0a in PR #44).
  - **R2h** tests whether the close already prices the injury part of each ratings-v1 estimate (2016–24, walk-forward in the football harness, as with R6).
  - **R2w** measures the consensus move from 6 days out to the close against starters newly ruled Out on the final report who played the previous game (2026 weeks 1–6, R1's consensus rules).
- **Robustness added after the result is labelled.** R2w's non-QB-only slope was added after the primary result was seen, and the report and page say so.

**Consequences.**

- **R2h:** no claim (+0.11, −0.27 to +0.50).
- **R2w:** claim met (+0.40 per event, +0.14 to +0.73), robust to excluding QBs (+0.30). This is the first primary claim met in MS-035.
- **Together:** the market moves on confirmed absences during the week and has priced them by kickoff.
- **Live R2 still runs once its gate is met,** with exact first-seen times.

## ADR-047 — Football features in the market-movement model: point-in-time substitutes, v1 split kept (2026-10-19)

**Context.** MS-036 planned four kinds of football feature. Two can't be built point in time for the training weeks (2026 weeks 1–4):

- The full model margin uses the final injury report, published late in the week.
- Live injury statuses with timestamps start in week 6.

**Decision.**

- **Substitutes, fixed in `ml/design_football.py` before any feature code** (9c3ef34 on `main`; first pushed as 85fd030 in PR #46):
  - **Rating-only margin** from the latest usable ratings-v1 snapshot, 16 h after its week's last kickoff.
  - **In-game injury signal:** starters who barely played in their team's latest game, from snap counts at least 36 h old.
  - **Weather:** forecast leads used only once issued.
  - **Schedule:** context features.
  - A unit test perturbs every input usable after t and asserts that no feature changes.
- **Same protocol as v1.** The split, C grid, bootstrap and claim rule are unchanged, so the comparison with the market-only model is paired and like for like. Family ablations are exploratory.

**Consequences.**

- **Will it move:** no lift (Δ Brier +0.0011, −0.0015 to +0.0039).
- **Direction:** worse (Δ Brier +0.0373, +0.0045 to +0.0776). The extra signed features overfit 152 training rows.
- **Exploratory:** the injury family came closest to helping on will-it-move (−0.0025, −0.0052 to 0.0000).
- **Forward check:** pending.
- **v2 waits for more live weeks:** rolling-origin evaluation, plus the live injury snapshots as a direct feature.

## ADR-048 — Portfolio release: automated accessibility checks, synthetic screenshots, documented security audit (2026-10-19)

**Context.** Phase 11 prepares the repository for reviewers: an accurate architecture, a README and case study, screenshots, an accessibility pass and a secret audit. The repo is public, and the site stays password-protected (ADR-022).

**Decision.**

- **Accessibility in CI.** axe-core runs the WCAG 2.1 A and AA rules on every page in the Playwright suite (`@axe-core/playwright` 4.13.0, pinned two months old). Any violation fails the build.
  - The first run found low-contrast "subtle" text, low-contrast secondary text on tinted rank cells, and colour-only links. These were fixed at the token level (`--color-subtle`, `rankText`, underlined links in running text).
  - A skip link was added for keyboard users.
  - Manual checks and known gaps are recorded in `ACCESSIBILITY.md`.
- **Screenshots only from the synthetic e2e database.** An opt-in spec (`SCREENSHOTS=1`) captures them, so no real odds appear in the public repo, and every image shows its synthetic-data banner. Desktop captures are capped at 2,200 px and phone captures are limited to three pages, which keeps the set under 4 MB.
- **Secret audit by value, not only by pattern.** Each real secret was searched for in the full git history, printing counts only, alongside pattern scans. The method and the results are in `SECURITY.md`, so it can be repeated.
- **Wording.** The docs now say "password-protected", not "private". Opening the site means removing the password, which still needs Jack's approval.

**Consequences.**

- **Clean results:** 0 axe violations on all pages and 0 secret matches in the history.
- **Upkeep:** screenshots need regenerating after visible UI changes (`SCREENSHOTS=1 pnpm exec playwright test e2e/screenshots.spec.ts`).

## ADR-049 — Invite-only accounts with Better Auth replace the shared Basic-auth password (2026-10-19)

**Context.** The site was protected by one shared HTTP Basic-auth password (ADR-022). Jack asked for proper accounts: sign in with a username or email and a password, on a well-designed login page. He chose (2026-10-19) invite-only accounts, the Better Auth library rather than our own session code or Supabase Auth, and no email for now.

**Decision.**

- **Library:** Better Auth 1.7.7, pinned 19 days old. It handles email + password plus the username plugin.
  - **Storage:** sessions live in our own Postgres through the Drizzle adapter. The five `auth_*` tables are in `schema.ts` with RLS (migration 0015), so there is no new cloud service and `supabase-js` stays out (ADR-018).
  - **Why a library:** password hashing (scrypt), session rotation and cookie signing are security-critical code better taken from a maintained library than written by hand.
- **Invite-only:** sign-up is disabled. Accounts are created, listed, reset and signed out from `pnpm --filter @marketscope/web users …`.
  - Passwords come from a hidden prompt or stdin, never from arguments.
  - The CLI shows the target database host and asks before changing a non-local database.
  - Users can change their own password on `/account`; that signs out their other sessions.
- **Enforcement in the proxy** (Node.js runtime in Next 16):
  - Every request except `/login`, `/api/auth/*`, `/api/health/live` and static assets needs a valid session.
  - Pages redirect to `/login?next=…`; API routes answer `401 UNAUTHENTICATED` in the standard error envelope.
  - **Fails closed:** on Vercel, a missing or short `BETTER_AUTH_SECRET` returns 503.
- **Hardening, each with a test:**
  - **Rate limit:** 5 sign-in attempts a minute per IP, stored in Postgres so all serverless instances share it.
  - **No account enumeration:** a wrong user and a wrong password get the same message.
  - **Same-origin guard on `/api/auth/*` writes.** Better Auth checks the Origin header only for some endpoints, not the username sign-in.
  - **Origin check forced on:** Better Auth skips its origin check when `NODE_ENV` is "test", so it is set explicitly on.
  - **Open redirects:** the post-login `next` only accepts same-site paths.
  - **Allowed hosts** for the base URL: production, previews and localhost.
  - **Cookies:** httpOnly, SameSite=Lax, and Secure over HTTPS.
- **Sessions last 30 days**, sliding daily, with a 5-minute signed cookie cache.
  - Most requests need no database lookup.
  - Trade-off: a revoked session keeps working for up to 5 minutes.
- **Login page:** a centred card with username-or-email and password (show/hide), plus inline errors. It is covered by the axe accessibility check. The site header and navigation appear only when signed in.
- **e2e:** the global setup creates a synthetic account through the real CLI. A Playwright setup project signs in once and shares the session; the auth specs run signed out.

**Consequences.**

- **Vercel environment:** needs `BETTER_AUTH_SECRET` (Production and Preview). `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD` can be deleted after the switch. Rotating the secret signs everyone out.
- **No self-service reset:** a forgotten password is reset by the owner with the CLI. Email reset is a later, approved addition (a provider account and an API key).
- **Opening the site to sign-ups** remains Jack's decision. `/api/*` stays session-only under the Odds API terms either way.

**Amendment (2026-10-19, MS-038b): password rule.**

- **The rule:** at Jack's request, passwords now need at least 9 characters, including a capital letter and a special character. The original rule was 12 characters with no composition requirement.
- **One source:** the rule lives in `lib/password-policy.ts`. Three places use it:
  - a Better Auth `before` hook on `/change-password` and `/reset-password`, so direct API calls can't bypass the form
  - the account CLI
  - the change-password form
- **Trade-off, noted when the change was made:** NIST SP 800-63B prefers length over composition rules. The remaining protections are rate-limited sign-in, scrypt hashing and invite-only accounts.

## ADR-050 — ratings-v2 (QB-keyed offensive reversion) tested and not adopted (2026-10-19)

**Context.** R7 found that QB continuity, not play-caller continuity, carries an offence's level into the next season. ratings-v1 keys reversion on play-caller continuity, which MS-030 never supported (p = 0.66).

**Decision.**

- **Pre-registered** in `ratings/design_v2.py` before any fit (adc7fdf and e7a5372 on `main`, first pushed as bae64e9 and 1f9b3ba in PR #52).
  - **Variants:** two candidates, chosen by 2016–22 likelihood.
  - **Adoption rule:** the likelihood must be at least that of v1's structure refitted on the same data (a clarification committed before the fit, because v1's stored likelihoods predate the ADR-045 coaching corrections), AND the 2023–24 Δ margin MAE ≤ 0, AND the Δ log loss ≤ 0.
  - **Separate files:** v2 parameters would go in `params_v2.json`. v1's `params.json` is never touched.

**Consequences.**

- **Not adopted.** The QB variant's likelihood was 38.4 against 38.6. The 2023–24 point estimates leaned better but were within noise (Δ MAE −0.005, −0.035 to +0.026).
- **No v2 artifacts:** no `params_v2.json` is written, and ratings-v1 stays the only deployed and forward-tested version.
- **What we learned:** continuity keys barely matter to the filter. Fitted carryover is higher when the QB changes, because the game layer's QB term already models the new starter.

## ADR-051 — Phase 12: the Sharp-Market Lab; CLV as the yardstick; research language (2026-10-19)

**Context.** Jack restated the project's goal. MarketScope is not trying to out-predict sportsbooks. It studies the market to find moves that indicate sharp betting, to learn from them, and to test whether any signals or systems are profitable. The ratings are internal context. The current data and signals can't answer that:

- **Coarse data:** 4 snapshots a day is far coarser than sharp action.
- **No sharp reference:** the live feed has no market-maker book.
- **No profitability test:** the v1 signals aren't scored on whether they beat the close.

**Decision.**

- **Phase 12 order** (Jack's choice):
  1. **MS-041:** data-source evaluation (`docs/DATA_SOURCES.md`).
  2. **MS-042:** a minute-level line-move event store, sharp books included.
  3. **MS-043:** a pre-registered sharp-market study, covering lead-lag, steam, stale retail lines, limits and key numbers.
  4. **MS-044:** a system backtester, starting with Wong teasers.
  5. **MS-045:** a paper portfolio.
  6. **Conditional on data purchases:** MS-046 (a real-time collector and alerts) and MS-047 (reverse line movement with licensed splits).
- **Closing-line value is the primary yardstick.** A signal or system is "sharp" if its side beats the close, measured against Pinnacle's no-vig close or the sharp-book consensus. Win/loss and ROI are reported too, but over NFL samples they are noisy.
- **Pre-registration and holdouts continue** (ADR-043). Every system or signal states its rule before it is scored. Historical systems keep holdout seasons, and 2026 is the live forward test. Mining many systems produces false positives, so the number of systems tested is published.
- **Language (supersedes part of ADR-028 rule 4 and the signal wording rule).** Research pages may describe sharp-book-led moves, steam, backtests, ROI and CLV as analysis.
  - Still no picks, recommendations, "locks" or advice.
  - Paper results are always labelled hypothetical, with the responsible-gambling disclaimers.
  - The site stays invite-only.
  - Signals may say "a sharp book moved first", but not "sharp money" as a claim about who bet.

**Consequences.**

- **Data:** MS-042 builds on OddsPapi's free minute-level history, which was tested and includes Pinnacle, Circa, Bookmaker.eu and the exchanges, with limits. Paid feeds (The Odds API at $59/month for live 5–10-minute snapshots; one month at $119 for a 2022–25 historical backfill) and licensed splits (Sportradar, SharpAPI) each need Jack's approval and come after MS-043 shows what matters.
- **Supabase storage** may become the constraint (minute-level exchange data is large). MS-042 measures it before committing.

## ADR-052 — Minute-level line moves as a separate event table (MS-042) (2026-10-19)

**Context.** OddsPapi's free history logs every price change, for the sharp books (Pinnacle, Circa, Bookmaker.eu) as well as the retail ones. The snapshot import (ADR-026) kept only 6-hourly samples of it, which is far too coarse for the sharp-market study (MS-043). Supabase's free tier (500 MB, about 109 MB used) caps what can be stored.

**Measured on one game (Bears @ Packers, 2026-10-11) before building:**

| What is stored, per game (7 books)                              | Rows   |
| --------------------------------------------------------------- | ------ |
| Raw entries in full-game spread/total/moneyline markets         | ~100k  |
| Main-line state changes, suspensions included                   | ~7,400 |
| Same, but suspensions under a minute ignored, last 14 days only | ~2,200 |

Caesars alone toggled its markets on and off about 900 times, mostly weeks before kickoff. A second game (Buccaneers @ Cowboys) gave 1,734 rows. A full season (~285 games) is therefore roughly 0.5–0.6M rows, about 100 MB with the primary key.

**Measured after the backfill (all 92 finished games, 2026-09-10 to 2026-10-19):**

- **v1** stored 261,436 rows (54 MB). Half were FanDuel limit changes with the line unchanged, so v2 keeps limits for the reference books only.
- **v2:** 132,952 rows (about 1,450 per game) in **23 MB** with the primary key, so a full season is about 70 MB. The database is at 133 MB of 500.
- **By book:** DraftKings 57.8k (24.8k of them suspensions of a minute or more), Caesars 38.4k, Pinnacle 15.1k, Bookmaker.eu 9.6k, FanDuel 5.0k, Hard Rock 4.0k, Circa 3.0k.
- **Cross-check against the stored OddsPapi snapshots:** 98,259 of 98,266 matched (99.99%). Every miss is FanDuel's, consistent with the settle and suspension rules.

**Decision.**

- **New table `line_moves`, separate from `odds_observations`.** Snapshots keep their meaning (ADR-009/026); moves are a different grain. One row each time a book's **main line** changes: the line (home spread or total), both prices, and both limits, with the provider's `changed_at`. Both sides travel together so any row gives a no-vig price.
- **Main line** = the same rule as the snapshot import (`pickMain`: both sides active, priced closest to even). The snapshot transform and the move transform now share that code.
- **Three noise rules** (all in `providers/oddspapi/line-moves.ts`):
  - **Settle:** entries less than 1 s apart are one change, recorded when the burst ends (books write their two sides and alternate lines milliseconds apart).
  - **Suspensions:** a main line off the board for 60 s or more gets a row with no prices, so a later study never mistakes "off the board" for "still offering the old number". Shorter blips are ignored.
  - **Window:** the last 14 days before kickoff, plus the line in effect at the start.
- **Books:** Pinnacle, Circa (`circa`) and Bookmaker.eu (`bookmaker_eu`) as references (`LINE_MOVE_ONLY_BOOKMAKERS`: never on the board, in consensus or in snapshots), plus DraftKings, FanDuel, Caesars and Hard Rock. BetMGM stays out (ADR-026). **Limits are kept for the reference books only** (import v2): in the first backfill, FanDuel's reported limit changed constantly with the line unchanged, producing half of all rows. Exchanges (Kalshi, Novig, ProphetX) are deferred: their histories are order-book depth, millions of entries per game.
- **Games collected live are included.** Moves attach to the game's existing event, whichever source created it, because the separate table means sources never mix in `odds_observations`.
- **Idempotent per fixture** (`oddspapi-moves:<fixture>:v2`); a new import version replaces a game's moves in one transaction.
- **Cross-check:** `import:line-moves --check` compares every stored OddsPapi snapshot in the window with the move in effect at that time. A unit test proves exact agreement with the settle and suspension rules switched off.

**Consequences.**

- MS-043 can measure lead-lag, steam and stale retail lines at second-to-minute resolution, from free data, for the 2026 season.
- Storage is about 70 MB a season. Two or three seasons fit the free tier alongside everything else; beyond that, pruning or the Supabase Pro plan is a decision for Jack.
- History starts in January 2026 (OddsPapi's limit). Earlier seasons need a paid source (`docs/DATA_SOURCES.md`).

## ADR-053 — Sharp-market study: discovery results, a post-hoc split registered for confirmation, signals wait (MS-043) (2026-10-19)

**Context.** Addendum C (`dd570b1`) fixed S1–S5 before any code: CLV in points against Pinnacle's line at kickoff, discovery on 2026 weeks 1–6, confirmation on weeks 7–14 with the same code. The code and tests were committed (`fa4afd5`) before the first run.

**Discovery results** (`research/reports/sharp-market-discovery.md`, 91 games):

| Study                   | Primary                                                                                  | Estimate (95% CI)                           | Result                   |
| ----------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------- | ------------------------ |
| S1 lead-lag             | Share of matched Pinnacle–retail changes where Pinnacle moved first                      | 0.741 (0.680 to 0.798), 216 pairs           | Discovery claim          |
| S2 stale retail numbers | Mean CLV of taking a retail book's old number 60 s after Pinnacle moved (−125 or better) | +0.44 (+0.36 to +0.52) points, 1,450 cases  | Discovery claim          |
| S3 steam                | Pinnacle's further move to the close in the steam direction                              | +0.17 (+0.01 to +0.34) points, 120 episodes | Discovery claim (barely) |

**What the numbers mean.**

- **S2 is mostly mechanical in points.** The old number starts +0.54 points ahead of Pinnacle's new one, and Pinnacle gives back −0.10 by the close. Points CLV ignores price, and the hypothetical cover rate (53.7%) is not distinguishable from break-even (52.9%).
- **Retail books are not simply slow copies of Pinnacle.** Only 4–15% of Pinnacle's changes were matched by a retail book within an hour, and 43–83% never before kickoff. Many "stale" numbers are retail books holding a different number with different juice.
- **Post-hoc split:** cases at −110 or better looked better than juiced ones. Because that was found after seeing results, it was registered as Addendum D (`3acbccf`) and will be tested on weeks 7–14 only. The discovery numbers are not evidence for it.

**Decision.**

- **Labels.** Results are shown as "discovery claim" (`/research`, new status) until the confirmation run.
- **No new product signals yet.** `sharp_book_lead`, `steam` and `stale_retail_line` wait for confirmation, so the Signal Lab never shows a signal whose evidence is discovery-only.
- **Confirmation run:** after week 14's games are imported (the nightly job does this), `run_sharp_market --phase confirmation`. Both outcomes get published.
- **Next: MS-044**, the system backtester and Wong teasers, per Jack's order.

**Consequences.** The project now has evidence that the reference books move first and that steam weakly persists. It also has an honest caution against reading points CLV as profit, which is exactly the lesson the Phase 12 yardstick was meant to teach.

## ADR-054 — Wong-teaser backtest: no claim at −125; a reusable backtester; /systems (MS-044) (2026-10-20)

**Context.** Jack asked whether betting every Wong teaser this season would be profitable. His best available price is −125 at Caesars; public sources report −120 to −135 at legal US books. Addendum E (`d431cb9`) fixed the legs, variants, prices, push rules and the primary before any code; the code (`33238e4`) was committed before the first run.

**Results** (`research/reports/systems-wong-teasers.md`; hypothetical, closing lines):

| Variant                    | Legs 2016–25 | Leg win rate (95% CI) | Return at −120 | Return at −125 |
| -------------------------- | ------------ | --------------------- | -------------- | -------------- |
| V0 every leg (**primary**) | 687          | 75.7% (72.5–78.9%)    | +4.4%          | +2.5%          |
| V1 total ≤ 49              | 561          | 76.8% (73.3–80.2%)    | +9.8%          | +7.8%          |
| V2 total ≤ 49, road teams  | 247          | 80.2% (74.9–85.0%)    | +7.7%          | +5.8%          |

- **Primary:** the interval includes the −125 break-even (74.5%), so **no claim**. Every return interval except V1 at −110 includes zero.
- **Recent seasons were weaker** (V0 76.4% in 2016–23, 73.6% in 2024–25). This is consistent with reports that books now shade lines away from the Wong ranges and price teasers higher.
- **Underdog legs** (+1.5 to +2.5) won more often than favourite legs (77.4% vs 72.5%). Exploratory.
- **2026 to date at −125:** 25–9 legs at the nflverse close (+0.2 units over 16 teasers); 25–10 at Caesars' own closing lines (−1.6 units). Far too few to mean anything.

**Decision.**

- `research/backtest.py` is the reusable engine: grading of spreads, totals, moneylines and teasers, two push conventions, chronological and all-pairs pairing, drawdown and cluster bootstraps. `systems.py` holds system definitions. Later systems each get their own pre-registration.
- `/systems` shows the result from a generated JSON (`apps/web/lib/generated/wong-teasers.json`, written by `run_systems.py --web-json`), labelled hypothetical throughout.
- **Price matters most.** The gap between −120 and −125 is worth about 2 points of return. The page and report show every price so the comparison is visible without naming a book to use.

**Consequences.** MS-045 (paper portfolio) can track V0/V1 legs weekly at −125 as a live, hypothetical forward test, graded against Caesars' own lines.

## ADR-055 — System catalogue F1–F10: none supported; all tracked forward (MS-045a) (2026-10-20)

**Context.** Jack asked for other sharp systems beyond Wong teasers. Addendum F (`b41edfb`) pre-registered nine public situational systems and one walk-forward ML system before code (`2c75e7e`). The correction is Holm–Bonferroni across all ten, plus a 2024–25 sign check.

**Result** (`research/reports/systems-catalogue.md`, 2016–25 at the close, −110): **0 of 10 supported.**

- **Best:** F8 primetime unders, 54.7% (50.5–58.7%), p = 0.14, falling to 51.2% in 2024–25.
- **F10,** the ML logistic regression on rest, travel, body-clock and line features: 48.6% (44.2–52.9%), with a return of −7.0% (−15.2 to +1.0). No better than the simple rules; refitting each season on earlier seasons found nothing that carried forward.
- **Correction (2026-10-20, MS-045b).** The first run joined game context on the `is_home` flag, which is false for both teams at neutral sites. That duplicated the 66 neutral-site games and could give the away side the wrong team's context. Context is now matched on the team (`attach_context`, with a regression test) and the catalogue was re-run with the unchanged pre-registered rules. Still 0 of 10. The first run had reported F10 at 47.1% with a return interval below zero; that claim was an artifact of the bug and is withdrawn. MS-036's 2026 context query had the same pattern and is fixed in code; its published report predates the fix and covers only a handful of neutral-site games.
- **The rest** (home underdogs, divisional underdogs, big underdogs, rest edge, short week, body clock, divisional unders, high-total unders) sit at 49–52%.

**Decision.**

- Shown on `/systems` (catalogue table, from `apps/web/lib/generated/systems-catalogue.json`).
- **Every F-system and both Wong variants are still tracked forward** in the paper portfolio (MS-045b), so the live record is not selected on these results.
- **Where to look next.** The closing line absorbs public situational information. The remaining places to look are the market's own microstructure (MS-043: who moves first, stale numbers, steam) and information that arrives during the week (R2w: injuries). ML effort should go there, not into situational features.

## ADR-056 — Paper portfolio: immutable hypothetical positions from every pre-registered system (MS-045b) (2026-10-20)

**Context.** Jack wants to see the systems tracked live and visualised. Backtests on closing lines (ADR-054, ADR-055) can't show what was actually available before kickoff.

**Decision.**

- **Table `paper_positions`** (migrations 0017/0018, RLS). One row per strategy, game and mode.
  - **Recorded at placement:** the book's posted line and price, the quote time and the placement time.
  - **Filled in at grading:** result, Pinnacle's closing line (`line_moves`; nflverse close as fallback) and CLV in points.
  - **Database guarantees:** a trigger makes the placement columns immutable and forbids deleting live rows. Checks require live positions to be placed before kickoff and every quote to precede kickoff.
- **Modes:**
  - `live`: placed by the scheduled job before kickoff.
  - `reconstructed`: games before the job existed, filled in afterwards by the same rules from snapshots stored at least 10 minutes before kickoff. Labelled on the page.
  - `synthetic`: demo and e2e databases only.
- **Strategies:** Wong V0–V2 (teaser legs, paired chronologically per week at −125) and F1–F10, regardless of backtest verdict.
  - The rules are the same functions as the backtests (`systems.py`), applied to the book's line instead of the nflverse close. F10 is refitted on every final game before the season.
  - **Book:** Caesars (`williamhill_us`), else DraftKings. The free Odds API plan never returns Caesars, so live positions currently price at DraftKings.
- **The job** (`research/paper.py`) is the one research module that writes, and only to `paper_positions`. Studies keep their read-only session. It lives with the systems so the rules are not duplicated in TypeScript.
- **Schedule:** `paper-portfolio.yml` places positions after every odds collection (games kicking off within about 6 hours, from the snapshot just collected) and grades daily at 11:30 UTC, after the line-move import.
- **`/portfolio`:** cumulative units by strategy (toggleable), mean CLV by strategy, a strategy table carrying each backtest verdict, and open and graded positions. Live, reconstructed or all. Everything is labelled hypothetical.

**Consequences.**

- The forward record accumulates without selection: a system that failed its backtest is still tracked.
- CLV gives a faster read than units. At four snapshots a day, a quote can be up to about 6 hours old at kickoff; a paid real-time feed (MS-046) would tighten that and allow paper positions on the market-signal strategies (S2, S3).

## ADR-057 — Market ML finds no exploitable value; price-aware CLV replaces points CLV for retail numbers (MS-046) (2026-10-20)

**Context.** MS-043 found that Pinnacle leads retail and that stale retail numbers beat Pinnacle's close by +0.44 points. Jack asked whether machine learning on the market itself could turn that into significant results. Addendum G (`02360c6`) fixed two models before code (`7a103bf`).

**Discovery results** (walk-forward inside weeks 1–6; `research/reports/market-ml-discovery.md`):

- **G1, Pinnacle's direction to the close:** the model's log loss was **+0.417 (+0.153 to +0.697)** worse than the class-frequency baseline. With about 60 games per horizon it overfits. Pinnacle's own path looks unpredictable from this data, which is consistent with an efficient sharp market.
- **G2, price-aware value of retail numbers:**
  - The value model is coherent: all retail numbers average −4.6%, roughly the books' margin.
  - The no-model rule "a better number than Pinnacle's at −125 or better" averages −2.0%.
  - The model's selections average **+0.0% (−1.9 to +2.0)**: break-even, not positive.
- **S2 re-scored with price (exploratory, added after the first run).** Stale retail numbers are **−2.0% (−2.7 to −1.3)** per unit against Pinnacle's no-vig close. At −110 or better they are −0.6% (−1.5 to +0.3). The +0.44 points was real, but the books charge for the old number.

**Decision.**

- **The yardstick for retail numbers is now price-aware value.** It is expected profit at Pinnacle's no-vig close, converted between lines with an empirical margin distribution in which 3 and 7 carry the most value. Points CLV stays for Pinnacle-versus-Pinnacle comparisons, where the price is comparable.
- **Addendum H (`b980392`)** registers the standard-price stale-number test (S2c) for the confirmation weeks before any was played.
- **No signals are added.** The paper portfolio keeps tracking the systems.
- **Live data.** Near-real-time OddsPapi polling still matters for confirmation and for live tracking, but it is no longer expected to unlock profit. An email asking OddsPapi to confirm acceptable use is with Jack.

**Consequences.** The project now has a clear, evidence-backed answer to "where is the structure?":

- Information flows from the market makers to retail books.
- Retail books price the lag into their juice.
- Neither the sharp book's path nor the retail numbers offered an exploitable advantage in weeks 1–6.

The remaining candidates are information that reaches the market during the week, such as injury news (R2w, MS-047), and the confirmation weeks.

## ADR-058 — Injury news is priced before the official report (MS-047) (2026-10-21)

**Context.** R2w found the consensus moves +0.40 points per newly-out starter during the week. MS-047 asked whether that move happens when teams file game-status designations (4 pm ET, the day before Thursday games and two days before others), and whether retail books lag it. Addendum I (`50762d0`) was committed before code (`9fb408f`).

**Discovery results** (weeks 2–6, `research/reports/injury-windows-discovery.md`):

- **I1:** Pinnacle's move inside the window [deadline − 4 h, deadline + 2 h] was **+0.02 points per net newly-out starter (−0.00 to +0.05)**. No claim; the window holds about 0% of the news-driven move.
- **I2:** only 18 stale retail numbers followed a news-direction Pinnacle move in the window (gate 50). **Inconclusive**; their mean price-aware value was −0.3% (−2.9 to +2.5).
- **When the move happens** (exploratory, added after the first run, 29 games): toward the healthier side, +0.24 points by 4 days out (67% of the move to the close), +0.28 by 2 days out, +0.36 at the close.

**Decision.**

- **Official designations are a lagging record.** The market prices injury news earlier in the week, from practice participation, coach comments and reporting that the project has no timestamped feed for.
- **Live injury snapshots** (twice daily since 2026-10-18) keep accumulating. A timing study of practice-report changes (Wednesday and Thursday) is possible once enough weeks exist; it is not scheduled.
- **No signals are added.** Confirmation runs with MS-043 and MS-046 after 2026-12-16.

## ADR-059 — Openers and totals: no value against Pinnacle's no-vig close (MS-050) (2026-10-21)

**Context.** After MS-046 showed stale retail spread numbers are worth −2.0% once priced, two places remained where books might be softer: their first numbers (openers) and totals. Addendum J (`b48baf6`) was committed before code (`ba56350`). It adds a totals value model: 2016–25 total-points frequencies by closing-total bucket, calibrated to Pinnacle's no-vig closing total.

**Discovery results** (weeks 1–6, `research/reports/openers-totals-discovery.md`):

- **J1, openers:** only 21 retail openers beat Pinnacle's concurrent line at −125 or better, at −2.3% (−6.3 to +1.8). No claim. Retail books mostly open at Pinnacle's number.
- **J2, stale totals:** −1.8% (−2.5 to −1.1), interval below zero, against +0.55 points of CLV. At −110 or better: −1.0% (−1.8 to −0.1).
- **J3, retail totals better than Pinnacle's** at 48/24/6/1 hours: −3.0% (−3.5 to −2.4).

**Decision.**

- **The discovery picture is complete.** Across spreads and totals, closing lines, openers and stale numbers, retail books price their lag into the juice. No public or market-structure pattern in weeks 1–6 offered positive value against Pinnacle's no-vig close.
- `/research` summarises the market studies together.
- **The next candidate is exchanges (MS-051).** Their margins are thin and their prices are set by other traders rather than a book's risk team, so a lag there would not be priced into juice. OddsPapi's free history covers Novig, ProphetX and Kalshi, but at order-book volume (about 1–2 million entries per game), so storage is measured first.
- **Confirmation** of MS-043/046/047/050 runs after 2026-12-16.

## ADR-060 — Exchanges: imported, and no value after fees (MS-051) (2026-10-21)

**Context.** Every retail pattern was priced into the juice (ADR-057, ADR-059). Exchanges have thin margins (median spread overround about 1%, against about 4.5% at retail books) and prices set by other traders, so a lag there might not be charged for. Addendum K (`32c2199`) was committed before any import or study code (`bb9d71d`).

**Import.**

- Novig, ProphetX and Kalshi spreads and totals go into `line_moves` under their own job key (`oddspapi-moves-ex:<fixture>:v1`).
- The size at the top of book is stored with each row but never creates a row by itself; moneylines are left out.
- Each exchange is a separate request. A history too large to parse (over V8's 512 MB string limit: five Kalshi games and one Novig game) is skipped for that game and recorded on the run.
- Result: 217k rows for 93 games, about 46 MB. The database is 181 MB of 500, and a full season adds about 140 MB.
- The nightly job imports both profiles.

**Discovery results** (weeks 1–6, `research/reports/exchanges-discovery.md`):

- **K1, stale exchange prices** (size ≥ 100, −125 or better): **−1.2% (−1.6 to −0.8)** after fees, over 1,715 cases. The opposite of the hypothesis.
  - **By exchange:** Kalshi −2.6%, ProphetX −1.4% (its old line lasted a median 32 minutes), **Novig +0.4% (−0.2 to +0.9)**.
  - **With a 1,000 size floor:** −1.6% overall, and Novig −0.1%.
- **K2, exchange prices better than Pinnacle's** at fixed horizons: −3.0% (−3.4 to −2.6).

**Decision.**

- **Novig, the no-fee exchange, is the only cell above zero.** That was exploratory and rests on thin quotes, so it is registered as **K1n (Addendum L, `6df5a39`)** for the confirmation weeks before any was played.
- **No signals.** Exchanges stay hidden by default in the replay panel; one click shows them.

**Consequences.** The discovery phase of the Sharp-Market Lab is complete. Across spreads, totals, openers, retail books and exchanges, the market prices its own lags. What remains are the pre-registered confirmation tests (S2b/S2c, K1n and the rest) after 2026-12-16, and the forward paper portfolio.

## ADR-061 — Phase 13: real value on main markets; a local research lake (MS-052) (2026-10-21)

**Context.** Phase 12 found nothing worth taking once price was counted. Its intervals are tight (closing-line value has low variance), so these are real absences: more of the same data would only confirm them. Jack chose: NFL only, real value on spreads, totals and moneylines (alternate lines and teasers welcome), free first, with a redirect if paid data would significantly change the findings.

**Decision: the Phase 13 plan.** Test what sharp bettors actually use (ROADMAP Phase 13):

- information timing;
- model versus opener;
- cross-market mis-pricing: moneyline versus spread, alternate lines, teasers.

These run on a better fair-value engine: a joint margin–total distribution and a sharp-consensus devig. Every pre-registration now states its power (the smallest detectable value per unit). A paid-data gate is written down in advance.

**Decision: the lake (MS-052).**

- **What it holds:** every book's full spread, total and moneyline ladders (all alternate lines), pregame, for Pinnacle, Circa, Bookmaker.eu, the retail books and the exchanges, as one Parquet file per game (zstd), queried with DuckDB.
- **Size and speed:** about 300 KB per game, roughly 85 MB a season, against the 500 MB database that forced us to keep only main lines.
- **Streaming parser:** `ijson` parses responses from disk, so there is no size limit (the collector skipped five Kalshi games over V8's 512 MB string limit).
- **Lossless reduction:** a price-unchanged entry is dropped. Limit changes are kept for the market makers.
- **Local, not cloud:** the lake is a reproducible cache of free provider history. `python -m marketscope_research.lake build` rebuilds it, so it lives under `fixtures/oddspapi/local/lake` (gitignored, so provider data never enters the public repo). No storage bucket or new secret is needed. Supabase Storage remains an option if the lake is ever needed in CI.
- **Verified:** a Python port of the main-line rules (`lake/mainline.py`, JavaScript rounding included) reproduces `line_moves` on a 15-minute grid. On the first two games: 100% for nine books, 99.7% for Kalshi.

**Consequences.** Cross-market and alternate-line studies become possible on free data. The website keeps reading Supabase only.
