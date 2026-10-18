"""Probabilistic scoring with game-clustered bootstrap CIs."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .design import BOOTSTRAP_RESAMPLES, CALIBRATION_EDGES

EPS = 1e-6


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    return float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else float("nan")


def score(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {"brier": brier(y, p), "log_loss": log_loss(y, p), "auc": auc(y, p)}


def bootstrap_scores(
    games: np.ndarray, y: np.ndarray, preds: dict[str, np.ndarray], reference: str, seed: int = 2026
) -> pd.DataFrame:
    """Point estimates and 95% CIs per model, resampling GAMES. Also the paired difference
    against `reference` (negative = better than the reference) for Brier and log loss."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(games)
    index = {g: np.flatnonzero(games == g) for g in uniq}
    draws: dict[str, list[tuple[float, float, float, float, float]]] = {m: [] for m in preds}
    for _ in range(BOOTSTRAP_RESAMPLES):
        rows = np.concatenate([index[g] for g in rng.choice(uniq, size=len(uniq), replace=True)])
        yb = y[rows]
        ref_b, ref_l = brier(yb, preds[reference][rows]), log_loss(yb, preds[reference][rows])
        for m, p in preds.items():
            pb = p[rows]
            b, l = brier(yb, pb), log_loss(yb, pb)
            draws[m].append((b, l, auc(yb, pb), b - ref_b, l - ref_l))
    out = []
    for m, p in preds.items():
        d = np.array(draws[m])
        point = score(y, p)
        lo, hi = np.nanpercentile(d, 2.5, axis=0), np.nanpercentile(d, 97.5, axis=0)
        out.append(
            {
                "model": m,
                "brier": point["brier"], "brier_lo": lo[0], "brier_hi": hi[0],
                "log_loss": point["log_loss"], "log_loss_lo": lo[1], "log_loss_hi": hi[1],
                "auc": point["auc"], "auc_lo": lo[2], "auc_hi": hi[2],
                "d_brier": point["brier"] - brier(y, preds[reference]), "d_brier_lo": lo[3], "d_brier_hi": hi[3],
                "d_log_loss": point["log_loss"] - log_loss(y, preds[reference]), "d_ll_lo": lo[4], "d_ll_hi": hi[4],
            }
        )
    return pd.DataFrame(out)


def calibration_table(y: np.ndarray, p: np.ndarray) -> pd.DataFrame:
    bins = pd.cut(p, bins=list(CALIBRATION_EDGES), include_lowest=True)
    df = pd.DataFrame({"bin": bins, "y": y, "p": p})
    g = df.groupby("bin", observed=False)
    return pd.DataFrame({"n": g.size(), "mean_predicted": g["p"].mean(), "observed_rate": g["y"].mean()})


def precision_recall(y: np.ndarray, p: np.ndarray, threshold: float) -> dict[str, float]:
    pred = p >= threshold
    tp = int(np.sum(pred & (y == 1)))
    return {
        "threshold": threshold,
        "flagged": int(pred.sum()),
        "precision": tp / pred.sum() if pred.sum() else float("nan"),
        "recall": tp / (y == 1).sum() if (y == 1).sum() else float("nan"),
    }


def best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    best, best_t = -1.0, 0.5
    for t in np.unique(np.round(p, 3)):
        pr = precision_recall(y, p, float(t))
        if pr["flagged"] == 0 or np.isnan(pr["precision"]):
            continue
        f1 = 2 * pr["precision"] * pr["recall"] / (pr["precision"] + pr["recall"]) if pr["precision"] + pr["recall"] else 0
        if f1 > best:
            best, best_t = f1, float(t)
    return best_t
