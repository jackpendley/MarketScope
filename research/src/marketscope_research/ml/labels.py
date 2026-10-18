"""Targets for the market-movement model. Labels look into the future by definition, so they
live apart from the features; `dataset.build_dataset` joins the two."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..consensus import consensus_series
from .design import HORIZON_HOURS, MOVE_THRESHOLD, TOLERANCE_HOURS


def label_moves(spreads: pd.DataFrame, kickoffs: pd.Series, times: pd.DataFrame) -> pd.DataFrame:
    """For each (event_id, t) in `times`, find the pregame consensus nearest t + 24 h within
    +/- 3 h. Missing when there is none (never imputed).

    Returns event_id, t, future_at, future_consensus, delta, moved (0/1/NaN), direction
    ("home" if the home spread decreased, i.e. moved toward the home side; "away"; or NaN).
    """
    cons = consensus_series(spreads)
    by_event = {e: g.sort_values("observed_at") for e, g in cons.groupby("event_id")}
    horizon, tol = pd.Timedelta(hours=HORIZON_HOURS), pd.Timedelta(hours=TOLERANCE_HOURS)
    rows = []
    for r in times.itertuples(index=False):
        series = by_event.get(r.event_id)
        now = series[series["observed_at"] == r.t] if series is not None else None
        kickoff = kickoffs.get(r.event_id)
        result = {"event_id": r.event_id, "t": r.t, "future_at": pd.NaT, "future_consensus": np.nan,
                  "delta": np.nan, "moved": np.nan, "direction": None}
        if series is not None and now is not None and not now.empty and kickoff is not None:
            target = r.t + horizon
            window = series[(series["observed_at"] >= target - tol) & (series["observed_at"] <= target + tol)
                            & (series["observed_at"] < kickoff)]
            if not window.empty:
                fut = window.iloc[(window["observed_at"] - target).abs().argsort().iloc[0]]
                delta = float(fut["consensus"]) - float(now["consensus"].iloc[0])
                moved = abs(delta) >= MOVE_THRESHOLD - 1e-9
                result.update(future_at=fut["observed_at"], future_consensus=float(fut["consensus"]), delta=delta,
                              moved=float(moved), direction=("home" if delta < 0 else "away") if moved else None)
        rows.append(result)
    return pd.DataFrame(rows)
