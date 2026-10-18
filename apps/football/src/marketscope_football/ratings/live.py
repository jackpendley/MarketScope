"""ratings-v1 as a running model (MS-032b): replay every completed game through the full model
(unit filters, QB layer, availability, key-number win probabilities) and estimate upcoming games.
Used by `ingest predictions` (the live forward test) and by the one-time 2025 test."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .availability_adj import AvailabilityAdjuster
from .design import BURN_IN_FROM
from .engine import PARAMS_PATH, UNIT_CHANNELS, KalmanRatings, load_params
from .fit import load_inputs
from .margin_dist import MarginDistribution
from .outputs import complete_slots
from .qb import QBAdjuster, QBParams
from .qb_fit import availability_inputs, qb_inputs

RATING_FEATURES = (*UNIT_CHANNELS, "st")


def build_model(games: pd.DataFrame, sigma: float, refresh: bool | set[int] = False, name: str = "ratings-v1") -> tuple:
    """A fresh ratings-v1 KalmanRatings plus its expected-starter table. `refresh` re-reads the
    nflverse depth charts, injury reports, snaps and rosters for those seasons."""
    _, obs, teams, sf, wf = load_inputs("model")
    units, st, layer = load_params("model")
    p = json.loads(PARAMS_PATH.read_text())["model"]
    last = int(games["season"].max())
    starters, qbg = qb_inputs(games, last, refresh)
    md = p["margin_dist"]
    dist = MarginDistribution(md["scale"], md["weights"]) if md["adopted"] else None
    model = KalmanRatings(name, teams, (units, st, layer), obs, sf, wf, sigma,
                          qb=QBAdjuster(QBParams(**p["qb"]), starters, qbg, layer.n_pass),
                          avail=AvailabilityAdjuster(availability_inputs(games, last, refresh)), dist=dist)
    return model, starters, obs


def replay(model: KalmanRatings, games: pd.DataFrame, obs: pd.DataFrame) -> tuple[int, int]:
    """Update the model with every completed game whose week has play-by-play; returns the last slot."""
    done = complete_slots(games[games["margin"].notna() & (games["season"] >= BURN_IN_FROM)], obs)
    last = (0, 0)
    for (season, week), slot in done.groupby(["season", "week"], sort=True):
        model.update(slot)
        last = (season, week)
    return last


def estimates(model: KalmanRatings, upcoming: pd.DataFrame, starters: pd.DataFrame) -> pd.DataFrame:
    """Model estimates for upcoming games (already-observed state), with the additive contributions."""
    layer = model.layer
    st = starters.set_index(["game_id", "team"])
    rows = []
    for (season, week), slot in upcoming.groupby(["season", "week"], sort=True):
        pred = model.predict(slot)
        for g, (_, pr) in zip(slot.itertuples(index=False), pred.iterrows()):
            f = model._features(g)
            contrib = {
                "ratings": float(sum(layer.w[k] * f[k] for k in RATING_FEATURES if k in layer.w)),
                "home": 0.0 if g.neutral else float(layer.c),
                "qb": float(layer.w.get("qb", 0.0) * f.get("qb", 0.0)),
                "absences": float(sum(layer.w[k] * f[k] for k in layer.w if k.startswith("avail_"))),
            }
            assert abs(sum(contrib.values()) - pr["margin"]) < 1e-6
            total = pr.get("total")
            hq, aq = st.loc[(g.game_id, g.home)], st.loc[(g.game_id, g.away)]
            rows.append({
                "game_id": g.game_id, "kickoff_utc": g.kickoff_utc, "home_team": g.home, "away_team": g.away,
                "expected_margin": float(pr["margin"]), "p_home": float(pr["p_home"]),
                "expected_total": None if total is None or pd.isna(total) else float(total),
                "home_score": None if total is None or pd.isna(total) else float((total + pr["margin"]) / 2),
                "away_score": None if total is None or pd.isna(total) else float((total - pr["margin"]) / 2),
                "home_qb": hq["exp_qb"], "away_qb": aq["exp_qb"], "home_qb_p": float(hq["p_exp"]),
                "away_qb_p": float(aq["p_exp"]), "contributions": {k: round(v, 4) for k, v in contrib.items()},
            })
    return pd.DataFrame(rows)
