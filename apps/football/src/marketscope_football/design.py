"""Frozen measurement-layer constants (docs/RATINGS.md §Architecture 1). Changing any value
here changes every stored aggregate: bump STATS_VERSION and re-ingest.

Set 2026-10-18, before any rating was fitted. The luck and field-goal constants are estimated
on the 2016-2022 fitting seasons only (`python -m marketscope_football.luck_fit`)."""

STATS_VERSION = "team-game-stats-v1"

FIT_SEASONS = tuple(range(2016, 2023))

# --- Model channel: WP-weighted, extreme-play-capped, luck-adjusted EPA -----------------
# Plays outside 10-90% pre-snap win probability (garbage time) are down-weighted linearly
# to WP_WEIGHT_FLOOR at 0%/100%, in the spirit of FPI removing "trash time" without
# discarding plays outright.
WP_FULL_WEIGHT = (0.10, 0.90)
WP_WEIGHT_FLOOR = 0.25
# Cap on per-play EPA after the luck adjustment (≈ the 1st/99th percentile of 2016-22
# scrimmage EPA: -4.56 / +3.69), so one return touchdown cannot dominate a game.
EPA_CAP = 4.5

# --- Situations ---------------------------------------------------------------------------
# "Neutral": the game state where play-calling reflects scheme, not the scoreboard.
NEUTRAL_WP = (0.20, 0.80)
NEUTRAL_MIN_HALF_SECONDS = 120
# Seconds between consecutive snaps of one drive; longer gaps are timeouts, injuries,
# reviews or quarter breaks.
PACE_MAX_GAP_SECONDS = 60
EXPLOSIVE_PASS_YARDS = 20
EXPLOSIVE_RUSH_YARDS = 10
SCORING_OPP_YARDLINE = 40  # a drive reaching the opponent's 40 is a scoring opportunity

# --- Luck (2016-22 fit) -----------------------------------------------------------------
# Fumbles: whether the offense recovers its own fumble is close to a coin flip. A play's
# luck = (lost - P_LOST) x (EPA_LOST - EPA_RECOVERED); the adjusted EPA removes it.
FUMBLE_P_LOST = 0.4611  # n = 3,852 own fumbles on scrimmage plays
FUMBLE_EPA_LOST = -4.997
FUMBLE_EPA_RECOVERED = -0.6628
# Interceptions: a fixed share of passes defensed (deflections + interceptions) become
# interceptions (the Football Outsiders / Bill Connelly proxy for interception luck).
INT_P_GIVEN_DEFENSED = 0.1904  # n = 16,021 passes defensed
INT_EPA = -4.4355
INT_EPA_DEFENSED = -0.8855

# --- Field-goal make probability by distance: 1 / (1 + exp(-(a + b·yards))) --------------
FG_INTERCEPT = 6.1888  # n = 7,318 attempts; 50 yards -> 0.70
FG_SLOPE = -0.1071
