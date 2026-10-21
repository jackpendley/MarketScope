# Injury-report windows and the line: discovery (MS-047)

_Generated 2026-10-21 02:54 UTC · commit `b2297ad` · reproduce with `research/src/marketscope_research/run_injury_windows.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum I, committed before this code). The window runs from 4 hours before to 2 hours after the 4 pm ET game-status deadline (the day before Thursday games, two days before others). Events: starters newly listed Out (R2w's definition). Intervals resample games (5,000 draws, seed 2026). Value is closing-line value at Pinnacle's no-vig close. **Analysis, not betting advice.**

**Sample:** 77 games from week 2; 76 with Pinnacle on the board at both window edges; 44 with net news (N ≠ 0); 95 events in qualifying games.

## I1: does Pinnacle price the news inside the window?

Slope of Pinnacle's window move (margin points, toward the healthier side) on N: +0.02 (-0.00 to +0.05) points per net event. Gate: 30 events (met). **Primary result:** not distinguishable: no claim.

| N (away − home events) | Games | Mean window move (points) |
|---|---|---|
| -3 | 1 | +0.00 |
| -2 | 7 | +0.00 |
| -1 | 16 | -0.06 |
| 0 | 32 | +0.08 |
| 1 | 16 | +0.03 |
| 2 | 4 | +0.00 |

Exploratory: in games with N ≠ 0, the window holds 0% of the net move from 6 days out to the close, oriented by the news.

## I2: are retail books slower on injury news?

News-window cases: 18 stale retail numbers after a Pinnacle move in the direction of the news, inside the window. Gate: 50 (not met).

Mean price-aware value: -0.3% (-2.9 to +2.5). **Primary result:** inconclusive (gate not met).

Difference from all other stale numbers: +1.8% (-1.2 to +4.8). Secondary: inconclusive (gate not met).

| Cases | Count | Median time the old number stayed up | Mean value per unit |
|---|---|---|---|
| News-window cases | 18 | 1940 min | -0.3% |
| All other cases | 1270 | 294 min | -2.1% |

## What this can't see

The minute each designation became public (only the deadline is known); practice-report news earlier in the week; Questionable and Doubtful designations.
