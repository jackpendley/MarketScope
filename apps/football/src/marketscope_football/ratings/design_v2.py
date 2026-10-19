"""Pre-registered design for ratings-v2 (MS-039): offensive between-season reversion keyed on QB
continuity. Fixed on 2026-10-19 BEFORE any v2 parameter was fitted or any v2 prediction scored.

Motivation and what was already known:
- R7 (research/reports/r7-play-caller.md, 2016–24): observed offensive points per drive carries over
  more when the main QB stays (+0.33 interaction, 0.04 to 0.60), not when the play-caller stays
  (+0.02, -0.23 to +0.25).
- ratings-v1 keys offensive and defensive reversion on play-caller continuity. In MS-030 that was
  not supported: likelihood-ratio test p = 0.66 on 2016–22 (reports/kalman-ratings.md), and the
  no-continuity ablation changed 2023–24 accuracy by about zero.
- The v1 game layer already has a QB term (expected starter vs the team's QB baseline), so a
  QB-keyed reversion might add nothing, or double-count. That is the empirical question.
- ratings-v1's 2023–24 and 2025 results are known. 2025 was v1's one-time test, so it can't be an
  untouched test for v2; it is reported, labelled as seen. v2's honest test is the live forward
  test.

Variants (the only change is which teams get rho_off_changed at a season boundary; defensive
reversion and every mid-season play-caller bump stay as in v1):
- "qb": offence changed = the team's expected starting QB for its first game of the season
  (point in time: depth chart and injury report before kickoff, from the QB layer) differs from
  its main QB of the previous regular season (most starts; ties go to the later starter).
- "qb_or_caller": offence changed = the QB changed (as above) OR the offensive play-caller changed.

Clarification (2026-10-19, committed before any fit ran): "v1's log likelihood" in step 4 means
the play-caller-keyed structure ("caller") refitted by the same code on the same data. v1's stored
likelihoods predate the ADR-045 coaching corrections, so comparing against them would favour v2.
Frozen v1 replayed on the current data is reported as well. The validation comparison (step 4)
is against the frozen, deployed ratings-v1.

Procedure:
1. Refit the four unit channels (pass, rush, succ, ppd) by maximum likelihood on LIKELIHOOD_SEASONS
   (2016–22) for each variant, with v1's code, start values and iteration limits. Special teams and
   pace don't use continuity; v1's values are reused.
2. Choose the variant with the higher summed 2016–22 log likelihood over the four unit channels
   (same parameter count as v1, so no penalty is needed).
3. Refit the game layer by OLS on 2016–22 with v1's final feature set (unit features, QB term,
   availability) on the v2 filters. v1's QB parameters, availability inputs, margin distribution
   and luck model are reused unchanged (they are fitted on inputs continuity doesn't touch).
4. Adoption rule: v2 is adopted only if BOTH
   - its summed 2016–22 unit-channel log likelihood is at least v1's, AND
   - on 2023–24, walk-forward and paired by game against v1, the point estimates of
     Δ margin MAE <= 0 and Δ log loss <= 0 (the MS-032 factor-selection rule). CIs are reported.
   Otherwise the result is published as a null and v1 stays the only version.
5. If adopted: params go in ratings/params_v2.json (v1's params.json is never touched), and v2 joins
   the live forward test as a second model version beside v1. The site keeps showing v1 until at
   least 50 forward-test games compare the two (a later, separate decision).
"""

from __future__ import annotations

VERSION = "ratings-v2"
VARIANTS = ("qb", "qb_or_caller")
REFERENCE = "caller"  # v1's structure, refitted on the same data for the likelihood comparison
VALIDATION_SEASONS = (2023, 2024)
