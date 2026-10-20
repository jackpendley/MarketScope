"""MS-045a system catalogue F1–F10 (PREREGISTRATION.md Addendum F)."""

import numpy as np
import pandas as pd

from marketscope_research import systems as sy

BASE = dict(season=2020, week=3, kickoff=pd.Timestamp("2020-09-27T17:00Z"), home="KC", away="LV",
            neutral=False, division=False, home_line=-3.0, total=45.0, margin=7.0, points=45.0, et_hour=13,
            home_rest=7, away_rest=7, home_bye=False, away_bye=False, home_short=False, away_short=False,
            home_travel_km=0.0, away_travel_km=1500.0, home_tz_shift=0.0, away_tz_shift=0.0,
            home_body_clock=13.0, away_body_clock=13.0, home_alt_change=0, away_alt_change=0)


def games(*overrides):
    return pd.DataFrame([{**BASE, "game_id": f"g{i}", **o} for i, o in enumerate(overrides)])


def systems_for(**o):
    return set(sy.rule_positions(games(o))["system"])


def test_plain_favourite_game_triggers_nothing():
    assert systems_for() == set()


def test_home_underdog_division_and_big_dog_rules():
    p = sy.rule_positions(games(dict(home_line=7.5, division=True, margin=-3)))
    got = {r.system: (r.side, r.line, r.result) for r in p.itertuples()}
    assert got["F1"] == ("KC", 7.5, "win") and got["F2"] == ("KC", 7.5, "win") and got["F3"] == ("KC", 7.5, "win")
    assert systems_for(home_line=3, neutral=True) == set()  # neutral site: no F1


def test_road_dog_sides():
    p = sy.rule_positions(games(dict(home_line=-8, division=True, margin=10)))
    sides = {r.system: (r.side, r.line, r.result) for r in p.itertuples() if r.market == "spread"}
    assert sides == {"F2": ("LV", 8, "loss"), "F3": ("LV", 8, "loss")}


def test_situational_rules():
    assert "F4" in systems_for(away_bye=True)
    assert "F4" not in systems_for(away_bye=True, home_bye=True)
    p = sy.rule_positions(games(dict(away_bye=True)))
    assert p.loc[p["system"] == "F4", "side"].item() == "LV"
    assert "F5" in systems_for(away_short=True)
    assert "F6" in systems_for(away_body_clock=10.0) and "F6" not in systems_for(away_body_clock=11.0)


def test_under_rules_and_pushes():
    p = sy.rule_positions(games(dict(division=True, et_hour=20, total=51, points=51)))
    unders = p[p["market"] == "total"]
    assert set(unders["system"]) == {"F7", "F8", "F9"} and set(unders["result"]) == {"push"}
    p = sy.rule_positions(games(dict(division=True, points=40)))
    assert p.loc[p["market"] == "total", "result"].tolist() == ["win"]


def test_holm_step_down():
    assert sy.holm({"a": 0.01, "b": 0.02, "c": 0.06}) == {"a": True, "b": True, "c": False}
    assert sy.holm({"a": 0.03, "b": 0.001}) == {"b": True, "a": True}
    assert sy.holm({"a": 0.2, "b": 0.001}) == {"b": True, "a": False}


def synthetic_seasons(seasons, flip_in=None, n=120, seed=0):
    """Home covers when the road team is on a short week (planted), except in season `flip_in`."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for i in range(n):
            short = bool(rng.integers(0, 2))
            cover = short if s != flip_in else not short
            rows.append({**BASE, "game_id": f"{s}-{i}", "season": s, "away_short": short,
                         "away_rest": 4 if short else 7, "margin": 10.0 if cover else -10.0})
    return pd.DataFrame(rows)


def test_f10_recovers_a_planted_signal_walk_forward():
    pos = sy.f10_positions(synthetic_seasons(range(2016, 2021)))
    assert set(pos["season"]) == {2018, 2019, 2020}
    assert (pos["result"] == "win").mean() > 0.95


def test_f10_never_trains_on_the_season_it_predicts():
    # The planted relationship reverses in 2019 only; a leak would let the model follow it there.
    pos = sy.f10_positions(synthetic_seasons(range(2016, 2021), flip_in=2019))
    assert (pos.loc[pos["season"] == 2019, "result"] == "win").mean() < 0.05
