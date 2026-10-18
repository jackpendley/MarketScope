"""Dynamic opponent-adjusted unit ratings as a Kalman filter (Glickman-Stern style), in numpy.

Pass and rush channels: the state is 32 offense units, 32 defense units and a league mean (EPA
per play). A team-game observation of team A's offense against team B's defense is
    y = mean + off[A] + def[B] + hfa * (+1/2 home, -1/2 away, 0 neutral) + e,  Var(e) = sigma2 / n_eff,
so every observation links two teams and the opponent adjustment happens inside the filter. A
positive defense unit means more EPA allowed (worse), as in KenPom's AdjD.
Special teams: 32 units; the home team's net special-teams EPA observes st[H] - st[A] + hfa.

Time: a random walk between weeks within a season; at a season boundary unit -> rho * unit with
extra variance, rho depending on play-caller continuity. Observations within a week are processed
sequentially (exact for the joint likelihood because states do not move within a week).
`state()` before a week's observations is the filtered, point-in-time rating used to predict it.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .design import INITIAL_VAR_MEAN, INITIAL_VAR_ST, INITIAL_VAR_UNIT

LOG_2PI = math.log(2 * math.pi)


@dataclass
class UnitParams:
    sigma2: float  # per-play observation variance
    q_week_off: float
    q_week_def: float
    q_season_off: float
    q_season_def: float
    rho_off_same: float
    rho_off_changed: float
    rho_def_same: float
    rho_def_changed: float
    hfa: float  # EPA/play, home minus away
    q_week_mean: float
    q_season_mean: float
    bump_off: float  # extra variance in the week of a mid-season play-caller change
    bump_def: float


@dataclass
class STParams:
    sigma2: float  # per-game observation variance (EPA^2)
    q_week: float
    q_season: float
    rho: float
    hfa: float


def to_dict(p) -> dict:
    return asdict(p)


class UnitFilter:
    """Offense/defense filter for one channel (pass or rush)."""

    def __init__(self, params: UnitParams, teams: list[str]):
        self.p, self.teams = params, list(teams)
        n = len(teams)
        self.ix = {t: i for i, t in enumerate(teams)}
        self.n, self.mean_ix = n, 2 * n
        self.x = np.zeros(2 * n + 1)
        self.P = np.diag([INITIAL_VAR_UNIT] * (2 * n) + [INITIAL_VAR_MEAN])
        self.season: int | None = None
        self.week: int | None = None

    def advance(self, season: int, week: int, season_change: dict, week_change: dict) -> None:
        """Move to (season, week). `season_change[team] = (off_changed, def_changed)` at a new
        season; `week_change[team]` the same for a mid-season play-caller change this week."""
        p, n = self.p, self.n
        if self.season is None:
            pass
        elif season > self.season:
            rho = np.ones(2 * n + 1)
            q = np.zeros(2 * n + 1)
            for t, i in self.ix.items():
                off_c, def_c = season_change.get(t, (False, False))
                rho[i] = p.rho_off_changed if off_c else p.rho_off_same
                rho[n + i] = p.rho_def_changed if def_c else p.rho_def_same
            q[:n], q[n:2 * n], q[2 * n] = p.q_season_off, p.q_season_def, p.q_season_mean
            self.x *= rho
            self.P = self.P * np.outer(rho, rho)
            self.P[np.diag_indices_from(self.P)] += q
        elif week != self.week:
            d = np.diag_indices_from(self.P)
            self.P[d[0][:n], d[1][:n]] += p.q_week_off
            self.P[d[0][n:2 * n], d[1][n:2 * n]] += p.q_week_def
            self.P[2 * n, 2 * n] += p.q_week_mean
        if self.season is not None and (season, week) != (self.season, self.week):
            for t, (off_c, def_c) in week_change.items():
                i = self.ix[t]
                if off_c:
                    self.P[i, i] += p.bump_off
                if def_c:
                    self.P[n + i, n + i] += p.bump_def
        self.season, self.week = season, week

    def expected(self, off_team: str, def_team: str, home_sign: float) -> float:
        i, j = self.ix[off_team], self.n + self.ix[def_team]
        return float(self.x[self.mean_ix] + self.x[i] + self.x[j] + self.p.hfa * home_sign / 2)

    def observe(self, off_team: str, def_team: str, home_sign: float, y: float, n_eff: float) -> float:
        """Update with one team-game observation; returns its log predictive density."""
        idx = (self.ix[off_team], self.n + self.ix[def_team], self.mean_ix)
        Ph = self.P[:, idx[0]] + self.P[:, idx[1]] + self.P[:, idx[2]]
        F = Ph[list(idx)].sum() + self.p.sigma2 / n_eff
        v = y - self.expected(off_team, def_team, home_sign)
        K = Ph / F
        self.x += K * v
        self.P -= np.outer(K, Ph)
        return -0.5 * (LOG_2PI + math.log(F) + v * v / F)

    def ratings(self) -> dict[str, np.ndarray]:
        """Offense and defense units centred on the league (mean absorbed), with standard errors."""
        n = self.n
        off, dfn = self.x[:n], self.x[n:2 * n]
        sd = np.sqrt(np.diag(self.P))
        return {"off": off - off.mean(), "def": dfn - dfn.mean(), "off_se": sd[:n], "def_se": sd[n:2 * n],
                "mean": self.x[self.mean_ix] + off.mean() + dfn.mean()}


class STFilter:
    """Special-teams filter: one unit per team, zero-sum observations."""

    def __init__(self, params: STParams, teams: list[str]):
        self.p, self.teams = params, list(teams)
        self.ix = {t: i for i, t in enumerate(teams)}
        self.x = np.zeros(len(teams))
        self.P = np.eye(len(teams)) * INITIAL_VAR_ST
        self.season: int | None = None
        self.week: int | None = None

    def advance(self, season: int, week: int, *_ignored) -> None:
        if self.season is None:
            pass
        elif season > self.season:
            self.x *= self.p.rho
            self.P *= self.p.rho ** 2
            self.P[np.diag_indices_from(self.P)] += self.p.q_season
        elif week != self.week:
            self.P[np.diag_indices_from(self.P)] += self.p.q_week
        self.season, self.week = season, week

    def expected(self, home: str, away: str, neutral: bool) -> float:
        return float(self.x[self.ix[home]] - self.x[self.ix[away]] + (0.0 if neutral else self.p.hfa))

    def observe(self, home: str, away: str, neutral: bool, y: float) -> float:
        i, j = self.ix[home], self.ix[away]
        Ph = self.P[:, i] - self.P[:, j]
        F = Ph[i] - Ph[j] + self.p.sigma2
        v = y - self.expected(home, away, neutral)
        K = Ph / F
        self.x += K * v
        self.P -= np.outer(K, Ph)
        return -0.5 * (LOG_2PI + math.log(F) + v * v / F)

    def ratings(self) -> dict[str, np.ndarray]:
        return {"st": self.x - self.x.mean(), "st_se": np.sqrt(np.diag(self.P))}
