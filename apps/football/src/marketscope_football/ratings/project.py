"""Season projections from the running ratings-v1 model (MS-034): builds `simulate.SeasonInputs` at a
point in time and replays the season week by week, simulating after each completed week.

Point in time: the strengths and their covariance are the filtered state after the games observed so
far. Next week's games use the model's full estimate (ratings, home, expected QBs, injury reports, the
same as the stored predictions). Later games use ratings, home field and each team's current QB term
(its expected starter for its next game vs its baseline): injury reports for later weeks aren't known.

Game noise: the margin distribution's scale was fitted on model errors, which include rating error.
The simulation draws rating error separately (correlated across a team's games), so the game noise
is the fitted scale with the average rating-error variance (2016-22) taken out: `simulation.json`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .design import BURN_IN_FROM
from .engine import UNIT_CHANNELS, Engine, GameLayer, KalmanRatings
from .margin_dist import MarginDistribution
from .outputs import complete_slots, home_advantage_points
from .simulate import IX, TEAMS, OutcomeTable, SeasonInputs, last_regular_week, simulate

SIM_PARAMS_PATH = Path(__file__).with_name("simulation.json")
LIVE_SIMS = 10_000
SEED = 2026


def strength_state(engine: Engine, layer: GameLayer) -> tuple[np.ndarray, np.ndarray, float]:
    """Team strength on the margin scale (TEAMS order), its covariance, and the weekly drift variance.
    Strength = sum over channels of weight x scale x (offense unit - defense unit) + special teams, so
    the ratings-plus-home part of a margin is strength[home] - strength[away] + home advantage."""
    scale = {"pass": layer.n_pass, "rush": layer.n_rush, "succ": 1.0, "ppd": layer.n_drives}
    teams = engine.filters["st"].teams
    n = len(teams)
    i = np.arange(n)
    e, cov, q = np.zeros(n), np.zeros((n, n)), 0.0
    for ch in UNIT_CHANNELS:
        if ch not in engine.filters:
            continue
        f, k = engine.filters[ch], layer.w.get(ch, 0.0) * scale[ch]
        a = np.zeros((n, 2 * n + 1))
        a[i, i], a[i, n + i] = k, -k
        e += a @ f.x
        cov += a @ f.P @ a.T
        q += k ** 2 * (f.p.q_week_off + f.p.q_week_def)
    st, k = engine.filters["st"], layer.w.get("st", 0.0)
    e += k * st.x
    cov += k ** 2 * st.P
    q += k ** 2 * st.p.q_week
    order = np.array([teams.index(t) for t in TEAMS])
    return e[order], cov[np.ix_(order, order)], q


def load_sim_params() -> dict:
    return json.loads(SIM_PARAMS_PATH.read_text())


def outcome_table(model: KalmanRatings, game_scale: float | None) -> OutcomeTable:
    d = model.dist
    return OutcomeTable(MarginDistribution(game_scale or d.scale, d.weights))


def season_inputs(model: KalmanRatings, games: pd.DataFrame, season: int, played_ids: set[str]) -> SeasonInputs:
    """Inputs for simulating `season` from the model's current state; `played_ids` are the games whose
    results count (everything else in the regular season is simulated)."""
    reg = games[(games["season"] == season) & (games["game_type"] == "REG")].sort_values(["kickoff_utc", "game_id"])
    played = reg["game_id"].isin(played_ids).to_numpy()
    unplayed = reg[~played]
    eng, layer = model.engine, model.layer
    if len(unplayed):
        base_week = int(unplayed["week"].min())
        eng.begin(season, base_week)  # the same advance the next update would make
    else:
        base_week = last_regular_week(season) + 1
    e, cov, q = strength_state(eng, layer)
    if not len(unplayed):
        cov = cov + q * np.eye(len(TEAMS))
    hfa = home_advantage_points(eng, layer)

    qb, rest = np.zeros(len(TEAMS)), np.zeros(len(TEAMS))
    w_qb = layer.w.get("qb", 0.0)
    if model.qb is not None and len(unplayed):
        tr = model.qb.tracker
        sides = pd.concat([unplayed[["game_id", "kickoff_utc", "home"]].rename(columns={"home": "team"}),
                           unplayed[["game_id", "kickoff_utc", "away"]].rename(columns={"away": "team"})])
        for team, g in sides.sort_values("kickoff_utc").groupby("team"):
            nxt = g.iloc[0]
            qb[IX[team]] = w_qb * model.qb.side(nxt["game_id"], team, nxt["kickoff_utc"])
            s = model.qb.starters.get((nxt["game_id"], team))
            if s is not None:
                gap = tr.rating(s[0], nxt["kickoff_utc"]) - tr.p.replacement
                rest[IX[team]] = w_qb * model.qb.n_pass * max(gap, 0.0)

    home = reg["home"].map(IX).to_numpy()
    away = reg["away"].map(IX).to_numpy()
    neutral = reg["neutral"].to_numpy(bool)
    week = reg["week"].to_numpy(int)
    mean = np.full(len(reg), np.nan)
    for j, g in enumerate(reg.itertuples(index=False)):
        if played[j]:
            continue
        base = e[home[j]] - e[away[j]] + (0.0 if neutral[j] else hfa)
        if week[j] == base_week:
            f = model._features(g)
            full = layer.margin(f, bool(neutral[j]))
            extra = sum(layer.w[k] * f[k] for k in layer.w if k == "qb" or k.startswith("avail_"))
            assert abs(full - extra - base) < 1e-6, (g.game_id, full - extra, base)
            mean[j] = full
        else:
            mean[j] = base + qb[home[j]] - qb[away[j]]
    result = np.where(played, reg["home_win"].to_numpy(float), np.nan)
    return SeasonInputs(season, home, away, week, neutral, result, mean, e + qb, cov, q, hfa, base_week, rest)


def summary_frame(season: int, week: int, inp: SeasonInputs, res) -> pd.DataFrame:
    s = res.summary()
    played = ~np.isnan(inp.result)
    return pd.DataFrame({
        "season": season, "week": week, "team": list(TEAMS), "sims": res.sims,
        "games_played": int(played.sum()), "strength": inp.strength,
        "mean_wins": s["mean_wins"], "win_dist": [list(np.round(r, 5)) for r in s["win_dist"]],
        "playoff_p": s["playoff_p"], "division_p": s["division_p"], "seed1_p": s["seed1_p"],
        "conf_p": s["conf_p"], "sb_p": s["sb_p"],
    })


def season_projections(model: KalmanRatings, games: pd.DataFrame, obs: pd.DataFrame, seasons: set[int],
                       n_sims: int, game_scale: float | None, uncertainty: bool = True,
                       include_unobserved_finals: bool = False, on_inputs=None,
                       latest_sims: int | None = None) -> pd.DataFrame:
    """Replay the model and simulate each season in `seasons` before week 1 (week 0) and after every
    completed regular-season week. `include_unobserved_finals` (live) also counts final results whose
    play-by-play isn't in yet in the last projection of the latest season. `on_inputs(season, week,
    inputs)` lets the evaluation inspect or replace inputs (e.g. a no-ratings baseline). `latest_sims`
    overrides `n_sims` for the latest season (more precision where people look)."""
    table = outcome_table(model, game_scale)
    done = complete_slots(games[games["margin"].notna() & (games["season"] >= BURN_IN_FROM)], obs)
    observed: set[str] = set()
    frames, current = [], None
    latest = max(seasons)

    def run(season: int, week: int, played: set[str]):
        inp = season_inputs(model, games, season, played)
        if on_inputs is not None:
            inp = on_inputs(season, week, inp)
        rng = np.random.default_rng([SEED, season, week])
        n = latest_sims if latest_sims and season == latest else n_sims
        frames.append(summary_frame(season, week, inp, simulate(inp, table, n, rng, uncertainty)))

    slots = list(done.groupby(["season", "week"], sort=True))
    for k, ((season, week), slot) in enumerate(slots):
        if season != current:
            current = season
            if season in seasons:
                run(season, 0, observed)
        model.update(slot)
        observed |= set(slot["game_id"])
        if season in seasons and slot["game_type"].eq("REG").all():
            last = k == len(slots) - 1 or slots[k + 1][0][0] != season
            played = observed
            if include_unobserved_finals and last and season == latest:
                finals = games[(games["season"] == season) & games["margin"].notna()]
                played = observed | set(finals["game_id"])
            run(season, int(week), played)
    if latest in seasons and current != latest and (games["season"] == latest).any():
        run(latest, 0, observed)  # preseason: no game of the season observed yet
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def rating_error_variance(model: KalmanRatings, games: pd.DataFrame, obs: pd.DataFrame,
                          seasons: range) -> tuple[float, int]:
    """Mean variance of strength[home] - strength[away] at prediction time over `seasons` (the share of
    the fitted margin spread that is rating error), replaying the model."""
    done = complete_slots(games[games["margin"].notna() & (games["season"] >= BURN_IN_FROM)], obs)
    v = []
    for (season, week), slot in done.groupby(["season", "week"], sort=True):
        if season in seasons:
            model.engine.begin(season, week)
            _, cov, _ = strength_state(model.engine, model.layer)
            h, a = slot["home"].map(IX).to_numpy(), slot["away"].map(IX).to_numpy()
            v.extend(cov[h, h] + cov[a, a] - 2 * cov[h, a])
        model.update(slot)
    return float(np.mean(v)), len(v)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
