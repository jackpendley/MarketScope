# Market-movement model: data gate (MS-024, v1)

_Generated 2026-10-18 03:31 UTC · commit `061dfb0` · sources `the-odds-api, oddspapi` ·
reproduce with `research/src/marketscope_research/run_market_gate.py`. Design: `research/src/marketscope_research/ml/design.py`
(pre-registered 2026-10-18, before any label was computed)._

## Question

At a snapshot t between 168 h and 24 h before kickoff, will the board consensus
home spread move by at least 0.5 points by t + 24 h? The future value is the pregame
consensus snapshot nearest t + 24 h within ±3 h; without one the label is missing,
never imputed. Secondary target: the direction of the move, given one.

## Verdict

**Gate passed.** Modelling (MS-025) may proceed on the pre-registered split.

| Pre-registered check | Result |
| -------------------- | ------ |
| games >= 60          | pass   |
| positives >= 150     | pass   |
| test games >= 15     | pass   |
| test positives >= 30 | pass   |

Core (train + validation + test): **79 games, 292 positive snapshots**; test: 15 games,
79 positives. Live forward check: 13 games labelled so far
(pending until ≥ 15 games).

## Leakage audit

**Passed** on 60 sampled snapshots: perturbing every observation after t changed no feature.

## Splits (chronological, grouped by game)

| split      | weeks   | games | snapshots | labelled | positives | positive_rate | toward_home | toward_away |
| ---------- | ------- | ----- | --------- | -------- | --------- | ------------- | ----------- | ----------- |
| train      | 1, 2, 3 | 48    | 1122      | 1120     | 152       | 13.6%         | 74          | 78          |
| validation | 4       | 16    | 363       | 363      | 61        | 16.8%         | 21          | 40          |
| test       | 5       | 15    | 349       | 348      | 79        | 22.7%         | 48          | 31          |
| forward    | 6       | 13    | 92        | 52       | 8         | 15.4%         | 6           | 2           |

Eligible snapshots that received a label: 97.8%. Weeks 1–5 are imported history (OddsPapi derived
6-hourly snapshots: Pinnacle and Caesars present, BetMGM absent); weeks ≥ 6 are live collection (BetMGM present, Caesars
and Pinnacle absent). The source changes exactly at the forward boundary, so the forward check doubles as a test of
transfer between sources.

## Positive rate by time to kickoff

| lead      | games | labelled | positive_rate |
| --------- | ----- | -------- | ------------- |
| 24–48 h   | 90    | 328      | 12.5%         |
| 48–72 h   | 91    | 352      | 13.6%         |
| 72–120 h  | 80    | 630      | 13.3%         |
| 120–168 h | 77    | 573      | 22.2%         |

## Positive rate by week

| week | games | labelled | positive_rate |
| ---- | ----- | -------- | ------------- |
| 1    | 16    | 384      | 9.1%          |
| 2    | 16    | 365      | 13.2%         |
| 3    | 16    | 371      | 18.6%         |
| 4    | 16    | 363      | 16.8%         |
| 5    | 15    | 348      | 22.7%         |
| 6    | 13    | 52       | 15.4%         |

## Feature missingness (labelled rows)

| feature             | missing_overall | missing_imported | missing_live |
| ------------------- | --------------- | ---------------- | ------------ |
| consensus           | 0.0%            | 0.0%             | 0.0%         |
| abs_consensus       | 0.0%            | 0.0%             | 0.0%         |
| books               | 0.0%            | 0.0%             | 0.0%         |
| hours_to_kickoff    | 0.0%            | 0.0%             | 0.0%         |
| mean_abs_dev        | 0.0%            | 0.0%             | 0.0%         |
| max_abs_dev         | 0.0%            | 0.0%             | 0.0%         |
| range               | 0.0%            | 0.0%             | 0.0%         |
| outlier_dev         | 0.0%            | 0.0%             | 0.0%         |
| move_6h             | 3.8%            | 3.2%             | 25.0%        |
| move_24h            | 9.2%            | 6.7%             | 100.0%       |
| abs_move_6h         | 3.8%            | 3.2%             | 25.0%        |
| abs_move_24h        | 9.2%            | 6.7%             | 100.0%       |
| changes_48h         | 0.0%            | 0.0%             | 0.0%         |
| median_quote_age_h  | 0.0%            | 0.0%             | 0.0%         |
| dist_key3           | 0.0%            | 0.0%             | 0.0%         |
| dist_key7           | 0.0%            | 0.0%             | 0.0%         |
| on_key              | 0.0%            | 0.0%             | 0.0%         |
| half_point          | 0.0%            | 0.0%             | 0.0%         |
| pinnacle_dev        | 11.6%           | 9.1%             | 100.0%       |
| totals_abs_move_24h | 8.7%            | 6.1%             | 100.0%       |
| source_live         | 0.0%            | 0.0%             | 0.0%         |
| dow_et              | 0.0%            | 0.0%             | 0.0%         |

`move_6h`/`move_24h` are missing when no snapshot lies within ±3 h of the lag; `pinnacle_dev` is structurally missing on
live data (Pinnacle is imported only), so it can only be evaluated on weeks 1–5.

## Notes

- Committed reports contain aggregates only, never raw lines or prices.
- Next (MS-025): baselines (majority, empirical rate by lead time, volatility heuristic, logistic regression) on this split,
  scored by Brier, log loss and calibration with game-clustered CIs.
