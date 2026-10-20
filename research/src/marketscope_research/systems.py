"""Betting-system definitions for the backtester (MS-044). Each system turns games into legs; the
backtest module grades and scores them. Wong teasers follow research/PREREGISTRATION.md Addendum E.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from .backtest import grade_spread

Variant = Literal["V0", "V1", "V2"]
VARIANTS: dict[Variant, str] = {
    "V0": "every Wong leg",
    "V1": "closing total 49 or less",
    "V2": "total 49 or less, road teams only",
}
PRICES = (-110, -120, -125, -130, -135, -140)
PRIMARY_PRICE = -125
TEASE = 6.0
TOTAL_MAX = 49.0


def in_wong_range(team_line: float) -> bool:
    """Favourite -7.5 to -8.5 (teased through 7 and 3) or underdog +1.5 to +2.5 (through 3 and 7)."""
    return -8.5 <= team_line <= -7.5 or 1.5 <= team_line <= 2.5


def wong_legs(games: pd.DataFrame, variant: Variant = "V0") -> pd.DataFrame:
    """Legs from games with columns: game_id, season, week, kickoff, home, away, home_line (the home
    team's closing spread), total (closing total), margin (home minus away, final).

    At most one leg per game: if the home line is in range the home team is the leg, else the away
    team (away line = -home line) if that is in range."""
    rows = []
    for g in games.itertuples():
        for team, road, line, margin in ((g.home, False, g.home_line, g.margin),
                                         (g.away, True, -g.home_line, -g.margin)):
            if not in_wong_range(line):
                continue
            if variant in ("V1", "V2") and not (g.total <= TOTAL_MAX):
                break
            if variant == "V2" and not road:
                break
            teased = line + TEASE
            rows.append({"game_id": g.game_id, "season": g.season, "week": g.week, "kickoff": g.kickoff,
                         "team": team, "road": road, "role": "favourite" if line < 0 else "underdog",
                         "line": line, "teased": teased, "total": g.total,
                         "result": grade_spread(margin, teased)})
            break
    return pd.DataFrame(rows, columns=["game_id", "season", "week", "kickoff", "team", "road", "role",
                                       "line", "teased", "total", "result"])
