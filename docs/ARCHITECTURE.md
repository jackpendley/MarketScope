# Architecture

## Current state (Phase 2)

```
 The Odds API ──HTTPS (key in query, server-only)──▶ apps/collector
                                                     ├─ config.ts       Zod-validated env
                                                     ├─ providers/the-odds-api/client.ts
                                                     │    retries, backoff, quota headers, key redaction
                                                     ├─ collect.ts      claim job_key → budget guard → fetch
                                                     │                  → normalize → ONE transaction
                                                     └─ scripts/        collect-nfl, verify-provider, probe-books
                                                              │
                         packages/shared (pure TS)            │ uses normalizer, bookmakers, season
                         schema · normalize · compare · odds  │
                                                              ▼
                         packages/db  (Drizzle + postgres.js) ──▶ PostgreSQL 17
                         schema.ts · drizzle/*.sql migrations      events · bookmakers · ingestion_runs
                                                                   ingestion_payloads · odds_observations
                                                                   (append-only)

 Browser ◀──HTML/JSON── apps/web (Next.js 16 App Router; DATABASE_URL only, never the odds key)
                        ├─ /nfl, /nfl/games/[id]   server components ─┐
                        ├─ /api/games, /api/games/:id/odds,           ├─▶ lib/server/games.ts ─▶ @marketscope/db queries
                        │  /api/health/data        route handlers ───┘     (DISTINCT ON latest quotes)
                        └─ lib/odds-board.ts       pure view model: exact-line best price, stale books, consensus
```

**Boundaries:**

- **Provider adapter** (client + schema + normalizer) is the only code that knows The Odds API's shape. Everything downstream uses domain types.
- **Persistence** (`packages/db`) owns the schema and migrations. Database constraints enforce the domain invariants a second time (point ⇔ market, selection ⇔ market, valid price, one row per selection per run).
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
