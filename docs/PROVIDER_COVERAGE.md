# Provider Coverage — The Odds API

**Status: live-verified on 2026-10-16 (free Starter plan).** DraftKings, FanDuel, BetMGM, and Hard Rock (via its multi-state feed) return data. Hard Rock AZ is empty, and Caesars needs a paid plan.

## Live findings (2026-10-16T01:21Z, one /odds call)

- **Cost confirmed:** `x-requests-last: 3` for `h2h,spreads,totals` × 5 named books. `/sports` and `/events` cost 0.
- **25 NFL events** returned: the current week plus next week. One game was in progress (a Thursday night kickoff).
- **DraftKings and FanDuel:** all 25 games, all three markets.
- **BetMGM:** only the current week (14 games, through Monday night). Next week's games aren't in its feed yet. Its in-progress game had no moneyline. **Coverage depends on time to kickoff**, so books can appear partway through a week.
- **Caesars (`williamhill_us`):** absent. This is expected on the free plan, per the docs.
- **Hard Rock AZ (`hardrockbet_az`):** absent. A 1-credit probe (`probe:books`, `h2h` only) found `hardrockbet` (IN / multi-state), `hardrockbet_fl`, and `hardrockbet_oh` each returning the 14 current-week games, while AZ returned 0. **Resolution (ADR-012):** collect both AZ and `hardrockbet`; the board shows AZ when present and otherwise the labeled IN feed.
- **Shape matches the docs:**
  - Outcome names exactly equal `home_team`/`away_team`, or `Over`/`Under`.
  - Every spread point is a half-point.
  - The deprecated bookmaker-level `last_update` is still present; we ignore it.
  - The in-progress game's `commence_time` had seconds (`00:15:50Z`), which suggests the provider updates it to the actual kickoff time. Event upserts must update `commence_time` (ADR-009 / MS-005).
- Zero events failed schema validation.
- **`last_update` is not a change marker** (observed 2026-10-16 in two runs 21 s apart): DraftKings' market `last_update` advanced while its line stayed the same. Treat it as "the book's market was refreshed", not "the price changed".

## Documentation review (2026-10-15)

