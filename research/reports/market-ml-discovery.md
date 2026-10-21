# Market ML on minute-level state: discovery (MS-046)

_Generated 2026-10-21 02:31 UTC · commit `b39fb92` · reproduce with `research/src/marketscope_research/run_market_ml.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum G, committed before this code). Units at 48, 24, 6 and 1 hours before kickoff; features use only line changes up to that time. Intervals resample games (5,000 draws, seed 2026). Value is closing-line value against Pinnacle's no-vig close, not results. **Analysis, not betting advice.**

**Sample:** walk-forward inside weeks 1–6 (train on earlier weeks, predict weeks 3–6). G1 units: 244; G2 units: 1892. Models chosen by discovery walk-forward loss: G1 `gbm` (log loss ridge 1.621, gbm 1.455); G2 `gbm` (MSE ridge 0.0018, gbm 0.0018).

## G1: can the model predict Pinnacle's direction to the close?

Log loss, model minus class-frequency baseline (negative = better): +0.417 (+0.153 to +0.697). **Primary result:** **the opposite** (discovery result; confirmation on weeks 7–14 decides).

| Hours before kickoff | Units | Model log loss | Baseline log loss | Difference |
| -------------------- | ----- | -------------- | ----------------- | ---------- |
| 48                   | 61    | 1.483          | 1.104             | +0.379     |
| 24                   | 61    | 1.460          | 1.090             | +0.370     |
| 6                    | 61    | 1.680          | 1.080             | +0.599     |
| 1                    | 61    | 1.200          | 0.881             | +0.319     |

Class shares (toward home / no change / toward away): 26% / 52% / 21%.

Exploratory, standardised ridge coefficients on all discovery units (positive = more likely toward home): imbalance -1.39, pin_line +1.27, retail_min -0.92, retail_mean +0.90, key +0.78, retail_max -0.46, bookmaker_eu_present -0.44, log_limit -0.43.

## G2: which retail numbers carry value against Pinnacle's close?

Positions: units the model scores above 0. 93 of 1892. Mean realised value per unit staked: -0.000 (-0.019 to +0.020). **Primary result:** not distinguishable: no claim.

Comparison (no model): book's line better than Pinnacle's for the side at −125 or better: 395 units, mean value -0.020 (-0.027 to -0.012). All units: -0.046 (-0.047 to -0.045) (the bookmakers' margin).

| Hours before kickoff | Units | Model positions | Model positions' value    | Rule's value              |
| -------------------- | ----- | --------------- | ------------------------- | ------------------------- |
| 48                   | 470   | 36              | -0.007 (-0.033 to +0.021) | -0.017 (-0.031 to -0.005) |
| 24                   | 472   | 25              | +0.013 (-0.010 to +0.039) | -0.019 (-0.030 to -0.008) |
| 6                    | 472   | 20              | -0.001 (-0.027 to +0.024) | -0.020 (-0.032 to -0.010) |
| 1                    | 478   | 12              | -0.007 (-0.031 to +0.042) | -0.022 (-0.029 to -0.015) |

| Retail book | Model positions | Value                     |
| ----------- | --------------- | ------------------------- |
| DraftKings  | 19              | -0.027 (-0.046 to -0.009) |
| FanDuel     | 28              | +0.001 (-0.023 to +0.024) |
| Hard Rock   | 21              | -0.004 (-0.024 to +0.013) |
| Caesars     | 25              | +0.021 (-0.023 to +0.065) |

Exploratory, standardised ridge coefficients (G2, value per unit): side_diff +0.024, price +0.008, side_home +0.005, retail_min +0.002, retail_mean -0.001, at_pin_previous -0.001, retail_max -0.001, changes_6h -0.001.

## Stale numbers re-scored with price (exploratory, added after the first run)

MS-043's S2 measured stale retail numbers in points, ignoring the price. Re-scored with the same price-aware value as G2 (expected profit per unit at Pinnacle's no-vig close):

| S2 cases                      | Count | Points CLV | Price-aware value per unit |
| ----------------------------- | ----- | ---------- | -------------------------- |
| All stale numbers             | 1473  | +0.43      | -0.020 (-0.027 to -0.013)  |
| At −110 or better             | 641   | +0.50      | -0.006 (-0.015 to +0.003)  |
| At −111 to −125               | 832   | +0.38      | -0.030 (-0.040 to -0.021)  |
| Crossing or landing on 3 or 7 | 371   | +0.32      | -0.013 (-0.028 to +0.001)  |

Retail books keep the old number but charge for it: in points it looks like a head start, at the price it is not. Registered as Addendum H for the confirmation weeks before any of them were played.

## What this can't see

Who bet; point-in-time injury news before 2026-10-18; exchange order books; moves more than 14 days out. Value is closing-line value (expected profit at Pinnacle's no-vig close), not results. The margin model is an empirical table by spread bucket, oriented to the favourite, calibrated to Pinnacle's close.
