# R7: play-caller impact, 2016–24 (MS-035b)

_Generated 2026-10-19 01:28 UTC · commit `9314b78` · reproduce with `research/src/marketscope_research/run_playcaller_study.py`._

Design pre-registered in `research/PREREGISTRATION.md` (R7 and addendum A, committed before this code). Measure: observed offensive points per drive for the regular season, centred on the league mean (not the filtered ratings, whose between-season reversion already depends on play-caller continuity). 95% intervals resample team-season pairs (5,000 draws). Descriptive research; coach and roster effects are confounded.

## Primary: extra carryover when the offensive play-caller stays

256 team-season pairs; 105 with a new offensive play-caller, 97 with a new main QB (gate: at least 40 each: met).

Model: next season's offence = a + b·this season's + c·same caller + d·same QB + e·(this season's × same caller) + f·(this season's × same QB).

| Term                                | Estimate (95% CI)      | vs 0       |
| ----------------------------------- | ---------------------- | ---------- |
| e: × same play-caller (primary)     | +0.02 (-0.22 to +0.25) | includes 0 |
| f: × same QB                        | +0.33 (+0.04 to +0.61) | above 0    |
| Carryover, all pairs (simple slope) | +0.45 (+0.34 to +0.56) | above 0    |

Result: not distinguishable from zero: no claim.

## Carryover by group (exploratory)

Slope of next season's points per drive on this season's (1 = fully kept, 0 = none).

| Group                | Pairs | Carryover (95% CI)     |
| -------------------- | ----- | ---------------------- |
| same caller, same QB | 98    | +0.55 (+0.37 to +0.73) |
| same caller, new QB  | 53    | +0.04 (-0.20 to +0.32) |
| new caller, same QB  | 61    | +0.38 (+0.18 to +0.61) |
| new caller, new QB   | 44    | +0.38 (-0.34 to +0.98) |

## Defence (exploratory)

Points per drive allowed; same defensive play-caller (106 pairs changed). No QB term.

| Term                             | Estimate (95% CI)      |
| -------------------------------- | ---------------------- |
| Carryover, same defensive caller | +0.24 (+0.10 to +0.38) |
| Carryover, new defensive caller  | +0.28 (+0.09 to +0.48) |
| Interaction (× same caller)      | -0.04 (-0.28 to +0.21) |

## Scheme: does it follow the play-caller? (exploratory)

Play-callers who were a team's main offensive caller in one season and a different team's in the next. Regression of the new team's value on the caller's old-team value and the new team's own prior value.

| Trait                              | Movers | Weight on caller's old team | Weight on new team's prior |
| ---------------------------------- | ------ | --------------------------- | -------------------------- |
| Pass rate over expected (pts of %) | 19     | +0.08 (-0.44 to +0.48)      | +0.38 (-0.26 to +0.78)     |
| Neutral seconds per play           | 19     | +0.16 (-0.80 to +0.83)      | +0.22 (-0.25 to +0.77)     |
