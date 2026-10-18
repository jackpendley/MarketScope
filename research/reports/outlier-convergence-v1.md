# Study: does an outlier book predict consensus convergence? (v1)

_Generated 2026-10-17 23:59 UTC · commit `e0a0448` · source `the-odds-api` ·
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
| Observations (home spreads, pregame)     | 592                                     |
| Snapshots                                | 8                                       |
| Games                                    | 24                                      |
| Observed range                           | 2026-10-16 02:32 – 2026-10-17 20:29 UTC |
| Divergence events                        | 13                                      |
| Events with an eligible horizon          | 9 (from 5 games)                        |
| Consensus cross-check (Python vs stored) | 13/13 match                             |

## Results

| Outcome                                       | Events                                       |
| --------------------------------------------- | -------------------------------------------- |
| Consensus moved toward the book               | 3                                            |
| Moved away                                    | 3                                            |
| No change                                     | 3                                            |
| **Toward rate**                               | **33.3%** (95% game-clustered CI 0.0%–52.9%) |
| Any consensus move at horizon (all snapshots) | 25.0% of 52                                  |
| Toward by chance (baseline)                   | 12.5%                                        |

**Verdict:** **Inconclusive: sample below the pre-registered minimum** (9 scored events from 5 games; minimum 30 events from 15 games). No claim is made either way. Re-run as history accumulates.

## Limitations

- **Polling resolution:** about 4 snapshots/day, so the horizon snapshot can be up to 6 h from t + 24 h.
- **Coverage:** only the target books. Caesars is absent on the free data plan, and BetMGM posts only the
  current week, so many snapshots have the 3-book minimum and little else.
- **Selection:** every game in the database with collected data is included; history begins 2026-10-16.
- **Cause:** a consensus moving toward a book does not mean the book "knew" anything. Shared news (injuries,
  weather) moves all books, and the diverging book may simply have updated first.
- **The chance baseline assumes symmetric direction.** That's reasonable for a first pass, but it's an
  assumption, not a fact.
