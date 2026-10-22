# Does the market move toward the model? discovery (MS-057)

_Generated 2026-10-22 21:31 UTC · commit `60b7473` · reproduce with `research/src/marketscope_research/run_model_open.py --phase discovery`._

Design pre-registered in `research/PREREGISTRATION.md` (Addendum O, committed before this code). Decision time 6 days before kickoff; the model line is ratings-only (AdjEM gap plus 1.6 home advantage) from the latest snapshot usable then. Game bootstrap (5,000, seed 2026). **Analysis, not betting advice.**

**Sample:** 66 games. Mean |disagreement| 2.07 points; mean |move to the close| 0.80 points; lines unchanged from 6 days out: 24%.

## Primary: slope of Pinnacle's move to the close on the model's disagreement

Slope: +0.116 (+0.051 to +0.189) points of move per point of disagreement. **Primary result:** **the market moves toward the model** (discovery result; confirmation on weeks 7–14 decides).

## Addendum V: is it the model, or the early line?

y and x share Pinnacle's line at d, so noise in that line alone makes the slope positive. The baseline is the market's own view before d: team ratings fitted to Pinnacle's closing lines of games already final. Discovery numbers are descriptive; confirmation decides.

- Games: 66 in 6 weeks; 50 with a baseline (week 1 has none).
- Joint regression, model coefficient: +0.100 (-0.008 to +0.238; 50 clusters); baseline coefficient: -0.006 (-0.127 to +0.094; 50 clusters). Not established beyond the market's own earlier closes: the model coefficient's interval includes 0 or it does not beat the permutation null.
- Addendum W null, the model coefficient with model lines shuffled within weeks (1,000 permutations): 97.5th percentile +0.053; the observed coefficient exceeds it.
- Baseline alone: +0.034 (-0.058 to +0.110; 50 clusters).
- Model lines shuffled within each week (1,000 permutations): mean slope +0.020, 95% of permutations -0.006 to +0.046.
- Frozen first (decisions after Addendum O was committed): – over 0 games.
- Week-block bootstrap of the primary slope: +0.116 (+0.040 to +0.189; 6 clusters).

## Secondary: the model's side at Pinnacle's line 6 days out (|disagreement| ≥ 1.5)

34 positions. Mean value at Pinnacle's no-vig close: -1.0% (-2.8 to +0.8). Secondary: not distinguishable: no claim.

Engine v3 (Addendum T secondary; MS-059 line conversion, logit scale): -1.0% (-2.8 to +0.7) (post hoc on discovery games: descriptive only).

## Exploratory: value by size of the disagreement (added after the first run)

| Disagreement size (points) | Positions | Value at Pinnacle's close |
| -------------------------- | --------- | ------------------------- |
| 1.5–2.5                    | 15        | -1.6% (-4.6 to +1.0)      |
| 2.5–3.5                    | 10        | +0.4% (-2.9 to +3.3)      |
| 3.5–+                      | 9         | -1.4% (-4.8 to +2.0)      |

## What this can't see

Injury and QB news (the model line here is ratings-only); openers more than 14 days out; earlier seasons (no early lines before 2026 without paid history).
