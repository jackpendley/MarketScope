# Does the market move toward the model? discovery (MS-057)

_Generated 2026-10-21 23:42 UTC · commit `9b4243b` · reproduce with `research/src/marketscope_research/run_model_open.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum O, committed before this code). Decision time 6 days before kickoff; the model line is ratings-only (AdjEM gap plus 1.6 home advantage) from the latest snapshot usable then. Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**

**Sample:** 66 games. Mean |disagreement| 2.07 points; mean |move to the close| 0.80 points; lines unchanged from 6 days out: 24%.

## Primary: slope of Pinnacle's move to the close on the model's disagreement

Slope: +0.116 (+0.048 to +0.189) points of move per point of disagreement. **Primary result:** **the market moves toward the model** (discovery result; confirmation on weeks 7–14 decides).

## Secondary: the model's side at Pinnacle's line 6 days out (|disagreement| ≥ 1.5)

34 positions. Mean value at Pinnacle's no-vig close: -1.0% (-2.8 to +0.8). Secondary: not distinguishable: no claim.

## Exploratory: value by size of the disagreement (added after the first run)

| Disagreement size (points) | Positions | Value at Pinnacle's close |
| -------------------------- | --------- | ------------------------- |
| 1.5–2.5                    | 15        | -1.6% (-4.6 to +1.0)      |
| 2.5–3.5                    | 10        | +0.4% (-2.9 to +3.3)      |
| 3.5–+                      | 9         | -1.4% (-4.8 to +2.0)      |

## What this can't see

Injury and QB news (the model line here is ratings-only); openers more than 14 days out; earlier seasons (no early lines before 2026 without paid history).
