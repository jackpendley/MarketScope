"""Benchmark models for the walk-forward harness (MS-029). Each implements predict/update
(walkforward.Model). Constants live in design.py; win probabilities from an expected margin use
Phi(margin / sigma) with sigma fit on 1999-2015 closing lines (outside every scored season)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import design as d
from .metrics import win_probability


class NaiveHomeField:
    """Expected margin = recent league home-field advantage (0 at neutral sites); total = recent
    league mean. Knows nothing about the teams: the floor every model must clear."""

    def __init__(self, sigma: float, window_seasons: int = d.HFA_WINDOW_SEASONS):
        self.name, self.sigma, self.window = "naive home field", sigma, window_seasons
        self.history: list[pd.DataFrame] = []

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        season = int(games["season"].iloc[0])
        h = pd.concat(self.history) if self.history else games.iloc[:0]
        h = h[h["season"] >= season - self.window]
        hfa = float(h.loc[~h["neutral"], "margin"].mean()) if len(h) else 0.0
        total = float(h["total"].mean()) if len(h) else float("nan")
        margin = np.where(games["neutral"], 0.0, hfa)
        return pd.DataFrame({"margin": margin, "p_home": win_probability(margin, self.sigma), "total": total},
                            index=games.index)

    def update(self, results: pd.DataFrame) -> None:
        self.history.append(results[["season", "neutral", "margin", "total"]])


class Elo538:
    """FiveThirtyEight's NFL Elo (fivethirtyeight/nfl-elo-game), constants as published."""

    def __init__(self, k: float = d.ELO_K, hfa: float = d.ELO_HFA, revert: float = d.ELO_REVERT,
                 mov: bool = True):
        self.name, self.k, self.hfa, self.revert, self.mov = "Elo (538)", k, hfa, revert, mov
        self.elo: dict[str, float] = {}
        self.season: int | None = None

    def _season(self, season: int) -> None:
        if self.season is not None and season > self.season:
            self.elo = {t: d.ELO_MEAN * self.revert + e * (1 - self.revert) for t, e in self.elo.items()}
        self.season = season

    def _diff(self, g) -> float:
        return (self.elo.get(g.home, d.ELO_START) - self.elo.get(g.away, d.ELO_START)
                + (0.0 if g.neutral else self.hfa))

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        self._season(int(games["season"].iloc[0]))
        diff = np.array([self._diff(g) for g in games.itertuples(index=False)])
        return pd.DataFrame({"margin": diff / d.ELO_POINTS_PER_POINT, "p_home": 1 / (1 + 10 ** (-diff / 400))},
                            index=games.index)

    def update(self, results: pd.DataFrame) -> None:
        self._season(int(results["season"].iloc[0]))
        for g in results.itertuples(index=False):
            diff = self._diff(g)
            p = 1 / (1 + 10 ** (-diff / 400))
            res = g.home_win
            if self.mov:
                winner_edge = diff if res == 1.0 else -diff
                mult = math.log(max(abs(g.margin), 1) + 1.0) * (2.2 / (1.0 if res == 0.5 else winner_edge * 0.001 + 2.2))
            else:
                mult = 1.0
            shift = self.k * mult * (res - p)
            self.elo[g.home] = self.elo.get(g.home, d.ELO_START) + shift
            self.elo[g.away] = self.elo.get(g.away, d.ELO_START) - shift


def ridge_ratings(h: pd.DataFrame, target: str, as_of: pd.Timestamp, half_life: float,
                  lam: float) -> tuple[dict[str, float], float]:
    """Team ratings and home-field advantage from past games: weighted ridge on
    target = r_home - r_away + hfa * (not neutral). Ratings shrink toward 0 (an average team)."""
    h = h[h[target].notna()]
    if h.empty:
        return {}, 0.0
    teams = sorted(set(h["home"]) | set(h["away"]))
    ix = {t: i for i, t in enumerate(teams)}
    n, k = len(h), len(teams)
    X = np.zeros((n, k + 1))
    rows = np.arange(n)
    X[rows, h["home"].map(ix).to_numpy()] = 1.0
    X[rows, h["away"].map(ix).to_numpy()] = -1.0
    X[:, k] = (~h["neutral"]).to_numpy(float)
    age = (as_of - h["kickoff_utc"]).dt.total_seconds().to_numpy() / 86400
    w = 0.5 ** (age / half_life)
    A = X.T @ (X * w[:, None])
    A[np.arange(k), np.arange(k)] += lam
    b = np.linalg.solve(A, X.T @ (w * h[target].to_numpy(float)))
    return {t: float(b[ix[t]]) for t in teams}, float(b[k])


class RidgeRatings:
    """SRS-style ratings (target `margin`) or market-implied ratings (target `close_margin`, the
    closing lines of PAST games). Refit before every slot on the last RIDGE_WINDOW_DAYS."""

    def __init__(self, name: str, target: str, sigma: float, half_life: float, lam: float,
                 season_only: bool = False):
        self.name, self.target, self.sigma = name, target, sigma
        self.half_life, self.lam, self.season_only = half_life, lam, season_only
        self.history: list[pd.DataFrame] = []

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        as_of = games["kickoff_utc"].min()
        h = pd.concat(self.history) if self.history else games.iloc[:0]
        h = h[h["kickoff_utc"] >= as_of - pd.Timedelta(days=d.RIDGE_WINDOW_DAYS)]
        if self.season_only:
            h = h[h["season"] == games["season"].iloc[0]]
        r, hfa = ridge_ratings(h, self.target, as_of, self.half_life, self.lam)
        margin = np.array([r.get(g.home, 0.0) - r.get(g.away, 0.0) + (0.0 if g.neutral else hfa)
                           for g in games.itertuples(index=False)])
        return pd.DataFrame({"margin": margin, "p_home": win_probability(margin, self.sigma)}, index=games.index)

    def update(self, results: pd.DataFrame) -> None:
        self.history.append(results[list(dict.fromkeys(["season", "kickoff_utc", "home", "away", "neutral", self.target]))])


class NflverseClose:
    """The market close itself: spread as expected margin, no-vig moneyline as win probability
    (Phi(spread / sigma) when a moneyline is missing), closing total."""

    def __init__(self, sigma: float):
        self.name, self.sigma = d.REFERENCE, sigma

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        margin = games["close_margin"].to_numpy(float)
        p = games["close_p_home"].to_numpy(float)
        p = np.where(np.isnan(p), win_probability(margin, self.sigma), p)
        return pd.DataFrame({"margin": margin, "p_home": p, "total": games["close_total"].to_numpy(float)},
                            index=games.index)

    def update(self, results: pd.DataFrame) -> None:
        pass
