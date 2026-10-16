# Data Dictionary

## Domain concepts

| Concept                     | Definition                                                                                                                    |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Market**                  | `h2h` (moneyline), `spreads` (point spread), `totals` (over/under)                                                            |
| **Selection**               | `HOME`, `AWAY` (h2h, spreads) · `OVER`, `UNDER` (totals)                                                                      |
| **Point**                   | The spread or total line. Spreads keep the book's sign (home −3.5 = home favored by 3.5). Always `null` for moneylines        |
| **American price**          | Integer with \|price\| ≥ 100. −110 means risk 110 to win 100; +150 means risk 100 to win 150. −100 ≡ +100                     |
| **Raw implied probability** | −A → A/(A+100); +A → 100/(A+100). Includes the bookmaker's margin; **not** a calibrated win probability                       |
| **Overround**               | Sum of raw implied probabilities across a complete outcome set at the same line, minus 1                                      |
| **Identical line**          | Same event, market, selection, **and point**. Prices are compared only within an identical line                               |
| **Home-oriented spread**    | For history, stats, and consensus, always use the home team's spread. A move from −3.5 to −2.5 is +1.0 (toward the away side) |

## NormalizedQuote (`packages/shared/src/domain.ts`)

| Field                | Type               | Meaning                                                                                           |
| -------------------- | ------------------ | ------------------------------------------------------------------------------------------------- |
| `providerEventId`    | string             | Provider's event ID (mapped to an internal UUID in Phase 1)                                       |
| `bookmakerKey`       | string             | Provider bookmaker key, e.g. `draftkings`                                                         |
| `market`             | Market             |                                                                                                   |
| `selection`          | Selection          | Taken from exact equality with the event's `home_team`/`away_team`, or Over/Under                 |
| `point`              | number \| null     | See above                                                                                         |
| `americanPrice`      | number             | Validated integer American odds                                                                   |
| `bookmakerUpdatedAt` | ISO string \| null | **Provider-reported** market `last_update`: when the book's market last changed, per the provider |
| `observedAt`         | ISO string         | **When we received** the response (live), or the provider's snapshot time (historical)            |
| `isLive`             | boolean            | `commence_time <= observedAt`: the event had started, so prices are in-play                       |

## Timestamp semantics

| Timestamp               | Source                                                                | Use                                                           |
| ----------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------- |
| `bookmaker_updated_at`  | Provider market `last_update`                                         | Book freshness, i.e. whether a book is stale for consensus    |
| `observed_at`           | Our collector clock at response time, or the historical snapshot time | Ordering observations and replay cursors                      |
| `requested_snapshot_at` | What we asked the historical endpoint for                             | Provenance and caching                                        |
| `provider_snapshot_at`  | What the historical endpoint actually returned                        | Becomes `observed_at` for historical rows                     |
| `commence_time`         | Provider event kickoff                                                | Pregame/live classification; can change when games are flexed |

**Rules:**

- A change seen between two observations happened somewhere in `(prev.observed_at, next.observed_at]`. We never claim an exact time.
- The first observation is "first observed", not the opening line. The last pregame observation is "last observed pregame", not the closing line.
- Never stamp historical data with the import time.

## Normalization issues

Codes are defined in `NORMALIZATION_ISSUE_CODES`:

- `BOOKMAKER_MISSING` / `UNEXPECTED_BOOKMAKER`
- `MARKET_MISSING` / `UNEXPECTED_MARKET`
- `INCOMPLETE_MARKET`
- `UNKNOWN_OUTCOME`
- `DUPLICATE_SELECTION` (all copies dropped)
- `INVALID_PRICE` (dropped)
- `INVALID_POINT` (dropped)
- `UNEXPECTED_POINT` (moneyline point ignored)
- `INCONSISTENT_SPREAD` (kept and flagged)
- `INVALID_TIMESTAMP` (stored as null)

## Database tables

Defined in Phase 1. See ROADMAP MS-004. This section will document each column once the migrations exist.
