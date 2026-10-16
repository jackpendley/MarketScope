# Provider Coverage — The Odds API

**Status: documentation reviewed, live verification pending.** No real response has been fetched yet; this needs Jack's API key (see README → "Provider verification").

## Documentation review (2026-10-15)

Sources: [v4 guide](https://the-odds-api.com/liveapi/guides/v4/), [bookmaker list](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html), [pricing](https://the-odds-api.com/).

| Book               | Key              | Region | Plan note (per docs)        | Live-verified |
| ------------------ | ---------------- | ------ | --------------------------- | ------------- |
| DraftKings         | `draftkings`     | us     | —                           | pending       |
| FanDuel            | `fanduel`        | us     | —                           | pending       |
| BetMGM             | `betmgm`         | us     | —                           | pending       |
| Caesars            | `williamhill_us` | us     | **Paid subscriptions only** | pending       |
| Hard Rock Bet (AZ) | `hardrockbet_az` | us2    | —                           | pending       |

Other Hard Rock keys exist (`hardrockbet`, `hardrockbet_fl`, `hardrockbet_oh`). We use the Arizona feed per the product spec.

**Cost model (documented):**

- `/odds` costs `markets × regions`.
- The `bookmakers` parameter counts as one region per group of 10 books, and takes priority over `regions`.
- Our request (`h2h,spreads,totals` × 5 named books) should cost **3 credits**. The us2 region of Hard Rock adds nothing.
- `/sports` and `/events` are free, and so are requests that return no events.
- Historical odds are paid-only at `10 × markets × regions` (30 credits per snapshot for us), with 5-minute resolution since September 2022.

**Response notes (documented):**

- Market-level `last_update` is the update timestamp to use.
- Bookmaker-level `last_update` is deprecated.
- Outcomes carry `name`, `price`, and `point` (spreads/totals).

**Rate limiting:** HTTP 429 with no documented Retry-After. Docs advise spacing requests over several seconds. Our client backs off exponentially, up to 3 attempts.

## What "absent" means

A book or market missing from a response means **the provider did not return it for that request**. It does not prove the sportsbook isn't offering the market. Caesars will be absent on the free plan by design.

## Live verification log

Appended by `pnpm verify:provider --spend`. Summaries only, no prices; raw responses stay in gitignored `fixtures/the-odds-api/local/`.
