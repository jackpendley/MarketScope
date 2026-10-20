# System catalogue F1–F10: backtest (MS-045a)

_Generated 2026-10-20 22:14 UTC · commit `288f664` · reproduce with `research/src/marketscope_research/run_catalogue.py`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum F, committed before this code). Graded at the nflverse close at −110 (break-even 52.38%); pushes excluded from win rates. Primary: one-sided exact binomial test per system, Holm–Bonferroni across all ten at a family-wise 0.05, plus a 2024–25 win rate above break-even. Intervals resample games (5,000 draws, seed 2026). F10 is walk-forward from 2018. **Hypothetical results on closing lines; not betting advice.**

**0 of 10 systems supported.**

| System                                             | Decided | Win rate (95% CI)  | p (one-sided) | Passes Holm | 2024–25 win rate (n) | Return at −110 (95% CI) | Result   |
| -------------------------------------------------- | ------- | ------------------ | ------------- | ----------- | -------------------- | ----------------------- | -------- |
| F1 Home underdogs                                  | 992     | 50.8% (47.8–53.9%) | 0.847         | no          | 50.0% (224)          | -2.9% (-9.0 to +2.8)    | no claim |
| F2 Divisional underdogs                            | 958     | 51.7% (48.5–54.8%) | 0.682         | no          | 53.8% (195)          | -1.3% (-7.1 to +4.4)    | no claim |
| F3 Underdogs of 7 or more                          | 775     | 50.7% (47.1–54.3%) | 0.833         | no          | 52.7% (150)          | -3.1% (-9.5 to +3.5)    | no claim |
| F4 Off a bye vs a team that is not                 | 289     | 49.5% (43.9–55.0%) | 0.852         | no          | 44.8% (58)           | -5.4% (-16.3 to +4.9)   | no claim |
| F5 Home team vs a road team on a short week        | 162     | 50.0% (42.6–57.4%) | 0.754         | no          | 52.5% (40)           | -4.4% (-18.6 to +9.8)   | no claim |
| F6 Home team vs a road team on an early body clock | 226     | 48.2% (41.6–54.4%) | 0.906         | no          | 49.1% (57)           | -7.8% (-20.1 to +4.6)   | no claim |
| F7 Divisional unders                               | 969     | 50.7% (47.6–53.8%) | 0.864         | no          | 46.2% (197)          | -3.2% (-9.1 to +2.9)    | no claim |
| F8 Primetime unders                                | 572     | 54.7% (50.5–58.7%) | 0.140         | no          | 51.2% (125)          | +4.4% (-3.0 to +11.7)   | no claim |
| F9 Unders on totals of 50 or more                  | 400     | 51.7% (47.0–56.8%) | 0.619         | no          | 48.1% (54)           | -1.2% (-10.4 to +8.3)   | no claim |
| F10 ML: walk-forward logistic regression           | 514     | 48.6% (44.2–52.9%) | 0.959         | no          | 50.0% (66)           | -7.0% (-15.2 to +1.0)   | no claim |

## Units by season (one unit per position, −110)

| System | 2016  | 2017  | 2018 | 2019  | 2020  | 2021  | 2022  | 2023  | 2024  | 2025 |
| ------ | ----- | ----- | ---- | ----- | ----- | ----- | ----- | ----- | ----- | ---- |
| F1     | -8.4  | -4.3  | +2.8 | -10.1 | +6.5  | -3.0  | +6.0  | -9.3  | -10.7 | +0.6 |
| F2     | -1.4  | -20.4 | -4.4 | -0.4  | +11.7 | -0.6  | +7.9  | -10.9 | +5.2  | +0.3 |
| F3     | -14.0 | -7.5  | +2.2 | -6.4  | +2.5  | -15.2 | +13.1 | -0.2  | +0.8  | +0.0 |
| F4     | +6.2  | -1.4  | +2.5 | -5.3  | -3.3  | -5.0  | -1.3  | -0.1  | -10.9 | +2.5 |
| F5     | +2.1  | +1.3  | +3.2 | -1.6  | -7.4  | -3.5  | -0.7  | -0.7  | +1.0  | -0.9 |
| F6     | -0.1  | +2.9  | -0.6 | -9.6  | -1.9  | -4.9  | +4.0  | -4.1  | -0.2  | -3.4 |
| F7     | -15.8 | +11.8 | +4.3 | -1.4  | -14.9 | -3.5  | +9.9  | +1.4  | -19.7 | -3.5 |
| F8     | -1.6  | -6.3  | -3.5 | +12.0 | +0.5  | +2.1  | +12.6 | +12.4 | -1.8  | -1.0 |
| F9     | -8.4  | +3.0  | +1.6 | +2.5  | -8.9  | -0.7  | +4.5  | +5.9  | -1.1  | -3.3 |
| F10    | +0.0  | +0.0  | -0.5 | -20.3 | -0.2  | -2.2  | -9.8  | -0.8  | -5.4  | +2.4 |

## Reading this

Each win rate is measured against the closing line, the market's most informed number. A public, well-known situation that still beat the close by enough to pay −110 for ten seasons would be surprising; most of these are expected to sit near 50%. The forward paper portfolio tracks every system anyway, so future results are not chosen by these past ones.
