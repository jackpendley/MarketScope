"""KenPom contract outputs: identities (AdjEM from AdjO/AdjD/AdjST), luck summing to zero, SOS by
hand, prior weight, point-in-time snapshots, the classic KenPom benchmark and the luck fits."""

import numpy as np
import pandas as pd
import pytest

from marketscope_football.ratings.engine import Engine, GameLayer
from marketscope_football.ratings.kalman import PaceParams
from marketscope_football.ratings.kenpom_classic import classic_ratings
from marketscope_football.ratings.luck import pythag_share
from marketscope_football.ratings.observations import EXTRA_COLUMNS
from marketscope_football.ratings.outputs import complete_slots, home_advantage_points, snapshots

from test_ratings import ST, TEAMS, UNIT, observations, schedule

PACE = PaceParams(sigma2=2.0, q_week=1e-3, q_season=0.05, rho=0.5, q_week_mean=1e-3, q_season_mean=0.01)
LAYER = GameLayer(38.0, 25.0, 11.0, {"pass": 0.2, "rush": 0.2, "succ": 50.0, "ppd": 0.5, "st": 0.8}, 0.3, 14.0, 0.7)
LUCK = {"expected_wins": {"alpha": 0.6, "beta": 0.3}, "pythag": {"exponent": 2.8}}


def inputs(seed=0):
    games = schedule(seasons=(2020, 2021), weeks=6)
    rng = np.random.default_rng(seed)
    games["margin"] = rng.integers(-14, 15, len(games)).astype(float)
    games["home_score"] = 20 + games["margin"].clip(lower=0)
    games["away_score"] = 20 + (-games["margin"]).clip(lower=0)
    games["home_win"] = np.where(games["margin"] > 0, 1.0, np.where(games["margin"] < 0, 0.0, 0.5))
    games["division"] = games["home"].isin(["A", "B"]) & games["away"].isin(["A", "B"])
    obs = observations(games, noise=0.2, seed=seed)
    for c in EXTRA_COLUMNS:
        obs[c] = rng.uniform(0.3, 2.0, len(obs))
    obs["plays"] = 63.0
    return games, obs


def run(games, obs, from_season=2021):
    eng = Engine(TEAMS, {**{ch: UNIT for ch in ("pass", "rush", "succ", "ppd")}, "pace": PACE}, ST, obs, {}, {})
    return snapshots(games, obs, eng, LAYER, LUCK, from_season, 2020), eng


def test_adjem_is_offense_minus_defense_per_drive_plus_special_teams():
    snap, _ = run(*inputs())
    assert np.allclose(snap["adj_em"], (snap["adj_o"] - snap["adj_d"]) * LAYER.n_drives + snap["adj_st"])
    assert set(snap["week"]) == set(range(0, 7))
    assert (snap.groupby(["season", "week"])["adj_em_rank"].apply(lambda r: sorted(r) == [1, 2, 3, 4])).all()


def test_league_luck_sums_to_zero_and_records_add_up():
    snap, _ = run(*inputs())
    assert snap.groupby("week")["luck"].sum().abs().max() < 1e-9
    last = snap[snap["week"] == 6]
    assert (last["wins"] + last["losses"] + last["ties"] == last["games"]).all()
    assert last["games"].sum() == 2 * 12


def test_preseason_prior_weight_is_one_and_falls_with_games():
    snap, _ = run(*inputs())
    assert np.allclose(snap.loc[snap["week"] == 0, "prior_weight"], 1.0)
    assert (snap.loc[snap["week"] == 6, "prior_weight"] < 0.9).all()


def test_sos_matches_a_hand_calculation():
    games, obs = inputs()
    snap, eng = run(games, obs)
    w3 = snap[(snap["season"] == 2021) & (snap["week"] == 3)].set_index("team")
    hfa = home_advantage_points(eng, LAYER)
    g = games[(games["season"] == 2021) & (games["week"] <= 3) & ((games["home"] == "A") | (games["away"] == "A"))]
    opp = [(r.away, -1.0) if r.home == "A" else (r.home, 1.0) for r in g.itertuples()]
    expected = np.mean([w3.loc[o, "adj_em"] + hfa * loc for o, loc in opp])
    assert w3.loc["A", "sos"] == pytest.approx(expected)
    rem = games[(games["season"] == 2021) & (games["week"] > 3) & ((games["home"] == "A") | (games["away"] == "A"))]
    assert w3.loc["A", "remaining_games"] == len(rem)


def test_snapshots_do_not_change_when_later_games_are_added():
    games, obs = inputs()
    full, _ = run(games, obs)
    cut, _ = run(games[(games["season"] < 2021) | (games["week"] <= 3)], obs)
    a = full[full["week"] <= 3].drop(columns=["remaining_sos", "remaining_games"]).reset_index(drop=True)
    b = cut.drop(columns=["remaining_sos", "remaining_games"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_snapshots_stop_before_a_week_with_missing_play_by_play():
    games, obs = inputs()
    missing = games[(games["season"] == 2021) & (games["week"] == 4)]["game_id"].iloc[0]
    kept = complete_slots(games, obs[obs["game_id"] != missing])
    assert kept["week"][kept["season"] == 2021].max() == 3


def test_classic_kenpom_recovers_multiplicative_strengths():
    o = {"A": 1.3, "B": 1.1, "C": 0.9, "D": 0.7}
    d = {"A": 0.8, "B": 0.95, "C": 1.05, "D": 1.2}
    rows = []
    for t in o:
        for u in o:
            if t != u:
                rows.append({"team": t, "opponent": u, "loc": 0, "ppd_for": 2.0 * o[t] * d[u],
                             "ppd_against": 2.0 * o[u] * d[t], "drives": 11.0})
    r = classic_ratings(pd.DataFrame(rows)).set_index("team")
    assert list(r["adj_em"].sort_values(ascending=False).index) == ["A", "B", "C", "D"]
    ratio = r["adj_o"] / pd.Series(o)
    assert np.allclose(ratio, ratio.iloc[0], rtol=1e-6)


def test_pythag_share():
    assert pythag_share(30, 20, 2.0) == pytest.approx(900 / 1300)
