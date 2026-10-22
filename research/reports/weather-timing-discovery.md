# Weather-forecast revisions and totals timing: discovery (MS-056)

_Generated 2026-10-22 21:00 UTC · commit `103e2bc` · reproduce with `research/src/marketscope_research/run_weather_timing.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum U, committed before this code). Archived ECMWF IFS runs (Open-Meteo Single Runs API; weather data by Open-Meteo.com, CC BY 4.0), available 6 hours after initialisation. An event is a game-window wind revision of at least 4 mph (either run at least 12 mph), public 72 to 1 hours before kickoff. Positions take the forecast's side of each book's main total 10 minutes after availability; value at the sharp-consensus close (engine v3, MS-058 ghost rule). Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**

**Sample:** 77 outdoor or retractable-roof games, 77 in the lake; 2 with at least one event; 15 positions.

## Primary

Mean value at the close: -5.45% (-8.29 to -4.02). **Primary result:** **the opposite** (discovery result; confirmation on weeks 7–18 decides).

_Positions come from 2 games in 2 weeks._ _With fewer than 10 games a game bootstrap cannot support any conclusion; read the primary as inconclusive whatever its interval (reporting note added after the first run)._

| Book         | Positions | Value at the close      |
| ------------ | --------- | ----------------------- |
| Caesars      | 3         | -5.05% (-8.52 to -3.31) |
| DraftKings   | 3         | -5.19% (-6.46 to -4.56) |
| FanDuel      | 3         | -6.28% (-9.43 to -4.70) |
| Hard Rock    | 3         | -5.87% (-8.52 to -4.55) |
| Pinnacle     | 3         | -4.84% (-8.52 to -2.99) |
| Retail books | 12        | -5.60% (-8.23 to -4.28) |

## Secondary

Placebo, the same positions 3 hours before the run existed: 15 positions, -5.68% (-8.29 to -4.37).

Reaction: Pinnacle's total move per mph of revision, over 908 in-window runs: within 6 hours +0.004 (-0.008 to +0.016) points; to the close -0.020 (-0.063 to +0.021) points. Negative means the market moves with the forecast.

## Exploratory

| Event source                   | Positions | Games | Value at the close       |
| ------------------------------ | --------- | ----- | ------------------------ |
| GFS wind                       | 25        | 2     | -2.91% (-3.28 to -1.42)  |
| HRRR wind (within 48 h)        | 14        | 3     | -7.11% (-14.47 to -2.42) |
| ECMWF precipitation (≥ 0.1 in) | 305       | 15    | -3.54% (-4.25 to -2.83)  |

Minutes from availability to Pinnacle's next total change (median): events 1816 min (3 runs); other in-window runs 1025 min (830 runs).

## What this can't see

Forecasts the market saw before Open-Meteo's archive did; runs other than 00, 06, 12 and 18 UTC; whether a retail price would have been accepted at size; wind inside the stadium bowl.
