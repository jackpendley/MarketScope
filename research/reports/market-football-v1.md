# Market-movement model with football features (MS-036, v1)

_Generated 2026-10-19 02:45 UTC · commit `ec4c490` on `main` · sources `the-odds-api, oddspapi` ·
reproduce with `research/src/marketscope_research/run_market_football.py`. Design pre-registered in
`ml/design_football.py` (committed before any football feature was built); the target, split and scoring are v1's
(`market-baseline-v1.md`)._

## Summary

- **Will it move:** football model minus market-only model on the test week: Δ Brier +0.0011 (-0.0015 to +0.0039), Δ log loss +0.002 (-0.007 to +0.011): **not distinguishable (a CI includes 0)**.
- **Direction:** football model minus market-only model on the test week: Δ Brier +0.0373 (+0.0045 to +0.0776), Δ log loss +0.081 (+0.010 to +0.172): **worse (both CIs above 0)**.

"Better" requires both the Brier and the log-loss difference CIs to lie below zero (2,000 game-resampled bootstraps).

## Football features (point in time at each snapshot)

| Family   | Will-it-move features                                                               | Direction feature                                       |
| -------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Ratings  | abs_rating_gap: \|rating margin − consensus margin\|                                | rating_gap (+ = ratings like home more than the market) |
| Injuries | starters_hurt_total: starters who played < 25% of snaps in their team's latest game | starters_hurt_net (away − home)                         |
| Weather  | wind_mph, abs_wind_change, outdoor (shortest usable forecast lead)                  | –                                                       |
| Schedule | abs_rest_diff, away_travel_km, short_week_any                                       | rest_diff (home − away)                                 |

