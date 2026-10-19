"""Research study R6 (research/PREREGISTRATION.md, addendum A): a model + market blend,
p = w * p_model + (1 - w) * p_close, with w set each week slot from the previous four slots and the
market weight never below 0.40. Research only: the displayed rating never uses market inputs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRAILING_SLOTS = 4
MAX_MODEL_WEIGHT = 0.60  # market weight at least 0.40
FIXED_MODEL_WEIGHT = 0.35  # nfelo's ~65% market weight (exploratory)
RESAMPLES = 5000
SEED = 2026


def trailing_weight(p_model: np.ndarray, p_close: np.ndarray, y: np.ndarray, cap: float = MAX_MODEL_WEIGHT) -> float:
    """The w in [0, cap] minimising the Brier of w * p_model + (1 - w) * p_close on these games."""
    d = np.asarray(p_model, float) - np.asarray(p_close, float)
    den = float(np.sum(d * d))
    if den == 0.0:
        return 0.0
    return float(np.clip(np.sum((np.asarray(p_close, float) - np.asarray(y, float)) * -d) / den, 0.0, cap))


def slot_weights(df: pd.DataFrame, trailing: int = TRAILING_SLOTS) -> pd.Series:
    """w per (season, week) slot from the games of the previous `trailing` slots in kickoff order.
    df: season, week, p_model, p_close, y. The first `trailing` slots get NaN (no full window)."""
    order = sorted(set(zip(df["season"], df["week"])))
    groups = {k: g for k, g in df.groupby(["season", "week"])}
    out = {}
    for i, slot in enumerate(order):
        if i < trailing:
            out[slot] = np.nan
            continue
        w = pd.concat([groups[s] for s in order[i - trailing:i]])
        out[slot] = trailing_weight(w["p_model"].to_numpy(), w["p_close"].to_numpy(), w["y"].to_numpy())
    return pd.Series(out, name="w")


def brier(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def log_loss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def mean_ci(v: np.ndarray, resamples: int = RESAMPLES) -> tuple[float, float, float]:
    """Mean with a 95% bootstrap interval resampling games."""
    v = np.asarray(v, float)
    boots = v[np.random.default_rng(SEED).integers(0, len(v), (resamples, len(v)))].mean(axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return float(v.mean()), float(lo), float(hi)


def r6(df: pd.DataFrame, score_seasons: set[int], resamples: int = RESAMPLES) -> dict:
    """df: season, week, game_id, p_model, p_close, y (every walk-forward game, warm-up included).
    Returns the primary paired Brier difference and the exploratory comparisons."""
    df = df.dropna(subset=["p_model", "p_close", "y"]).copy()
    w = slot_weights(df)
    df["w"] = [w[(s, k)] for s, k in zip(df["season"], df["week"])]
    s = df[df["season"].isin(score_seasons)].copy()
    if s["w"].isna().any():
        raise ValueError("a scored slot has no full trailing window; add warm-up seasons")
    s["p_blend"] = s["w"] * s["p_model"] + (1 - s["w"]) * s["p_close"]
    s["p_fixed"] = FIXED_MODEL_WEIGHT * s["p_model"] + (1 - FIXED_MODEL_WEIGHT) * s["p_close"]
    y = s["y"].to_numpy()
    close_b, close_l = brier(s["p_close"], y), log_loss(s["p_close"], y)
    rows = {}
    for name, col in (("close", "p_close"), ("model", "p_model"), ("blend (trailing w)", "p_blend"),
                      (f"blend (fixed w = {FIXED_MODEL_WEIGHT})", "p_fixed")):
        b, ll = brier(s[col], y), log_loss(s[col], y)
        rows[name] = {"brier": float(b.mean()), "log_loss": float(ll.mean()),
                      "d_brier": None if col == "p_close" else mean_ci(b - close_b, resamples),
                      "d_log_loss": None if col == "p_close" else mean_ci(ll - close_l, resamples)}
    primary = rows["blend (trailing w)"]["d_brier"]
    slot_w = s.groupby(["season", "week"])["w"].first()
    return {"games": len(s), "rows": rows, "primary": primary, "claim": primary[2] < 0,
            "w_mean": float(slot_w.mean()), "w_at_cap": int((slot_w >= MAX_MODEL_WEIGHT).sum()),
            "w_zero": int((slot_w == 0).sum()), "slots": len(slot_w), "w_by_slot": slot_w}
