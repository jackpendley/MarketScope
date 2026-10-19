"""Pre-registered design for MS-036: the market-movement model with football features.

Fixed on 2026-10-19 BEFORE any football feature was built or any model with football features was
fit. It reuses everything in design.py: target, split, gate, C grid, bootstrap and the claim rule.
Changing a value here after results are read must be recorded as a deviation in the report.

What was known when this was written:
- MS-025 (v1): the market-only logistic model's test-week gains over the constant were not
  distinguishable from zero (AUC 0.72; Brier and log-loss CIs include 0). Direction: no skill.
- R4 exploratory (football-studies-v1): on the same 2026 weeks, the consensus moved toward the
  rating margin between 6 days out and the close (+0.10 per point of gap). So a direction gain from
  the rating gap would not be independent evidence.
- R2w: the consensus moved toward the opponent when a starter who played last week was ruled Out.
  This design's injury feature is different (in-game injuries visible in snap counts, known
  before the week's injury reports), but related.
- Counts only: 2026 has rating snapshots for every week, forecasts at leads 1/3/7 days for the
  77 outdoor or retractable-roof games, snap counts for weeks 1-6, and game context for all games.

Point-in-time rules (each football feature at snapshot time t uses only):
- Ratings: the ratings-v1 snapshot after week k, usable from the last kickoff of week k plus
  RATING_LAG_HOURS (the daily job builds it the next morning). The latest usable k is taken,
  never the game's own week. No injury or QB terms: those come from reports published during the
  week, so the rating margin is AdjEM(home) - AdjEM(away) + home-field advantage.
- Snap counts: from games that kicked off at least SNAPS_LAG_HOURS before t.
- Weather: a forecast at lead N days for the game window is usable from kickoff - N days. Lead 0
  is a near-kickoff estimate and is never used.
- Schedule context (rest, travel, short week) is fixed when the schedule is published, so it is
  known at every t.
A leakage test perturbs every input that becomes usable after t and asserts that no football
feature changes.
"""

from __future__ import annotations

RATING_VERSION = "ratings-v1"
RATING_LAG_HOURS = 16  # last kickoff of the week (Monday night) + 16 h lands after the 13:00 UTC daily build
HOME_ADVANTAGE = 1.6  # ratings-v1 home advantage, points (as in R4)
SNAPS_LAG_HOURS = 36
WEATHER_LEADS = (1, 3, 7)  # days; lead 0 excluded
STARTER_SHARE = 0.5  # a starter averaged at least this offensive or defensive snap share ...
STARTER_GAMES = 3  # ... over his team's previous three games before the most recent one
HURT_SHARE = 0.25  # and played less than this share (or not at all) in the team's most recent game

# Will-it-move model: the v1 market features plus unsigned football features, by family.
FOOTBALL_MOVE_FAMILIES = {
    "ratings": ["abs_rating_gap"],  # |rating margin - consensus margin|
    "injuries": ["starters_hurt_total"],  # home + away starters hurt in their most recent game
    "weather": ["wind_mph", "abs_wind_change", "outdoor"],  # shortest usable lead; change vs the previous lead
    "schedule": ["abs_rest_diff", "away_travel_km", "short_week_any"],
}
# Direction model: the v1 direction features plus signed, home-oriented football features.
# Positive values favour the home side, so a positive coefficient means "toward home".
FOOTBALL_DIRECTION_FEATURES = [
    "rating_gap",  # rating margin - consensus margin (+ = ratings like home more than the market)
    "starters_hurt_net",  # away hurt - home hurt
    "rest_diff",  # home rest days - away rest days
]

# Primary comparison (both targets): logistic with v1 market features + all football features vs
# the v1 market-only logistic, each with C chosen on validation, refit on train + validation and
# scored once on the test week, paired by game. "Football features add lift" only when BOTH the
# Brier and log-loss difference CIs lie entirely below zero. Market + one family at a time is
# reported as exploratory (ablation). The forward check (live weeks >= 6) is reported when
# design.MIN_FORWARD_GAMES labelled games exist.
PRIMARY_REFERENCE = "logistic (market only)"
PRIMARY_MODEL = "logistic + football"
# Coverage gate, in addition to the v1 data gate: a rating margin must exist for at least this
# share of labelled rows, or the study is reported as inconclusive.
MIN_RATING_COVERAGE = 0.9
