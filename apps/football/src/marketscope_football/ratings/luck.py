"""Luck models (KenPom's Luck, mapped to the NFL), fitted on 2016-22 and frozen in params.json:

- Expected wins: P(home win) = logistic(alpha * home + beta * game net adjusted EPA), i.e. how
  often a team that played this well (luck-adjusted, capped, WP-weighted EPA; ADR-029) wins.
- Pythagorean wins: games * PF^x / (PF^x + PA^x), exponent x by least squares on team-seasons.

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.luck
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar

from .design import LIKELIHOOD_SEASONS
from .engine import PARAMS_PATH


def team_offense_epa(obs: pd.DataFrame) -> pd.Series:
    """Offensive adjusted EPA total in a game (channel mean times plays, pass + rush)."""
    return obs["pass_epa"].fillna(0) * obs["pass_plays"].fillna(0) + obs["rush_epa"].fillna(0) * obs["rush_plays"].fillna(0)


def game_net_epa(games: pd.DataFrame, obs: pd.DataFrame) -> pd.Series:
    """Home net adjusted EPA in each game: own offense EPA - opponent offense EPA + own net special
    teams (NaN when play-by-play is missing)."""
    o = obs.assign(off=team_offense_epa(obs)).set_index(["game_id", "team"])
    h = o.reindex(pd.MultiIndex.from_arrays([games["game_id"], games["home"]]))
    a = o.reindex(pd.MultiIndex.from_arrays([games["game_id"], games["away"]]))
    return pd.Series(h["off"].to_numpy() - a["off"].to_numpy() + h["st_epa"].to_numpy(), index=games.index)


def win_probability(alpha: float, beta: float, home: np.ndarray, net: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(alpha * home + beta * net)))


def fit_expected_wins(games: pd.DataFrame, net: pd.Series) -> dict:
    g = games.assign(net=net)
    g = g[g["season"].isin(LIKELIHOOD_SEASONS) & g["net"].notna() & g["home_win"].isin([0.0, 1.0])]
    h, x, y = (~g["neutral"]).to_numpy(float), g["net"].to_numpy(float), g["home_win"].to_numpy(float)

    def nll(z):
        p = np.clip(win_probability(z[0], z[1], h, x), 1e-9, 1 - 1e-9)
        return -np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))

    res = minimize(nll, np.array([0.0, 0.2]), method="BFGS")
    return {"alpha": float(res.x[0]), "beta": float(res.x[1]), "games": int(len(g))}


def team_seasons(games: pd.DataFrame) -> pd.DataFrame:
    rows = []
    done = games[games["margin"].notna()]
    for side, opp in (("home", "away"), ("away", "home")):
        rows.append(pd.DataFrame({
            "season": done["season"], "team": done[side],
            "pf": done[f"{side}_score"], "pa": done[f"{opp}_score"],
            "win": done["home_win"] if side == "home" else 1 - done["home_win"]}))
    return pd.concat(rows).groupby(["season", "team"]).agg(pf=("pf", "sum"), pa=("pa", "sum"), wins=("win", "sum"),
                                                           games=("win", "size")).reset_index()


def pythag_share(pf, pa, x: float):
    pf, pa = np.asarray(pf, float), np.asarray(pa, float)
    return pf ** x / (pf ** x + pa ** x)


def fit_pythag_exponent(games: pd.DataFrame) -> dict:
    ts = team_seasons(games[games["season"].isin(LIKELIHOOD_SEASONS)])
    wpct = ts["wins"] / ts["games"]
    res = minimize_scalar(lambda x: float(np.sum((pythag_share(ts["pf"], ts["pa"], x) - wpct) ** 2)),
                          bounds=(1.0, 5.0), method="bounded")
    return {"exponent": float(res.x), "team_seasons": int(len(ts))}


def main() -> None:
    from .fit import load_inputs

    games, obs, *_ = load_inputs("model")
    ew = fit_expected_wins(games, game_net_epa(games, obs))
    py = fit_pythag_exponent(games)
    params = json.loads(PARAMS_PATH.read_text())
    params["luck"] = {"expected_wins": ew, "pythag": py, "fit_seasons": [min(LIKELIHOOD_SEASONS), max(LIKELIHOOD_SEASONS)]}
    PARAMS_PATH.write_text(json.dumps(params, indent=2))
    print(params["luck"])


if __name__ == "__main__":
    main()
