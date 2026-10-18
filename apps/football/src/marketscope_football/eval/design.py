"""Pre-registered evaluation design (MS-029, docs/RATINGS.md "Validation protocol").

Fixed on 2026-10-18 BEFORE any benchmark was run. Changing a value after results are read
must be recorded as a deviation in reports/benchmarks.md and the RATINGS.md changelog.
"""

from __future__ import annotations

# ---- Season roles ---------------------------------------------------------------------------
WARMUP_FROM = 1999  # schedules from here feed Elo/SRS warm-up; never scored
TUNING_SEASONS = tuple(range(2016, 2023))  # benchmark hyperparameters are chosen here (walk-forward)
VALIDATION_SEASONS = (2023, 2024)  # headline benchmark table; factor selection later (MS-032)
TEST_SEASON = 2025  # untouched: evaluated exactly once, in MS-032. The runner refuses it otherwise.
SIGMA_FIT_SEASONS = tuple(range(1999, 2016))  # margin -> win probability mapping, outside every scored season

# ---- Scoring --------------------------------------------------------------------------------
# All games with a result (regular season and playoffs). Outcome for win probability: home win 1,
# loss 0, tie 0.5. Margin = home score - away score.
BOOTSTRAP_RESAMPLES = 5000  # resampling GAMES (one prediction per game per model)
CI_LEVEL = 0.95
REFERENCE = "nflverse close"  # paired differences are reported against the market close
CALIBRATION_EDGES = tuple(i / 10 for i in range(11))

# ---- Benchmarks -----------------------------------------------------------------------------
# Naive home field: mean home margin of non-neutral games over the previous HFA_WINDOW_SEASONS
# seasons plus the current season's completed games. Neutral sites get 0.
HFA_WINDOW_SEASONS = 3

# FiveThirtyEight NFL Elo, constants as published in fivethirtyeight/nfl-elo-game (forecast.py):
# K 20, home field 65 Elo, a third of the way back to 1505 between seasons, margin-of-victory
# multiplier ln(max(|MOV|, 1) + 1) * 2.2 / (winner's Elo edge * 0.001 + 2.2). Spread = Elo diff / 25.
# Every franchise starts at 1500 in WARMUP_FROM (17 seasons of burn-in before scoring).
ELO_K = 20.0
ELO_HFA = 65.0
ELO_REVERT = 1 / 3
ELO_MEAN = 1505.0
ELO_START = 1500.0
ELO_POINTS_PER_POINT = 25.0

# Ridge ratings (SRS and market-implied are the same estimator on different targets):
# target = r_home - r_away + hfa * (not neutral) + e, games weighted 0.5 ** (age_days / half-life),
# ridge penalty `lambda` on the team ratings only (shrinks toward an average team), refit weekly
# on games from the last RIDGE_WINDOW_DAYS. SRS target: the actual margin. Market-implied target:
# the nflverse closing spread (home-positive) of past games, never the current week's.
RIDGE_WINDOW_DAYS = 730
RIDGE_HALF_LIFE_GRID = (28, 56, 84, 126, 182, 273, 365)  # days
RIDGE_LAMBDA_GRID = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)  # in units of full-weight games
TUNING_METRIC = "margin_mae"  # grid point with the lowest walk-forward MAE over TUNING_SEASONS
