"""Pre-registered factor selection (MS-032, docs/RATINGS.md "Factor selection").

Fixed on 2026-10-18 BEFORE any candidate factor was fitted or scored. Each candidate is added on
its own to the MS-031 model's OLS game layer (fitted on 2016-22, the filters unchanged) and kept only
if BOTH:
  (1) in-sample (2016-22) its coefficient has the expected sign with |t| >= MIN_T, and
  (2) on 2023-24 (walk-forward, paired against the MS-031 model) Δ margin MAE <= 0 AND Δ log loss <= 0
      (point estimates).
Kept factors are then refitted jointly; that model is ratings-v1. Selecting on 2023-24 makes its
validation score optimistic by construction; the 2025 test (run once, after the freeze) is the
honest estimate. Ten candidates are tested, so about one could pass (1)+(2) by chance; the joint
2025 test guards against that too.

Features are home minus away (positive = favours the home team unless stated). Expected sign is
the sign of the coefficient if the factor works as the literature suggests.
"""

from __future__ import annotations

MIN_T = 2.0

CANDIDATES = {
    # name: (features, expected sign, rationale)
    "rest difference": (["rest_diff"], +1, "days of rest, home minus away, clipped to ±7"),
    "bye week": (["bye_diff"], +1, "coming off a bye (rest >= 13 days), home minus away; ≈ 0 since 2011 per arXiv 2408.10867"),
    "travel distance": (["travel_diff"], +1, "away travel minus home travel, 1000 km"),
    "time-zone shift": (["tz_diff"], +1, "|time-zone shift| of the away team minus the home team's, hours"),
    "body clock": (["body_clock_diff"], +1, "kickoff before 11:00 on the team's home clock (e.g. a West team at 1 pm ET), away minus home"),
    "altitude": (["altitude_diff"], +1, "away team's altitude change minus home team's, km (Denver)"),
    "division game": (["division_home"], -1, "division game x not neutral: a smaller home edge between familiar teams"),
    "playoffs": (["playoff_home"], +1, "playoff game x not neutral: a larger home edge (ELWAY +0.75)"),
    "new head coach": (["new_hc_diff"], -1, "head coach in his first 10 games with the franchise, home minus away (ELWAY)"),
    "new offensive play-caller": (["new_oc_diff"], -1, "offensive play-caller in his first 4 games with the team, home minus away"),
}
# The RB absence value (-2.41, ADR-037) is implausible; it is kept only if it passes the same rule as
# a candidate (tested by removing it from the model).
RB_FEATURE = "avail_rb"
# Not testable on 2016-22: margin weather (forecasts start 2024). Not tested: team-specific home field
# (32 parameters; altitude covers the one known outlier).
NEW_HC_GAMES = 10
NEW_OC_GAMES = 4
EARLY_BODY_CLOCK_HOUR = 11.0
