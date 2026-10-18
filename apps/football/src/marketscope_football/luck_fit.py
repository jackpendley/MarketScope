"""Estimate the league constants behind the luck adjustment and the field-goal make model.

Fit ONLY on the 2016-2022 fitting seasons (docs/RATINGS.md validation protocol), then frozen
in design.py. Re-running reproduces the committed values:

    PYTHONPATH=src .venv/bin/python -m marketscope_football.luck_fit
"""

from __future__ import annotations

import numpy as np
import polars as pl

from .design import FIT_SEASONS
from .pbp import load_season
from .team_stats import own_fumble, scrimmage


def fumble_constants(pbp: pl.DataFrame) -> dict:
    f = scrimmage(pbp).filter(own_fumble())
    lost = f.filter(pl.col("fumble_lost") == 1)["epa"]
    kept = f.filter(pl.col("fumble_lost") == 0)["epa"]
    return {"n": f.height, "p_lost": lost.len() / f.height, "epa_lost": lost.mean(), "epa_recovered": kept.mean()}


def interception_constants(pbp: pl.DataFrame) -> dict:
    pd_ = scrimmage(pbp).filter((pl.col("pass") == 1) & pl.col("pass_defense_1_player_id").is_not_null())
    ints = pd_.filter(pl.col("interception") == 1)["epa"]
    rest = pd_.filter(pl.col("interception") == 0)["epa"]
    return {"n": pd_.height, "p_int": ints.len() / pd_.height, "epa_int": ints.mean(), "epa_defensed": rest.mean()}


def logistic_fit(x: np.ndarray, y: np.ndarray, iters: int = 50) -> tuple[float, float]:
    """Unregularized 1-D logistic regression by Newton's method: P(y=1) = 1/(1+exp(-(a+b·x)))."""
    X = np.column_stack([np.ones_like(x), x])
    beta = np.zeros(2)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ beta))
        grad = X.T @ (y - p)
        hess = (X * (p * (1 - p))[:, None]).T @ X
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    return float(beta[0]), float(beta[1])


def fg_constants(pbp: pl.DataFrame) -> dict:
    fg = pbp.filter((pl.col("field_goal_attempt") == 1) & pl.col("kick_distance").is_not_null())
    a, b = logistic_fit(fg["kick_distance"].to_numpy().astype(float),
                        (fg["field_goal_result"] == "made").to_numpy().astype(float))
    return {"n": fg.height, "intercept": a, "slope": b}


def main() -> None:
    pbp = pl.concat([load_season(s) for s in FIT_SEASONS])
    print(f"seasons {FIT_SEASONS[0]}-{FIT_SEASONS[-1]}: {pbp.height} plays")
    for name, fn in (("fumbles", fumble_constants), ("interceptions", interception_constants), ("field goals", fg_constants)):
        print(name, {k: round(v, 4) if isinstance(v, float) else v for k, v in fn(pbp).items()})


if __name__ == "__main__":
    main()
