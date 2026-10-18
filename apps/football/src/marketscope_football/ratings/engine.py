"""Runs the three channel filters together over games in kickoff order, and turns unit ratings
into game predictions (the game layer). `KalmanRatings` plugs the engine into the MS-029
walk-forward harness."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..eval.metrics import win_probability
from .design import BURN_IN_FROM
from .kalman import PaceFilter, PaceParams, STFilter, STParams, UnitFilter, UnitParams

PARAMS_PATH = Path(__file__).with_name("params.json")


UNIT_CHANNELS = ("pass", "rush", "succ", "ppd")
FEATURES = ("pass", "rush", "succ", "ppd", "st")  # + "qb" (qb.py) and "avail_*" (availability_adj.py)


@dataclass
class GameLayer:
    """margin = sum over channels of w[ch] * feature[ch] + c * (not neutral), fitted by OLS on the
    tuning seasons. Features: expected net pass / rush EPA per game (EPA/play difference times
    league plays per team-game), expected success-rate difference, expected net points from drives
    (points-per-drive difference times league drives per team-game), expected net special-teams EPA."""
    n_pass: float
    n_rush: float
    n_drives: float
    w: dict
    c: float
    # Total = total_a + total_b * expected drives * (expected points per drive, both offenses).
    total_a: float | None = None
    total_b: float | None = None

    def total(self, raw: float) -> float | None:
        return None if self.total_b is None else self.total_a + self.total_b * raw

    def margin(self, f: dict[str, float], neutral: bool) -> float:
        return sum(self.w[k] * f[k] for k in self.w) + (0.0 if neutral else self.c)


def continuity(games: pd.DataFrame, callers: dict) -> tuple[dict, dict]:
    """Play-caller changes from the coaching staff table.
    season_flags[(season, team)] = (offense changed, defense changed) vs the team's last game of the
    previous season; week_flags[(season, week)][team] = the same vs the team's previous game this
    season. Unknown callers (before 2016) count as unchanged."""
    season_flags, week_flags = {}, defaultdict(dict)
    rows = pd.concat([games[["season", "week", "kickoff_utc", "home"]].rename(columns={"home": "team"}),
                      games[["season", "week", "kickoff_utc", "away"]].rename(columns={"away": "team"})])
    for team, g in rows.sort_values("kickoff_utc").groupby("team"):
        prev = None  # (season, week) of the team's previous game
        for season, week in zip(g["season"], g["week"]):
            cur = callers.get((season, team, week))
            old = callers.get((prev[0], team, prev[1])) if prev else None
            if cur and old:
                changed = (cur[0] != old[0], cur[1] != old[1])
                if prev[0] < season:
                    season_flags[(season, team)] = changed
                elif any(changed):
                    week_flags[(season, week)][team] = changed
            prev = (season, week)
    return season_flags, dict(week_flags)


def load_params(variant: str = "model", path: Path = PARAMS_PATH) -> tuple[dict, STParams, GameLayer]:
    """(unit params by channel, special teams, game layer). Pace params, when fitted, ride along in
    the units dict under "pace" (Engine routes them to a PaceFilter)."""
    p = json.loads(path.read_text())[variant]
    units = {ch: UnitParams(**p[ch]) for ch in UNIT_CHANNELS if ch in p}
    if "pace" in p:
        units["pace"] = PaceParams(**p["pace"])
    return units, STParams(**p["st"]), GameLayer(**p["game"])


class Engine:
    def __init__(self, teams: list[str], unit_params: dict[str, UnitParams], st_p: STParams,
                 obs: pd.DataFrame, season_flags: dict, week_flags: dict, use_st: bool = True):
        self.filters = {ch: UnitFilter(p, teams) for ch, p in unit_params.items() if ch != "pace"}
        self.filters["st"] = STFilter(st_p, teams)
        if "pace" in unit_params:
            self.filters["pace"] = PaceFilter(unit_params["pace"], teams)
        self.obs = obs_lookup(obs)
        self.season_flags, self.week_flags, self.use_st = season_flags, week_flags, use_st
        self.slot: tuple[int, int] | None = None

    def begin(self, season: int, week: int) -> None:
        if self.slot == (season, week):
            return
        sc = {t: f for (s, t), f in self.season_flags.items() if s == season}
        wc = self.week_flags.get((season, week), {})
        for f in self.filters.values():
            f.advance(season, week, sc, wc)
        self.slot = (season, week)

    def components(self, home: str, away: str, neutral: bool) -> dict[str, float]:
        """Expected per-play value of each offense in this matchup per unit channel, and expected
        net special-teams EPA."""
        s = 0.0 if neutral else 1.0
        out = {}
        for ch in self.filters:
            if ch in UNIT_CHANNELS:
                out[f"{ch}_home"] = self.filters[ch].expected(home, away, s)
                out[f"{ch}_away"] = self.filters[ch].expected(away, home, -s)
        out["st"] = self.filters["st"].expected(home, away, neutral) if self.use_st else 0.0
        return out

    def features(self, home: str, away: str, neutral: bool, layer: "GameLayer | None" = None,
                 n_pass: float = 0.0, n_rush: float = 0.0, n_drives: float = 0.0) -> dict[str, float]:
        if layer is not None:
            n_pass, n_rush, n_drives = layer.n_pass, layer.n_rush, layer.n_drives
        c = self.components(home, away, neutral)
        f = {"st": c["st"]}
        for ch, scale in (("pass", n_pass), ("rush", n_rush), ("succ", 1.0), ("ppd", n_drives)):
            if f"{ch}_home" in c:
                f[ch] = scale * (c[f"{ch}_home"] - c[f"{ch}_away"])
        return f

    def raw_total(self, home: str, away: str, neutral: bool) -> float | None:
        """Expected drives per team times both offenses' expected points per drive."""
        if "pace" not in self.filters or "ppd" not in self.filters:
            return None
        s = 0.0 if neutral else 1.0
        ppd = self.filters["ppd"].expected(home, away, s) + self.filters["ppd"].expected(away, home, -s)
        return self.filters["pace"].expected(home, away) * ppd

    def observe(self, game) -> dict[str, float]:
        """Update all filters with one completed game; returns log predictive density per channel."""
        ll = dict.fromkeys(self.filters, 0.0)
        for ch, *args in game_observations(game, self.obs):
            if ch not in self.filters or (ch == "st" and not self.use_st):
                continue
            ll[ch] += self.filters[ch].observe(*args)
        return ll


