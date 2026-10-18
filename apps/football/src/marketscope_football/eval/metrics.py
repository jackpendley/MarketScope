"""Scoring for game predictions: margin MAE/RMSE, total MAE, win-probability Brier and log loss,
with 95% bootstrap CIs resampling games and paired differences against a reference model."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .design import BOOTSTRAP_RESAMPLES, CALIBRATION_EDGES, CI_LEVEL

EPS = 1e-6
METRICS = ("margin_mae", "margin_rmse", "brier", "log_loss", "total_mae")


def normal_cdf(x: np.ndarray | float) -> np.ndarray:
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(x, dtype=float) / math.sqrt(2)))


def win_probability(margin: np.ndarray, sigma: float) -> np.ndarray:
    """P(home wins) when the final margin ~ Normal(expected margin, sigma)."""
    return normal_cdf(np.asarray(margin, dtype=float) / sigma)


def fit_sigma(expected_margin: np.ndarray, home_win: np.ndarray) -> float:
    """Maximum-likelihood sigma for P(home win) = Phi(m / sigma), ties excluded (golden section)."""
    keep = (home_win == 0) | (home_win == 1)
    m, y = np.asarray(expected_margin, float)[keep], np.asarray(home_win, float)[keep]

    def nll(s: float) -> float:
        p = np.clip(win_probability(m, s), EPS, 1 - EPS)
        return float(-np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))

    lo, hi, g = 5.0, 30.0, (math.sqrt(5) - 1) / 2
    for _ in range(80):
        a, b = hi - g * (hi - lo), lo + g * (hi - lo)
        lo, hi = (lo, b) if nll(a) < nll(b) else (a, hi)
    return (lo + hi) / 2


def _scores(y_margin, y_win, y_total, margin, p, total) -> np.ndarray:
    err = margin - y_margin
    pc = np.clip(p, EPS, 1 - EPS)
    tot = total - y_total
    return np.array([
        np.mean(np.abs(err)),
        math.sqrt(np.mean(err ** 2)),
        np.mean((p - y_win) ** 2),
        -np.mean(y_win * np.log(pc) + (1 - y_win) * np.log(1 - pc)),
        np.nanmean(np.abs(tot)) if np.isfinite(tot).any() else np.nan,
    ])


def score_table(preds: pd.DataFrame, reference: str | None, seed: int = 2026,
                resamples: int = BOOTSTRAP_RESAMPLES) -> pd.DataFrame:
    """`preds`: long frame (model, game_id, margin, p_home, total?, actual_margin, home_win,
    actual_total). Every model must cover the same games (paired comparison). Returns one row
    per model: point estimates, CIs, and differences vs `reference` (negative = better)."""
    models = list(dict.fromkeys(preds["model"]))
    wide = {m: preds[preds["model"] == m].set_index("game_id").sort_index() for m in models}
    games = wide[models[0]].index
    for m in models:
        if not wide[m].index.equals(games):
            raise ValueError(f"model {m!r} does not cover the same games as {models[0]!r}")
    base = wide[models[0]]
    y_m, y_w, y_t = (base[c].to_numpy(float) for c in ("actual_margin", "home_win", "actual_total"))
    arrays = {m: tuple(wide[m][c].to_numpy(float) if c in wide[m] else np.full(len(games), np.nan)
                       for c in ("margin", "p_home", "total")) for m in models}
    point = {m: _scores(y_m, y_w, y_t, *arrays[m]) for m in models}

    rng = np.random.default_rng(seed)
    n = len(games)
    draws = {m: np.empty((resamples, len(METRICS))) for m in models}
    for i in range(resamples):
        idx = rng.integers(0, n, n)
        for m in models:
            draws[m][i] = _scores(y_m[idx], y_w[idx], y_t[idx], *(a[idx] for a in arrays[m]))
    alpha = (1 - CI_LEVEL) / 2 * 100
    rows = []
    for m in models:
        row = {"model": m, "games": n}
        for j, k in enumerate(METRICS):
            row[k] = point[m][j]
            row[f"{k}_lo"], row[f"{k}_hi"] = np.nanpercentile(draws[m][:, j], [alpha, 100 - alpha]) \
                if np.isfinite(draws[m][:, j]).any() else (np.nan, np.nan)
            if reference is not None:
                d = draws[m][:, j] - draws[reference][:, j]
                row[f"d_{k}"] = point[m][j] - point[reference][j]
                row[f"d_{k}_lo"], row[f"d_{k}_hi"] = np.nanpercentile(d, [alpha, 100 - alpha]) \
                    if np.isfinite(d).any() else (np.nan, np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def calibration_table(p: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    bins = pd.cut(p, bins=list(CALIBRATION_EDGES), include_lowest=True)
    df = pd.DataFrame({"bin": bins, "y": y, "p": p})
    g = df.groupby("bin", observed=False)
    return pd.DataFrame({"n": g.size(), "mean_predicted": g["p"].mean(), "observed": g["y"].mean()})
