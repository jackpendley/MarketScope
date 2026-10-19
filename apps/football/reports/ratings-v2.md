# ratings-v2: QB-keyed offensive reversion (MS-039)

_Generated 2026-10-19 15:41 UTC · code `1f9b3ba`. Design pre-registered in `ratings/design_v2.py` (committed before any fit)._

## Result

**Not adopted: ratings-v1 stays the only version.** Rule (all must hold):

- ✗ 2016–22 unit log likelihood ≥ v1
- ✓ 2023–24 Δ margin MAE ≤ 0
- ✓ 2023–24 Δ log loss ≤ 0

## Variant selection (2016–22 log likelihood, four unit channels)

| Model                                         | Offensive reversion keyed on | Log likelihood |
| --------------------------------------------- | ---------------------------- | -------------- |
| ratings-v1 frozen (replayed, not refitted)    | play-caller                  | 33.8           |
| ratings-v1 structure refitted (the reference) | play-caller                  | 38.6           |
| qb (chosen)                                   | QB                           | 38.4           |
| qb_or_caller                                  | QB or play-caller            | 37.3           |

QB changed at 77 of 224 team-season boundaries in 2016–22 (34%).

Fitted offensive carryover (ρ same / changed):

| Channel | v1 frozen (play-caller) | v2 (qb)     |
| ------- | ---------------- | ----------- |
| pass    | 0.72 / 0.58      | 0.59 / 0.73 |
| rush    | 0.58 / 0.58      | 0.56 / 0.65 |
| succ    | 0.59 / 0.58      | 0.53 / 0.68 |
| ppd     | 0.64 / 0.46      | 0.51 / 0.67 |

## Validation, 2023–24 (walk-forward, paired by game; v2 minus v1, negative = better)

Games: 570. Δ margin MAE -0.005 (-0.035 to +0.026); Δ Brier -0.0002 (-0.0010 to +0.0007); Δ log loss -0.0004 (-0.0023 to +0.0014).

## 2025 (seen: ratings-v1's one-time test season, so not an untouched test for v2)

Games: 285. Δ margin MAE -0.021 (-0.065 to +0.023); Δ Brier -0.0008 (-0.0019 to +0.0003); Δ log loss -0.0019 (-0.0044 to +0.0006).

Game layer refitted on the v2 filters (in-sample 2016–22 MAE 9.964); QB parameters, availability, margin distribution and luck reused from v1.
