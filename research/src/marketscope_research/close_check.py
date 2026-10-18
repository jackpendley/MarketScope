"""Data-quality check: nflverse closing lines vs MarketScope's last observed pregame consensus
for the same linked games (MS-026). Confirms the sign convention used on ingest and measures
agreement. "Last observed pregame" is not the closing line: for imported games it is the
kickoff-5-minute snapshot, for live games up to ~6 h before kickoff."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .consensus import MIN_CONSENSUS_BOOKS, board_quotes, consensus_series


def last_pregame(consensus: pd.DataFrame, kickoffs: pd.Series, column: str) -> pd.DataFrame:
    c = consensus.copy()
    c["kickoff"] = c["event_id"].map(kickoffs)
    c = c[c["observed_at"] < c["kickoff"]].sort_values("observed_at")
    last = c.groupby("event_id").tail(1)
    out = last[["event_id", "observed_at", column]].rename(columns={"observed_at": "last_observed_at"})
    out["minutes_before_kickoff"] = (last["kickoff"] - last["observed_at"]).dt.total_seconds().to_numpy() / 60
    return out


def totals_consensus(totals: pd.DataFrame) -> pd.DataFrame:
    q = board_quotes(totals)
    g = q.groupby(["event_id", "observed_at"])["point"].agg(total="median", books="count").reset_index()
    return g[g["books"] >= MIN_CONSENSUS_BOOKS]


def compare(games: pd.DataFrame, spreads: pd.DataFrame, totals: pd.DataFrame, kickoffs: pd.Series) -> pd.DataFrame:
    """games: event_id, game_id, nflverse_close_home_spread, nflverse_close_total."""
    s = last_pregame(consensus_series(spreads), kickoffs, "consensus")
    t = last_pregame(totals_consensus(totals), kickoffs, "total")[["event_id", "total"]]
    df = games.merge(s, on="event_id", how="inner").merge(t, on="event_id", how="left")
    df["spread_diff"] = df["consensus"] - df["nflverse_close_home_spread"]
    df["total_diff"] = df["total"] - df["nflverse_close_total"]
    df["same_favorite"] = np.sign(df["consensus"]) == np.sign(df["nflverse_close_home_spread"])
    df["source"] = df["event_id"].map(spreads.groupby("event_id")["source"].first())
    return df


def summary(df: pd.DataFrame) -> pd.DataFrame:
    def stats(g: pd.DataFrame) -> pd.Series:
        sd, td = g["spread_diff"].abs(), g["total_diff"].abs().dropna()
        return pd.Series({
            "games": len(g),
            "median_hours_before_kickoff": round(float(g["minutes_before_kickoff"].median()) / 60, 1),
            "spread_exact": float((sd < 1e-9).mean()),
            "spread_within_0.5": float((sd <= 0.5).mean()),
            "spread_within_1": float((sd <= 1.0).mean()),
            "spread_mean_abs_diff": float(sd.mean()),
            "spread_mean_signed_diff": float(g["spread_diff"].mean()),
            "same_favorite": float(g["same_favorite"].mean()),
            "spread_correlation": float(g["consensus"].corr(g["nflverse_close_home_spread"])) if len(g) >= 3 else float("nan"),
            "total_within_1": float((td <= 1.0).mean()) if len(td) else float("nan"),
            "total_mean_abs_diff": float(td.mean()) if len(td) else float("nan"),
        })
    rows = {src: stats(g) for src, g in df.groupby("source")}
    rows["all"] = stats(df)
    return pd.DataFrame(rows).T
