# Market-movement model: baselines (MS-025, v1)


_Generated 2026-10-18 03:36 UTC · commit `deab8ac` · sources `the-odds-api, oddspapi` ·
reproduce with `research/src/marketscope_research/run_market_baseline.py`. Data gate and features: `market-ml-gate-v1.md`._

## Summary

- **Will it move:** logistic regression test AUC 0.72 (95% CI 0.57–0.86); Δ log loss vs constant -0.062 (-0.148 to +0.009); Δ Brier -0.0205 (-0.0509 to +0.0040): **not distinguishable (a CI includes 0)** under the pre-registered rule.
- **Direction:** logistic regression test AUC 0.54 (95% CI 0.32–0.71); Δ log loss vs constant -0.030 (-0.084 to +0.015); Δ Brier -0.0144 (-0.0410 to +0.0076): **not distinguishable (a CI includes 0)** under the pre-registered rule.

## Protocol (pre-registered in `ml/design.py` before any model was fit)

- Hyperparameters (logistic L2 strength C from [0.01, 0.03, 0.1, 0.3, 1.0, 3.0]) are chosen by validation log loss with models fit
  on the training weeks; every model is then **refit on train + validation and scored once on the test week**.
- Scores: Brier, log loss, AUC; 95% CIs and paired differences from 2,000 bootstrap resamples of
  **games** (snapshots within a game are correlated). A model "beats" a baseline only when both the Brier and log-loss
  difference CIs lie entirely below zero.
- Baselines: constant (train + validation rate); recent-week rate (the last fitting week's rate, added after the gate report
  showed the rate rising by week, before any model was fit); smoothed rate by time to kickoff; volatility heuristic
  (smoothed rate by recent consensus changes and 24 h movement).
- The headline logistic model uses only features present in both sources so it can run on live data; Pinnacle is an ablation.

## 1. Will the consensus move ≥ 0.5 pts within 24 h?

| split | games | rows | positives | positive_rate |
|---|---|---|---|---|
| train | 48 | 1120 | 152 | 13.6% |
| validation | 16 | 363 | 61 | 16.8% |
| test | 15 | 348 | 79 | 22.7% |
| forward | 13 | 52 | 8 | 15.4% |

Chosen L2 strength C on validation: logistic = 0.01, logistic + Pinnacle = 0.01.

### Test week (scored once)

| Model | Brier (95% CI) | Log loss (95% CI) | AUC (95% CI) | Δ Brier vs constant | Δ log loss vs constant |
|---|---|---|---|---|---|
| constant | 0.1824 (0.1274 to 0.2351) | 0.5604 (0.4226 to 0.6923) | 0.500 (0.500 to 0.500) | 0.0000 (0.0000 to 0.0000) | 0.0000 (0.0000 to 0.0000) |
| recent-week rate | 0.1790 (0.1277 to 0.2280) | 0.5471 (0.4236 to 0.6653) | 0.500 (0.500 to 0.500) | -0.0035 (-0.0071 to 0.0003) | -0.0133 (-0.0270 to 0.0011) |
| rate by lead time | 0.1807 (0.1254 to 0.2336) | 0.5579 (0.4193 to 0.6950) | 0.533 (0.371 to 0.700) | -0.0017 (-0.0101 to 0.0062) | -0.0024 (-0.0348 to 0.0290) |
| volatility heuristic | 0.1813 (0.1262 to 0.2344) | 0.5636 (0.4188 to 0.7045) | 0.523 (0.407 to 0.639) | -0.0011 (-0.0135 to 0.0114) | 0.0032 (-0.0402 to 0.0473) |
| logistic | 0.1619 (0.1132 to 0.2150) | 0.4983 (0.3677 to 0.6391) | 0.724 (0.568 to 0.860) | -0.0205 (-0.0509 to 0.0040) | -0.0621 (-0.1477 to 0.0086) |
| logistic + Pinnacle | 0.1588 (0.1082 to 0.2139) | 0.4899 (0.3537 to 0.6382) | 0.737 (0.586 to 0.872) | -0.0236 (-0.0560 to 0.0041) | -0.0705 (-0.1646 to 0.0099) |

