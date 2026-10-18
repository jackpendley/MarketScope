"""Maximum-likelihood fit of the filter parameters (2016-22 only) and of the game layer, frozen
into params.json. Reproducible:

    PYTHONPATH=src .venv/bin/python -m marketscope_football.ratings.fit [--variants all] [--report reports/kalman-fit.md]
"""

from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..eval.data import games_frame, load_schedules
from .design import BURN_IN_FROM, LIKELIHOOD_SEASONS, NO_CONTINUITY, VARIANTS
from .engine import FEATURES, PARAMS_PATH, UNIT_CHANNELS, Engine, GameLayer, channel_events, continuity
from .kalman import PaceFilter, PaceParams, STFilter, STParams, UnitFilter, UnitParams
from .observations import load_observations, playcallers

# Starting values and the transform of each parameter (log: variances; logit: rho; none: hfa).
UNIT_START = dict(sigma2=2.0, q_week_off=1e-4, q_week_def=1e-4, q_season_off=3e-3, q_season_def=3e-3,
                  rho_off_same=0.6, rho_off_changed=0.5, rho_def_same=0.5, rho_def_changed=0.4, hfa=0.03,
                  q_week_mean=1e-6, q_season_mean=1e-4, bump_off=1e-3, bump_def=1e-3)
SUCC_START = dict(UNIT_START, sigma2=0.25, q_week_off=2e-5, q_week_def=2e-5, q_season_off=4e-4, q_season_def=4e-4,
                  hfa=0.005, q_week_mean=1e-7, q_season_mean=1e-5, bump_off=2e-4, bump_def=2e-4)
PPD_START = dict(UNIT_START, sigma2=6.0, q_week_off=1e-3, q_week_def=1e-3, q_season_off=0.03, q_season_def=0.03,
                 hfa=0.1, q_week_mean=1e-5, q_season_mean=1e-3, bump_off=0.01, bump_def=0.01)
ST_START = dict(sigma2=16.0, q_week=0.01, q_season=0.5, rho=0.4, hfa=0.3)
PACE_START = dict(sigma2=1.0, q_week=1e-3, q_season=0.05, rho=0.5, q_week_mean=1e-3, q_season_mean=0.05)
STARTS = {"pass": UNIT_START, "rush": UNIT_START, "succ": SUCC_START, "ppd": PPD_START, "st": ST_START,
          "pace": PACE_START}
CLASSES = {"st": (STFilter, STParams), "pace": (PaceFilter, PaceParams)}


def _kind(name: str) -> str:
    return "logit" if name.startswith("rho") else "none" if name == "hfa" else "log"


def encode(p: dict) -> np.ndarray:
    return np.array([math.log(v) if _kind(k) == "log" else math.log(v / (1 - v)) if _kind(k) == "logit" else v
                     for k, v in p.items()])


def decode(names: list[str], z: np.ndarray) -> dict:
    return {k: math.exp(v) if _kind(k) == "log" else 1 / (1 + math.exp(-v)) if _kind(k) == "logit" else float(v)
            for k, v in zip(names, z)}


def replay(events: list[tuple], filt) -> tuple[float, int]:
    """Log likelihood of the LIKELIHOOD_SEASONS observations (burn-in seasons excluded)."""
    ll, n = 0.0, 0
    for e in events:
        if e[0] == "advance":
            filt.advance(*e[1:])
        else:
            v = filt.observe(*e[2:])
            if e[1] in LIKELIHOOD_SEASONS:
                ll, n = ll + v, n + 1
    return ll, n


def fit_channel(events: list[tuple], channel: str, teams: list[str], start: dict | None = None,
                maxiter: int = 300) -> tuple[dict, dict]:
    start = start or STARTS[channel]
    names = list(start)
    cls, pcls = CLASSES.get(channel, (UnitFilter, UnitParams))

    def nll(z):
        try:
            return -replay(events, cls(pcls(**decode(names, z)), teams))[0]
        except (ValueError, OverflowError, np.linalg.LinAlgError):
            return 1e12

    t0 = time.time()
    res = minimize(nll, encode(start), method="L-BFGS-B", options={"maxiter": maxiter})
    p = decode(names, res.x)
    ll, n = replay(events, cls(pcls(**p), teams))
    return p, {"loglik": ll, "observations": n, "converged": bool(res.success), "message": str(res.message),
               "iterations": int(res.nit), "seconds": round(time.time() - t0, 1)}


