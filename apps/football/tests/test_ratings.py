"""Kalman unit ratings: recovery on synthetic games, point-in-time immutability, play-caller
continuity, and the channel measurement matching nfl_team_game_stats."""

from dataclasses import replace

import numpy as np
import pandas as pd
import polars as pl
import pytest

from marketscope_football.ratings.engine import Engine, GameLayer, KalmanRatings, channel_events, continuity
from marketscope_football.ratings.fit import decode, encode, replay
from marketscope_football.ratings.kalman import STFilter, STParams, UnitFilter, UnitParams
from marketscope_football.ratings.observations import channel_frame
from marketscope_football.team_stats import team_game_stats
from marketscope_football.eval.walkforward import walk_forward

from test_team_stats import frame, play

TEAMS = ["A", "B", "C", "D"]
OFF = {"A": 0.15, "B": 0.05, "C": -0.05, "D": -0.15}
DEF = {"A": -0.10, "B": 0.0, "C": 0.04, "D": 0.06}
UNIT = UnitParams(sigma2=2.0, q_week_off=1e-5, q_week_def=1e-5, q_season_off=1e-3, q_season_def=1e-3,
                  rho_off_same=0.7, rho_off_changed=0.4, rho_def_same=0.6, rho_def_changed=0.3, hfa=0.02,
                  q_week_mean=1e-6, q_season_mean=1e-5, bump_off=1e-2, bump_def=1e-2)
ST = STParams(sigma2=16.0, q_week=0.01, q_season=0.3, rho=0.5, hfa=0.3)


def schedule(seasons=(2020, 2021, 2022), weeks=12):
    pairings = [(("A", "B"), ("C", "D")), (("A", "C"), ("B", "D")), (("A", "D"), ("B", "C"))]
    rows = []
    for s in seasons:
        start = pd.Timestamp(f"{s}-09-10", tz="UTC")
        for w in range(1, weeks + 1):
            for i, (h, a) in enumerate(pairings[(w - 1) % 3]):
                if w % 2 == 0:
                    h, a = a, h
                rows.append({"game_id": f"{s}_{w:02d}_{a}_{h}", "season": s, "week": w, "home": h, "away": a,
                             "kickoff_utc": start + pd.Timedelta(days=7 * (w - 1), hours=i), "neutral": False,
                             "margin": 3.0, "home_win": 1.0, "close_margin": 0.0, "close_total": 44.0,
                             "close_p_home": np.nan, "total": 44.0, "home_score": 23, "away_score": 20,
                             "game_type": "REG"})
    return pd.DataFrame(rows)