Sources: [v4 guide](https://the-odds-api.com/liveapi/guides/v4/), [bookmaker list](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html), [pricing](https://the-odds-api.com/).

| Book               | Key              | Region | Plan note (per docs)        | Live (2026-10-16)       |
| ------------------ | ---------------- | ------ | --------------------------- | ----------------------- |
| DraftKings         | `draftkings`     | us     | —                           | ✅ 25/25 games          |
| FanDuel            | `fanduel`        | us     | —                           | ✅ 25/25 games          |
| BetMGM             | `betmgm`         | us     | —                           | ✅ current week only    |
| Caesars            | `williamhill_us` | us     | **Paid subscriptions only** | ❌ absent (free plan)   |
| Hard Rock Bet (AZ) | `hardrockbet_az` | us2    | —                           | ❌ absent (unexplained) |

Other Hard Rock keys exist (`hardrockbet`, `hardrockbet_fl`, `hardrockbet_oh`). We collect `hardrockbet_az` (preferred, per the product spec) plus `hardrockbet` as the fallback (ADR-012).

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

### Live verification — 2026-10-16T01:21:46.474Z

- Events returned: 25 (rejected by schema: 0, already started: 1)
- Response time: 264 ms
- Credits: this request 3, used 3, remaining 497

| Book                                  | Events with data | Moneyline | Spread | Total | Latest market update     |
| ------------------------------------- | ---------------- | --------- | ------ | ----- | ------------------------ |
| DraftKings (`draftkings`)             | 25               | 25        | 25     | 25    | 2026-10-16T01:21:45.000Z |
| FanDuel (`fanduel`)                   | 25               | 25        | 25     | 25    | 2026-10-16T01:21:22.000Z |
| BetMGM (`betmgm`)                     | 14               | 13        | 14     | 14    | 2026-10-16T01:20:56.000Z |
| Caesars (`williamhill_us`)            | 0                | 0         | 0      | 0     | —                        |
| Hard Rock Bet (AZ) (`hardrockbet_az`) | 0                | 0         | 0      | 0     | —                        |

Normalization issues: MARKET_MISSING × 1, BOOKMAKER_MISSING × 61

<details><summary>Market availability by game (M = moneyline, S = spread, T = total)</summary>

| Game                                        | Kickoff (UTC)            | DraftKings | FanDuel | BetMGM | Caesars | Hard Rock Bet (AZ) |
| ------------------------------------------- | ------------------------ | ---------- | ------- | ------ | ------- | ------------------ |
| Seattle Seahawks @ Denver Broncos (started) | 2026-10-16T00:15:50.000Z | MST        | MST     | ST     | —       | —                  |
| Houston Texans @ Jacksonville Jaguars       | 2026-10-18T13:30:00.000Z | MST        | MST     | MST    | —       | —                  |
| Chicago Bears @ Atlanta Falcons             | 2026-10-18T17:00:00.000Z | MST        | MST     | MST    | —       | —                  |
| Baltimore Ravens @ Cleveland Browns         | 2026-10-18T17:00:00.000Z | MST        | MST     | MST    | —       | —                  |
| Carolina Panthers @ Philadelphia Eagles     | 2026-10-18T17:00:00.000Z | MST        | MST     | MST    | —       | —                  |
| Tennessee Titans @ Indianapolis Colts       | 2026-10-18T17:00:00.000Z | MST        | MST     | MST    | —       | —                  |
| New York Jets @ New England Patriots        | 2026-10-18T17:00:00.000Z | MST        | MST     | MST    | —       | —                  |
| New Orleans Saints @ New York Giants        | 2026-10-18T17:00:00.000Z | MST        | MST     | MST    | —       | —                  |
| Pittsburgh Steelers @ Tampa Bay Buccaneers  | 2026-10-18T17:00:00.000Z | MST        | MST     | MST    | —       | —                  |
| Arizona Cardinals @ Los Angeles Rams        | 2026-10-18T20:05:00.000Z | MST        | MST     | MST    | —       | —                  |
| Buffalo Bills @ Las Vegas Raiders           | 2026-10-18T20:25:00.000Z | MST        | MST     | MST    | —       | —                  |
| Los Angeles Chargers @ Kansas City Chiefs   | 2026-10-18T20:25:00.000Z | MST        | MST     | MST    | —       | —                  |
| Dallas Cowboys @ Green Bay Packers          | 2026-10-19T00:20:00.000Z | MST        | MST     | MST    | —       | —                  |
| Washington Commanders @ San Francisco 49ers | 2026-10-20T00:15:00.000Z | MST        | MST     | MST    | —       | —                  |
| New England Patriots @ Chicago Bears        | 2026-10-23T00:15:00.000Z | MST        | MST     | —      | —       | —                  |
| Pittsburgh Steelers @ New Orleans Saints    | 2026-10-25T13:30:00.000Z | MST        | MST     | —      | —       | —                  |
| San Francisco 49ers @ Atlanta Falcons       | 2026-10-25T17:00:00.000Z | MST        | MST     | —      | —       | —                  |
| Cincinnati Bengals @ Baltimore Ravens       | 2026-10-25T17:00:00.000Z | MST        | MST     | —      | —       | —                  |
| Tampa Bay Buccaneers @ Carolina Panthers    | 2026-10-25T17:00:00.000Z | MST        | MST     | —      | —       | —                  |
| Cleveland Browns @ Tennessee Titans         | 2026-10-25T17:00:00.000Z | MST        | MST     | —      | —       | —                  |
| New York Giants @ Houston Texans            | 2026-10-25T17:00:00.000Z | MST        | MST     | —      | —       | —                  |
| Indianapolis Colts @ Minnesota Vikings      | 2026-10-25T17:00:00.000Z | MST        | MST     | —      | —       | —                  |
| Miami Dolphins @ New York Jets              | 2026-10-25T17:00:00.000Z | MST        | MST     | —      | —       | —                  |
| Green Bay Packers @ Detroit Lions           | 2026-10-25T20:25:00.000Z | MST        | MST     | —      | —       | —                  |
| Los Angeles Rams @ Las Vegas Raiders        | 2026-10-25T20:25:00.000Z | MST        | MST     | —      | —       | —                  |

</details>
