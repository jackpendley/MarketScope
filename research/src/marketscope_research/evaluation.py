"""Evaluation boundaries and the confirmation family (research/PREREGISTRATION.md Addendum V).

Sensitivities only: no registered primary, sample or decision rule changes.

- FROZEN_AT: when each addendum that fixed a confirmation rule landed on `main` (commit time, UTC;
  conservative because it is later than the authoring time).
- frozen_first: the positions whose decision came after that freeze.
- mean_bootstrap: a mean with a 95% interval from resampling a cluster column (games by default, weeks
  for the shared-shock sensitivity), plus the draws for a two-sided bootstrap p-value.
- holm: Holm's step-down adjustment across the confirmation family.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .football_studies import RESAMPLES, SEED

FROZEN_AT = {
    "C": "2026-10-20T03:26:37Z", "D": "2026-10-20T03:26:37Z",
    "G": "2026-10-21T02:36:54Z", "H": "2026-10-21T02:36:54Z",
    "I": "2026-10-21T03:00:16Z", "J": "2026-10-21T03:09:32Z",
    "K": "2026-10-21T04:16:29Z", "L": "2026-10-21T04:16:29Z",
    "O": "2026-10-21T23:47:45Z",
    "P": "2026-10-22T17:07:52Z", "Q": "2026-10-22T17:07:52Z", "R": "2026-10-22T17:07:52Z",
    "S": "2026-10-22T17:07:52Z",
    "U": "2026-10-22T19:31:35Z",
}


def frozen_at(addendum: str) -> pd.Timestamp:
    return pd.Timestamp(FROZEN_AT[addendum])


def frozen_first(df: pd.DataFrame, decision_col: str, addendum: str) -> pd.DataFrame:
    """Rows whose decision time is strictly after the addendum's freeze."""
    return df[pd.to_datetime(df[decision_col], utc=True) > frozen_at(addendum)]


@dataclass(frozen=True)
class Boot:
    value: float
    low: float
    high: float
    n: int
    clusters: int
    p: float  # two-sided bootstrap p-value: 2 * min(share of draws <= 0, share >= 0), capped at 1


def mean_bootstrap(df: pd.DataFrame, col: str, cluster: str = "event_id", resamples: int = RESAMPLES) -> Boot:
    """Mean of `col` over rows, resampling whole clusters with replacement (5,000 draws, seed 2026)."""
    g = df.groupby(cluster)[col].agg(["sum", "count"])
    s, c = g["sum"].to_numpy(float), g["count"].to_numpy(float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(g), (resamples, len(g)))
    boots = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    lo, hi = np.nanquantile(boots, [0.025, 0.975])
    return Boot(float(s.sum() / c.sum()), float(lo), float(hi), len(df), len(g), boot_p(boots))


def boot_p(draws: np.ndarray) -> float:
    draws = draws[~np.isnan(draws)]
    if not len(draws):
        return 1.0
    return float(min(1.0, 2 * min((draws <= 0).mean(), (draws >= 0).mean())))


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Which hypotheses Holm's step-down procedure rejects at family-wise `alpha`."""
    order = sorted(pvalues, key=pvalues.get)
    m, out, stopped = len(order), {}, False
    for i, k in enumerate(order):
        stopped = stopped or pvalues[k] > alpha / (m - i)
        out[k] = not stopped
    return out


def ols_ci(df: pd.DataFrame, y: str, xs: list[str], cluster: str = "event_id",
           resamples: int = RESAMPLES) -> list[Boot]:
    """OLS coefficients of y on xs (with an intercept), each with a 95% interval from resampling whole
    clusters (5,000 draws, seed 2026)."""
    groups = [g for _, g in df.groupby(cluster)]
    X_all = np.column_stack([np.ones(len(df))] + [df[x].to_numpy(float) for x in xs])
    yv = df[y].to_numpy(float)

    def fit(X, yy):
        return np.linalg.lstsq(X, yy, rcond=None)[0][1:] if np.linalg.matrix_rank(X) == X.shape[1] else \
            np.full(len(xs), np.nan)

    pos = {k: np.flatnonzero(df[cluster].to_numpy() == k) for k in df[cluster].unique()}
    keys = sorted(pos)  # deterministic regardless of row order
    rng = np.random.default_rng(SEED)
    draws = np.empty((resamples, len(xs)))
    for b in range(resamples):
        rows = np.concatenate([pos[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
        draws[b] = fit(X_all[rows], yv[rows])
    est = fit(X_all, yv)
    out = []
    for j in range(len(xs)):
        lo, hi = np.nanquantile(draws[:, j], [0.025, 0.975])
        out.append(Boot(float(est[j]), float(lo), float(hi), len(df), len(groups), boot_p(draws[:, j])))
    return out
