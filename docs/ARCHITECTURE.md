# Architecture

## Current state (Phase 0)

```
 The Odds API ──HTTPS (key in query, server-only)──▶ apps/collector
                                                     ├─ config.ts          Zod-validated env
                                                     ├─ providers/the-odds-api/client.ts
                                                     │    retries, backoff, quota headers, key redaction
                                                     ├─ coverage.ts        price-free coverage summary
                                                     └─ scripts/verify-provider.ts
                                                            │ raw JSON → fixtures/the-odds-api/local/ (gitignored)
                                                            │ summary  → docs/PROVIDER_COVERAGE.md
                                                            ▼
                         packages/shared  (pure TypeScript, no I/O)
                         ├─ providers/the-odds-api/schema.ts     Zod: structure only
                         ├─ providers/the-odds-api/normalize.ts  provider JSON → NormalizedQuote + issues
                         ├─ domain.ts, bookmakers.ts             Market, Selection, target books
                         ├─ odds.ts, format.ts                   odds math, display formatting
                         ├─ compare.ts                           exact-line best-price groups
                         └─ fixtures (synthetic, NOT real odds)
                                                            ▲
 Browser ◀──HTML── apps/web (Next.js 16 App Router, server components)
                   └─ /nfl  synthetic fixture → normalize → lib/odds-board.ts view model → table
```

**Boundaries:**

- **Provider adapter** (client + schema + normalizer) is the only code that knows The Odds API's shape. Everything downstream uses domain types.
- **Pure domain logic** (`packages/shared`) has no I/O, so it's unit-testable and reusable by the web app, the collector, and later the signal engine.
- **Presentation logic** (`apps/web/lib/odds-board.ts`) is a pure view-model builder, tested separately from React.

## Target state (after Phase 3)

```
 EventBridge / GH Actions cron ─▶ collector (Lambda or Action)
                                   1. budget guard  2. claim run (job_key)  3. fetch (no tx open)
                                   4. one transaction: upsert events, insert payload + observations, complete run
                                                  │
                                                  ▼
                                   PostgreSQL (managed) — append-only odds_observations
                                                  │
                         packages/db query layer (Drizzle + raw SQL for analytics)
                                  │                                   │
             Next.js server components                     Next.js route handlers (/api/*)
                                  │                                   │
                                Browser (Vercel, Deployment Protection until terms reviewed)
```

Later phases add the signal engine (`market_signals`), Python research and ML that read Postgres, and `model_runs` / `model_predictions`.

## Key technology choices

See `DECISIONS.md`. In short: a pnpm monorepo with JIT internal packages, TS 5.9 strict, Next.js 16, Tailwind 4, Zod 4, Vitest 5, and (Phase 1) Drizzle + postgres.js on PostgreSQL 17.
