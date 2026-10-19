# Football studies v1: R1, R3, R4, R5 (MS-035)

_Generated 2026-10-19 00:14 UTC · commit `81edd33` · reproduce with `research/src/marketscope_research/run_football_studies.py`._

Design pre-registered in `research/PREREGISTRATION.md` (commit 168538a, before this code). 95% intervals resample games (5,000 draws). Model estimates and market data; not betting advice.

## Summary

| Study | Primary hypothesis                                   | Estimate (95% CI)                                 | Claim?              |
| ----- | ---------------------------------------------------- | ------------------------------------------------- | ------------------- |
| R1    | Consensus more accurate at the close than 6 days out | +0.03 (-0.26 to +0.28) pts                        | no                  |
| R3    | Wind under- or over-priced in closing totals         | -0.084 (-0.377 to +0.198) pts per mph             | inconclusive (gate) |
| R4    | Ratings carry information beyond the close           | +0.118 (-0.047 to +0.290) ATS pts per pt of gap   | no                  |
| R5    | Market overrates lucky teams                         | -0.017 (-0.502 to +0.466) ATS pts per win of luck | no                  |

## R1: market accuracy over time (2026)

77 final 2026 games with a board consensus at all four leads (gate: 60; sources: oddspapi 77).

| Line           | Margin MAE | Minus our close (paired) |
| -------------- | ---------- | ------------------------ |
| 6 days         | 9.93       | +0.03 (-0.26 to +0.28)   |
| 3 days         | 10.02      | +0.12 (-0.02 to +0.27)   |
| 1 day          | 9.94       | +0.03 (-0.06 to +0.12)   |
| close          | 9.90       | –                        |
| nflverse close | 9.90       | +0.00 (-0.10 to +0.08)   |

Closing line of each board book vs the consensus in the same snapshot (exploratory; negative = the book was closer to the result):

| Book       | Games | MAE   | Minus consensus        |
| ---------- | ----- | ----- | ---------------------- |
| caesars    | 76    | 10.04 | +0.14 (-0.10 to +0.54) |
| draftkings | 74    | 10.16 | +0.07 (-0.01 to +0.17) |
| fanduel    | 77    | 9.89  | -0.01 (-0.08 to +0.06) |
| hardrock   | 77    | 9.90  | -0.01 (-0.07 to +0.06) |

## R3: weather and totals (2024–26)

534 outdoor/open-roof games with a 1-day forecast and a closing total; 29 with forecast wind ≥ 15 mph (gate: 200 and 30). **The gate is not met, so the primary result is inconclusive**; the estimate is shown for transparency and makes no claim. It will be re-run when more windy games are final.

- **Primary:** total residual (actual − close) per mph of forecast wind: -0.084 (-0.377 to +0.198).
- **Market response (exploratory):** the closing total moves -0.193 points per mph (HC1 SE 0.051, season fixed effects).
- **Precipitation (descriptive):** 59 games with forecast precipitation; mean residual -0.93 vs +1.69 dry.

| Forecast wind (mph) | Games | Mean close | Mean residual (actual − close) |
| ------------------- | ----- | ---------- | ------------------------------ |
| < 10                | 402   | 44.9       | +1.70 (+0.42 to +3.01)         |
| 10-15               | 103   | 43.7       | +0.07 (-1.97 to +2.16)         |
| >= 15               | 29    | 42.2       | +1.97 (-3.55 to +7.88)         |

- **Movement (exploratory, 2026 odds):** 1 game crossed 15 mph between the 3-day and 1-day forecasts (gate 15): inconclusive.

## R4: is performance priced? (2016–24)

2367 games. Mean absolute gap between the rating margin and the close: 2.42 pts.

- **Primary:** ATS residual per point of gap: +0.118 (-0.047 to +0.290); positive in 6 of 9 seasons. Claim rule (interval above 0 and ≥ 6 positive seasons): not met.
- **2023–24 only (out-of-sample for the rating parameters):** -0.110 (-0.443 to +0.260).
- **Per season:** 2016 +0.414, 2017 -0.278, 2018 +0.350, 2019 +0.273, 2020 +0.381, 2021 +0.111, 2022 +0.273, 2023 -0.214, 2024 -0.039.
- **Closing move (exploratory, 2026):** 77 games (gate 60); consensus move per point of 6-day gap: +0.100 (+0.029 to +0.178).

## R5: luck regression (2016–24)

1796 games from week 5; SD of the luck difference 1.22 wins.

- **Primary (market):** ATS residual per win of luck difference: -0.017 (-0.502 to +0.466).
- **Ratings (exploratory):** rating residual per win of luck difference: +0.369 (-0.142 to +0.887).
- **Persistence (exploratory):** luck gained after week 9 per win of luck through week 9: +0.077 (-0.047 to +0.202) (288 team-seasons).

## Not run yet

- **R2 (injury news):** live injury snapshots began 2026-10-18; gate 30 events.
- **R6 (model + market blend) and R7 (play-caller impact):** next milestone.
