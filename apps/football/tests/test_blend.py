"""R6 model + market blend on synthetic data with known answers."""

import numpy as np
import pandas as pd
import pytest

from marketscope_football.ratings import blend


def test_trailing_weight_is_the_brier_optimal_weight_clipped():
    rng = np.random.default_rng(0)
    pc, pm = rng.uniform(0.2, 0.8, 500), rng.uniform(0.2, 0.8, 500)
    y = (rng.uniform(size=500) < pc).astype(float)
    w = blend.trailing_weight(pm, pc, y, cap=1.0)
    grid = np.linspace(0, 1, 1001)
    best = grid[np.argmin([np.mean((g * pm + (1 - g) * pc - y) ** 2) for g in grid])]
    assert w == pytest.approx(best, abs=1e-3)
    truth = (rng.uniform(size=500) < pm).astype(float)  # the model is right: optimum above the cap
    assert blend.trailing_weight(pm, pc, truth) == blend.MAX_MODEL_WEIGHT
    assert blend.trailing_weight(pc, pc, y) == 0.0  # identical forecasts


def _frame(n_slots=12, per=16, model_informative=True, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_slots):
        truth = rng.uniform(0.15, 0.85, per)
        pc = np.clip(truth + rng.normal(scale=0.10, size=per), 0.02, 0.98)
        pm = np.clip(truth + rng.normal(scale=0.10, size=per), 0.02, 0.98) if model_informative else rng.uniform(0.2, 0.8, per)
        y = (rng.uniform(size=per) < truth).astype(float)
        season, week = (2022, k + 1) if k < 4 else (2023, k - 3)
        rows.append(pd.DataFrame({"season": season, "week": week, "game_id": [f"{k}-{i}" for i in range(per)],
                                  "p_model": pm, "p_close": pc, "y": y}))
    return pd.concat(rows, ignore_index=True)


def test_slot_weight_never_uses_its_own_slot():
    df = _frame()
    w = blend.slot_weights(df)
    assert w.iloc[:4].isna().all() and w.iloc[4:].notna().all()
    flipped = df.copy()
    last = (flipped["season"] == 2023) & (flipped["week"] == 8)
    flipped.loc[last, "y"] = 1 - flipped.loc[last, "y"]
    assert blend.slot_weights(flipped)[(2023, 8)] == w[(2023, 8)]


def test_r6_blend_of_two_independent_noisy_forecasts_beats_either():
    r = blend.r6(_frame(n_slots=60, per=16, seed=2), {2023}, resamples=500)
    assert r["games"] == 56 * 16
    assert r["rows"]["blend (trailing w)"]["brier"] < r["rows"]["close"]["brier"]
    assert r["w_mean"] > 0.2
    noise = blend.r6(_frame(n_slots=60, per=16, model_informative=False, seed=3), {2023}, resamples=500)
    # A 64-game window still fits some weight to pure noise; it costs Brier rather than helping.
    assert noise["w_mean"] < r["w_mean"] / 2 and not noise["claim"]
    assert noise["rows"]["blend (trailing w)"]["d_brier"][0] > 0