def obs_lookup(obs: pd.DataFrame) -> dict[tuple[str, str], tuple]:
    cols = ["st_epa", "drives"] + [f"{ch}_{k}" for ch in UNIT_CHANNELS for k in ("epa", "n")]
    return {(g, t): tuple(v) for g, t, *v in obs[["game_id", "team", *cols]].itertuples(index=False)}


def game_observations(game, lookup: dict) -> list[tuple]:
    """The filter observations one completed game provides: (channel, *observe args)."""
    out = []
    s = 0.0 if game.neutral else 1.0
    for off, dfn, sign in ((game.home, game.away, s), (game.away, game.home, -s)):
        o = lookup.get((game.game_id, off))
        if o is None:
            continue
        for k, ch in enumerate(UNIT_CHANNELS):
            y, n = o[2 + 2 * k], o[3 + 2 * k]
            if pd.notna(y) and pd.notna(n) and n >= 1:
                out.append((ch, off, dfn, sign, float(y), float(n)))
    o = lookup.get((game.game_id, game.home))
    if o is not None and pd.notna(o[0]):
        out.append(("st", game.home, game.away, bool(game.neutral), float(o[0])))
    a = lookup.get((game.game_id, game.away))
    if o is not None and a is not None and pd.notna(o[1]) and pd.notna(a[1]) and o[1] + a[1] > 0:
        out.append(("pace", game.home, game.away, (float(o[1]) + float(a[1])) / 2))
    return out


def channel_events(games: pd.DataFrame, obs: pd.DataFrame, season_flags: dict, week_flags: dict,
                   channel: str, last_season: int) -> list[tuple]:
    """The sequence of filter operations for one channel from BURN_IN_FROM through `last_season`:
    ("advance", season, week, season_changes, week_changes) and ("obs", season, *observe args).
    Lets maximum likelihood replay one channel quickly."""
    lookup = obs_lookup(obs)
    done = games[games["margin"].notna() & games["season"].between(BURN_IN_FROM, last_season)]
    events = []
    for (season, week), slot in done.groupby(["season", "week"], sort=True):
        sc = {t: f for (s, t), f in season_flags.items() if s == season}
        events.append(("advance", season, week, sc, week_flags.get((season, week), {})))
        for g in slot.sort_values("kickoff_utc").itertuples(index=False):
            for ch, *args in game_observations(g, lookup):
                if ch == channel:
                    events.append(("obs", season, *args))
    return events


class KalmanRatings:
    """Walk-forward model: filtered ratings before each week -> expected margin and win probability."""

    def __init__(self, name: str, teams: list[str], params: tuple, obs: pd.DataFrame, season_flags: dict,
                 week_flags: dict, sigma: float, use_st: bool = True, qb=None, avail=None, extras=(), dist=None):
        units, st_p, self.layer = params
        self.name, self.sigma, self.qb, self.avail, self.extras = name, sigma, qb, avail, tuple(extras)
        self.dist = dist  # margin_dist.MarginDistribution (ratings-v1) or None for Phi(m / sigma)
        self.engine = Engine(teams, units, st_p, obs, season_flags, week_flags, use_st)

    def _features(self, g) -> dict[str, float]:
        f = self.engine.features(g.home, g.away, bool(g.neutral), self.layer)
        if self.qb is not None:
            f["qb"] = self.qb.feature(g)
        if self.avail is not None:
            f.update(self.avail.features(g))
        for x in self.extras:
            f.update(x.features(g))
        return f

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        self.engine.begin(int(games["season"].iloc[0]), int(games["week"].iloc[0]))
        margin = np.array([self.layer.margin(self._features(g), bool(g.neutral)) for g in games.itertuples(index=False)])
        p = self.dist.p_home(margin) if self.dist is not None else win_probability(margin, self.sigma)
        out = pd.DataFrame({"margin": margin, "p_home": p}, index=games.index)
        if self.layer.total_b is not None and "pace" in self.engine.filters:
            out["total"] = [self.layer.total(self.engine.raw_total(g.home, g.away, bool(g.neutral)))
                            for g in games.itertuples(index=False)]
        return out

    def update(self, results: pd.DataFrame) -> None:
        season = int(results["season"].iloc[0])
        if season < BURN_IN_FROM:
            return
        self.engine.begin(season, int(results["week"].iloc[0]))
        for g in results.itertuples(index=False):
            self.engine.observe(g)
        if self.qb is not None:
            self.qb.update(results)
