"""Join point-in-time features with labels, NFL week and split."""

from __future__ import annotations

import pandas as pd

from .design import nfl_week, split_for_week
from .features import build_features
from .labels import label_moves


def build_dataset(spreads: pd.DataFrame, totals: pd.DataFrame, kickoffs: pd.Series) -> pd.DataFrame:
    feats = build_features(spreads, totals, kickoffs)
    if feats.empty:
        return feats.assign(week=pd.Series(dtype=int), split=pd.Series(dtype=str))
    labels = label_moves(spreads, kickoffs, feats[["event_id", "t"]])
    df = feats.merge(labels, on=["event_id", "t"], how="left", validate="one_to_one")
    weeks = nfl_week(pd.to_datetime(df["event_id"].map(kickoffs), utc=True))
    df["week"] = weeks
    df["split"] = weeks.map(split_for_week)
    df["source"] = df["event_id"].map(spreads.groupby("event_id")["source"].first())
    return df
