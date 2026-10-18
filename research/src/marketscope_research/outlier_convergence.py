"""Study: does a book's divergence from consensus predict the consensus moving toward it
within 24 hours? (ROADMAP MS-021, spec section 15.)

Pre-registered design (fixed before looking at results):
- Events: book_divergence v1 onsets (point-in-time: computed only from the snapshot at t).
- Outcome: the consensus at the snapshot nearest t + 24h within [t + 18h, t + 30h], pregame,
  with >= 3 books. "toward" if it moved in the direction of the book's deviation,
  "away" if opposite, "none" if unchanged. Events without such a snapshot are excluded
  (counted, never imputed).
- Baselines: the unconditional rate of ANY consensus move at the same horizon across all
  eligible snapshots, and "toward by chance" = half of that (direction symmetric).
- Inference: 95% bootstrap CI resampling GAMES (events within a game are correlated).
- Minimum sample: >= 30 events from >= 15 games, else the result is reported inconclusive.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HORIZON_HOURS = 24
TOLERANCE_HOURS = 6
MIN_EVENTS = 30
MIN_GAMES = 15
BOOTSTRAP_RESAMPLES = 5000


def label_outcomes(events: pd.DataFrame, consensus: pd.DataFrame, kickoffs: pd.Series) -> pd.DataFrame:
    """Attach the horizon consensus and an outcome label to each divergence event.

    events: event_id, detected_at, value (book minus consensus at t), consensus (at t).
    consensus: event_id, observed_at, consensus, books (from consensus_series).
    kickoffs: event_id -> commence time (only pregame horizon snapshots count).
    """
    rows = []
    by_event = {eid: g.sort_values("observed_at") for eid, g in consensus.groupby("event_id")}
    for ev in events.itertuples(index=False):
        series = by_event.get(ev.event_id)
        horizon = None
        if series is not None:
            target = ev.detected_at + pd.Timedelta(hours=HORIZON_HOURS)
            window = series[
                (series["observed_at"] >= target - pd.Timedelta(hours=TOLERANCE_HOURS))
                & (series["observed_at"] <= target + pd.Timedelta(hours=TOLERANCE_HOURS))
                & (series["observed_at"] < kickoffs.get(ev.event_id, pd.Timestamp.max.tz_localize("UTC")))
            ]
            if not window.empty:
                horizon = window.iloc[(window["observed_at"] - target).abs().argsort().iloc[0]]
        if horizon is None:
            rows.append({**ev._asdict(), "horizon_at": pd.NaT, "horizon_consensus": np.nan, "outcome": "no_horizon"})
            continue
        move = float(horizon["consensus"]) - float(ev.consensus)
        if abs(move) < 1e-9:
            outcome = "none"
        elif np.sign(move) == np.sign(ev.value):
            outcome = "toward"
        else:
            outcome = "away"
        rows.append(
            {
                **ev._asdict(),
                "horizon_at": horizon["observed_at"],
                "horizon_consensus": float(horizon["consensus"]),
                "outcome": outcome,
            }
        )
    return pd.DataFrame(rows)


def unconditional_move_rate(consensus: pd.DataFrame, kickoffs: pd.Series) -> tuple[float, int]:
    """Share of eligible snapshots whose consensus changed by the horizon (any direction)."""
    moved, eligible = 0, 0
    for eid, g in consensus.groupby("event_id"):
        g = g.sort_values("observed_at")
        kickoff = kickoffs.get(eid, pd.Timestamp.max.tz_localize("UTC"))
        for row in g.itertuples(index=False):
            target = row.observed_at + pd.Timedelta(hours=HORIZON_HOURS)
            window = g[
                (g["observed_at"] >= target - pd.Timedelta(hours=TOLERANCE_HOURS))
                & (g["observed_at"] <= target + pd.Timedelta(hours=TOLERANCE_HOURS))
                & (g["observed_at"] < kickoff)
            ]
            if window.empty:
                continue
            horizon = window.iloc[(window["observed_at"] - target).abs().argsort().iloc[0]]
            eligible += 1
            moved += int(abs(float(horizon["consensus"]) - float(row.consensus)) > 1e-9)
    return (moved / eligible if eligible else float("nan")), eligible


def game_clustered_ci(labelled: pd.DataFrame, seed: int = 2026) -> tuple[float, float]:
    """95% bootstrap CI for the 'toward' rate, resampling games with replacement."""
    scored = labelled[labelled["outcome"] != "no_horizon"]
    games = scored["event_id"].unique()
    if len(games) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    per_game = {g: (scored["event_id"] == g) for g in games}
    rates = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = rng.choice(games, size=len(games), replace=True)
        mask = np.concatenate([np.flatnonzero(per_game[g]) for g in sample])
        subset = scored.iloc[mask]
        rates.append((subset["outcome"] == "toward").mean())
    lo, hi = np.percentile(rates, [2.5, 97.5])
    return float(lo), float(hi)


@dataclass
class StudyResult:
    events_total: int
    events_scored: int
    games_scored: int
    toward: int
    away: int
    none: int
    toward_rate: float
    ci: tuple[float, float]
    any_move_rate: float
    baseline_eligible: int
    chance_toward_rate: float
    conclusive: bool


def summarize(labelled: pd.DataFrame, any_move_rate: float, baseline_eligible: int) -> StudyResult:
    scored = labelled[labelled["outcome"] != "no_horizon"]
    counts = scored["outcome"].value_counts()
    games = scored["event_id"].nunique()
    return StudyResult(
        events_total=len(labelled),
        events_scored=len(scored),
        games_scored=games,
        toward=int(counts.get("toward", 0)),
        away=int(counts.get("away", 0)),
        none=int(counts.get("none", 0)),
        toward_rate=float((scored["outcome"] == "toward").mean()) if len(scored) else float("nan"),
        ci=game_clustered_ci(labelled),
        any_move_rate=any_move_rate,
        baseline_eligible=baseline_eligible,
        chance_toward_rate=any_move_rate / 2 if any_move_rate == any_move_rate else float("nan"),
        conclusive=len(scored) >= MIN_EVENTS and games >= MIN_GAMES,
    )


# ---- Exploratory robustness checks (added after v1 results; NOT pre-registered) ---------------


def toward_share_among_moved(labelled: pd.DataFrame, seed: int = 2026) -> tuple[float, tuple[float, float], int]:
    """Among events where the consensus moved, the share that moved toward the book, with a
    game-clustered 95% bootstrap CI. Under "divergence carries no directional information"
    the share is 50%. This conditions away the confound that divergences occur while
    markets are already moving, which inflates the unconditional chance baseline."""
    moved = labelled[labelled["outcome"].isin(["toward", "away"])].reset_index(drop=True)
    if moved.empty:
        return float("nan"), (float("nan"), float("nan")), 0
    share = float((moved["outcome"] == "toward").mean())
    games = moved["event_id"].unique()
    if len(games) < 2:
        return share, (float("nan"), float("nan")), len(moved)
    rng = np.random.default_rng(seed)
    idx = {g: np.flatnonzero(moved["event_id"].to_numpy() == g) for g in games}
    shares = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        rows = np.concatenate([idx[g] for g in rng.choice(games, size=len(games), replace=True)])
        shares.append(float((moved.iloc[rows]["outcome"] == "toward").mean()))
    lo, hi = np.percentile(shares, [2.5, 97.5])
    return share, (float(lo), float(hi)), len(moved)


def breakdown(labelled: pd.DataFrame, by: str) -> pd.DataFrame:
    """Outcome counts and rates per group (e.g. source or bookmaker), scored events only."""
    scored = labelled[labelled["outcome"] != "no_horizon"]
    table = scored.pivot_table(index=by, columns="outcome", values="event_id", aggfunc="count", fill_value=0)
    for col in ("toward", "away", "none"):
        if col not in table:
            table[col] = 0
    table["events"] = table[["toward", "away", "none"]].sum(axis=1)
    table["games"] = scored.groupby(by)["event_id"].nunique()
    table["toward_rate"] = table["toward"] / table["events"]
    moved = table["toward"] + table["away"]
    table["toward_share_of_moves"] = (table["toward"] / moved).where(moved > 0)
    return table[["events", "games", "toward", "away", "none", "toward_rate", "toward_share_of_moves"]].sort_values(
        "events", ascending=False
    )
