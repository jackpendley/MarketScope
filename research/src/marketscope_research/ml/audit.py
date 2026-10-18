"""Mechanical leakage audit for point-in-time features.

For a sample of (event, t) rows, every observation of that event AFTER t is perturbed (lines
shifted, quote times changed, an extra future snapshot added) and the features are rebuilt.
A point-in-time feature cannot change; any feature that does is reading the future.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

FeatureFn = Callable[[pd.DataFrame, pd.DataFrame, pd.Series], pd.DataFrame]


def _perturb_after(df: pd.DataFrame, event_id: str, t: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    out = df.copy()
    future = (out["event_id"] == event_id) & (out["observed_at"] > t)
    shifts = rng.choice([-3.0, -1.5, -0.5, 0.5, 1.5, 3.0], size=int(future.sum()))
    out.loc[future, "point"] = out.loc[future, "point"].to_numpy() + shifts
    if "bookmaker_updated_at" in out:
        out.loc[future, "bookmaker_updated_at"] = out.loc[future, "observed_at"]
    # A brand-new snapshot shortly after t, copied from t with shifted lines.
    at_t = out[(out["event_id"] == event_id) & (out["observed_at"] == t)].copy()
    if not at_t.empty:
        at_t["observed_at"] = t + pd.Timedelta(hours=1)
        at_t["point"] = at_t["point"] + 2.5
        out = pd.concat([out, at_t], ignore_index=True)
    return out


def leakage_audit(
    feature_fn: FeatureFn,
    spreads: pd.DataFrame,
    totals: pd.DataFrame,
    kickoffs: pd.Series,
    samples: int = 40,
    seed: int = 2026,
) -> dict[str, int]:
    """Return {feature: number of sampled rows where it changed}. Empty dict = audit passed."""
    base = feature_fn(spreads, totals, kickoffs)
    if base.empty:
        return {}
    rng = np.random.default_rng(seed)
    picks = base.sample(n=min(samples, len(base)), random_state=seed)
    violations: dict[str, int] = {}
    feature_cols = [c for c in base.columns if c not in ("event_id", "t")]
    for row in picks.itertuples(index=False):
        ev_s = spreads[spreads["event_id"] == row.event_id]
        ev_t = totals[totals["event_id"] == row.event_id]
        rebuilt = feature_fn(_perturb_after(ev_s, row.event_id, row.t, rng),
                             _perturb_after(ev_t, row.event_id, row.t, rng), kickoffs)
        before = base[(base["event_id"] == row.event_id) & (base["t"] == row.t)].iloc[0]
        after = rebuilt[(rebuilt["event_id"] == row.event_id) & (rebuilt["t"] == row.t)]
        if after.empty:
            violations["<row disappeared>"] = violations.get("<row disappeared>", 0) + 1
            continue
        after = after.iloc[0]
        for col in feature_cols:
            a, b = before[col], after[col]
            same = (pd.isna(a) and pd.isna(b)) or (not pd.isna(a) and not pd.isna(b) and np.isclose(float(a), float(b)))
            if not same:
                violations[col] = violations.get(col, 0) + 1
    return violations