# Channel ablations: the same filters, a game layer refitted without some channels.
GAME_LAYER_ABLATIONS = {
    "no success-rate channel": ["pass", "rush", "ppd", "st"],
    "no points-per-drive channel": ["pass", "rush", "succ", "st"],
    "EPA channels only (pass, rush, special teams)": ["pass", "rush", "st"],
    "no special-teams channel": ["pass", "rush", "succ", "ppd"],
    "points per drive + special teams only": ["ppd", "st"],
}


def fit_game_layer(games, obs, teams, units, st_p, season_flags, week_flags) -> tuple[GameLayer, dict, dict]:
    """OLS of actual margin on the filter's pre-week expected features over LIKELIHOOD_SEASONS.
    Also fits the layers of the channel ablations (same filters, fewer features)."""
    fit_obs = obs[obs["game_id"].isin(games.loc[games["season"].isin(LIKELIHOOD_SEASONS), "game_id"])]
    n_pass, n_rush = float(fit_obs["pass_plays"].mean()), float(fit_obs["rush_plays"].mean())
    n_drives = float(fit_obs["drives"].mean())
    eng = Engine(teams, units, st_p, obs, season_flags, week_flags)
    done = games[games["margin"].notna() & games["season"].between(BURN_IN_FROM, max(LIKELIHOOD_SEASONS))]
    rows = []
    for (season, week), slot in done.groupby(["season", "week"], sort=True):
        eng.begin(season, week)
        if season in LIKELIHOOD_SEASONS:
            for g in slot.itertuples(index=False):
                f = eng.features(g.home, g.away, bool(g.neutral), n_pass=n_pass, n_rush=n_rush, n_drives=n_drives)
                rows.append({**f, "home": 0.0 if g.neutral else 1.0, "margin": g.margin, "total": g.total,
                             "raw_total": eng.raw_total(g.home, g.away, bool(g.neutral))})
        for g in slot.itertuples(index=False):
            eng.observe(g)
    X = pd.DataFrame(rows)
    X["net_epa"] = X["pass"] + X["rush"] + X["st"]

    def ols(cols):
        beta, *_ = np.linalg.lstsq(X[cols + ["home"]].to_numpy(), X["margin"].to_numpy(), rcond=None)
        resid = X["margin"].to_numpy() - X[cols + ["home"]].to_numpy() @ beta
        return beta, {"mae": float(np.mean(np.abs(resid))), "rmse": float(np.sqrt(np.mean(resid ** 2)))}

    def layer(cols):
        beta, m = ols(cols)
        return GameLayer(n_pass, n_rush, n_drives, {f: float(b) for f, b in zip(cols, beta[:-1])}, float(beta[-1])), m

    feats = [f for f in FEATURES if f in X]
    chosen, m = layer(feats)
    if X["raw_total"].notna().all():
        A = np.column_stack([np.ones(len(X)), X["raw_total"].to_numpy(float)])
        (ta, tb), *_ = np.linalg.lstsq(A, X["total"].to_numpy(float), rcond=None)
        chosen.total_a, chosen.total_b = float(ta), float(tb)
        m["total_mae"] = float(np.mean(np.abs(X["total"] - (ta + tb * X["raw_total"]))))
    alternatives = {name: layer(cols) for name, cols in GAME_LAYER_ABLATIONS.items()}
    meta = {"games": len(X), **m, "alternatives": {k: v[1] for k, v in alternatives.items()},
            "one EPA coefficient (pass + rush + st)": ols(["net_epa"])[1]}
    return chosen, {k: asdict(v[0]) for k, v in alternatives.items()}, meta


