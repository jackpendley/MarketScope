# Deployment

| Component            | Where                                                                                                                                                              | How it updates                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Web app (`apps/web`) | Vercel project `marketscope` (`prj_qkPeUA6ADjQKFEW2jjckjevjNw8o`, Hobby, Node 24), root directory `apps/web`. **Production: https://marketscope-delta.vercel.app** | Every push to `main` deploys production; PRs get preview deployments                        |
| Database             | Supabase Postgres 17                                                                                                                                               | `migrate-production.yml` applies migrations when `packages/db/drizzle/**` changes on `main` |
| Collector            | GitHub Actions `collect-odds.yml`                                                                                                                                  | 4×/day (00/06/12/18:07 UTC) plus manual dispatch                                            |
| Line moves           | GitHub Actions `line-moves.yml` (needs repo secrets `DATABASE_URL` and `ODDSPAPI_API_KEY`; skips with a warning without the key)                                   | Daily 11:00 UTC plus manual dispatch                                                        |
| Paper portfolio      | GitHub Actions `paper-portfolio.yml` (repo secret `DATABASE_URL`)                                                                                                  | After each `collect-odds` run (place) and daily 11:30 UTC (grade); manual dispatch          |

## Web app environment (Vercel → Project → Settings → Environment Variables)

| Variable                  | Value                                                                                                                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`            | Supabase **transaction pooler** URL (port **6543**). `createDb` disables prepared statements there, and serverless instances use one connection each                            |
| `BETTER_AUTH_SECRET`      | Random, at least 32 characters. Signs session cookies. Set for Production and Preview. Without it on Vercel the site answers 503 (fails closed). Rotating it signs everyone out |
| `BETTER_AUTH_URL`         | optional. Unset, the allowed hosts in `lib/auth-config.ts` (production, previews, localhost) apply; `BETTER_AUTH_ALLOWED_HOSTS` adds more, comma-separated                      |
| `QUOTE_FRESHNESS_MINUTES` | optional, default 15                                                                                                                                                            |

The web app never receives `ODDS_API_KEY` (ADR-003).

## Access

First deployed 2026-10-16 (`dpl_8EEKWRxZDFX7Fad6PDqJVYM46TLk`). The Vercel CLI (`npx vercel@64.3.1`, logged in as Jack) was used to create the project and set env vars. The Vercel MCP connector's token is read-only.

Vercel Authentication is also enabled (`all_except_custom_domains`), which protects preview and deployment URLs. The production domain is protected by the app's own accounts.

The site is on the public internet, but every page and `/api/*` route requires a signed-in account (ADR-049). Signed-out visitors are sent to `/login`; API calls get a JSON 401. `GET /api/health/live` is open for uptime checks.

### Accounts (invite-only)

There is no sign-up page. Accounts are created and managed from a terminal. Passwords are typed at a hidden prompt and never passed as arguments:

```bash
# Production: point DATABASE_URL at Supabase (read from the collector's env file, never printed)
export DATABASE_URL="$(grep '^SUPABASE_DATABASE_URL=' apps/collector/.env.local | cut -d= -f2-)"
pnpm --filter @marketscope/web users create --username jack --email you@example.com
pnpm --filter @marketscope/web users list
pnpm --filter @marketscope/web users reset-password --user jack   # also signs them out everywhere
pnpm --filter @marketscope/web users sign-out --user jack
```

Each command shows the database host and asks for confirmation before changing anything that isn't local. Signed-in users can change their own password on `/account`.

## Verifying a deployment

1. `curl -I https://<domain>/api/health/live` → 200.
2. `curl -I https://<domain>/nfl` → 307 redirect to `/login?next=%2Fnfl`; `curl -I https://<domain>/api/games` → 401.
3. In a browser, sign in and open `/nfl`. Check that the snapshot timestamp matches the latest `collect-odds` run.
