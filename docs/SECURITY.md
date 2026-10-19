# Security

How MarketScope protects its secrets, its data and its users, and the results of the MS-037 audit
(2026-10-19).

## Controls

- **Site access (ADR-049).** The site is reachable on the public internet, but every page and
  `/api/*` route requires a signed-in account. `apps/web/proxy.ts` checks the session on every
  request; `/api/health/live` is open for uptime checks. The JSON API needs a session too, because
  The Odds API terms forbid redistributing its data "through your own API".
- **Accounts.** [Better Auth](https://www.better-auth.com/) with username or email + password:
  - **Invite-only:** sign-up is disabled; accounts come from `pnpm --filter @marketscope/web users`.
  - **Passwords:** at least 12 characters, stored only as salted scrypt hashes. Hidden-prompt input in the CLI.
  - **Sessions:** a random token in an httpOnly, SameSite=Lax cookie (Secure over HTTPS), stored
    in `auth_sessions`, 30 days with a sliding expiry. A signed 5-minute cookie cache saves
    database lookups, so a revoked session can keep working for up to 5 minutes.
  - **Brute force:** sign-in is limited to 5 attempts a minute per IP address, counted in Postgres
    so every serverless instance shares the limit.
  - **No account enumeration:** a wrong username and a wrong password get the same answer.
  - **Login CSRF and open redirects:** the proxy refuses `/api/auth/*` writes whose Origin isn't
    this site, and the post-login `next` parameter only accepts same-site paths.
  - **Resets:** a password reset (CLI) or change (`/account`) signs out the other sessions.
  - **Secret:** `BETTER_AUTH_SECRET` signs cookies. On Vercel, a missing secret makes the site
    answer 503 rather than run with a default.
- **Database.**
  - Supabase Postgres, with row-level security enabled on all 24 tables (`.enableRLS()` in
    `schema.ts`, checked by an integration test). This locks the public REST API out.
  - The site and the jobs connect through the pooler with credentials held as secrets.
  - Research uses a read-only session.
- **Secrets.**
  - Kept only in gitignored `.env.local` files (locally), in Vercel environment variables
    (`DATABASE_URL`, `BETTER_AUTH_SECRET`), and in GitHub Actions secrets (`DATABASE_URL`, the
    Odds API key).
  - Never logged and never sent to the browser.
- **API key handling.** The Odds API key travels in the query string, so request URLs are never
  logged. Provider error bodies pass through `redact()`, which replaces the key with `[REDACTED]`
  (`apps/collector/src/providers/the-odds-api/client.ts`).
- **Provider data.** Raw responses go only to `fixtures/the-odds-api/local/`, which is gitignored.
  Committed docs and reports contain coverage summaries and aggregates, never raw prices.
  Screenshots are taken from the synthetic e2e database.
- **Continuous checks.** GitGuardian scans every PR. CI runs migrations against a fresh database,
  and `migrate-production.yml` is the only path that changes the production schema.

## Audit, 2026-10-19 (MS-037)

| Check                        | Method                                                                                                                                                                                                                                             | Result                                                                                            |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Secret values in git history | Each of the five real secrets was read from `.env.local` into a shell variable and searched for in `git log --all -p` (every commit on every branch). The two database passwords were searched for on their own as well. Only counts were printed. | 0 matches for every secret                                                                        |
| Secret patterns in history   | Searched for database URLs with credentials, `apiKey=` followed by 32 hex characters, and common token formats (`sk-`, `ghp_`, `AKIA`, JWTs)                                                                                                       | 0 matches                                                                                         |
| Env files ever committed     | `git log --all -- '*.env.local' '*.env'`                                                                                                                                                                                                           | none                                                                                              |
| Tracked data files           | `git ls-files`, looking for fixtures, caches and payloads                                                                                                                                                                                          | only synthetic fixtures, our own model outputs and the nflverse results fixture (CC-BY, credited) |
| Ignore rules                 | `git check-ignore` on provider captures and the play-by-play cache                                                                                                                                                                                 | both ignored                                                                                      |
| Key redaction                | read the code path; client unit tests                                                                                                                                                                                                              | present                                                                                           |

**To re-run the history scan,** without printing any secret:

```bash
git log --all -p --no-color > /tmp/history.patch
val="$(grep '^ODDS_API_KEY=' apps/collector/.env.local | cut -d= -f2-)"; grep -cF -- "$val" /tmp/history.patch
rm /tmp/history.patch
```

## If a secret leaks

1. Rotate it at the provider (Odds API dashboard, Supabase database password or Vercel env).
2. Update it in GitHub Actions secrets and in Vercel.
3. Purge it from history only if it was committed. Rotating comes first, because a pushed secret
   must be treated as public.