**Logistic regression** vs the constant baseline: not distinguishable (a CI includes 0).

Against the recent-week base rate:

| Model | Brier (95% CI) | Log loss (95% CI) | AUC (95% CI) | Δ Brier vs recent-week rate | Δ log loss vs recent-week rate |
|---|---|---|---|---|---|
| constant | 0.1824 (0.1274 to 0.2351) | 0.5604 (0.4226 to 0.6923) | 0.500 (0.500 to 0.500) | 0.0035 (-0.0003 to 0.0071) | 0.0133 (-0.0011 to 0.0270) |
| recent-week rate | 0.1790 (0.1277 to 0.2280) | 0.5471 (0.4236 to 0.6653) | 0.500 (0.500 to 0.500) | 0.0000 (0.0000 to 0.0000) | 0.0000 (0.0000 to 0.0000) |
| rate by lead time | 0.1807 (0.1254 to 0.2336) | 0.5579 (0.4193 to 0.6950) | 0.533 (0.371 to 0.700) | 0.0018 (-0.0068 to 0.0104) | 0.0108 (-0.0232 to 0.0453) |
| volatility heuristic | 0.1813 (0.1262 to 0.2344) | 0.5636 (0.4188 to 0.7045) | 0.523 (0.407 to 0.639) | 0.0024 (-0.0097 to 0.0150) | 0.0165 (-0.0271 to 0.0635) |
| logistic | 0.1619 (0.1132 to 0.2150) | 0.4983 (0.3677 to 0.6391) | 0.724 (0.568 to 0.860) | -0.0170 (-0.0458 to 0.0064) | -0.0488 (-0.1291 to 0.0199) |
| logistic + Pinnacle | 0.1588 (0.1082 to 0.2139) | 0.4899 (0.3537 to 0.6382) | 0.737 (0.586 to 0.872) | -0.0201 (-0.0520 to 0.0064) | -0.0572 (-0.1487 to 0.0218) |

Logistic regression vs the recent-week rate: not distinguishable (a CI includes 0).

### Brier score by time to kickoff (test)

| lead_h | rows | positive_rate | brier: constant | brier: rate by lead time | brier: volatility heuristic | brier: logistic |
|---|---|---|---|---|---|---|
| 24-48 | 60 | 6.7% | 0.07 | 0.07 | 0.06 | 0.06 |
| 48-72 | 60 | 13.3% | 0.12 | 0.12 | 0.13 | 0.12 |
| 72-120 | 119 | 26.1% | 0.21 | 0.22 | 0.22 | 0.20 |
| 120+ | 109 | 33.0% | 0.26 | 0.24 | 0.24 | 0.20 |

At the validation-chosen threshold p ≥ 0.155, logistic regression flags 120 test snapshots: precision 40.8%, recall 62.0%.

### Calibration (test)

**constant**

| bin | n | mean_predicted | observed_rate |
|---|---|---|---|
| (-0.001, 0.1] | 0 | n/a | n/a |
| (0.1, 0.2] | 348 | 14.4% | 22.7% |
| (0.2, 0.3] | 0 | n/a | n/a |
| (0.3, 0.5] | 0 | n/a | n/a |
| (0.5, 1.0] | 0 | n/a | n/a |

**recent-week rate**

| bin | n | mean_predicted | observed_rate |
|---|---|---|---|
| (-0.001, 0.1] | 0 | n/a | n/a |
| (0.1, 0.2] | 348 | 16.8% | 22.7% |
| (0.2, 0.3] | 0 | n/a | n/a |
| (0.3, 0.5] | 0 | n/a | n/a |
| (0.5, 1.0] | 0 | n/a | n/a |

**logistic**

| bin | n | mean_predicted | observed_rate |
|---|---|---|---|
| (-0.001, 0.1] | 117 | 8.5% | 11.1% |
| (0.1, 0.2] | 163 | 14.1% | 20.2% |
| (0.2, 0.3] | 33 | 24.1% | 45.5% |
| (0.3, 0.5] | 22 | 36.7% | 50.0% |
| (0.5, 1.0] | 13 | 71.8% | 53.8% |

