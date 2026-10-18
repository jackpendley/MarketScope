"""The KenPom contract (docs/RATINGS.md): weekly point-in-time snapshots of every team.

Snapshot (season, week) = the filtered state after all games through that week (week 0 = the
preseason prior, right after the season-boundary reversion). Everything in a snapshot uses only
games played by then, and future schedule (remaining SOS) known in advance.

- AdjEM: expected margin vs an average team on a neutral field, points per game
  = (AdjO - AdjD) * league drives per team-game + AdjST.
- AdjO / AdjD: points per drive scored / allowed vs an average opponent, from the channel units
  through the game-layer weights (EPA-based, so "expected points per drive"). Lower AdjD is better.
- AdjST: special-teams points per game vs average. AdjPace: drives per team-game vs an average opponent.
- Luck: wins - expected wins (luck.py), with the decomposition; Pythagorean wins.
- SOS: average current AdjEM of opponents faced, venue-adjusted (an opponent at home counts its
  home advantage); Opp AdjO/AdjD; non-division SOS; remaining SOS.
- Five Factors (season to date, raw): success rate, explosiveness, field position, finishing
  drives, turnovers.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .engine import UNIT_CHANNELS, Engine, GameLayer
from .luck import game_net_epa, pythag_share, win_probability

ONE_SCORE = 8
MODEL_VERSION = "kalman-v0"  # ratings-v1 is frozen in MS-032


def home_advantage_points(eng: Engine, layer: GameLayer) -> float:
    """Model margin between two identical teams at a non-neutral site."""
    scale = {"pass": layer.n_pass, "rush": layer.n_rush, "succ": 1.0, "ppd": layer.n_drives}
    pts = layer.c + layer.w.get("st", 0.0) * eng.filters["st"].p.hfa
    for ch in UNIT_CHANNELS:
        if ch in eng.filters:
            pts += layer.w.get(ch, 0.0) * scale[ch] * eng.filters[ch].p.hfa
    return pts


def team_ratings(eng: Engine, layer: GameLayer) -> pd.DataFrame:
    """Current KenPom-contract ratings (with SEs) and unit ratings for every team."""
    scale = {"pass": layer.n_pass, "rush": layer.n_rush, "succ": 1.0, "ppd": layer.n_drives}
    teams = eng.filters["st"].teams
    n = len(teams)
    i = np.arange(n)
    o, d, vo, vd, vem = (np.zeros(n) for _ in range(5))
    out = {"team": teams}
    for ch in UNIT_CHANNELS:
        f, k = eng.filters[ch], layer.w.get(ch, 0.0) * scale[ch]
        r = f.ratings()
        o, d = o + k * r["off"], d + k * r["def"]
        vo += k ** 2 * f.P[i, i]
        vd += k ** 2 * f.P[n + i, n + i]
        vem += k ** 2 * (f.P[i, i] + f.P[n + i, n + i] - 2 * f.P[i, n + i])
        out[f"{ch}_off"], out[f"{ch}_def"] = r["off"], r["def"]
    st = eng.filters["st"]
    w_st = layer.w.get("st", 0.0)
    out["adj_st"] = w_st * st.ratings()["st"]
    out["adj_st_se"] = abs(w_st) * np.sqrt(np.diag(st.P))
    league_ppd = eng.filters["ppd"].ratings()["mean"]
    out["adj_o"] = league_ppd + o / layer.n_drives
    out["adj_o_se"] = np.sqrt(vo) / layer.n_drives
    out["adj_d"] = league_ppd + d / layer.n_drives
    out["adj_d_se"] = np.sqrt(vd) / layer.n_drives
    out["adj_em"] = o - d + out["adj_st"]
    out["adj_em_se"] = np.sqrt(vem + out["adj_st_se"] ** 2)
    if "pace" in eng.filters:
        pr = eng.filters["pace"].ratings()
        out["adj_pace"], out["adj_pace_se"] = pr["pace"], pr["pace_se"]
    return pd.DataFrame(out)


def rank(values: pd.Series, ascending: bool = False) -> pd.Series:
    return values.rank(ascending=ascending, method="min").astype("Int64")


def team_games(games: pd.DataFrame, obs: pd.DataFrame, luck_params: dict) -> pd.DataFrame:
    """One row per team per completed game: result, points, expected win probability, and the
    luck and Five Factors inputs for the team and its opponent."""
    ew = luck_params["expected_wins"]
    done = games[games["margin"].notna()].copy()
    done["net"] = game_net_epa(done, obs)
    home = (~done["neutral"]).to_numpy(float)
    done["p_home"] = win_probability(ew["alpha"], ew["beta"], home, done["net"].to_numpy(float))
    o = obs.set_index(["game_id", "team"])
    rows = []
    for side, opp in (("home", "away"), ("away", "home")):
        t = pd.DataFrame({
            "game_id": done["game_id"], "season": done["season"], "week": done["week"], "team": done[side],
            "opponent": done[opp], "division": done["division"],
            "loc": 0.0 if side == "home" else 1.0,  # +1 = at the opponent's home (set below)
            "pf": done[f"{side}_score"], "pa": done[f"{opp}_score"],
            "win": done["home_win"] if side == "home" else 1 - done["home_win"],
            "p_win": done["p_home"] if side == "home" else 1 - done["p_home"],
        })
        t["loc"] = np.where(done["neutral"], 0.0, -1.0 if side == "home" else 1.0)
        own = o.reindex(pd.MultiIndex.from_arrays([t["game_id"], t["team"]]))
        oth = o.reindex(pd.MultiIndex.from_arrays([t["game_id"], t["opponent"]]))
        for c in ("fumble_luck_epa", "int_luck_epa", "fg_made", "fg_expected", "return_tds", "defensive_tds",
                  "success_rate", "epa_per_success", "avg_start_yardline", "scoring_opps", "scoring_opp_points",
                  "interceptions", "fumbles_lost", "plays"):
            t[f"own_{c}"] = own[c].to_numpy()
            t[f"opp_{c}"] = oth[c].to_numpy()
        rows.append(t)
    return pd.concat(rows, ignore_index=True)


def season_to_date(tg: pd.DataFrame, luck_params: dict) -> pd.DataFrame:
    """Record, luck and Five Factors per team from its games so far (tg already filtered)."""
    x = luck_params["pythag"]["exponent"]
    one = (tg["pf"] - tg["pa"]).abs() <= ONE_SCORE

    def wmean(v, w):
        m = v.notna() & w.notna() & (w > 0)
        return (v[m] * w[m]).sum() / w[m].sum() if m.any() else np.nan

    out = []
    for team, g in tg.groupby("team"):
        n = len(g)
        o1 = one.loc[g.index]
        own_turn = (g["own_interceptions"] + g["own_fumbles_lost"]).sum()
        opp_turn = (g["opp_interceptions"] + g["opp_fumbles_lost"]).sum()
        out.append({
            "team": team, "games": n,
            "wins": int((g["win"] == 1).sum()), "losses": int((g["win"] == 0).sum()), "ties": int((g["win"] == 0.5).sum()),
            "points_for": int(g["pf"].sum()), "points_against": int(g["pa"].sum()),
            "expected_wins": float(g["p_win"].sum(skipna=True)),
            "pythag_wins": float(n * pythag_share(g["pf"].sum(), g["pa"].sum(), x)) if g["pf"].sum() + g["pa"].sum() else 0.0,
            "one_score_luck": float((g["win"] - g["p_win"])[o1].sum()),
            "fumble_luck": float((g["own_fumble_luck_epa"] - g["opp_fumble_luck_epa"]).sum()),
            "int_luck": float((g["own_int_luck_epa"] - g["opp_int_luck_epa"]).sum()),
            "fg_luck": float(3 * ((g["own_fg_made"] - g["own_fg_expected"]) - (g["opp_fg_made"] - g["opp_fg_expected"])).sum()),
            "return_td_diff": int((g["own_return_tds"] + g["own_defensive_tds"] - g["opp_return_tds"] - g["opp_defensive_tds"]).sum()),
            "off_success_rate": wmean(g["own_success_rate"], g["own_plays"]),
            "def_success_rate": wmean(g["opp_success_rate"], g["opp_plays"]),
            "off_explosiveness": wmean(g["own_epa_per_success"], g["own_success_rate"] * g["own_plays"]),
            "def_explosiveness": wmean(g["opp_epa_per_success"], g["opp_success_rate"] * g["opp_plays"]),
            "off_start_yardline": float(g["own_avg_start_yardline"].mean()),
            "def_start_yardline": float(g["opp_avg_start_yardline"].mean()),
            "off_points_per_opp": float(g["own_scoring_opp_points"].sum() / g["own_scoring_opps"].sum()) if g["own_scoring_opps"].sum() else np.nan,
            "def_points_per_opp": float(g["opp_scoring_opp_points"].sum() / g["opp_scoring_opps"].sum()) if g["opp_scoring_opps"].sum() else np.nan,
            "off_turnovers": float(own_turn / n), "def_turnovers": float(opp_turn / n),
        })
    if not out:
        return pd.DataFrame({"team": pd.Series(dtype=str)})
    df = pd.DataFrame(out)
    df["luck"] = df["wins"] + 0.5 * df["ties"] - df["expected_wins"]
    return df


def schedule_strength(r: pd.DataFrame, played: pd.DataFrame, remaining: pd.DataFrame, hfa: float) -> pd.DataFrame:
    """SOS from current ratings. `played`/`remaining`: team, opponent, loc (+1 at opponent's home,
    -1 at own home, 0 neutral), division."""
    em, ao, ad = (r.set_index("team")[c] for c in ("adj_em", "adj_o", "adj_d"))
    out = defaultdict(dict)
    for name, g in (("played", played), ("remaining", remaining)):
        if g.empty:
            continue
        g = g.assign(opp_em=g["opponent"].map(em) + hfa * g["loc"], opp_o=g["opponent"].map(ao), opp_d=g["opponent"].map(ad))
        for team, t in g.groupby("team"):
            if name == "played":
                nd = t[~t["division"]]
                out[team].update(sos=t["opp_em"].mean(), opp_adj_o=t["opp_o"].mean(), opp_adj_d=t["opp_d"].mean(),
                                 nondiv_sos=nd["opp_em"].mean() if len(nd) else np.nan)
            else:
                out[team].update(remaining_sos=t["opp_em"].mean(), remaining_games=len(t))
    if not out:
        return pd.DataFrame({"team": pd.Series(dtype=str)})
    return pd.DataFrame.from_dict(out, orient="index").rename_axis("team").reset_index()


def snapshot_frame(r: pd.DataFrame, std: pd.DataFrame, sos: pd.DataFrame, prior_var: dict, season: int,
                   week: int) -> pd.DataFrame:
    df = r.merge(std, on="team", how="left").merge(sos, on="team", how="left")
    df.insert(0, "week", week)
    df.insert(0, "season", season)
    df.insert(0, "model_version", MODEL_VERSION)
    for c in ("games", "wins", "losses", "ties", "points_for", "points_against", "remaining_games", "return_td_diff"):
        if c not in df:
            df[c] = 0
        df[c] = df[c].fillna(0).astype(int)
    for c in ("expected_wins", "pythag_wins", "luck", "one_score_luck", "fumble_luck", "int_luck", "fg_luck"):
        if c not in df:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)
    df["prior_weight"] = [min(1.0, se ** 2 / prior_var[t]) if t in prior_var else 1.0
                          for t, se in zip(df["team"], df["adj_em_se"])]
    for col, asc in (("adj_em", False), ("adj_o", False), ("adj_d", True), ("adj_st", False), ("adj_pace", False),
                     ("luck", False), ("sos", False)):
        if col in df:
            df[f"{col}_rank"] = rank(df[col], asc)
    return df


def complete_slots(done: pd.DataFrame, obs: pd.DataFrame) -> pd.DataFrame:
    """Completed games up to (not including) the first week with a final game whose play-by-play
    is not available yet, so a snapshot never mixes counted results with missing measurements."""
    have = set(obs["game_id"])
    missing = done[~done["game_id"].isin(have)]
    if missing.empty:
        return done
    first = min(zip(missing["season"], missing["week"]))
    keep = [(s, w) < first for s, w in zip(done["season"], done["week"])]
    return done[keep]


def snapshots(games: pd.DataFrame, obs: pd.DataFrame, engine: Engine, layer: GameLayer, luck_params: dict,
              from_season: int, burn_in_from: int) -> pd.DataFrame:
    """Every weekly snapshot from `from_season` on (the engine is replayed from `burn_in_from`)."""
    tg = team_games(games, obs, luck_params)
    sched = pd.concat([
        pd.DataFrame({"season": games["season"], "week": games["week"], "team": games["home"], "opponent": games["away"],
                      "loc": np.where(games["neutral"], 0.0, -1.0), "division": games["division"],
                      "game_type": games["game_type"]}),
        pd.DataFrame({"season": games["season"], "week": games["week"], "team": games["away"], "opponent": games["home"],
                      "loc": np.where(games["neutral"], 0.0, 1.0), "division": games["division"],
                      "game_type": games["game_type"]}),
    ], ignore_index=True)
    done = complete_slots(games[games["margin"].notna() & (games["season"] >= burn_in_from)], obs)
    hfa = home_advantage_points(engine, layer)
    frames, prior_var = [], {}

    def record(season: int, week: int):
        r = team_ratings(engine, layer)
        if week == 0:
            prior_var.clear()
            prior_var.update(dict(zip(r["team"], r["adj_em_se"] ** 2)))
        played_games = tg[(tg["season"] == season) & (tg["week"] <= week)]
        std = season_to_date(played_games, luck_params)
        s = sched[sched["season"] == season]
        played = s[s["week"] <= week]
        played = played[played.set_index(["team", "week"]).index.isin(played_games.set_index(["team", "week"]).index)]
        remaining = s[(s["week"] > week) & (s["game_type"] == "REG")]
        sos = schedule_strength(r, played, remaining, hfa)
        frames.append(snapshot_frame(r, std, sos, prior_var, season, week))

    for (season, week), slot in done.groupby(["season", "week"], sort=True):
        new_season = engine.slot is None or engine.slot[0] != season
        engine.begin(season, week)
        if new_season and season >= from_season:
            record(season, 0)
        for g in slot.itertuples(index=False):
            engine.observe(g)
        if season >= from_season:
            record(season, week)
    return pd.concat(frames, ignore_index=True)
