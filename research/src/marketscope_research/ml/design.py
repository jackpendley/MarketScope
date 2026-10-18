"""Pre-registered design for the market-movement model (MS-024, ROADMAP Phase 7).

Everything in this file was fixed on 2026-10-18 BEFORE any label, class balance or model
result was computed. Only game and snapshot counts per week were looked at (to size the split).
Changing a value here after results are read must be recorded as a deviation in the report.
"""

from __future__ import annotations

import pandas as pd

# ---- Target ---------------------------------------------------------------------------------
HORIZON_HOURS = 24  # predict the consensus this far ahead
TOLERANCE_HOURS = 3  # the future snapshot must lie within t + 24 h +/- 3 h (snapshots are ~6 h apart)
MOVE_THRESHOLD = 0.5  # positive class: |consensus(t + 24 h) - consensus(t)| >= 0.5 points
# Eligible prediction times: between 7 days and 24 h before kickoff. 24 h is the spec's rule
# (the horizon must end before kickoff); 7 days matches what live collection covers, so the
# imported and live regimes are comparable (imported history reaches 30 days back).
MIN_LEAD_HOURS = 24
MAX_LEAD_HOURS = 168

# ---- Split (chronological, grouped by game: a game lives in exactly one split) ---------------
# NFL weeks run Tuesday -> Monday, US Eastern. Week 1 of 2026 starts Tuesday 2026-09-08.
SEASON_WEEK1_TUESDAY = pd.Timestamp("2026-09-08")
TRAIN_WEEKS = (1, 2, 3)
VALIDATION_WEEKS = (4,)
TEST_WEEKS = (5,)
# Weeks >= 6 come from live collection (a different source and book mix): reported separately
# as a forward check, never folded into the headline test result.
FORWARD_FROM_WEEK = 6

# ---- Data gate (if any fails, publish exploratory analysis only; no model claims) -----------
MIN_GAMES = 60
MIN_POSITIVES = 150
MIN_TEST_GAMES = 15
MIN_TEST_POSITIVES = 30
MIN_FORWARD_GAMES = 15  # below this the forward check is reported as "pending"

# ---- Key numbers (home-spread magnitudes) ---------------------------------------------------
KEY_NUMBERS = (3.0, 7.0)


def nfl_week(kickoff_utc: pd.Series) -> pd.Series:
    """2026 NFL week of each kickoff (Tuesday-to-Monday weeks in US Eastern time)."""
    local = kickoff_utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return ((local - SEASON_WEEK1_TUESDAY).dt.days // 7 + 1).astype(int)


def split_for_week(week: int) -> str:
    if week in TRAIN_WEEKS:
        return "train"
    if week in VALIDATION_WEEKS:
        return "validation"
    if week in TEST_WEEKS:
        return "test"
    if week >= FORWARD_FROM_WEEK:
        return "forward"
    return "excluded"
