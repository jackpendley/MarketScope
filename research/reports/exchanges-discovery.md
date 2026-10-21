# Exchanges, price-aware with fees: discovery (MS-051)

_Generated 2026-10-21 04:11 UTC · commit `86e9bf6` · reproduce with `research/src/marketscope_research/run_exchanges.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum K, committed before any exchange import or study code). Value is expected profit per unit at Pinnacle's no-vig close after fees (Novig none; ProphetX 2% of net winnings; Kalshi 0.07·p·(1−p) per contract). Size floor: 100 at the top of book. Intervals resample games (5,000 draws, seed 2026). **Analysis, not betting advice.**

**Sample:** 93 games. Exchange rows: Kalshi 63,216, Novig 57,702, ProphetX 96,192.

## K1: stale exchange prices

1715 cases: an exchange still offering Pinnacle's old line 60 s after it moved, on the side Pinnacle moved toward, at −125 or better with size ≥ 100. Mean value after fees: -1.2% (-1.6 to -0.8). **Primary result:** **the opposite** (discovery result; confirmation on weeks 7–14 decides).

| Exchange | Cases | Median time the old line stayed up | Value                |
| -------- | ----- | ---------------------------------- | -------------------- |
| Kalshi   | 593   | 341 min                            | -2.6% (-3.2 to -2.1) |
| Novig    | 635   | 290 min                            | +0.4% (-0.2 to +0.9) |
| ProphetX | 487   | 32 min                             | -1.4% (-2.0 to -0.9) |

| Market  | Cases | Points CLV | Value                |
| ------- | ----- | ---------- | -------------------- |
| spreads | 978   | +0.36      | -1.2% (-1.9 to -0.6) |
| totals  | 737   | +0.46      | -1.1% (-1.6 to -0.6) |

Exploratory: with a size floor of 1,000: 1218 cases, -1.6% (-2.1 to -1.2). With ProphetX at 1%: -1.0% (-1.5 to -0.6).

### K1n: Novig only (Addendum L; registered after discovery, tested on confirmation)

Novig cases: 635, mean value +0.4% (-0.2 to +0.9); with a size floor of 1,000: 429, -0.1% (-0.6 to +0.5). Discovery numbers motivated this hypothesis, so they are not evidence for it.

## K2: exchange prices better than Pinnacle's at fixed horizons (secondary)

855 positions. Mean value after fees: -3.0% (-3.4 to -2.6). Secondary: **the opposite** (discovery result; confirmation on weeks 7–14 decides).

| Exchange | Positions | Value                |
| -------- | --------- | -------------------- |
| Kalshi   | 358       | -4.5% (-5.0 to -4.0) |
| Novig    | 346       | -1.5% (-2.0 to -1.1) |
| ProphetX | 151       | -3.0% (-3.6 to -2.5) |

| Hours before kickoff | Positions | Value                |
| -------------------- | --------- | -------------------- |
| 48                   | 213       | -3.6% (-4.3 to -2.8) |
| 24                   | 235       | -3.2% (-3.9 to -2.6) |
| 1                    | 210       | -2.4% (-2.8 to -1.9) |
| 6                    | 197       | -2.9% (-3.4 to -2.4) |

## What this can't see

Depth beyond the top of book; whether an order would have filled before the price moved; exchange account limits; Kalshi fees rounded to cents.
