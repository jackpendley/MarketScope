"""Point-in-time market features for each (game, snapshot t).

Point-in-time contract: the features for (event, t) depend only on observations with
observed_at <= t. `audit.leakage_audit` checks this mechanically by perturbing everything
after t and asserting that no feature changes.

Inputs (pregame rows only, as returned by data.load_home_spreads / data.load_totals):
- spreads: event_id, observed_at, bookmaker_key, point, source, bookmaker_updated_at (HOME spreads)
- totals:  event_id, observed_at, bookmaker_key, point (OVER totals)
- kickoffs: Series event_id -> kickoff (UTC)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..consensus import MIN_CONSENSUS_BOOKS, board_quotes
from .design import KEY_NUMBERS, MAX_LEAD_HOURS, MIN_LEAD_HOURS

HOUR = pd.Timedelta(hours=1)
LAG_TOLERANCE = 3 * HOUR

# Feature columns, in a fixed order. Signed features are home-oriented (negative = toward home).
FEATURES = [
    "consensus",  # median board home spread at t
    "abs_consensus",
    "books",  # board books in the consensus at t
    "hours_to_kickoff",
    "mean_abs_dev",  # mean |book - consensus| at t
    "max_abs_dev",
    "range",  # max - min board line at t
    "outlier_dev",  # signed (book - consensus) of the most deviating book if >= 0.5, else 0
    "move_6h",  # consensus(t) - consensus(~t-6h); NaN if no snapshot in [t-9h, t-3h]
    "move_24h",  # consensus(t) - consensus(~t-24h); NaN if none in [t-27h, t-21h]
    "abs_move_6h",
    "abs_move_24h",
    "changes_48h",  # consensus changes between consecutive snapshots in (t-48h, t]
    "median_quote_age_h",  # median over board books of t - bookmaker_updated_at
    "dist_key3",  # | |consensus| - 3 |
    "dist_key7",
    "on_key",  # |consensus| is exactly 3 or 7
    "half_point",  # consensus ends in .5
    "pinnacle_dev",  # Pinnacle (reference book) - consensus at t; NaN when Pinnacle absent
    "totals_abs_move_24h",  # |totals consensus(t) - totals consensus(~t-24h)|
    "source_live",  # 1 = live collection, 0 = imported history
    "dow_et",  # weekday of t in US Eastern (0 = Monday)
]


def _snapshot_stats(board: pd.DataFrame) -> pd.DataFrame:
    """Per-snapshot statistics for ONE event, each computed from that snapshot's rows only."""
    rows = []
    for t, snap in board.groupby("observed_at", sort=True):
        if len(snap) < MIN_CONSENSUS_BOOKS:
            continue
        points = snap["point"].to_numpy(dtype=float)
        consensus = float(np.median(points))
        devs = points - consensus
        i = int(np.argmax(np.abs(devs)))
        ages = (t - snap["bookmaker_updated_at"]).dropna() / HOUR if "bookmaker_updated_at" in snap else pd.Series([], dtype=float)
        rows.append(
            {
                "observed_at": t,
                "consensus": consensus,
                "books": len(snap),
                "mean_abs_dev": float(np.mean(np.abs(devs))),
                "max_abs_dev": float(np.max(np.abs(devs))),
                "range": float(points.max() - points.min()),
                "outlier_dev": float(devs[i]) if abs(devs[i]) >= 0.5 else 0.0,
                "median_quote_age_h": float(ages.median()) if len(ages) else np.nan,
                "source_live": int((snap["source"] == "the-odds-api").any()) if "source" in snap else 0,
            }
        )
    return pd.DataFrame(rows)


def _value_near(series: pd.DataFrame, target: pd.Timestamp, column: str) -> float:
    """Value at the snapshot nearest `target` within +/- 3 h, or NaN. `series` must already be
    restricted to observed_at <= t by the caller."""
    window = series[(series["observed_at"] >= target - LAG_TOLERANCE) & (series["observed_at"] <= target + LAG_TOLERANCE)]
    if window.empty:
        return np.nan
    return float(window.iloc[(window["observed_at"] - target).abs().argsort().iloc[0]][column])


