# Openers and totals, price-aware: discovery (MS-050)

_Generated 2026-10-21 03:04 UTC · commit `f0263ed` · reproduce with `research/src/marketscope_research/run_openers_totals.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum J, committed before this code). Value is expected profit per unit at Pinnacle's no-vig close, converted between lines with empirical 2016–25 margin and total-points distributions. Intervals resample games (5,000 draws, seed 2026). **Analysis, not betting advice.**

**Sample:** 93 games; 93 with Pinnacle spreads, 93 with Pinnacle totals.

## J1: retail openers better than Pinnacle's line at the time

21 positions. Mean value: -2.3% (-6.3 to +1.8). **Primary result:** not distinguishable: no claim.

| Retail book | Positions | Value                |
| ----------- | --------- | -------------------- |
| DraftKings  | 2         | -4.2% (-5.4 to -2.9) |
| Hard Rock   | 16        | -1.8% (-7.0 to +3.3) |
| Caesars     | 3         | -3.7% (-4.8 to -2.1) |

| Opened                          | Positions | Value                 |
| ------------------------------- | --------- | --------------------- |
| More than 7 days before kickoff | 8         | -5.7% (-13.5 to -0.1) |
| 2–7 days                        | 13        | -0.2% (-4.9 to +5.0)  |
| Within 2 days                   | 0         | –                     |

## J2: stale totals

1286 cases. Mean value: -1.8% (-2.5 to -1.1). **Primary result:** **the opposite** (discovery result; confirmation on weeks 7–14 decides).

| Cases             | Count | Points CLV | Value                |
| ----------------- | ----- | ---------- | -------------------- |
| All stale totals  | 1286  | +0.55      | -1.8% (-2.5 to -1.1) |
| At −110 or better | 708   | +0.51      | -1.0% (-1.8 to -0.1) |
| At −111 to −125   | 578   | +0.60      | -2.9% (-3.5 to -2.1) |

## J3: totals at fixed horizons (secondary)

690 retail totals better than Pinnacle's for the side, at −125 or better. Mean value: -3.0% (-3.5 to -2.4). Secondary: **the opposite** (discovery result; confirmation on weeks 7–14 decides).

| Hours before kickoff | Positions | Value                |
| -------------------- | --------- | -------------------- |
| 48                   | 183       | -3.3% (-4.4 to -2.3) |
| 24                   | 163       | -3.4% (-4.2 to -2.5) |
| 6                    | 162       | -2.7% (-3.5 to -1.8) |
| 1                    | 182       | -2.6% (-3.2 to -2.0) |

| Side  | Positions | Value                |
| ----- | --------- | -------------------- |
| over  | 349       | -3.3% (-4.2 to -2.3) |
| under | 341       | -2.7% (-3.7 to -1.8) |

## What this can't see

Openers more than 14 days before kickoff appear as the line in effect 14 days out; exchange totals; who bet.