Rating margins use the latest ratings-v1 snapshot usable at t (16 h after its week's last kickoff); snap counts only from
games that kicked off at least 36 h before t; a forecast at lead N days only from kickoff − N days. A unit test perturbs
everything usable after t and checks that no feature changes. Implementation detail fixed before fitting: a starter's
average uses up to three of his team's games before its latest one (at least one), so weeks 2–3 are covered.

Share of labelled rows (train, validation, test) where each feature is missing (imputed with the median plus a missing
indicator, as in v1):

| index               | missing |
| ------------------- | ------- |
| rating_gap          | 0.0%    |
| abs_rating_gap      | 0.0%    |
| starters_hurt_home  | 45.5%   |
| starters_hurt_away  | 46.0%   |
| starters_hurt_total | 46.5%   |
| starters_hurt_net   | 46.5%   |
| wind_mph            | 1.6%    |
| abs_wind_change     | 1.6%    |
| outdoor             | 0.0%    |
| rest_diff           | 5.1%    |
| abs_rest_diff       | 5.1%    |
| away_travel_km      | 0.0%    |
| short_week_any      | 0.0%    |

## 1. Will the consensus move ≥ 0.5 pts within 24 h?

| split      | games | rows | positives | positive_rate |
| ---------- | ----- | ---- | --------- | ------------- |
| train      | 48    | 1120 | 152       | 13.6%         |
| validation | 16    | 363  | 61        | 16.8%         |
| test       | 15    | 348  | 79        | 22.7%         |
| forward    | 13    | 92   | 15        | 16.3%         |

Rating margin available for 100.0% of fitting rows (gate 90%: met).

Chosen L2 strength C on validation: logistic (market only) = 0.01, logistic + football = 0.01, market + ratings = 0.01, market + injuries = 0.01, market + weather = 0.01, market + schedule = 0.01.

### Test week (scored once), paired against the market-only model

| Model                  | Brier (95% CI)            | Log loss (95% CI)         | AUC (95% CI)           | Δ Brier vs logistic (market only) | Δ log loss vs logistic (market only) |
| ---------------------- | ------------------------- | ------------------------- | ---------------------- | --------------------------------- | ------------------------------------ |
| constant               | 0.1824 (0.1274 to 0.2351) | 0.5604 (0.4226 to 0.6923) | 0.500 (0.500 to 0.500) | 0.0205 (-0.0040 to 0.0509)        | 0.0621 (-0.0086 to 0.1477)           |
| logistic (market only) | 0.1619 (0.1132 to 0.2150) | 0.4983 (0.3677 to 0.6391) | 0.724 (0.568 to 0.860) | 0.0000 (0.0000 to 0.0000)         | 0.0000 (0.0000 to 0.0000)            |
| logistic + football    | 0.1630 (0.1153 to 0.2150) | 0.5002 (0.3738 to 0.6362) | 0.714 (0.563 to 0.853) | 0.0011 (-0.0015 to 0.0039)        | 0.0019 (-0.0074 to 0.0111)           |
| market + ratings       | 0.1634 (0.1144 to 0.2166) | 0.5037 (0.3732 to 0.6453) | 0.708 (0.551 to 0.852) | 0.0014 (-0.0001 to 0.0029)        | 0.0054 (0.0008 to 0.0098)            |
| market + injuries      | 0.1594 (0.1118 to 0.2103) | 0.4905 (0.3670 to 0.6240) | 0.726 (0.570 to 0.862) | -0.0025 (-0.0052 to 0.0000)       | -0.0078 (-0.0162 to 0.0009)          |
| market + weather       | 0.1620 (0.1134 to 0.2147) | 0.4973 (0.3686 to 0.6366) | 0.731 (0.578 to 0.865) | 0.0000 (-0.0010 to 0.0014)        | -0.0010 (-0.0053 to 0.0034)          |
| market + schedule      | 0.1623 (0.1125 to 0.2152) | 0.4999 (0.3659 to 0.6427) | 0.721 (0.570 to 0.857) | 0.0004 (-0.0020 to 0.0031)        | 0.0016 (-0.0054 to 0.0090)           |

**Primary (logistic + football vs logistic (market only)):** not distinguishable (a CI includes 0). Rows other than these two and the constant are exploratory ablations.

### Coefficients of the football model (final fit, standardized)

| Feature (standardized)               | Coefficient |
| ------------------------------------ | ----------- |
| short_week_any                       | +0.241      |
| abs_move_24h                         | +0.157      |
| range                                | +0.141      |
| mean_abs_dev                         | +0.136      |
| half_point                           | -0.125      |
| missingindicator_abs_move_6h         | +0.122      |
| median_quote_age_h                   | -0.104      |
| missingindicator_starters_hurt_total | -0.100      |
| totals_abs_move_24h                  | +0.099      |
| dow_et_4                             | -0.099      |
| abs_rating_gap                       | +0.092      |
| dow_et_5                             | +0.084      |
| abs_wind_change                      | -0.083      |
| dow_et_3                             | -0.076      |
| dist_key3                            | +0.074      |
| dow_et_6                             | +0.071      |

Forward check (live weeks ≥ 6): pending, 13 games labelled (needs 15).

## 2. Direction, given a move

| split      | games | rows | positives | positive_rate |
| ---------- | ----- | ---- | --------- | ------------- |
| train      | 32    | 152  | 74        | 48.7%         |
| validation | 13    | 61   | 21        | 34.4%         |
| test       | 13    | 79   | 48        | 60.8%         |
| forward    | 6     | 15   | 7         | 46.7%         |

Rating margin available for 100.0% of fitting rows (gate 90%: met).

Chosen L2 strength C on validation: logistic (market only) = 0.01, logistic + football = 0.03, market + rating_gap = 0.01, market + starters_hurt_net = 0.03, market + rest_diff = 0.01.

### Test week (scored once), paired against the market-only model

| Model                      | Brier (95% CI)            | Log loss (95% CI)         | AUC (95% CI)           | Δ Brier vs logistic (market only) | Δ log loss vs logistic (market only) |
| -------------------------- | ------------------------- | ------------------------- | ---------------------- | --------------------------------- | ------------------------------------ |
| constant                   | 0.2645 (0.2429 to 0.2880) | 0.7223 (0.6789 to 0.7694) | 0.500 (0.500 to 0.500) | 0.0144 (-0.0076 to 0.0410)        | 0.0296 (-0.0152 to 0.0842)           |
| logistic (market only)     | 0.2502 (0.2337 to 0.2694) | 0.6927 (0.6591 to 0.7321) | 0.536 (0.321 to 0.708) | 0.0000 (0.0000 to 0.0000)         | 0.0000 (0.0000 to 0.0000)            |
| logistic + football        | 0.2875 (0.2485 to 0.3411) | 0.7742 (0.6891 to 0.8911) | 0.442 (0.244 to 0.646) | 0.0373 (0.0045 to 0.0776)         | 0.0815 (0.0103 to 0.1724)            |
| market + rating_gap        | 0.2530 (0.2348 to 0.2752) | 0.6986 (0.6621 to 0.7437) | 0.534 (0.304 to 0.725) | 0.0028 (0.0000 to 0.0067)         | 0.0059 (0.0000 to 0.0137)            |
| market + starters_hurt_net | 0.2713 (0.2132 to 0.3370) | 0.7403 (0.6170 to 0.8823) | 0.497 (0.249 to 0.722) | 0.0211 (-0.0296 to 0.0744)        | 0.0475 (-0.0608 to 0.1633)           |
| market + rest_diff         | 0.2643 (0.2397 to 0.2935) | 0.7215 (0.6707 to 0.7815) | 0.420 (0.236 to 0.607) | 0.0142 (-0.0034 to 0.0456)        | 0.0288 (-0.0071 to 0.0931)           |

**Primary (logistic + football vs logistic (market only)):** worse (both CIs above 0). Rows other than these two and the constant are exploratory ablations.

### Coefficients of the football model (final fit, standardized)

| Feature (standardized)             | Coefficient |
| ---------------------------------- | ----------- |
| starters_hurt_net                  | +0.225      |
| move_24h                           | -0.201      |
| missingindicator_starters_hurt_net | +0.167      |
| missingindicator_rest_diff         | -0.154      |
| rating_gap                         | +0.124      |
| missingindicator_move_24h          | +0.100      |
| consensus                          | +0.091      |
| mean_abs_dev                       | +0.077      |
| missingindicator_move_6h           | +0.065      |
| move_6h                            | -0.047      |
| outlier_dev                        | +0.017      |
| rest_diff                          | +0.016      |

Forward check (live weeks ≥ 6): pending, 6 games labelled (needs 15).

## Limitations

- The same small sample as v1: three training weeks, one validation week and a 15-game test week. A null here means
  "not detectable with this much data", not "no effect".
- The direction result is not independent of R4's exploratory finding on the same weeks (the consensus drifted toward
  the ratings), and the injury feature is related to R2w.
- These models describe market behaviour. Predicting a line move is not evidence of profitable betting after the vig.