def _totals_consensus(totals: pd.DataFrame) -> pd.DataFrame:
    if totals.empty:
        return pd.DataFrame(columns=["event_id", "observed_at", "total"])
    q = board_quotes(totals)
    g = q.groupby(["event_id", "observed_at"])["point"].agg(total="median", books="count").reset_index()
    return g[g["books"] >= MIN_CONSENSUS_BOOKS][["event_id", "observed_at", "total"]]


def build_features(spreads: pd.DataFrame, totals: pd.DataFrame, kickoffs: pd.Series) -> pd.DataFrame:
    """One row per (event_id, t) for snapshots between MAX_LEAD_HOURS and MIN_LEAD_HOURS
    before kickoff that have a board consensus. Columns: event_id, t, FEATURES."""
    board = board_quotes(spreads)
    pinnacle = spreads[spreads["bookmaker_key"] == "pinnacle"][["event_id", "observed_at", "point"]]
    totals_c = _totals_consensus(totals)
    out = []
    for event_id, ev_board in board.groupby("event_id", sort=True):
        kickoff = kickoffs.get(event_id)
        if kickoff is None or pd.isna(kickoff):
            continue
        stats = _snapshot_stats(ev_board)
        if stats.empty:
            continue
        ev_pin = pinnacle[pinnacle["event_id"] == event_id]
        ev_tot = totals_c[totals_c["event_id"] == event_id]
        for row in stats.itertuples(index=False):
            t = row.observed_at
            lead = (kickoff - t) / HOUR
            if not (MIN_LEAD_HOURS <= lead <= MAX_LEAD_HOURS):
                continue
            # Everything below reads only snapshots at or before t.
            hist = stats[stats["observed_at"] <= t]
            prev_6 = _value_near(hist, t - 6 * HOUR, "consensus")
            prev_24 = _value_near(hist, t - 24 * HOUR, "consensus")
            recent = hist[hist["observed_at"] > t - 48 * HOUR]["consensus"].to_numpy()
            changes = int(np.count_nonzero(np.abs(np.diff(recent)) > 1e-9)) if len(recent) > 1 else 0
            pin_now = ev_pin[ev_pin["observed_at"] == t]["point"]
            tot_hist = ev_tot[ev_tot["observed_at"] <= t]
            tot_at_t = tot_hist[tot_hist["observed_at"] == t]["total"]
            tot_now = float(tot_at_t.iloc[0]) if len(tot_at_t) else np.nan
            tot_prev = _value_near(tot_hist, t - 24 * HOUR, "total")
            a = abs(row.consensus)
            move_6, move_24 = row.consensus - prev_6, row.consensus - prev_24
            out.append(
                {
                    "event_id": event_id,
                    "t": t,
                    "consensus": row.consensus,
                    "abs_consensus": a,
                    "books": row.books,
                    "hours_to_kickoff": lead,
                    "mean_abs_dev": row.mean_abs_dev,
                    "max_abs_dev": row.max_abs_dev,
                    "range": row.range,
                    "outlier_dev": row.outlier_dev,
                    "move_6h": move_6,
                    "move_24h": move_24,
                    "abs_move_6h": abs(move_6),
                    "abs_move_24h": abs(move_24),
                    "changes_48h": changes,
                    "median_quote_age_h": row.median_quote_age_h,
                    "dist_key3": abs(a - KEY_NUMBERS[0]),
                    "dist_key7": abs(a - KEY_NUMBERS[1]),
                    "on_key": int(a in KEY_NUMBERS),
                    "half_point": int(abs(a * 2) % 2 == 1),
                    "pinnacle_dev": float(pin_now.iloc[0]) - row.consensus if len(pin_now) else np.nan,
                    "totals_abs_move_24h": abs(tot_now - tot_prev),
                    "source_live": row.source_live,
                    "dow_et": int(t.tz_convert("America/New_York").weekday()),
                }
            )
    return pd.DataFrame(out, columns=["event_id", "t", *FEATURES])
