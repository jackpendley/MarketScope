"""Research study R2h (research/PREREGISTRATION.md, addendum B): is the injury part of each ratings-v1
estimate already priced in the closing line? The availability adjustment A is the game layer's QB
term plus its non-QB availability terms (weight x feature, points, home-oriented), recorded during
the walk-forward run so it is exactly what the model used before kickoff.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RESAMPLES = 5000
SEED = 2026
MIN_GAMES = 1000
BIG = 2.0  # |A| for the exploratory "large adjustment" subset


class RecordingModel:
    """Wraps a KalmanRatings: identical predictions, plus each game's availability contributions."""

    def __init__(self, model) -> None:
        self.model = model
        self.name = model.name
        self.rows: list[dict] = []

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        out = self.model.predict(games)  # sets the engine to this slot
        w = self.model.layer.w
        for g in games.itertuples(index=False):
            f = self.model._features(g)
            qb = w.get("qb", 0.0) * f.get("qb", 0.0)
            other = sum(w[k] * f.get(k, 0.0) for k in w if k.startswith("avail_"))
            self.rows.append({"game_id": g.game_id, "avail_qb": qb, "avail_other": other})
        return out

    def update(self, results: pd.DataFrame) -> None:
        self.model.update(results)


def _boot_slopes(y: np.ndarray, X: np.ndarray, resamples: int) -> tuple[np.ndarray, np.ndarray]:
    Xc = np.column_stack([np.ones(len(y)), X])
    beta = np.linalg.lstsq(Xc, y, rcond=None)[0]
    rng = np.random.default_rng(SEED)
    boots = np.empty((resamples, Xc.shape[1]))
    for b in range(resamples):
        i = rng.integers(0, len(y), len(y))
        boots[b] = np.linalg.lstsq(Xc[i], y[i], rcond=None)[0]
    return beta, boots


def estimate(beta: np.ndarray, boots: np.ndarray, j: int) -> tuple[float, float, float]:
    lo, hi = np.quantile(boots[:, j], [0.025, 0.975])
    return float(beta[j]), float(lo), float(hi)


def r2h(df: pd.DataFrame, resamples: int = RESAMPLES) -> dict:
    """df: season, ats (actual margin - close margin), avail_qb, avail_other (one row per game)."""
    d = df.dropna(subset=["ats", "avail_qb", "avail_other"]).copy()
    d["A"] = d["avail_qb"] + d["avail_other"]
    y = d["ats"].to_numpy(float)
    beta, boots = _boot_slopes(y, d[["A"]].to_numpy(float), resamples)
    primary = estimate(beta, boots, 1)
    b2, boots2 = _boot_slopes(y, d[["avail_qb", "avail_other"]].to_numpy(float), resamples)
    big = d[d["A"].abs() >= BIG]
    directed = np.sign(big["A"].to_numpy()) * big["ats"].to_numpy()
    rng = np.random.default_rng(SEED)
    mb = directed[rng.integers(0, len(directed), (resamples, len(directed)))].mean(axis=1) if len(directed) else np.array([np.nan])
    nonzero = int((d["A"] != 0).sum())
    per_season = {int(s): float(np.polyfit(g["A"], g["ats"], 1)[0]) for s, g in d.groupby("season") if g["A"].std() > 0}
    return {"games": len(d), "nonzero": nonzero, "gate": nonzero >= MIN_GAMES, "primary": primary,
            "claim": "under-priced" if primary[1] > 0 else "over-priced" if primary[2] < 0 else None,
            "qb": estimate(b2, boots2, 1), "other": estimate(b2, boots2, 2),
            "big_games": len(big), "big_directed": (float(directed.mean()) if len(directed) else np.nan,
                                                     *map(float, np.quantile(mb, [0.025, 0.975]))),
            "a_sd": float(d["A"].std()), "a_abs_mean": float(d["A"].abs().mean()), "per_season": per_season}
