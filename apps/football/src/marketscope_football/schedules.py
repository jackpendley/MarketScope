"""Transform nflverse teams and schedules into nfl_teams / nfl_games rows. Pure functions over
pandas frames so they are unit-tested without network or database."""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

EASTERN = ZoneInfo("America/New_York")

# Relocated franchises keep their historical abbreviation; ratings follow the franchise.
# LAR is an nflverse alias of LA (used by some datasets, never by schedules).
FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA"}


def _none(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def team_rows(teams: pd.DataFrame) -> list[dict]:
    """nflverse load_teams() -> nfl_teams rows. Only current franchises get an odds name."""
    rows = []
    for t in teams.itertuples(index=False):
        abbr = t.team_abbr
        rows.append(
            {
                "abbr": abbr,
                "franchise": FRANCHISE.get(abbr, abbr),
                "full_name": t.team_name,
                "nickname": t.team_nick,
                "conference": t.team_conf,
                "division": t.team_division,
                "odds_api_name": None if abbr in FRANCHISE else t.team_name,
            }
        )
    return rows


def kickoff_utc(gameday: str, gametime: str | None) -> datetime:
    """nflverse gameday/gametime are US Eastern local time."""
    hhmm = gametime or "13:00"
    local = datetime.fromisoformat(f"{gameday}T{hhmm}:00").replace(tzinfo=EASTERN)
    return local.astimezone(ZoneInfo("UTC"))


def home_spread_from_nflverse(spread_line) -> float | None:
    """nflverse spread_line is positive when the HOME team is favored (verified 2026-10-18:
    positive lines pair with negative home moneylines). Our convention is the posted home
    spread: negative = home favored. So ours = -spread_line."""
    v = _none(spread_line)
    return None if v is None else -float(v)


def game_rows(schedules: pd.DataFrame) -> list[dict]:
    rows = []
    for g in schedules.itertuples(index=False):
        home_score, away_score = _none(g.home_score), _none(g.away_score)
        rows.append(
            {
                "game_id": g.game_id,
                "season": int(g.season),
                "game_type": g.game_type,
                "week": int(g.week),
                "kickoff_utc": kickoff_utc(g.gameday, _none(g.gametime)),
                "home_team": g.home_team,
                "away_team": g.away_team,
                "neutral_site": g.location == "Neutral",
                "division_game": bool(_none(g.div_game) or 0),
                "home_rest_days": _none(g.home_rest),
                "away_rest_days": _none(g.away_rest),
                "home_score": None if home_score is None else int(home_score),
                "away_score": None if away_score is None else int(away_score),
                "overtime": None if _none(g.overtime) is None else bool(g.overtime),
                "stadium_id": _none(g.stadium_id),
                "stadium": _none(g.stadium),
                "roof": _none(g.roof),
                "surface": _none(g.surface) or None,
                "observed_temp_f": None if _none(g.temp) is None else int(g.temp),
                "observed_wind_mph": None if _none(g.wind) is None else int(g.wind),
                "referee": _none(g.referee),
                "home_coach": _none(g.home_coach),
                "away_coach": _none(g.away_coach),
                "home_qb_id": _none(g.home_qb_id),
                "away_qb_id": _none(g.away_qb_id),
                "nflverse_close_home_spread": home_spread_from_nflverse(g.spread_line),
                "nflverse_close_total": None if _none(g.total_line) is None else float(g.total_line),
                "nflverse_close_home_moneyline": None if _none(g.home_moneyline) is None else int(g.home_moneyline),
                "nflverse_close_away_moneyline": None if _none(g.away_moneyline) is None else int(g.away_moneyline),
            }
        )
    return rows
