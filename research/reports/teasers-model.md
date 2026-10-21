# Model-priced teaser legs, "Wong 2.0" (MS-055a)

_Generated 2026-10-21 23:41 UTC · commit `69ff544` · reproduce with `research/src/marketscope_research/run_teasers_model.py`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum N, committed before this code). Each team's 6-point teased line is priced with the fair-value engine's margin distribution (fitted only on earlier seasons, calibrated so the nflverse close is the median); legs at or above the −125 break-even (74.54%) are selected, one per game. A push counts as a loss. Game bootstrap (5,000, seed 2026). **Hypothetical results on closing lines; not betting advice.**

## Primary: 2023–25 (out of sample for the model and its bandwidths)

Selected legs: 74.5% (68.7–79.8%), 243 legs. Mean model probability 76.7%. Result: not distinguishable from the −125 break-even: no claim.

## Secondary

- 2018–22: 74.9% (70.3–79.4%), 350 legs. 2018–25: 74.7% (71.2–78.1%), 593 legs.
- Teasers at −125, chronological: 2023–25 -0.9% (-18.2 to +16.4), 109 teasers; 2018–25 +0.8% (-11.3 to +12.7), 259 teasers.
- Selection at the −120 break-even (73.85%): 2018–25 74.3% (70.9–77.5%), 685 legs; teasers at −120 -0.1% (-11.3 to +11.4), 299 teasers.
- Wong V0 legs over the same seasons (2018–25): 75.0% (71.2–78.7%), 553 legs.

| Season | Selected legs | Won   | Mean model probability |
| ------ | ------------- | ----- | ---------------------- |
| 2018   | 107           | 75.7% | 77.3%                  |
| 2019   | 49            | 75.5% | 77.2%                  |
| 2020   | 58            | 79.3% | 76.4%                  |
| 2021   | 75            | 76.0% | 76.5%                  |
| 2022   | 61            | 67.2% | 75.9%                  |
| 2023   | 69            | 76.8% | 76.4%                  |
| 2024   | 75            | 74.7% | 76.2%                  |
| 2025   | 99            | 72.7% | 77.2%                  |

Selected legs by original line (10 or more):

| Line | Legs | Won   | Mean model probability |
| ---- | ---- | ----- | ---------------------- |
| -8.5 | 38   | 71.1% | 76.4%                  |
| -8.0 | 25   | 80.0% | 75.2%                  |
| -7.5 | 124  | 69.4% | 76.6%                  |
| -7.0 | 17   | 52.9% | 74.8%                  |
| +1.5 | 90   | 78.9% | 76.3%                  |
| +2.0 | 19   | 63.2% | 75.5%                  |
| +2.5 | 225  | 76.9% | 77.2%                  |
| +3.0 | 39   | 79.5% | 76.0%                  |

## What this can't see

Prices before the close; each book's teaser rules beyond a push losing; the 2026 season (tracked forward in the paper portfolio as `wong-model`).
