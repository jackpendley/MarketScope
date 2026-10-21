"""Fair-value engine v2 (MS-053, research/PREREGISTRATION.md Addendum M, committed before this code).

- Margin model: P(favourite margin = k | |spread|, total). Kernel-weighted empirical frequencies over
  2016–25 games near the game's spread and total, mixed with 2% of the spread-bucket table (model A,
  market_ml.margin_tables) so nothing seen in training gets zero probability.
- Total model: P(total points = k | total, |spread|), built the same way.
- Devig: multiplicative, power and Shin for two-way prices.

A distribution is a pandas Series indexed by integer outcome, so it plugs straight into
market_ml.side_probabilities and openers_totals.total_side_probabilities, which calibrate it to a
market's no-vig price.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from . import market_ml as ml
from . import openers_totals as ot

MIX = 0.02
EPS = 1e-6  # floor for scoring only: a margin never seen anywhere would otherwise score -inf
H_SPREAD = (0.5, 1.0, 1.5, 2.0)
H_TOTAL = (2.0, 4.0, 6.0, 1000.0)  # 1000 = total effectively ignored


def favourite_frame(games: pd.DataFrame) -> pd.DataFrame:
    """Columns s (|closing spread|), t (closing total), k (favourite margin), pts (total points).
    games: home_line (closing home spread), total, margin (home - away), points."""
    fav_home = games["home_line"] <= 0
    return pd.DataFrame({"s": games["home_line"].abs().to_numpy(float), "t": games["total"].to_numpy(float),
                         "k": np.where(fav_home, games["margin"], -games["margin"]).astype(int),
                         "pts": games["points"].to_numpy(float).astype(int),
                         "season": games["season"].to_numpy() if "season" in games else 0})


@dataclass
class KernelModel:
    """Kernel-weighted outcome distribution conditioned on (spread, total)."""
    train: pd.DataFrame
    outcome: str          # "k" (favourite margin) or "pts" (total points)
    h_s: float
    h_t: float
    base: list[pd.Series]  # model A tables, for the 2% mix
    base_bucket: callable

    def pmf(self, s: float, t: float) -> pd.Series:
        """Cached per (s, t): lines come in half-points, so studies hit a small set of inputs."""
        cache = self.__dict__.setdefault("_cache", {})
        key = (round(float(s), 2), round(float(t), 2))
        if key not in cache:
            cache[key] = self._pmf(*key)
        return cache[key]

    def _pmf(self, s: float, t: float) -> pd.Series:
        w = np.exp(-0.5 * (((self.train["s"] - s) / self.h_s) ** 2 + ((self.train["t"] - t) / self.h_t) ** 2))
        w = w.to_numpy()
        y = self.train[self.outcome].to_numpy()
        kernel = pd.Series(w).groupby(y).sum()
        kernel = kernel / kernel.sum()
        base = self.base[self.base_bucket(s if self.outcome == "k" else t)]
        out = kernel.mul(1 - MIX).add(base.mul(MIX), fill_value=0.0)
        return (out / out.sum()).sort_index()


def margin_model(train: pd.DataFrame, h_s: float, h_t: float) -> KernelModel:
    base = ml.margin_tables(pd.DataFrame({"home_line": -train["s"], "margin": train["k"]}))
    return KernelModel(train, "k", h_s, h_t, base, lambda s: ml.bucket_of(s))


def total_model(train: pd.DataFrame, h_s: float, h_t: float) -> KernelModel:
    base = ot.total_tables(pd.DataFrame({"total": train["t"], "points": train["pts"]}))
    return KernelModel(train, "pts", h_s, h_t, base, lambda t: ot.total_bucket(t))


def bucket_pmf(train: pd.DataFrame, outcome: str):
    """Model A as a pmf function, for comparison on the same footing."""
    if outcome == "k":
        tables = ml.margin_tables(pd.DataFrame({"home_line": -train["s"], "margin": train["k"]}))
        return lambda s, t: tables[ml.bucket_of(s)]
    tables = ot.total_tables(pd.DataFrame({"total": train["t"], "points": train["pts"]}))
    return lambda s, t: tables[ot.total_bucket(t)]


def log_losses(pmf, test: pd.DataFrame, outcome: str) -> np.ndarray:
    out = np.empty(len(test))
    for i, r in enumerate(test.itertuples()):
        p = pmf(r.s, r.t)
        out[i] = -np.log(max(float(p.get(getattr(r, outcome), 0.0)), EPS))
    return out


def choose_bandwidths(train: pd.DataFrame, outcome: str) -> tuple[float, float, dict]:
    """Leave-one-season-out mean log loss on the training seasons for each bandwidth pair."""
    build = margin_model if outcome == "k" else total_model
    scores = {}
    for h_s in H_SPREAD:
        for h_t in H_TOTAL:
            losses = []
            for season in sorted(train["season"].unique()):
                fit, held = train[train["season"] != season], train[train["season"] == season]
                losses.append(log_losses(build(fit, h_s, h_t).pmf, held, outcome))
            scores[(h_s, h_t)] = float(np.concatenate(losses).mean())
    best = min(scores, key=scores.get)
    return best[0], best[1], scores


# --- devig ---------------------------------------------------------------------------------

def implied(american: float) -> float:
    return -american / (-american + 100) if american < 0 else 100 / (american + 100)


def devig(q1: float, q2: float, method: str) -> float:
    """Fair probability of side 1 from two implied probabilities (with overround)."""
    total = q1 + q2
    if method == "multiplicative":
        return q1 / total
    if method == "power":
        k = brentq(lambda k: q1 ** k + q2 ** k - 1, 0.5, 2.0) if total > 1 else 1.0
        return q1 ** k
    if method == "shin":
        def p(z, q):
            return (np.sqrt(z * z + 4 * (1 - z) * q * q / total) - z) / (2 * (1 - z))
        z = brentq(lambda z: p(z, q1) + p(z, q2) - 1, 0.0, 0.4) if total > 1 else 0.0
        return float(p(z, q1))
    raise ValueError(method)


DEVIG_METHODS = ("multiplicative", "power", "shin")


def win_probability(pmf: pd.Series) -> float:
    """P(favourite wins) from a margin pmf, ties excluded (moneylines push on a tie)."""
    k, p = pmf.index.to_numpy(), pmf.to_numpy()
    win, tie = p[k > 0].sum(), p[k == 0].sum()
    return float(win / (1 - tie)) if tie < 1 else 0.5


# --- the frozen engine (fair_value_params.json, written by run_fair_value) ---------------------

@dataclass
class Engine:
    """Margin and total-points distributions fitted on 2016–25, plus the chosen devig method."""
    margin: KernelModel | None
    total: KernelModel | None
    margin_bucket: callable
    total_bucket: callable
    devig_method: str

    def margin_pmf(self, home_spread: float, total: float) -> pd.Series:
        s = abs(home_spread)
        return self.margin.pmf(s, total) if self.margin else self.margin_bucket(s, total)

    def total_pmf(self, total: float, home_spread: float) -> pd.Series:
        s = abs(home_spread)
        return self.total.pmf(s, total) if self.total else self.total_bucket(s, total)


def load_engine(history: pd.DataFrame, params_path=None) -> Engine:
    """history: 2016–25 final games (home_line, total, margin, points, season)."""
    import json
    from pathlib import Path

    p = json.loads(Path(params_path or Path(__file__).with_name("fair_value_params.json")).read_text())
    f = favourite_frame(history)
    m, t = p["margin"], p["total"]
    return Engine(
        margin=margin_model(f, m["h_s"], m["h_t"]) if m["model"] == "kernel" else None,
        total=total_model(f, t["h_s"], t["h_t"]) if t["model"] == "kernel" else None,
        margin_bucket=bucket_pmf(f, "k"), total_bucket=bucket_pmf(f, "pts"), devig_method=p["devig"])