def observations(games, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for g in games.itertuples(index=False):
        for off, dfn, sign in ((g.home, g.away, 1), (g.away, g.home, -1)):
            mu = OFF[off] + DEF[dfn] + 0.02 * sign / 2
            row = {"game_id": g.game_id, "team": off, "st_epa": 0.0 if sign < 0 else 0.3,
                   "drives": 11, "pass_plays": 38, "rush_plays": 25}
            for ch in ("pass", "rush", "succ", "ppd"):
                row[f"{ch}_epa"] = mu + noise * rng.standard_normal()
                row[f"{ch}_n"] = 40.0
            rows.append(row)
    return pd.DataFrame(rows)


def test_unit_filter_recovers_offense_and_defense_from_noise_free_games():
    games = schedule(seasons=(2020,), weeks=30)
    obs = observations(games)
    ev = channel_events(games, obs, {}, {}, "pass", 2020)
    f = UnitFilter(replace(UNIT, sigma2=0.02), TEAMS)  # low noise: the prior's shrinkage vanishes
    for e in ev:
        f.advance(*e[1:]) if e[0] == "advance" else f.observe(*e[2:])
    r = f.ratings()
    off_true = np.array([OFF[t] for t in TEAMS]) - np.mean(list(OFF.values()))
    def_true = np.array([DEF[t] for t in TEAMS]) - np.mean(list(DEF.values()))
    assert np.allclose(r["off"], off_true, atol=0.01) and np.allclose(r["def"], def_true, atol=0.01)
    assert (r["off_se"] > 0).all()


def test_st_filter_is_zero_sum_and_learns_home_field():
    f = STFilter(ST, TEAMS)
    f.advance(2020, 1)
    for _ in range(50):
        f.observe("A", "B", False, 3.3)  # A is 3 better, plus 0.3 home field
    assert f.expected("A", "B", True) == pytest.approx(3.0, abs=0.3)
    assert f.ratings()["st"].sum() == pytest.approx(0.0)


def test_season_boundary_reverts_by_continuity_and_inflates_uncertainty():
    f = UnitFilter(UNIT, TEAMS)
    f.advance(2020, 1, {}, {})
    f.x[0], f.x[1] = 0.1, 0.1  # A and B offense
    p_before = f.P[0, 0]
    f.advance(2021, 1, {"A": (False, False), "B": (True, False)}, {})
    assert f.x[0] == pytest.approx(0.07) and f.x[1] == pytest.approx(0.04)
    assert f.P[0, 0] == pytest.approx(0.49 * p_before + UNIT.q_season_off)


def test_mid_season_playcaller_change_adds_variance_once():
    f = UnitFilter(UNIT, TEAMS)
    f.advance(2020, 1, {}, {})
    before = f.P[2, 2]  # C offense
    f.advance(2020, 2, {}, {"C": (True, False)})
    assert f.P[2, 2] == pytest.approx(before + UNIT.q_week_off + UNIT.bump_off)
    f.advance(2020, 2, {}, {"C": (True, False)})  # same slot again: no double count
    assert f.P[2, 2] == pytest.approx(before + UNIT.q_week_off + UNIT.bump_off)


def test_continuity_flags_from_the_staff_table():
    games = schedule(seasons=(2020, 2021), weeks=3)
    callers = {(s, t, w): ("oc1", "dc1") for s in (2020, 2021) for t in TEAMS for w in (1, 2, 3)}
    callers[(2021, "A", 1)] = callers[(2021, "A", 2)] = callers[(2021, "A", 3)] = ("oc2", "dc1")
    callers[(2020, "B", 3)] = ("oc1", "dc9")
    sf, wf = continuity(games, callers)
    assert sf[(2021, "A")] == (True, False) and sf[(2021, "C")] == (False, False)
    assert wf[(2020, 3)] == {"B": (False, True)}
    assert sf[(2021, "B")] == (False, True)  # last 2020 game had dc9; 2021 back to dc1


def test_filtered_ratings_do_not_change_when_later_games_are_added():
    games = schedule()
    obs = observations(games, noise=0.3)
    layer = GameLayer(38.0, 25.0, 11.0, {"pass": 1.0, "rush": 1.0, "succ": 0.0, "ppd": 0.0, "st": 1.0}, 1.0)
    params = ({ch: UNIT for ch in ("pass", "rush", "succ", "ppd")}, ST, layer)

    def run(g):
        return walk_forward(g, KalmanRatings("k", TEAMS, params, obs, {}, {}, 12.0), [2021])
    full = run(games)
    cut = run(games[(games["season"] < 2021) | (games["week"] <= 6)])
    pd.testing.assert_frame_equal(full[full["week"] <= 6].reset_index(drop=True), cut.reset_index(drop=True))


def test_parameter_transforms_round_trip():
    p = {"sigma2": 2.0, "rho_off_same": 0.7, "hfa": -0.01}
    assert decode(list(p), encode(p)) == pytest.approx(p)


def test_channel_frame_matches_team_game_stats():
    plays = [play(1, epa=0.8, success=1.0, wp=0.5), play(2, epa=-6.0, wp=0.97),
             play(3, play_type="pass", pass_=None, rush=0.0, qb_dropback=1.0, epa=1.5, success=1.0, wp=0.3),
             play(4, play_type="pass", rush=0.0, qb_dropback=1.0, epa=-0.4, wp=0.95,
                  pass_defense_1_player_id="X")]
    for p_ in plays:
        if p_.get("qb_dropback") == 1.0:
            p_["pass"] = 1.0
    pbp = frame(plays)
    ch = channel_frame(pbp).filter(pl.col("team") == "LA").to_dicts()[0]
    tgs = team_game_stats(pbp).filter(pl.col("team") == "LA").to_dicts()[0]
    assert ch["pass_epa"] == pytest.approx(tgs["adj_epa_per_dropback"])
    assert ch["rush_epa"] == pytest.approx(tgs["adj_epa_per_rush"])
    raw = channel_frame(pbp, luck=False, cap=False, wp=False).filter(pl.col("team") == "LA").to_dicts()[0]
    assert raw["rush_epa"] == pytest.approx(tgs["epa_per_rush"]) and raw["rush_n"] == pytest.approx(2.0)
