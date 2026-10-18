"""Classic KenPom adjustment as an explicit benchmark (docs/RATINGS.md): within a season,

    AdjO[T] = mean over T's games of RawO_game * (league average / AdjD[opponent]) / venue,
    AdjD[T] = mean over T's games of RawD_game * (league average / AdjO[opponent]) * venue,

iterated to convergence on raw points per drive, with a multiplicative home factor (offense at
home divided by it, on the road multiplied), equal game weights and no prior. Compared with the
Kalman engine by rank correlation to show they agree on who is good, and where the filter's
prior and opponent adjustment differ.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def classic_ratings(tg: pd.DataFrame, iterations: int = 100) -> pd.DataFrame:
    """`tg`: one row per team per game with team, opponent, loc (-1 home, +1 away, 0 neutral),
    ppd_for, ppd_against, drives. Returns team, adj_o, adj_d, adj_em (points per game)."""
    tg = tg.dropna(subset=["ppd_for", "ppd_against"])
    league = tg["ppd_for"].mean()
    home, away = tg.loc[tg["loc"] == -1, "ppd_for"].mean(), tg.loc[tg["loc"] == 1, "ppd_for"].mean()
    h = np.sqrt(home / away) if away > 0 else 1.0
    venue = np.where(tg["loc"] == -1, h, np.where(tg["loc"] == 1, 1 / h, 1.0))  # this offense's venue boost
    raw_o, raw_d = tg["ppd_for"].to_numpy() / venue, tg["ppd_against"].to_numpy() * venue
    teams = sorted(set(tg["team"]))
    ao = pd.Series(league, index=teams)
    ad = pd.Series(league, index=teams)
    for _ in range(iterations):
        o = raw_o * league / ad.reindex(tg["opponent"]).to_numpy()
        d = raw_d * league / ao.reindex(tg["opponent"]).to_numpy()
        new_o = pd.Series(o).groupby(tg["team"].to_numpy()).mean()
        new_d = pd.Series(d).groupby(tg["team"].to_numpy()).mean()
        done = np.allclose(new_o, ao.reindex(new_o.index)) and np.allclose(new_d, ad.reindex(new_d.index))
        ao, ad = new_o, new_d
        if done:
            break
    drives = tg["drives"].mean()
    return pd.DataFrame({"team": ao.index, "adj_o": ao.to_numpy(), "adj_d": ad.reindex(ao.index).to_numpy(),
                         "adj_em": (ao.to_numpy() - ad.reindex(ao.index).to_numpy()) * drives})


def season_team_games(games: pd.DataFrame, obs: pd.DataFrame, season: int, through_week: int) -> pd.DataFrame:
    o = obs.set_index(["game_id", "team"])
    g = games[(games["season"] == season) & (games["week"] <= through_week) & games["margin"].notna()]
    rows = []
    for side, opp in (("home", "away"), ("away", "home")):
        own = o.reindex(pd.MultiIndex.from_arrays([g["game_id"], g[side]]))
        oth = o.reindex(pd.MultiIndex.from_arrays([g["game_id"], g[opp]]))
        rows.append(pd.DataFrame({
            "team": g[side].to_numpy(), "opponent": g[opp].to_numpy(),
            "loc": np.where(g["neutral"], 0, -1 if side == "home" else 1),
            "ppd_for": own["ppd_epa"].to_numpy(), "ppd_against": oth["ppd_epa"].to_numpy(),
            "drives": own["drives"].to_numpy()}))
    return pd.concat(rows, ignore_index=True)
