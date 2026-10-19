# R7: play-caller impact, 2016–24 (MS-035b)

_Generated 2026-10-19 02:29 UTC · commit `9678b20` on `main` · reproduce with `research/src/marketscope_research/run_playcaller_study.py`._

Design pre-registered in `research/PREREGISTRATION.md` (R7 and addendum A, committed before this code). Measure: observed offensive points per drive for the regular season, centred on the league mean (not the filtered ratings, whose between-season reversion already depends on play-caller continuity). 95% intervals resample team-season pairs (5,000 draws). Descriptive research; coach and roster effects are confounded.

## Primary: extra carryover when the offensive play-caller stays

256 team-season pairs; 104 with a new offensive play-caller, 97 with a new main QB (gate: at least 40 each: met).

Model: next season's offence = a + b·this season's + c·same caller + d·same QB + e·(this season's × same caller) + f·(this season's × same QB).

| Term                                | Estimate (95% CI)      | vs 0       |
| ----------------------------------- | ---------------------- | ---------- |
| e: × same play-caller (primary)     | +0.02 (-0.23 to +0.25) | includes 0 |
| f: × same QB                        | +0.33 (+0.04 to +0.60) | above 0    |
| Carryover, all pairs (simple slope) | +0.45 (+0.34 to +0.56) | above 0    |

Result: not distinguishable from zero: no claim.

## Carryover by group (exploratory)

Slope of next season's points per drive on this season's (1 = fully kept, 0 = none).

| Group                | Pairs | Carryover (95% CI)     |
| -------------------- | ----- | ---------------------- |
| same caller, same QB | 99    | +0.54 (+0.36 to +0.72) |
| same caller, new QB  | 53    | +0.04 (-0.20 to +0.32) |
| new caller, same QB  | 60    | +0.38 (+0.18 to +0.61) |
| new caller, new QB   | 44    | +0.38 (-0.34 to +0.98) |

## Defence (exploratory)

Points per drive allowed; same defensive play-caller (100 pairs changed). No QB term.

| Term                             | Estimate (95% CI)      |
| -------------------------------- | ---------------------- |
| Carryover, same defensive caller | +0.26 (+0.13 to +0.41) |
| Carryover, new defensive caller  | +0.25 (+0.04 to +0.45) |
| Interaction (× same caller)      | +0.01 (-0.24 to +0.27) |

## Scheme: does it follow the play-caller? (exploratory)

Play-callers who were a team's main offensive caller in one season and a different team's in the next. Regression of the new team's value on the caller's old-team value and the new team's own prior value.

| Trait                                    | Movers | Weight on caller's old team | Weight on new team's prior |
| ---------------------------------------- | ------ | --------------------------- | -------------------------- |
| Pass rate over expected (share of plays) | 20     | +0.06 (-0.47 to +0.45)      | +0.36 (-0.15 to +0.70)     |
| Neutral seconds per play                 | 20     | +0.28 (-0.42 to +0.89)      | +0.32 (-0.10 to +0.84)     |
