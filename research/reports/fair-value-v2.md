# Fair-value engine v2: model selection (MS-053)

_Generated 2026-10-21 23:35 UTC · commit `be4de8c` · reproduce with `research/src/marketscope_research/run_fair_value.py`._

Protocol pre-registered in `research/PREREGISTRATION.md` (Addendum M, committed before this code). Bandwidths chosen by leave-one-season-out log loss on 2016–22; models fitted on 2016–22 and validated once on 2023–25; game bootstrap (5,000, seed 2026). The adopted engine is then fitted on 2016–25 for use in 2026.

## Margin model: **kernel adopted**

Bandwidths chosen: spread 2.0, total 1000.0. Validation log loss of the exact favourite margin: kernel 3.8729, buckets 4.0032; difference -0.1303 (-0.1954 to -0.0712) (855 games).

| Closing total | Margin | Games | Observed | Kernel | Buckets |
| ------------- | ------ | ----- | -------- | ------ | ------- |
| total ≤ 41.5  | 3      | 251   | 7.2%     | 8.7%   | 8.5%    |
| total ≤ 41.5  | 7      | 251   | 6.0%     | 5.3%   | 5.2%    |
| 42–46.5       | 3      | 371   | 7.5%     | 8.7%   | 8.6%    |
| 42–46.5       | 7      | 371   | 5.1%     | 5.3%   | 5.3%    |
| ≥ 47          | 3      | 233   | 10.3%    | 8.7%   | 8.5%    |
| ≥ 47          | 7      | 233   | 6.4%     | 5.3%   | 5.2%    |

Moneyline implied by the spread vs the devigged nflverse closing moneyline (855 games): mean absolute difference kernel 0.022, buckets 0.038.

## Total-points model: **kernel adopted**

Bandwidths chosen: spread 2.0, total 6.0. Validation log loss: kernel 4.0556, buckets 4.1500; difference -0.0943 (-0.1708 to -0.0260).

## Devig method: **shin**

| Method         | Log loss 2016–22 | Log loss 2023–25 |
| -------------- | ---------------- | ---------------- |
| multiplicative | 0.6090           | 0.6077           |
| power          | 0.6089           | 0.6071           |
| shin           | 0.6089           | 0.6073           |

Chosen on 2016–22: shin; on 2023–25 its difference from multiplicative is -0.0005 (-0.0017 to +0.0008).

## Frozen parameters

```json
{
  "margin": {
    "model": "kernel",
    "h_s": 2.0,
    "h_t": 1000.0
  },
  "total": {
    "model": "kernel",
    "h_s": 2.0,
    "h_t": 6.0
  },
  "devig": "shin",
  "mix": 0.02,
  "train_seasons": "2016-2025"
}
```
