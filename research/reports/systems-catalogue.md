# System catalogue F1–F10: backtest (MS-045a)

_Generated 2026-10-20 22:04 UTC · commit `2c75e7e` · reproduce with `research/src/marketscope_research/run_catalogue.py`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum F, committed before this code). Graded at the nflverse close at −110 (break-even 52.38%); pushes excluded from win rates. Primary: one-sided exact binomial test per system, Holm–Bonferroni across all ten at a family-wise 0.05, plus a 2024–25 win rate above break-even. Intervals resample games (5,000 draws, seed 2026). F10 is walk-forward from 2018. **Hypothetical results on closing lines; not betting advice.**

**0 of 10 systems supported.**

| System                                             | Decided | Win rate (95% CI)  | p (one-sided) | Passes Holm | 2024–25 win rate (n) | Return at −110 (95% CI) | Result   |
| -------------------------------------------------- | ------- | ------------------ | ------------- | ----------- | -------------------- | ----------------------- | -------- |
| F1 Home underdogs                                  | 992     | 50.8% (47.8–53.9%) | 0.847         | no          | 50.0% (224)          | -2.9% (-9.0 to +2.8)    | no claim |
| F2 Divisional underdogs                            | 966     | 51.6% (48.4–54.7%) | 0.708         | no          | 54.1% (196)          | -1.6% (-7.4 to +4.2)    | no claim |
| F3 Underdogs of 7 or more                          | 783     | 50.6% (47.0–54.2%) | 0.853         | no          | 53.0% (151)          | -3.4% (-9.9 to +3.2)    | no claim |
| F4 Off a bye vs a team that is not                 | 309     | 49.5% (43.8–55.3%) | 0.857         | no          | 45.2% (62)           | -5.4% (-15.9 to +5.2)   | no claim |
| F5 Home team vs a road team on a short week        | 162     | 50.0% (42.6–57.4%) | 0.754         | no          | 52.5% (40)           | -4.4% (-18.6 to +9.8)   | no claim |
| F6 Home team vs a road team on an early body clock | 256     | 49.2% (42.5–55.9%) | 0.859         | no          | 52.2% (67)           | -5.9% (-18.6 to +6.3)   | no claim |
| F7 Divisional unders                               | 977     | 50.6% (47.4–53.6%) | 0.879         | no          | 46.0% (198)          | -3.4% (-9.2 to +2.7)    | no claim |
| F8 Primetime unders                                | 584     | 54.5% (50.3–58.5%) | 0.168         | no          | 50.8% (128)          | +3.9% (-3.7 to +11.2)   | no claim |
| F9 Unders on totals of 50 or more                  | 410     | 52.2% (47.3–57.2%) | 0.550         | no          | 48.1% (54)           | -0.4% (-9.7 to +9.1)    | no claim |
| F10 ML: walk-forward logistic regression           | 556     | 47.1% (42.7–51.5%) | 0.994         | no          | 45.2% (73)           | -9.8% (-18.1 to -1.8)   | no claim |

## Units by season (one unit per position, −110)

| System | 2016  | 2017  | 2018 | 2019  | 2020  | 2021  | 2022  | 2023  | 2024  | 2025 |
| ------ | ----- | ----- | ---- | ----- | ----- | ----- | ----- | ----- | ----- | ---- |
| F1     | -8.4  | -4.3  | +2.8 | -10.1 | +6.5  | -3.0  | +6.0  | -9.3  | -10.7 | +0.6 |
| F2     | -2.5  | -21.4 | -4.4 | -1.4  | +12.6 | -0.6  | +6.9  | -10.9 | +5.2  | +1.2 |
| F3     | -14.0 | -9.6  | +2.2 | -7.4  | +3.4  | -15.2 | +12.0 | -0.2  | +0.8  | +0.9 |
| F4     | +6.1  | +2.4  | +4.3 | -7.3  | -5.3  | -7.0  | +0.6  | -2.1  | -12.9 | +4.4 |
| F5     | +2.1  | +1.3  | +3.2 | -1.6  | -7.4  | -3.5  | -0.7  | -0.7  | +1.0  | -0.9 |
| F6     | -1.2  | +3.8  | -1.6 | -9.8  | -1.9  | -3.1  | +3.8  | -5.3  | +3.5  | -3.6 |
| F7     | -16.8 | +12.7 | +4.3 | -0.6  | -15.9 | -3.5  | +8.9  | +1.4  | -19.7 | -4.5 |
| F8     | -2.5  | -7.4  | -1.6 | +12.9 | -0.6  | +2.1  | +11.6 | +12.4 | -1.9  | -2.0 |
| F9     | -9.4  | +4.8  | +2.5 | +4.3  | -8.0  | -0.7  | +2.5  | +6.8  | -1.1  | -3.3 |
| F10    | +0.0  | +0.0  | -2.6 | -19.4 | -5.7  | -2.5  | -9.8  | -5.7  | -8.3  | -1.7 |

## Reading this

Each win rate is measured against the closing line, the market's most informed number. A public, well-known situation that still beat the close by enough to pay −110 for ten seasons would be surprising; most of these are expected to sit near 50%. The forward paper portfolio tracks every system anyway, so future results are not chosen by these past ones.
