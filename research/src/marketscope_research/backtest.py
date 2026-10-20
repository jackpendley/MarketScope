"""System backtester (MS-044, research/PREREGISTRATION.md Addendum E, committed before this code).

Pure functions: bet grading with push rules, prices as parameters, teaser pairing, units, ROI,
drawdown and bootstrap intervals. Systems (e.g. Wong teasers in systems.py) produce legs; this
module grades and scores them. Every result here is hypothetical analysis, not advice.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from .football_studies import RESAMPLES, SEED, Estimate

Result = Literal["win", "push", "loss"]
PushRule = Literal["loses", "voids"]


# --- grading ------------------------------------------------------------------------------------

def grade_spread(team_margin: float, line: float) -> Result:
    """A side at `line` (from its own perspective, e.g. -3) given its margin (points for - against)."""
    v = team_margin + line
    return "win" if v > 0 else "push" if v == 0 else "loss"


def grade_total(total_points: float, line: float, side: Literal["over", "under"]) -> Result:
    v = total_points - line if side == "over" else line - total_points
    return "win" if v > 0 else "push" if v == 0 else "loss"


def grade_moneyline(team_margin: float) -> Result:
    return "win" if team_margin > 0 else "push" if team_margin == 0 else "loss"


def profit(price: int) -> float:
    """Profit per unit staked on a win at an American price."""
    return 100 / -price if price < 0 else price / 100


def units(result: Result, price: int) -> float:
    return profit(price) if result == "win" else 0.0 if result == "push" else -1.0


def decimal(price: int) -> float:
    return 1 + profit(price)


def teaser_break_even(price: int, legs: int = 2) -> float:
    """Leg win rate at which a `legs`-team teaser at `price` breaks even (independent legs)."""
    return (1 / decimal(price)) ** (1 / legs)


def teaser_units(results: tuple[Result, ...], price: int, push_rule: PushRule) -> float:
    """One unit on a teaser. Any loss loses. A push loses the teaser ("loses") or returns the stake
    ("voids"); otherwise all wins pay `price`."""
    if "loss" in results:
        return -1.0
    if "push" in results:
        return -1.0 if push_rule == "loses" else 0.0
    return profit(price)


# --- pairing ------------------------------------------------------------------------------------

def pair_chronological(legs: pd.DataFrame) -> pd.DataFrame:
    """Within each season-week, legs sorted by kickoff (then team) paired 1-2, 3-4, ...; an odd last
    leg is dropped. Returns one row per teaser with both legs' results."""
    rows = []
    for (season, week), g in legs.sort_values(["kickoff", "team"]).groupby(["season", "week"], sort=True):
        r = g.reset_index(drop=True)
        for i in range(0, len(r) - 1, 2):
            rows.append({"season": season, "week": week, "kickoff": r.loc[i + 1, "kickoff"],
                         "leg1": r.loc[i, "result"], "leg2": r.loc[i + 1, "result"]})
    return pd.DataFrame(rows, columns=["season", "week", "kickoff", "leg1", "leg2"])


def pair_all(legs: pd.DataFrame) -> pd.DataFrame:
    """Every pair of legs in the same season-week."""
    rows = []
    for (season, week), g in legs.groupby(["season", "week"], sort=True):
        res = list(g["result"])
        for i in range(len(res)):
            for j in range(i + 1, len(res)):
                rows.append({"season": season, "week": week, "leg1": res[i], "leg2": res[j]})
    return pd.DataFrame(rows, columns=["season", "week", "leg1", "leg2"])


def score_teasers(teasers: pd.DataFrame, price: int, push_rule: PushRule) -> pd.Series:
    return pd.Series([teaser_units((a, b), price, push_rule) for a, b in zip(teasers["leg1"], teasers["leg2"])],
                     index=teasers.index, dtype=float)


# --- summaries ----------------------------------------------------------------------------------

def max_drawdown(unit_results: pd.Series) -> float:
    """Largest peak-to-trough fall of cumulative units (as a positive number of units)."""
    equity = np.concatenate([[0.0], unit_results.cumsum().to_numpy()])
    return float((np.maximum.accumulate(equity) - equity).max())


def cluster_mean_ci(values: pd.Series, clusters: pd.Series, resamples: int = RESAMPLES) -> Estimate:
    """Mean of values with a 95% interval from resampling clusters (games, weeks) with replacement."""
    df = pd.DataFrame({"v": values.to_numpy(float), "c": clusters.to_numpy()})
    g = df.groupby("c")["v"].agg(["sum", "count"])
    s, n = g["sum"].to_numpy(), g["count"].to_numpy(float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(g), (resamples, len(g)))
    boots = s[idx].sum(axis=1) / n[idx].sum(axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return Estimate(float(s.sum() / n.sum()), float(lo), float(hi), int(n.sum()))
