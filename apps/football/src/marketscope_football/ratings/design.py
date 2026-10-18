"""Pre-registered design for the Kalman unit ratings (MS-030, docs/RATINGS.md "Model architecture").

Fixed on 2026-10-18 before any rating was fitted or scored. Parameters themselves are fitted by
maximum likelihood on the tuning seasons (fit.py) and frozen in params.json.
"""

from __future__ import annotations

from ..eval.design import TUNING_SEASONS, VALIDATION_SEASONS  # noqa: F401  (same season roles)

BURN_IN_FROM = 2012  # the filter starts here; 2012-15 observations are never in the likelihood
LIKELIHOOD_SEASONS = TUNING_SEASONS  # 2016-22: parameters and the game layer are fitted here only

# ---- Channels -------------------------------------------------------------------------------
# Each channel is a separate filter (pass and rush: 32 offense + 32 defense + a league mean; special
# teams: 32 teams). Observation noise for a team-game is sigma^2 / n_eff, n_eff the Kish effective
# number of plays under the play weights (= the play count when unweighted).
CHANNELS = ("pass", "rush", "st")
# Variants of the play-level measurement (ADR-029). The model uses all three adjustments; each is
# switched off in an ablation (parameters refitted for every variant, so the comparison is fair).
VARIANTS = {
    "model": dict(luck=True, cap=True, wp=True),
    "no luck adjustment": dict(luck=False, cap=True, wp=True),
    "no EPA cap": dict(luck=True, cap=False, wp=True),
    "no WP weighting": dict(luck=True, cap=True, wp=False),
    "raw EPA": dict(luck=False, cap=False, wp=False),
}
# Structural ablation: same measurement, but play-caller continuity switched off (one rho per unit,
# no mid-season bumps). Refitted like the variants above.
NO_CONTINUITY = "no play-caller continuity"

# ---- Filter structure -----------------------------------------------------------------------
# Within a season every unit is a random walk between weeks (variance q_week). At a season boundary
# unit = rho * unit + noise (variance q_season); rho depends on whether the unit's play-caller
# changed (offense: offensive play-caller; defense: defensive play-caller). A mid-season play-caller
# change adds a one-time variance `bump` to that unit. QB continuity joins in MS-031 (QB state).
INITIAL_VAR_UNIT = 0.01  # EPA/play^2 (team sd 0.1) at BURN_IN_FROM
INITIAL_VAR_MEAN = 0.01
INITIAL_VAR_ST = 4.0  # (EPA/game)^2

# ---- QB layer (MS-031a; qb.py) --------------------------------------------------------------
# Grid searched on 2016-22 (in-sample game-layer MAE with the expected starter).
QB_HALF_LIFE_GRID = (182.0, 365.0, 730.0)  # days: QB rating memory
QB_PRIOR_GRID = (100.0, 250.0, 500.0)  # dropbacks of replacement-level prior
QB_BASELINE_HALF_LIFE_GRID = (28.0, 56.0, 112.0)  # days: memory of the team's QB baseline
