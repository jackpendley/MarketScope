# Architecture

## Current state (after MS-023)

```
 GitHub Actions cron (4×/day) ─▶ apps/collector  collect:nfl  →  signals:compute
 The Odds API (key server-only)    claim job_key → budget guard → fetch (no tx) → normalize → ONE transaction
                                                            │
 OddsPapi (free history, manual) ─▶ import:oddspapi        │   one idempotent run per fixture; derived
                                    change log → snapshots  │   6-hourly + near-close snapshots (ADR-026)
                                                            ▼
                         packages/db (Drizzle + postgres.js) ──▶ Supabase PostgreSQL 17 (RLS on, ADR-018)
                         schema.ts · drizzle/*.sql (migrate-on-merge)
                         queries/{odds,signals,coverage}.ts      events · bookmakers · ingestion_runs
                         scripts/explain.ts (EXPLAIN ANALYZE)    ingestion_payloads · odds_observations
                                                                 (append-only) · market_signals
                                  │
 Browser ◀── Basic auth (proxy.ts, ADR-022) ── apps/web on Vercel (DATABASE_URL only; transaction pooler)
   /nfl · /nfl/games/[id] · /nfl/games/[id]/history (replay) · /replay · /signals · /data
   /api/games · /odds · /history · /movements · /signals · /health/live · /health/data
   lib/*-view.ts and lib/odds-board.ts: pure view models, unit-tested apart from React

 research/ (Python) ── read-only SQL ──▶ pre-registered studies, cross-checked against stored values
```

**Boundaries:**

- **Provider adapters** (`packages/shared/src/providers/the-odds-api`, `apps/collector/src/providers/oddspapi`) are the only code that knows a provider's shape. Everything downstream uses domain types and the same tables.
- **Persistence** (`packages/db`) owns the schema, migrations, and every SQL query. Database constraints enforce the domain invariants a second time (point ⇔ market, selection ⇔ market, valid price, one row per selection per run per snapshot).
- **Pure domain logic** (`packages/shared`): odds math, consensus, history, replay, and signals. It has no I/O, so it's unit-testable and shared by the web app, the collector, and the signal job.
- **Presentation logic** (`apps/web/lib`) is pure view-model code, tested separately from React.
- **Health vs history:** run-health queries (`latestCompletedRun`, `recentRuns`) count **live** runs only; historical imports never make collection look healthy (ADR-027).

## Key technology choices

See `DECISIONS.md`. In short: a pnpm monorepo with JIT internal packages, TS 5.9 strict, Next.js 16, Tailwind 4, Zod 4, Vitest 5, and (Phase 1) Drizzle + postgres.js on PostgreSQL 17.
