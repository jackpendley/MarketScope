"""MS-055a: model-priced teaser legs, "Wong 2.0" (research/PREREGISTRATION.md Addendum N, committed
before this code). Pure functions; the runner is run_teasers_model.py.

Each team's 6-point teased line is priced with the fair-value engine's margin distribution, fitted only
on earlier seasons and calibrated so the closing spread is the market's median. Legs whose fair win
probability clears the teaser price's break-even are selected (one per game).
"""

from __future__ import annotations

import pandas as pd

from . import fair_value as fv
from . import market_ml as ml
from .backtest import grade_spread, teaser_break_even

TEASE = 6.0
PRIMARY_PRICE = -125


def leg_frame(games: pd.DataFrame, first_season: int, h_s: float, h_t: float) -> pd.DataFrame:
    """Both teams' teased legs with their fair win probability, walk-forward by season.
    games: game_id, season, week, kickoff, home, away, home_line, total, margin, points."""
    f = fv.favourite_frame(games)
    rows = []
    for season in sorted(s for s in games["season"].unique() if s >= first_season):
        model = fv.margin_model(f[(games["season"] < season).to_numpy()], h_s, h_t)
        for g in games[games["season"] == season].itertuples():
            pmf = model.pmf(abs(g.home_line), g.total)
            for side, team, line, margin in (("home", g.home, g.home_line, g.margin),
                                             ("away", g.away, -g.home_line, -g.margin)):
                teased = line + TEASE
                win, _push, _loss = ml.side_probabilities(pmf, g.home_line, 0.5, side, teased)
                rows.append({"game_id": g.game_id, "season": season, "week": g.week, "kickoff": g.kickoff,
                             "team": team, "side": side, "line": line, "teased": teased, "p": win,
                             "result": grade_spread(margin, teased)})
    return pd.DataFrame(rows, columns=["game_id", "season", "week", "kickoff", "team", "side", "line", "teased",
                                       "p", "result"])


def select_legs(legs: pd.DataFrame, price: int = PRIMARY_PRICE) -> pd.DataFrame:
    """The higher-probability leg per game, kept if it clears the price's break-even."""
    best = legs.sort_values("p", ascending=False).drop_duplicates("game_id")
    return best[best["p"] >= teaser_break_even(price)].sort_values(["kickoff", "team"]).reset_index(drop=True)
