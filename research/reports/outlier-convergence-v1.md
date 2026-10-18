# Study: does an outlier book predict consensus convergence? (v1)

_Generated 2026-10-18 01:14 UTC · commit `93eb271` · sources `the-odds-api, oddspapi` ·
reproduce with `research/src/marketscope_research/run_outlier_convergence.py`._

## Question

When a sportsbook's home spread diverges from the same-snapshot consensus, does the rest of the market
(the consensus) move toward that book's line within the next 24 hours more often than chance?

## Pre-registered design

- **Events:** `book_divergence` v1 onsets: a book ≥ 0.5 pts from the median of ≥ 3 target books in one
  snapshot (`docs/SIGNAL_DEFINITIONS.md`). Point-in-time: uses only data observed at the event's snapshot.
- **Outcome:** consensus at the snapshot nearest t + 24 h within ±6 h, pregame, ≥ 3 books.
  _toward_ = moved in the direction of the book's deviation; _away_ = opposite; _none_ = unchanged. Events with
  no eligible horizon snapshot are excluded and counted.
- **Baselines:** the unconditional share of eligible snapshots whose consensus changed by the horizon, in either
  direction; _toward by chance_ = half of it.
- **Inference:** 95% bootstrap CI (5,000 resamples) resampling **games**, since events within a game are correlated.
- **Minimum sample:** ≥ 30 scored events from ≥ 15 games, otherwise inconclusive.

## Data

|                                          |                                         |
| ---------------------------------------- | --------------------------------------- |
| Observations (home spreads, pregame)     | 27,199                                  |
| Snapshots                                | 292                                     |
| Games                                    | 103 (oddspapi: 79, the-odds-api: 24)    |
| Observed range                           | 2026-08-11 06:00 – 2026-10-17 20:29 UTC |
| Divergence events                        | 571                                     |
| Events with an eligible horizon          | 476 (from 83 games)                     |
| Consensus cross-check (Python vs stored) | 571/571 match                           |

## Results

| Outcome                                       | Events                                        |
| --------------------------------------------- | --------------------------------------------- |
| Consensus moved toward the book               | 138                                           |
| Moved away                                    | 80                                            |
| No change                                     | 258                                           |
| **Toward rate**                               | **29.0%** (95% game-clustered CI 24.7%–33.2%) |
| Any consensus move at horizon (all snapshots) | 20.6% of 4141                                 |
| Toward by chance (baseline)                   | 10.3%                                         |

**Verdict:** The consensus moved toward the diverging book in 29.0% of events (95% game-clustered CI 24.7%–33.2%), above the 10.3% chance baseline.

## Exploratory robustness checks (added after seeing v1 results; not pre-registered)

The chance baseline is unconditional, but divergences tend to occur while a market is already moving, so
the baseline may understate how often the consensus moves after one. A check that doesn't depend on it:
**among events where the consensus moved, what share moved toward the book?** If divergence carried no
directional information, that share would be about 50%.

- Toward share of moves: **63.3%** of 218 (95% game-clustered CI 58.5%–68.6%)

| Source       | Events | Games | Toward | Away | None | Toward rate | Toward share of moves |
| ------------ | ------ | ----- | ------ | ---- | ---- | ----------- | --------------------- |
| oddspapi     | 467    | 78    | 135    | 77   | 255  | 28.9%       | 63.7%                 |
| the-odds-api | 9      | 5     | 3      | 3    | 3    | 33.3%       | 50.0%                 |

| Diverging book | Events | Games | Toward | Away | None | Toward rate | Toward share of moves |
| -------------- | ------ | ----- | ------ | ---- | ---- | ----------- | --------------------- |
| fanduel        | 134    | 66    | 40     | 31   | 63   | 29.9%       | 56.3%                 |
| draftkings     | 123    | 62    | 34     | 23   | 66   | 27.6%       | 59.6%                 |
| hardrockbet    | 118    | 58    | 29     | 12   | 77   | 24.6%       | 70.7%                 |
| williamhill_us | 99     | 47    | 34     | 14   | 51   | 34.3%       | 70.8%                 |
| betmgm         | 2      | 2     | 1      | 0    | 1    | 50.0%       | 100.0%                |

Treat these as descriptive. They were chosen after the primary result was known, and per-group cells are small.

## Limitations

- **Polling resolution:** about 4 snapshots/day, so the horizon snapshot can be up to 6 h from t + 24 h.
- **Coverage:** only board books count toward consensus (Pinnacle is stored but excluded). Live snapshots lack
  Caesars (paid plan) and imported history lacks BetMGM (failed validation), so most snapshots have 4 books.
- **Derived snapshots:** imported games are resampled from change logs. If the provider missed a book's update,
  that book looks stale-but-divergent until its next recorded change, and the consensus can appear to move
  "toward" it when the other books revert. Validation agreement was 85–100% for the books used, not 100%.
- **Source imbalance:** almost all scored events come from imported history (see the per-source table).
- **Sources:** live Odds API snapshots (from 2026-10-16) and OddsPapi line-move history imported for
  earlier games as derived 6-hourly snapshots (ADR-026). Each game uses exactly one source. OddsPapi
  excludes BetMGM and carries quotes forward between recorded changes (its change-log semantics).
- **Cause:** a consensus moving toward a book does not mean the book "knew" anything. Shared news (injuries,
  weather) moves all books, and the diverging book may simply have updated first.
- **The chance baseline assumes symmetric direction.** That's reasonable for a first pass, but it's an
  assumption, not a fact.
