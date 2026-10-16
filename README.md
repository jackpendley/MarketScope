# MarketScope

**NFL sportsbook market intelligence.** Compare the market. Replay its history. Investigate the signals. Test the evidence.

MarketScope compares NFL odds across five sportsbooks (DraftKings, FanDuel, BetMGM, Caesars, Hard Rock Bet AZ). Each collection is stored as an append-only observation, so the app can reconstruct how lines moved. The goal is a research tool that keeps observable evidence separate from speculation. It is not a picks service.

> **Status:** Phase 2 complete. The odds board reads real NFL odds snapshots that the collector stores in PostgreSQL. See [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Stack

- **Web:** Next.js 16 (App Router, server components), React 19, TypeScript (strict), Tailwind CSS 4
- **Collector:** Node.js 22 worker (TypeScript via `tsx`), Zod-validated config and provider responses
- **Shared:** pure-TypeScript domain logic (odds math, normalization, exact-line price comparison)
- **Data:** PostgreSQL 17, Drizzle ORM, committed SQL migrations
- **Quality:** Vitest, ESLint, Prettier, GitHub Actions CI
- **Data source:** [The Odds API](https://the-odds-api.com/) v4

## Repository layout

```
apps/web          Next.js app (odds board at /nfl)
apps/collector    ingestion worker (collect:nfl) + provider verification
packages/db       Drizzle schema, migrations, client
packages/shared   domain types, odds math, normalizer, comparison, synthetic fixture
docs/             roadmap, status, decisions, architecture, data dictionary, provider coverage
```

## Getting started

Requirements: Node ≥ 22.12 (`nvm use`), pnpm 10 (`corepack enable`), and PostgreSQL 17.

```bash
pnpm install

# Local database (macOS / Homebrew)
brew install postgresql@17 && brew services start postgresql@17
createdb marketscope_dev && createdb marketscope_test
cp packages/db/.env.example packages/db/.env.local
cp apps/web/.env.example apps/web/.env.local
pnpm db:migrate

pnpm dev            # http://localhost:3000/nfl
```

Quality checks (CI runs all of these):

```bash
pnpm format:check && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

End-to-end browser tests (Playwright, against a database seeded with **synthetic** history):

```bash
createdb marketscope_e2e_test
pnpm --filter @marketscope/web exec playwright install chromium   # once
pnpm --filter @marketscope/web build && pnpm --filter @marketscope/web test:e2e
```

## Provider verification

The collector needs a key from The Odds API (the free Starter plan works; Caesars requires a paid plan).

```bash
cp apps/collector/.env.example apps/collector/.env.local
# edit apps/collector/.env.local and set ODDS_API_KEY (never commit it or paste it anywhere)
pnpm verify:provider           # free: /sports + /events, 0 credits
pnpm verify:provider --spend   # one /odds call, ~3 credits
pnpm collect:nfl               # store a snapshot in Postgres (~3 credits)
```

The collector is idempotent per job key (`--scheduled` uses one key per 6-hour slot) and refuses to run past the configured credit budget. Every run is recorded in `ingestion_runs`.

In production, a GitHub Actions workflow (`collect-odds.yml`) collects 4× a day into a Supabase-hosted Postgres. Migrations are applied automatically when they merge to `main`. Supabase's public REST API is locked out of every table via row-level security.

Raw responses are saved to `fixtures/the-odds-api/local/`, which is gitignored. A price-free coverage summary is appended to [`docs/PROVIDER_COVERAGE.md`](docs/PROVIDER_COVERAGE.md).

## Principles

- Prices are compared only at an **identical line**. Home −3.5 at −110 and home −3 at −115 are different bets.
- Missing data is shown as missing. Nothing is invented or carried forward.
- "First observed" is not the opening line, and "last observed" is not the closing line.
- Odds data is labeled as timestamped snapshots, never implied to be real-time.
- Market signals describe evidence. They don't claim to detect sharp money or recommend bets.

## Documentation

- [Roadmap](docs/ROADMAP.md) · [Project status](docs/PROJECT_STATUS.md) · [Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md)
- [Decisions](docs/DECISIONS.md) · [Data dictionary](docs/DATA_DICTIONARY.md) · [Provider coverage](docs/PROVIDER_COVERAGE.md)
- [Original product specification](docs/PRODUCT_SPEC.md)

MarketScope is an analytics and education project. It doesn't place bets or give betting advice.
