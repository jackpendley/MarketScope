"""Candidate game factors for MS-032 (selection_design.py), computed point-in-time from the nflverse
schedule, the venue catalog and the coaching staff table via context.team_game_context, and the
feature matrix of the MS-031 model's walk-forward predictions (so each candidate is tested by
refitting only the linear game layer: exactly what the harness would do, much faster)."""

from __future__ import annotations

import csv

import numpy as np
import pandas as pd

from .. import venues
from ..context import team_game_context
from ..schedules import FRANCHISE, kickoff_utc
from .engine import KalmanRatings
from .observations import STAFF_CSV
from .selection_design import EARLY_BODY_CLOCK_HOUR, NEW_HC_GAMES, NEW_OC_GAMES


def context_rows(schedules: pd.DataFrame, from_season: int = 2016) -> pd.DataFrame:
    """nfl_game_context-equivalent rows (team-game) from the raw nflverse schedule."""
    s = schedules[schedules["season"] >= from_season].copy()
    alias, fixed = venues.aliases(), venues.overrides()
    unknown = sorted(set(s["stadium"].dropna()) - set(alias))
    if unknown:
        raise SystemExit(f"stadiums missing from data/venue_aliases.csv: {unknown}")
    games = pd.DataFrame({
        "game_id": s["game_id"], "season": s["season"], "week": s["week"],
        "kickoff_utc": [kickoff_utc(d, None if pd.isna(t) else t) for d, t in zip(s["gameday"], s["gametime"])],
        "home_team": s["home_team"], "away_team": s["away_team"], "neutral_site": s["location"].eq("Neutral"),
        "division_game": s["div_game"].fillna(0).astype(bool), "home_rest_days": s["home_rest"], "away_rest_days": s["away_rest"],
        "venue_key": s["game_id"].map(fixed).fillna(s["stadium"].map(alias)),
    })
    prior = schedules[schedules["season"] < from_season]
    prior_hc = pd.concat([
        prior[["gameday", "home_team", "home_coach"]].set_axis(["kickoff_utc", "team", "coach"], axis=1),
        prior[["gameday", "away_team", "away_coach"]].set_axis(["kickoff_utc", "team", "coach"], axis=1),
    ]).dropna()
    prior_hc["kickoff_utc"] = pd.to_datetime(prior_hc["kickoff_utc"], utc=True)
    staff = list(csv.DictReader(STAFF_CSV.read_text().splitlines()))
    ctx = team_game_context(games, venues.venues(), staff, prior_hc)
    ctx["team"] = ctx["team"].map(lambda t: FRANCHISE.get(t, t))
    return ctx


def candidate_features(ctx: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """One row per game_id with every candidate feature (home minus away unless stated)."""
    c = ctx.set_index(["game_id", "team"])
    g = games.set_index("game_id")
    idx = [gid for gid in g.index if (gid, g.at[gid, "home"]) in c.index and (gid, g.at[gid, "away"]) in c.index]
    h = c.loc[[(gid, g.at[gid, "home"]) for gid in idx]].reset_index(drop=True)
    a = c.loc[[(gid, g.at[gid, "away"]) for gid in idx]].reset_index(drop=True)
    gg = g.loc[idx].reset_index()
    home = (~gg["neutral"]).astype(float).to_numpy()

    def new(tenure, n):
        return (pd.to_numeric(tenure, errors="coerce") < n).astype(float).fillna(0.0).to_numpy()

    out = pd.DataFrame({
        "game_id": idx,
        "rest_diff": (h["rest_diff"].astype(float).clip(-7, 7)).fillna(0.0).to_numpy(),
        "bye_diff": h["bye_before"].astype(float).fillna(0).to_numpy() - a["bye_before"].astype(float).fillna(0).to_numpy(),
        "travel_diff": (a["travel_km"].to_numpy() - h["travel_km"].to_numpy()) / 1000,
        "tz_diff": a["tz_shift_hours"].abs().to_numpy() - h["tz_shift_hours"].abs().to_numpy(),
        "body_clock_diff": (a["body_clock_kickoff_hour"] < EARLY_BODY_CLOCK_HOUR).astype(float).to_numpy()
        - (h["body_clock_kickoff_hour"] < EARLY_BODY_CLOCK_HOUR).astype(float).to_numpy(),
        "altitude_diff": (a["altitude_change_m"].to_numpy() - h["altitude_change_m"].to_numpy()) / 1000,
        "division_home": gg["division"].astype(float).to_numpy() * home,
        "playoff_home": (gg["game_type"] != "REG").astype(float).to_numpy() * home,
        "new_hc_diff": new(h["hc_tenure_games"], NEW_HC_GAMES) - new(a["hc_tenure_games"], NEW_HC_GAMES),
        "new_oc_diff": new(h["off_playcaller_tenure_games"], NEW_OC_GAMES) - new(a["off_playcaller_tenure_games"], NEW_OC_GAMES),
    })
    return out


class RecordingKalman(KalmanRatings):
    """KalmanRatings that keeps the pre-game feature vector of every game it predicts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows: list[dict] = []

    def predict(self, games: pd.DataFrame) -> pd.DataFrame:
        out = super().predict(games)
        for g in games.itertuples(index=False):
            self.rows.append({"game_id": g.game_id, **self._features(g), "home": 0.0 if g.neutral else 1.0})
        return out


class FactorTable:
    """Game factors for the walk-forward model (known before kickoff: schedule, venues, staff)."""

    def __init__(self, table: pd.DataFrame, names: list[str]):
        self.names = list(names)
        self.t = table.set_index("game_id")[self.names].to_dict("index")

    def features(self, g) -> dict[str, float]:
        return self.t.get(g.game_id, dict.fromkeys(self.names, 0.0))
