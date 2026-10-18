"""Fit the QB layer on 2016-22 (MS-031a): replacement level from QB debuts, a small grid over the
rating and baseline memories and the prior weight (in-sample game-layer MAE with the expected
starter). Then the final game layer with the QB feature and the non-QB availability features
(MS-031b), plus the layers the ablations need. Frozen into params.json["model"]. Run after
`ratings.fit` (which writes the unit-ratings-only layer).

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.qb_fit
"""

from __future__ import annotations

import itertools
import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from .design import BURN_IN_FROM, LIKELIHOOD_SEASONS, QB_BASELINE_HALF_LIFE_GRID, QB_HALF_LIFE_GRID, QB_PRIOR_GRID
from .engine import FEATURES, PARAMS_PATH, Engine, GameLayer, load_params
from .availability_adj import FEATURES as AVAIL_FEATURES, SNAPS_FROM, AvailabilityAdjuster, absences, load_reserve, \
    load_snaps
from .fit import load_inputs
from .qb import QBAdjuster, QBParams, expected_starters, load_depth, load_injury_status, load_qb_games, \
    replacement_level, team_games


UNIT_ONLY = "unit ratings only"
NO_QB = "no QB adjustment"
NO_AVAIL = "no availability adjustment"
ORACLE = "oracle starter (actual QB, hindsight)"


def availability_inputs(games: pd.DataFrame, last_season: int, refresh: bool | set[int] = False) -> pd.DataFrame:
    """Point-in-time expected absences per team-game (availability_adj.py)."""
    seasons = list(range(SNAPS_FROM, last_season + 1))
    g = games[games["season"] >= SNAPS_FROM]
    return absences(g, load_snaps(seasons, refresh), load_injury_status(list(range(BURN_IN_FROM, last_season + 1)), refresh),
                    load_reserve(seasons, refresh))


def qb_inputs(games: pd.DataFrame, last_season: int, refresh: bool | set[int] = False):
    """Expected starters for every team-game since BURN_IN_FROM, and QB dropbacks per game.
    `refresh` re-reads the nflverse depth charts, injury reports and play-by-play aggregates."""
    seasons = list(range(BURN_IN_FROM, last_season + 1))
    g = games[games["season"] >= BURN_IN_FROM]
    starters = expected_starters(team_games(g), load_depth(seasons, refresh), load_injury_status(seasons, refresh))
    return starters, load_qb_games(seasons, refresh)


def main() -> None:
    games, obs, teams, sf, wf = load_inputs("model")
    units, st, layer0 = load_params("model")
    alts0 = json.loads(PARAMS_PATH.read_text())["model"]["game_alternatives"]
    if UNIT_ONLY in alts0:  # a re-run: start from the unit-ratings-only layer written by ratings.fit
        layer0 = GameLayer(**alts0[UNIT_ONLY])
    last = int(games["season"].max())
    starters, qbg = qb_inputs(games, last)
    r = replacement_level(qbg, games, range(BURN_IN_FROM + 1, max(LIKELIHOOD_SEASONS) + 1))

    done = games[games["margin"].notna() & games["season"].between(BURN_IN_FROM, max(LIKELIHOOD_SEASONS))]
    slots = [(k, s) for k, s in done.groupby(["season", "week"], sort=True)]

    # Base features once (the filters do not depend on the QB layer).
    eng = Engine(teams, units, st, obs, sf, wf)
    base = []
    for (season, week), slot in slots:
        eng.begin(season, week)
        if season in LIKELIHOOD_SEASONS:
            for g in slot.itertuples(index=False):
                base.append({**eng.features(g.home, g.away, bool(g.neutral), layer0), "home": 0.0 if g.neutral else 1.0,
                             "margin": g.margin, "game_id": g.game_id})
        for g in slot.itertuples(index=False):
            eng.observe(g)
    X = pd.DataFrame(base).set_index("game_id")
    feats = [f for f in FEATURES if f in X]

    def ols(cols, frame):
        A = frame[cols + ["home"]].to_numpy(float)
        beta, *_ = np.linalg.lstsq(A, frame["margin"].to_numpy(float), rcond=None)
        resid = frame["margin"].to_numpy(float) - A @ beta
        return beta, float(np.mean(np.abs(resid)))

    def qb_features(p: QBParams, mode: str) -> pd.Series:
        adj = QBAdjuster(p, starters, qbg, layer0.n_pass, mode)
        out = {}
        for (season, _), slot in slots:
            if season in LIKELIHOOD_SEASONS:
                for g in slot.itertuples(index=False):
                    out[g.game_id] = adj.feature(g)
            adj.update(slot)
        return pd.Series(out)

    _, mae_none = ols(feats, X)
    grid = []
    for h, k, b in itertools.product(QB_HALF_LIFE_GRID, QB_PRIOR_GRID, QB_BASELINE_HALF_LIFE_GRID):
        p = QBParams(h, k, b, r)
        Xq = X.assign(qb=qb_features(p, "expected"))
        beta, mae = ols(feats + ["qb"], Xq)
        grid.append({"half_life_days": h, "prior_dropbacks": k, "baseline_half_life_days": b, "mae": mae,
                     "w_qb": float(beta[len(feats)])})
        print(grid[-1])
    grid = pd.DataFrame(grid)
    best = grid.loc[grid["mae"].idxmin()]
    p = QBParams(float(best["half_life_days"]), float(best["prior_dropbacks"]), float(best["baseline_half_life_days"]), r)

    def layer(cols, frame):
        beta, mae = ols(cols, frame)
        return GameLayer(layer0.n_pass, layer0.n_rush, layer0.n_drives, {c: float(v) for c, v in zip(cols, beta[:-1])},
                         float(beta[-1]), layer0.total_a, layer0.total_b), mae

    av = AvailabilityAdjuster(availability_inputs(games, last))
    av_rows = pd.DataFrame({gid: av.features(g) for (season, _), slot in slots if season in LIKELIHOOD_SEASONS
                            for gid, g in zip(slot["game_id"], slot.itertuples(index=False))}).T
    Xe = X.assign(qb=qb_features(p, "expected")).join(av_rows)
    Xo = X.assign(qb=qb_features(p, "oracle")).join(av_rows)
    avf = list(AVAIL_FEATURES)
    lay_m, mae_m = layer(feats + ["qb"] + avf, Xe)
    lay_q, mae_q = layer(feats + ["qb"], Xe)
    lay_a, mae_a = layer(feats + avf, Xe)
    lay_o, mae_o = layer(feats + ["qb"] + avf, Xo)

    params = json.loads(PARAMS_PATH.read_text())
    m = params["model"]
    m["game_alternatives"].update({UNIT_ONLY: asdict(layer0), NO_QB: asdict(lay_a), NO_AVAIL: asdict(lay_q),
                                   ORACLE: asdict(lay_o)})
    m["game"] = asdict(lay_m)
    m["qb"] = asdict(p)
    m["meta"]["qb"] = {"replacement": r, "in_sample_mae": {UNIT_ONLY: mae_none, NO_QB: mae_a, NO_AVAIL: mae_q,
                                                          "model": mae_m, ORACLE: mae_o},
                       "grid": grid.to_dict(orient="records")}
    PARAMS_PATH.write_text(json.dumps(params, indent=2))
    print(f"replacement {r:+.3f}; best {asdict(p)}")
    print(f"in-sample MAE: unit only {mae_none:.3f}, +QB {mae_q:.3f}, +avail {mae_a:.3f}, model {mae_m:.3f}, oracle {mae_o:.3f}")
    print("weights:", {k: round(v, 3) for k, v in lay_m.w.items()})


if __name__ == "__main__":
    main()
