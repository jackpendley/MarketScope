# MarketScope — guide for Claude sessions

MarketScope is an NFL sportsbook market-intelligence platform and a portfolio project: "Compare the market. Replay its history. Understand the matchup. Investigate the signals. Test the evidence." It has four parts:

- **Odds board:** compare five books.
- **Market replay:** reconstruct line history from stored observations.
- **Football context ("KenPom for the NFL"):** MarketScope Ratings (AdjO/AdjD/AdjST/AdjPace/AdjEM with uncertainty, luck, SOS, Five Factors), results, availability, weather, coaching, and a labeled model line. The design is frozen in `docs/RATINGS.md` (ADR-028).
- **Signal lab and ML lab:** reproducible, evidence-backed research.

The developer (Jack) is building it to move into a backend/full-stack software engineering role. Act as senior mentor and pair programmer: explain significant decisions and trade-offs, and keep the code understandable to him.

## Start here every session

1. Read `docs/PROJECT_STATUS.md`: current milestone, blockers, exact next task.
2. Read the current phase in `docs/ROADMAP.md`: goals, milestones, acceptance criteria.
3. Check `docs/DECISIONS.md` before changing anything it covers.
4. Read `docs/PRODUCT_SPEC.md` (the full original handoff, long) only for scope questions.
5. At session end, **rewrite** `docs/PROJECT_STATUS.md` (don't append) and tick milestones in `ROADMAP.md`.

## Working agreement

- **Ask clarifying questions** when a decision is genuinely Jack's. Explain the plan before large changes. Challenge questionable designs.
- **Claude implements everything.** Never stop to hand Jack code to write. He learns by reading the explanations: when you finish a milestone, summarize its key concepts (see ROADMAP §Concepts).
- Build vertical slices in small, tested increments. No new frameworks or infrastructure without a stated reason.
- **Git:** one branch per milestone and a PR via `gh pr create`. **Claude squash-merges once CI is green** (standing approval, 2026-10-16). `main` stays deployable. The repo is **public**: `git@github.com:jackpendley/MarketScope.git`.
- **Odds API credits:** standing approval to spend within the collector's guards (`MONTHLY_CREDIT_BUDGET=400`, `MIN_CREDITS_REMAINING=25`). Report usage in each summary.
- **Still requires approval:** adding or changing repo secrets, creating any cloud resource (Vercel, AWS, new DBs), buying any plan, raising the credit budget, and making a deployment public.
- **Supabase = managed Postgres only** (ADR-018). Don't add `supabase-js` or the shadcn Supabase blocks without a feature that needs them. Every table must keep RLS enabled (`.enableRLS()` in `schema.ts`). Project skills for Supabase live in `.claude/skills/`.
- **Production data:** GitHub Actions collects 4×/day into Supabase (ADR-019). Locally, `SUPABASE_DATABASE_URL` in `apps/collector/.env.local` points at it. Never print it.

## Non-negotiable domain rules

- **Never fabricate odds**, coverage, opening/closing lines, or model results. Fixture data must be labeled synthetic in the file name, its README, and the UI.
- **Exact-line comparison:** compare prices only when event, market, selection, **and point** are identical (`compareIdenticalMarketPrices`).
- **HOME/AWAY** come from exact equality with the event's `home_team`/`away_team`, never alphabetical. Spread signs are preserved as posted. Moneyline `point` is always `null`.
- For history, stats, and consensus, **orient spreads to the home team**. Home −3.5 → −2.5 is a 1-point move toward the away side.
- **Timestamps are distinct**:
  - `bookmaker_updated_at`: the provider's market `last_update`.
  - `observed_at`: when we received the data.
  - `provider_snapshot_at`: the historical snapshot time.

  Never assign the import time to historical data.

- "First observed" is not the opening line, and "last observed pregame" is not the closing line. A line change happened somewhere in the interval `(prev_observed_at, observed_at]`, not at an exact moment.
- Missing data is shown as missing. Never carry prices forward across gaps or treat missing as unchanged.
- Signals describe observable evidence. They never claim "sharp action" or recommend bets.

**Football and model rules (ADR-028):**

1. **Point-in-time everything.**
   - Every rating, availability estimate, forecast, feature and prediction carries `as_of`.
   - It may use only data available before that time:
     - games final before `as_of`
     - injury reports fetched or published before it
     - forecasts issued before it
   - Observed game weather is post-hoc only.
2. **A game's result never feeds features for that game.** Filtered (point-in-time) ratings drive predictions. Smoothed (hindsight) ratings are only for labeled retrospective charts.
3. **The nflverse closing line is a labeled benchmark.**
   - It never goes into `odds_observations`, because it has no observation timestamp.
   - Convert it to home orientation on ingest. Verify the sign against our last-pregame consensus.
4. **Model output is always labeled "model estimate"** and shown with its measured error. Never use bet, pick, value, edge, or lock language.
5. **Attribution:**
   - Credit nflverse (CC-BY 4.0), PFR snap counts via nflverse, and Open-Meteo (CC-BY 4.0).
   - **FTN data (participation 2023+, charting) is CC-BY-SA 4.0.** It stays local research only and never feeds the product.
6. **Predictions in `model_predictions` are immutable.** A new model version writes new rows. Forward-test rows must be created before kickoff.
7. **The displayed MarketScope rating uses no market inputs.** Market-informed variants (blends, market priors) are research only. This keeps "ratings vs market" meaningful.
8. **Factors earn their place.** A candidate enters the game model only if it improves 2023–24 validation beyond noise. The 2025 test season is evaluated exactly once.

## Security

- Secrets live only in gitignored `.env.local` files. Never ask for keys in chat, never log request URLs (the Odds API key is in the query string), and never send them to the browser.
- Real provider responses go only in `fixtures/the-odds-api/local/` (gitignored, because of provider terms and the public repo). Committed docs contain coverage summaries, never raw prices.

## Commands (run from repo root)

|                                                                                                                                                       |                                                                                                            |
| ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `pnpm install`                                                                                                                                        | install workspace (Node ≥ 22.12, pnpm 10)                                                                  |
| `pnpm dev`                                                                                                                                            | Next.js dev server → http://localhost:3000/nfl                                                             |
| `pnpm lint` / `pnpm typecheck` / `pnpm test` / `pnpm build`                                                                                           | quality gates (CI runs these plus `format:check`)                                                          |
| `pnpm format`                                                                                                                                         | Prettier                                                                                                   |
| `pnpm --filter @marketscope/web build && pnpm --filter @marketscope/web test:e2e`                                                                     | Playwright e2e (seeds `marketscope_e2e_test` with synthetic history; `createdb marketscope_e2e_test` once) |
| `pnpm verify:provider [--spend]`                                                                                                                      | Odds API check. Free without `--spend`; 3 credits with it                                                  |
| `pnpm db:migrate`                                                                                                                                     | apply migrations to `packages/db/.env.local` `DATABASE_URL`                                                |
| `pnpm --filter @marketscope/db db:generate --name <x>`                                                                                                | new migration from `schema.ts` changes (commit it; CI checks drift)                                        |
| `pnpm collect:nfl [--scheduled \| --job-key K]`                                                                                                       | collect odds into Postgres (3 credits; budget-guarded, idempotent per job key)                             |
| `DATABASE_URL=postgres://localhost:5432/marketscope_demo pnpm --filter @marketscope/collector seed:synthetic --reset`                                 | synthetic multi-day history for UI work (guarded: demo/e2e DBs only; ADR-021)                              |
| `pnpm --filter @marketscope/collector import:oddspapi [--limit N] [--dry-run]`                                                                        | backfill completed pre-live games from OddsPapi (free history; ~1 billable request; ADR-026)               |
| `DATABASE_URL=… pnpm --filter @marketscope/db explain [--json]`                                                                                       | EXPLAIN ANALYZE the app's hot queries (read-only, rolled back; safe on production)                         |
| `cd apps/football && PYTHONPATH=src DATABASE_URL=… .venv/bin/python -m marketscope_football.ingest schedules --seasons 2016-2026 [--dry-run]`         | load nflverse schedules/results and link odds events (idempotent per UTC day)                              |
| `cd apps/football && PYTHONPATH=src DATABASE_URL=… .venv/bin/python -m marketscope_football.ingest team-stats --seasons 2016-2026 [--refresh]`        | play-by-play (cached Parquet) → `nfl_team_game_stats` for final games; `--seasons current` in CI           |
| `cd research && PYTHONPATH=src STUDY_DATABASE_URL=… .venv/bin/python -m marketscope_research.run_market_baseline --out reports/market-baseline-v1.md` | market ML report (read-only; also `run_market_gate`, `run_outlier_convergence`)                            |
| `pnpm --filter @marketscope/<pkg> <script>`                                                                                                           | run one package's script                                                                                   |

## Repo map

- `apps/web`: Next.js 16 App Router, React 19, Tailwind 4, TS strict. Pages call `lib/server/*` (server-only) → `@marketscope/db` queries; `/api/*` wraps the same functions (`docs/API.md`). Needs `apps/web/.env.local` with `DATABASE_URL` only. Read `apps/web/AGENTS.md`: Next 16 differs from older versions, so check the bundled docs in `node_modules/next/dist/docs/` before using unfamiliar APIs.
- `apps/collector`: Node worker run via `tsx`. Config (Zod env), The Odds API client (retries, quota headers, redaction), `collect.ts` (claim → budget guard → fetch → one transaction), and scripts.
- `packages/shared`: domain types, odds math, formatting, exact-line comparison, provider Zod schemas, normalizer. Synthetic fixture at `@marketscope/shared/fixtures`.
- `apps/football` (Phase 8+, Python): nflverse ingest, team-game stats, coaching staff, weather, ratings, evaluation, predictions.
  - Writes only `nfl_*`, `rating_*` and `model_*` tables.
  - Raw play-by-play stays in a gitignored Parquet cache.
- `research/` (Python): read-only studies and the market ML (`ml/`).
- `packages/db`: Drizzle schema (`src/schema.ts`), committed SQL migrations (`drizzle/`), client, and test helpers (`@marketscope/db/testing`).
- Local Postgres: Homebrew `postgresql@17`, with DBs `marketscope_dev` and `marketscope_test`. Tests use `TEST_DATABASE_URL` (default: local test DB). Root `pnpm test` runs packages sequentially because they share the test DB.
- `docs/`: ROADMAP, PROJECT_STATUS, DECISIONS, ARCHITECTURE, API, DEPLOYMENT, DATA_DICTIONARY, PROVIDER_COVERAGE, PERFORMANCE, SIGNAL_DEFINITIONS, RATINGS (ratings design + results), MODEL_CARD (Phase 7+), PRODUCT_SPEC (with a 2026-10-17 scope addendum).
- **Deployed site is private** (Basic auth via `apps/web/proxy.ts`, ADR-022). The Odds API terms forbid exposing our JSON API publicly; keep `/api/*` protected even if the UI is opened up later.

Workspace packages export TypeScript source directly. There's no build step: Next uses `transpilePackages`, and the collector uses `tsx`.

## Toolchain pins (see DECISIONS)

- TypeScript **5.9**, not 7: typescript-eslint supports TS < 6.1 only.
- ESLint 9 (pinned by eslint-config-next 16.4).
- Zod 4, Vitest 5.