def load_inputs(variant: str, continuity_on: bool = True, refresh: bool = False):
    """Games, filter observations, teams and play-caller continuity. `refresh` re-reads the
    schedule and rebuilds the observations from the (already refreshed) play-by-play cache."""
    last = date.today().year if date.today().month >= 3 else date.today().year - 1
    games = games_frame(load_schedules(last, refresh))
    obs = load_observations(list(range(BURN_IN_FROM, last + 1)), variant, refresh)
    teams = sorted(set(games.loc[games["season"] >= BURN_IN_FROM, "home"]))
    season_flags, week_flags = continuity(games[games["season"] >= BURN_IN_FROM], playcallers())
    if not continuity_on:  # ablation: every unit reverts alike and no mid-season bumps
        season_flags, week_flags = {}, {}
    return games, obs, teams, season_flags, week_flags


def _fit_one(args) -> tuple[str, dict, dict]:
    variant, ch, continuity_on, start, maxiter = args
    games, obs, teams, sf, wf = load_inputs(variant, continuity_on)
    p, meta = fit_channel(channel_events(games, obs, sf, wf, ch, max(LIKELIHOOD_SEASONS)), ch, teams, start, maxiter)
    return ch, p, meta


def fit_variant(variant: str, previous: dict | None = None, channels: tuple[str, ...] | None = None) -> dict:
    """Fits the channels in parallel processes (each replays its own filter). With `previous`
    (refine), only channels that stopped at the iteration limit are refitted, warm-started from
    their stored values with a higher limit; with `channels`, only those are refitted (cold start).
    Pace is fitted for the model variant only (it feeds totals and AdjPace, not the margin)."""
    continuity_on = variant != NO_CONTINUITY
    measure = "model" if variant == NO_CONTINUITY else variant
    games, obs, teams, sf, wf = load_inputs(measure, continuity_on)
    out, meta = {}, {}
    jobs = []
    for ch in (*UNIT_CHANNELS, "st", *(["pace"] if variant == "model" else [])):
        if previous and ch in previous and (channels and ch not in channels):
            out[ch], meta[ch] = previous[ch], previous["meta"][ch]
        elif previous and ch in previous and not channels and previous["meta"][ch]["converged"]:
            out[ch], meta[ch] = previous[ch], previous["meta"][ch]
        else:
            warm = previous.get(ch) if previous and not channels else None
            jobs.append((measure, ch, continuity_on, warm, 1500 if warm else 300))
    with ProcessPoolExecutor(max_workers=len(UNIT_CHANNELS) + 1) as pool:
        for ch, p, m in pool.map(_fit_one, jobs):
            out[ch], meta[ch] = p, m
            print(f"  {variant} / {ch}: loglik {m['loglik']:.1f} ({m['seconds']} s, {m['message']})")
    units = {ch: UnitParams(**out[ch]) for ch in UNIT_CHANNELS}
    if "pace" in out:
        units["pace"] = PaceParams(**out["pace"])
    layer, alternatives, meta["game"] = fit_game_layer(games, obs, teams, units, STParams(**out["st"]), sf, wf)
    out["game"] = asdict(layer)
    out["game_alternatives"] = alternatives
    out["meta"] = meta
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="model", help="'all' or comma-separated names from design.VARIANTS")
    ap.add_argument("--refine", action="store_true", help="refit only channels that hit the iteration limit")
    ap.add_argument("--channels", help="refit only these channels (comma-separated), keeping the rest")
    args = ap.parse_args()
    names = [*VARIANTS, NO_CONTINUITY] if args.variants == "all" else args.variants.split(",")
    params = json.loads(PARAMS_PATH.read_text()) if PARAMS_PATH.exists() else {}
    for v in names:
        channels = tuple(args.channels.split(",")) if args.channels else None
        if args.refine and v in params and all(params[v]["meta"][c]["converged"] for c in (*UNIT_CHANNELS, "st")):
            continue
        params[v] = fit_variant(v, params.get(v) if (args.refine or channels) else None, channels)
        PARAMS_PATH.write_text(json.dumps(params, indent=2))
    print(f"wrote {PARAMS_PATH}")


if __name__ == "__main__":
    main()
