# Deployment

| Component            | Where                                                           | How it updates                                                                              |
| -------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Web app (`apps/web`) | Vercel project `marketscope` (Hobby), root directory `apps/web` | Every push to `main` deploys production; PRs get preview deployments                        |
| Database             | Supabase Postgres 17                                            | `migrate-production.yml` applies migrations when `packages/db/drizzle/**` changes on `main` |
| Collector            | GitHub Actions `collect-odds.yml`                               | 4×/day (00/06/12/18:07 UTC) plus manual dispatch                                            |

## Web app environment (Vercel → Project → Settings → Environment Variables)

| Variable                  | Value                                                                                                                                                |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`            | Supabase **transaction pooler** URL (port **6543**). `createDb` disables prepared statements there, and serverless instances use one connection each |
| `BASIC_AUTH_USER`         | `marketscope`                                                                                                                                        |
| `BASIC_AUTH_PASSWORD`     | Random. Jack's copy is in gitignored `apps/web/.env.local` as `VERCEL_SITE_PASSWORD` (a different name, so local dev and e2e stay open)              |
| `QUOTE_FRESHNESS_MINUTES` | optional, default 15                                                                                                                                 |

The web app never receives `ODDS_API_KEY` (ADR-003).

## Access

The whole site is private behind HTTP Basic auth (ADR-022). Your browser prompts for the user and password above. `GET /api/health/live` is open for uptime checks.

## Verifying a deployment

1. `curl -I https://<domain>/api/health/live` → 200.
2. `curl -I https://<domain>/nfl` → 401 with `WWW-Authenticate: Basic`.
3. In a browser, log in and open `/nfl`. Check that the snapshot timestamp matches the latest `collect-odds` run.