### Logistic regression coefficients (final fit)

| Feature (standardized) | Coefficient |
|---|---|
| abs_move_24h | +0.160 |
| range | +0.145 |
| mean_abs_dev | +0.139 |
| missingindicator_abs_move_6h | +0.122 |
| totals_abs_move_24h | +0.119 |
| dow_et_4 | -0.114 |
| half_point | -0.114 |
| median_quote_age_h | -0.092 |
| books | -0.088 |
| dow_et_3 | -0.086 |
| missingindicator_abs_move_24h | +0.079 |
| abs_move_6h | +0.076 |

Forward check (live weeks ≥ 6): pending, 13 games labelled (needs 15).

## 2. Direction, given a move (toward the home side vs the away side)

| split | games | rows | positives | positive_rate |
|---|---|---|---|---|
| train | 32 | 152 | 74 | 48.7% |
| validation | 13 | 61 | 21 | 34.4% |
| test | 13 | 79 | 48 | 60.8% |
| forward | 4 | 8 | 6 | 75.0% |

Chosen L2 strength C on validation: logistic = 0.01, logistic + Pinnacle = 3.0.

### Test week (scored once)

| Model | Brier (95% CI) | Log loss (95% CI) | AUC (95% CI) | Δ Brier vs constant | Δ log loss vs constant |
|---|---|---|---|---|---|
| constant | 0.2645 (0.2429 to 0.2880) | 0.7223 (0.6789 to 0.7694) | 0.500 (0.500 to 0.500) | 0.0000 (0.0000 to 0.0000) | 0.0000 (0.0000 to 0.0000) |
| outlier-direction rule | 0.2632 (0.2277 to 0.3027) | 0.7207 (0.6483 to 0.8005) | 0.560 (0.392 to 0.759) | -0.0013 (-0.0288 to 0.0254) | -0.0017 (-0.0576 to 0.0531) |
| momentum rule | 0.2494 (0.2196 to 0.2749) | 0.6927 (0.6288 to 0.7478) | 0.569 (0.384 to 0.761) | -0.0151 (-0.0446 to 0.0128) | -0.0296 (-0.0931 to 0.0293) |
| logistic | 0.2502 (0.2337 to 0.2694) | 0.6927 (0.6591 to 0.7321) | 0.536 (0.321 to 0.708) | -0.0144 (-0.0410 to 0.0076) | -0.0296 (-0.0842 to 0.0152) |
| logistic + Pinnacle | 0.2268 (0.1630 to 0.3060) | 0.7525 (0.4940 to 1.1395) | 0.750 (0.579 to 0.889) | -0.0377 (-0.1043 to 0.0425) | 0.0301 (-0.2335 to 0.4136) |

**Logistic regression** vs the constant baseline: not distinguishable (a CI includes 0).

### Calibration (test)

**logistic**

| bin | n | mean_predicted | observed_rate |
|---|---|---|---|
| (-0.001, 0.1] | 0 | n/a | n/a |
| (0.1, 0.2] | 0 | n/a | n/a |
| (0.2, 0.3] | 0 | n/a | n/a |
| (0.3, 0.5] | 60 | 44.7% | 56.7% |
| (0.5, 1.0] | 19 | 54.8% | 73.7% |

### Logistic regression coefficients (final fit)

| Feature (standardized) | Coefficient |
|---|---|
| move_24h | -0.100 |
| missingindicator_move_24h | +0.066 |
| mean_abs_dev | +0.058 |
| missingindicator_move_6h | +0.044 |
| move_6h | -0.041 |
| consensus | +0.038 |
| outlier_dev | -0.003 |

Forward check (live weeks ≥ 6): pending, 4 games labelled (needs 15).

## Limitations

- One season, five weeks of imported history and one test week (15 games): CIs are wide and a single week can be atypical.
- The positive rate drifts upward by week, so any fixed base rate is miscalibrated on later weeks.
- Imported snapshots are derived from change logs (ADR-026); live snapshots come from a different book mix. The forward
  check measures transfer between them once enough live games are labelled.
- These models describe market behaviour. Predicting a line move is not evidence of profitable betting after the vig.
