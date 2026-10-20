# Wong teasers: system backtest (MS-044)

_Generated 2026-10-20 21:42 UTC · commit `33238e4` · reproduce with `research/src/marketscope_research/run_systems.py`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum E, committed before this code). Legs: a team at the nflverse closing spread of −7.5 to −8.5 or +1.5 to +2.5, teased six points through 3 and 7. A push counts as a loss for the leg win rate. 95% intervals resample games (legs) or season-weeks (teasers), 5,000 draws, seed 2026. **Hypothetical results on closing lines; not betting advice.**

Break-even leg win rate for a two-team teaser: -110 → 72.4%, -120 → 73.9%, -125 → 74.5%, -130 → 75.2%, -135 → 75.8%, -140 → 76.4%.

## Primary: V0 leg win rate, 2016–25

687 legs: 75.7% (72.5–78.9%). Result: not distinguishable from the -125 break-even (74.5%): no claim.

## Variants

| Variant                               | Legs | Leg win rate (95% CI) | Pushes | Prices whose break-even the interval clears |
| ------------------------------------- | ---- | --------------------- | ------ | ------------------------------------------- |
| V0: every Wong leg                    | 687  | 75.7% (72.5–78.9%)    | 0.3%   | -110                                        |
| V1: closing total 49 or less          | 561  | 76.8% (73.3–80.2%)    | 0.4%   | -110                                        |
| V2: total 49 or less, road teams only | 247  | 80.2% (74.9–85.0%)    | 0.4%   | -110, -120, -125                            |

Stability check (no parameters are fitted; this only asks whether the rate held up recently):

| Variant | 2016–23            | 2024–25            |
| ------- | ------------------ | ------------------ |
| V0      | 76.4% (72.7–80.1%) | 73.6% (67.2–79.9%) |
| V1      | 77.6% (73.4–81.5%) | 74.8% (67.5–81.5%) |
| V2      | 82.1% (76.3–87.9%) | 75.7% (66.2–85.1%) |

Favourites versus underdogs:

| Variant | Favourites (−7.5 to −8.5) | Underdogs (+1.5 to +2.5) |
| ------- | ------------------------- | ------------------------ |
| V0      | 72.5% (66.5–78.0%)        | 77.4% (73.4–81.2%)       |
| V1      | 73.1% (66.7–79.6%)        | 78.7% (74.4–82.7%)       |
| V2      | 76.1% (63.0–87.0%)        | 81.1% (75.6–86.6%)       |

## Teaser return per unit (hypothetical), chronological pairing, push loses

| Variant | -110                   | -120                   | -125                   | -130                   | -135                   | -140                   |
| ------- | ---------------------- | ---------------------- | ---------------------- | ---------------------- | ---------------------- | ---------------------- |
| V0      | +8.7% (-2.2 to +19.4)  | +4.4% (-6.1 to +14.7)  | +2.5% (-7.8 to +12.6)  | +0.8% (-9.4 to +10.7)  | -0.9% (-10.8 to +8.9)  | -2.4% (-12.2 to +7.2)  |
| V1      | +14.4% (+1.5 to +27.0) | +9.8% (-2.5 to +22.0)  | +7.8% (-4.3 to +19.7)  | +6.0% (-5.9 to +17.7)  | +4.3% (-7.5 to +15.8)  | +2.7% (-8.9 to +14.0)  |
| V2      | +12.2% (-8.3 to +32.4) | +7.7% (-11.9 to +27.1) | +5.8% (-13.5 to +24.8) | +3.9% (-15.0 to +22.7) | +2.3% (-16.4 to +20.7) | +0.7% (-17.6 to +18.9) |

At -125:

| Variant | Teasers | Units | Max drawdown (units) | ROI if a push voids | ROI, all pairs in a week |
| ------- | ------- | ----- | -------------------- | ------------------- | ------------------------ |
| V0      | 295     | +7.4  | 12.4                 | +3.2%               | +6.9%                    |
| V1      | 232     | +18.2 | 8.8                  | +8.3%               | +9.6%                    |
| V2      | 80      | +4.6  | 8.0                  | +7.0%               | +6.6%                    |

## By season at -125 (chronological teasers, units)

| Season | V0 legs | V0 win | V0 units | V1 legs | V1 win | V1 units |
| ------ | ------- | ------ | -------- | ------- | ------ | -------- |
| 2016   | 66      | 83.3%  | +7.2     | 53      | 84.9%  | +7.6     |
| 2017   | 68      | 73.5%  | -0.2     | 60      | 73.3%  | +1.2     |
| 2018   | 64      | 71.9%  | +0.0     | 48      | 72.9%  | +0.8     |
| 2019   | 42      | 71.4%  | -4.4     | 34      | 76.5%  | -3.0     |
| 2020   | 61      | 80.3%  | +2.8     | 38      | 81.6%  | +3.0     |
| 2021   | 64      | 84.4%  | +6.4     | 46      | 87.0%  | +6.4     |
| 2022   | 68      | 69.1%  | -3.0     | 58      | 70.7%  | -1.4     |
| 2023   | 80      | 76.2%  | -0.8     | 73      | 76.7%  | -0.6     |
| 2024   | 75      | 74.7%  | -3.2     | 68      | 75.0%  | -0.2     |
| 2025   | 99      | 72.7%  | +2.6     | 83      | 74.7%  | +4.4     |

## 2026 so far (hypothetical; too few legs for any conclusion)

Teasers at -125, chronological pairing, push loses. Caesars' line is its latest main line before kickoff in `line_moves` (games imported so far).

| Line                  | Variant | Legs | W–L–P   | Leg win rate | Teasers | Units | ROI     |
| --------------------- | ------- | ---- | ------- | ------------ | ------- | ----- | ------- |
| nflverse close        | V0      | 34   | 25–9–0  | 73.5%        | 16      | +0.20 | +1.3%   |
| nflverse close        | V1      | 30   | 22–8–0  | 73.3%        | 14      | +0.40 | +2.9%   |
| nflverse close        | V2      | 10   | 7–3–0   | 70.0%        | 2       | -2.00 | -100.0% |
| Caesars' closing line | V0      | 35   | 25–10–0 | 71.4%        | 16      | -1.60 | -10.0%  |
| Caesars' closing line | V1      | 32   | 23–9–0  | 71.9%        | 14      | -1.40 | -10.0%  |
| Caesars' closing line | V2      | 14   | 9–5–0   | 64.3%        | 6       | -0.60 | -10.0%  |

## What this can't see

Prices before the close (a line can be in range on Wednesday and out of it by Sunday); each book's actual teaser rules; limits or account restrictions. Legs are treated as independent; pairing within a week keeps the real constraint that both games must be available together.
