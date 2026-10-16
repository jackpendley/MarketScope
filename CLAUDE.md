# MarketScope — guide for Claude sessions

MarketScope is an NFL sportsbook market-intelligence platform and a portfolio project. It has three parts:

- **Odds board:** compare five books.
- **Market replay:** reconstruct line history from stored observations.
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
- **Still requires approval:** adding repo secrets, creating any cloud resource (DB, Vercel, AWS), buying any plan, raising the credit budget, and making a deployment public. Managed DB choice: **Supabase** (Jack creates the project).

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

## Security

- Secrets live only in gitignored `.env.local` files. Never ask for keys in chat, never log request URLs (the Odds API key is in the query string), and never send them to the browser.
- Real provider responses go only in `fixtures/the-odds-api/local/` (gitignored, because of provider terms and the public repo). Committed docs contain coverage summaries, never raw prices.

## Commands (run from repo root)

|                                                             |                                                                                |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `pnpm install`                                              | install workspace (Node ≥ 22.12, pnpm 10)                                      |
| `pnpm dev`                                                  | Next.js dev server → http://localhost:3000/nfl                                 |
| `pnpm lint` / `pnpm typecheck` / `pnpm test` / `pnpm build` | quality gates (CI runs these plus `format:check`)                              |
| `pnpm format`                                               | Prettier                                                                       |
| `pnpm verify:provider [--spend]`                            | Odds API check. Free without `--spend`; 3 credits with it                      |
| `pnpm db:migrate`                                           | apply migrations to `packages/db/.env.local` `DATABASE_URL`                    |
| `pnpm --filter @marketscope/db db:generate --name <x>`      | new migration from `schema.ts` changes (commit it; CI checks drift)            |
| `pnpm collect:nfl [--scheduled \| --job-key K]`             | collect odds into Postgres (3 credits; budget-guarded, idempotent per job key) |
| `pnpm --filter @marketscope/<pkg> <script>`                 | run one package's script                                                       |

## Repo map

- `apps/web`: Next.js 16 App Router, React 19, Tailwind 4, TS strict. Pages call `lib/server/*` (server-only) → `@marketscope/db` queries; `/api/*` wraps the same functions (`docs/API.md`). Needs `apps/web/.env.local` with `DATABASE_URL` only. Read `apps/web/AGENTS.md`: Next 16 differs from older versions, so check the bundled docs in `node_modules/next/dist/docs/` before using unfamiliar APIs.
- `apps/collector`: Node worker run via `tsx`. Config (Zod env), The Odds API client (retries, quota headers, redaction), `collect.ts` (claim → budget guard → fetch → one transaction), and scripts.
- `packages/shared`: domain types, odds math, formatting, exact-line comparison, provider Zod schemas, normalizer. Synthetic fixture at `@marketscope/shared/fixtures`.
- `packages/db`: Drizzle schema (`src/schema.ts`), committed SQL migrations (`drizzle/`), client, and test helpers (`@marketscope/db/testing`).
- Local Postgres: Homebrew `postgresql@17`, with DBs `marketscope_dev` and `marketscope_test`. Tests use `TEST_DATABASE_URL` (default: local test DB). Root `pnpm test` runs packages sequentially because they share the test DB.
- `docs/`: ROADMAP, PROJECT_STATUS, DECISIONS, ARCHITECTURE, API, DATA_DICTIONARY, PROVIDER_COVERAGE, PRODUCT_SPEC.

Workspace packages export TypeScript source directly. There's no build step: Next uses `transpilePackages`, and the collector uses `tsx`.

## Toolchain pins (see DECISIONS)

- TypeScript **5.9**, not 7: typescript-eslint supports TS < 6.1 only.
- ESLint 9 (pinned by eslint-config-next 16.4).
- Zod 4, Vitest 5.
